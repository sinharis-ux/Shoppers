"""
Django management command to scrape Nordstrom products using Scrapfly.
This command uses Scrapfly's anti-scraping protection bypass and residential proxies
to reliably extract product data from Nordstrom.

Usage:
    # Random mode - scrapes from popular pages automatically
    python manage.py scrape_nordstrom_scrapfly --max-products 50
    
    # Specific URL
    python manage.py scrape_nordstrom_scrapfly --url "https://www.nordstrom.com/s/gucci-men-shoes"
    
    # Search term
    python manage.py scrape_nordstrom_scrapfly --search-term "shoes" --max-products 100
"""
import os
import re
import json
import requests
from urllib.parse import urljoin, quote_plus, urlparse
from django.core.management.base import BaseCommand
from django.db import transaction
from scrapfly import ScrapflyClient, ScrapeConfig
from bs4 import BeautifulSoup
from api.models import NordstromProduct, NordstromFilter


class Command(BaseCommand):
    help = 'Scrape Nordstrom products using Scrapfly and save to knowledge base'

    def add_arguments(self, parser):
        parser.add_argument(
            '--url',
            type=str,
            help='Nordstrom page URL to scrape (e.g., https://www.nordstrom.com/s/gucci-men-shoes)',
        )
        parser.add_argument(
            '--search-term',
            type=str,
            help='Search term to build Nordstrom search URL (e.g., "gucci men shoes")',
        )
        parser.add_argument(
            '--max-products',
            type=int,
            default=50,
            help='Maximum number of products to scrape (default: 50)',
        )
        parser.add_argument(
            '--api-key',
            type=str,
            help='Scrapfly API key (defaults to SCRAPFLY_API_KEY environment variable)',
        )
        parser.add_argument(
            '--country',
            type=str,
            default='us',
            help='Country code for proxy (default: us)',
        )
        parser.add_argument(
            '--proxy-pool',
            type=str,
            default='public_residential_pool',
            help='Proxy pool name (default: public_residential_pool). Set to None to disable proxy pool.',
        )
        parser.add_argument(
            '--no-proxy',
            action='store_true',
            help='Disable proxy pool (use default proxy)',
        )

    def extract_price(self, price_text):
        """Extract numeric price from text."""
        if not price_text:
            return None
        # Remove currency symbols and extract numbers
        price_match = re.search(r'[\d,]+\.?\d*', price_text.replace(',', ''))
        if price_match:
            try:
                return float(price_match.group())
            except ValueError:
                return None
        return None

    def extract_product_id(self, url):
        """Extract product ID from URL."""
        if not url:
            return None
        # Try to find product ID in URL patterns like /p/123456 or /browse/123456
        match = re.search(r'/p/(\d+)', url) or re.search(r'/browse/(\d+)', url)
        if match:
            return match.group(1)
        # Fallback: generate ID from URL hash
        return str(abs(hash(url)) % 1000000)

    def convert_url_to_api_endpoint(self, url):
        """Convert Nordstrom page URL to API endpoint."""
        # Example: https://www.nordstrom.com/browse/men/new -> 
        #          https://www.nordstrom.com/api/browse/browse/men/new/clothing
        
        parsed = urlparse(url)
        path = parsed.path.strip('/')
        
        # Skip if already an API endpoint
        if '/api/' in path:
            return url
        
        # Build API endpoint
        if path.startswith('browse/'):
            # Extract the path after 'browse/'
            # e.g., 'browse/men/new' -> 'men/new'
            browse_path = path.replace('browse/', '', 1)
            # Build API path: /api/browse/browse/{browse_path}/clothing
            api_url = f"https://www.nordstrom.com/api/browse/browse/{browse_path}/clothing"
        elif path.startswith('s/'):
            # Search page - convert differently
            search_term = path.replace('s/', '')
            api_url = f"https://www.nordstrom.com/api/browse/search/{quote_plus(search_term)}"
        else:
            # Fallback: try to build from path
            api_url = f"https://www.nordstrom.com/api/browse/browse/{path}/clothing"
        
        return api_url

    def fetch_api_json(self, api_url, params, api_key=None, country='us', proxy_pool=None):
        """Fetch JSON API - uses requests directly, with Scrapfly proxy if needed."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
        }
        
        # If proxy is needed, use Scrapfly
        if proxy_pool and api_key:
            client = ScrapflyClient(key=api_key)
            from urllib.parse import urlencode
            full_url = f"{api_url}?{urlencode(params)}"
            
            config_params = {
                'url': full_url,
                'country': country,
                'asp': True,
                'proxy_pool': proxy_pool,
                'headers': headers,
            }
            
            result = client.scrape(ScrapeConfig(**config_params))
            return json.loads(result.content)
        else:
            # Direct requests call (matching user's example)
            response = requests.get(api_url, params=params, headers=headers)
            response.raise_for_status()
            return response.json()

    def scrape_products_from_api(self, url, max_products, api_key, country='us', proxy_pool=None):
        """Scrape products from Nordstrom using their JSON API."""
        self.stdout.write(self.style.SUCCESS(f'🔍 Scraping API: {url}'))
        
        try:
            # Convert page URL to API endpoint
            api_url = self.convert_url_to_api_endpoint(url)
            self.stdout.write(f'   API Endpoint: {api_url}')
            
            # Fetch JSON data using Scrapfly
            params = {
                "top": max_products,
                "isDynamicFacetsEnabled": "true"
            }
            
            data = self.fetch_api_json(api_url, params, api_key, country, proxy_pool)
            self.stdout.write(self.style.SUCCESS(f'   ✓ Fetched API response'))
            
            products = []
            
            # Extract products from content
            content = data.get("content", {})
            
            # Extract products from various possible locations in the API response
            product_items = []
            
            # Try different possible product locations in the JSON
            if "products" in content:
                product_items = content["products"]
            elif "items" in content:
                product_items = content["items"]
            elif "results" in content:
                product_items = content["results"]
            elif isinstance(content, list):
                product_items = content
            else:
                # Look for any array that might contain products
                for key, value in content.items():
                    if isinstance(value, list) and len(value) > 0:
                        # Check if first item looks like a product
                        first_item = value[0] if value else {}
                        if any(prod_key in first_item for prod_key in ['id', 'productId', 'title', 'name', 'price']):
                            product_items = value
                            break
            
            self.stdout.write(f'   Found {len(product_items)} product items in API response')
            
            # Extract product details
            for item in product_items[:max_products]:
                try:
                    # Extract product ID
                    product_id = (
                        str(item.get("id")) or 
                        str(item.get("productId")) or 
                        str(item.get("styleId")) or
                        str(item.get("sku")) or
                        None
                    )
                    
                    if not product_id:
                        continue
                    
                    # Extract title
                    title = (
                        item.get("title") or 
                        item.get("name") or 
                        item.get("displayName") or
                        item.get("productTitle") or
                        ""
                    )
                    
                    if not title:
                        continue
                    
                    # Extract price
                    price = None
                    price_data = item.get("price") or item.get("pricing") or {}
                    if isinstance(price_data, dict):
                        price = price_data.get("sale") or price_data.get("current") or price_data.get("price")
                    elif isinstance(price_data, (int, float)):
                        price = float(price_data)
                    elif isinstance(price_data, str):
                        price = self.extract_price(price_data)
                    
                    # Extract original price
                    original_price = None
                    if isinstance(price_data, dict):
                        original_price = price_data.get("original") or price_data.get("regular")
                    
                    # Extract brand
                    brand = (
                        item.get("brand") or 
                        item.get("brandName") or 
                        item.get("designer") or
                        None
                    )
                    
                    # Extract URL
                    product_url = (
                        item.get("url") or 
                        item.get("productUrl") or
                        item.get("link") or
                        None
                    )
                    if product_url and not product_url.startswith('http'):
                        product_url = urljoin('https://www.nordstrom.com', product_url)
                    
                    # Extract image
                    image_url = None
                    image_data = item.get("image") or item.get("images") or item.get("media") or {}
                    if isinstance(image_data, dict):
                        image_url = image_data.get("url") or image_data.get("src") or image_data.get("href")
                    elif isinstance(image_data, list) and len(image_data) > 0:
                        image_url = image_data[0].get("url") or image_data[0].get("src")
                    elif isinstance(image_data, str):
                        image_url = image_data
                    
                    if image_url and not image_url.startswith('http'):
                        image_url = urljoin('https://www.nordstrom.com', image_url)
                    
                    # Extract category from URL or item
                    category = item.get("category") or item.get("department") or None
                    if not category and url:
                        # Extract from original URL
                        if '/browse/' in url:
                            category = url.split('/browse/')[-1].split('/')[0].title()
                    
                    # Extract colors
                    colors = []
                    if "colors" in item:
                        colors = [c.get("name") or c.get("label") for c in item["colors"] if c.get("name") or c.get("label")]
                    
                    # Extract sizes
                    sizes = []
                    if "sizes" in item:
                        sizes = [s.get("name") or s.get("label") for s in item["sizes"] if s.get("name") or s.get("label")]
                    
                    products.append({
                        'product_id': str(product_id),
                        'title': str(title)[:500],
                        'brand': str(brand)[:255] if brand else None,
                        'price': float(price) if price else None,
                        'original_price': float(original_price) if original_price else None,
                        'url': str(product_url)[:1000] if product_url else None,
                        'image_url': str(image_url)[:1000] if image_url else None,
                        'category': str(category)[:255] if category else None,
                        'colors': colors,
                        'sizes': sizes,
                        'in_stock': item.get("inStock", True),
                        'currency': 'USD',
                        'additional_data': item  # Store full item data
                    })
                    
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'   ⚠️  Error extracting product: {str(e)}'))
                    continue
            
            # Extract filters from API response
            self.extract_filters_from_api(data)
            
            self.stdout.write(self.style.SUCCESS(f'   ✓ Extracted {len(products)} products from API'))
            return products
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'   ✗ Error scraping API: {str(e)}'))
            raise

    def extract_filters_from_api(self, data):
        """Extract filters from API response and save to knowledge base."""
        try:
            facet_list = data.get("filters", {}).get("facets", [])
            
            filters_to_save = []
            
            for facet in facet_list:
                facet_name = facet.get("name")
                if not facet_name:
                    continue
                
                values = facet.get("values", [])
                
                for v in values:
                    label = v.get("label") or v.get("value")
                    value = v.get("value")
                    count = v.get("count", 0)
                    
                    if label:
                        filters_to_save.append({
                            'filter_type': facet_name.lower(),
                            'filter_name': str(label)[:255],
                            'filter_data': {
                                'value': value,
                                'count': count,
                                'extracted_from': 'api'
                            }
                        })
            
            # Extract color filters
            colors = {}
            color_ids = data.get("content", {}).get("colorIds", [])
            color_by_id = data.get("content", {})
            
            for cid in color_ids:
                item = color_by_id.get(cid, {})
                if item:
                    label = item.get("label")
                    if label:
                        filters_to_save.append({
                            'filter_type': 'color',
                            'filter_name': str(label)[:255],
                            'filter_data': {
                                'color_id': cid,
                                'swatch': item.get("swatchMediaId"),
                                'media': item.get("mediaIds"),
                                'extracted_from': 'api'
                            }
                        })
            
            # Save filters to database
            if filters_to_save:
                with transaction.atomic():
                    for filter_data in filters_to_save:
                        try:
                            NordstromFilter.objects.update_or_create(
                                filter_type=filter_data['filter_type'],
                                filter_name=filter_data['filter_name'],
                                defaults={'filter_data': filter_data['filter_data']}
                            )
                        except:
                            pass
                
                self.stdout.write(f'   ✓ Extracted {len(filters_to_save)} filters from API')
                
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'   ⚠️  Error extracting filters: {str(e)}'))

    def scrape_products(self, url, max_products, api_key, country='us', proxy_pool=None):
        """Scrape products from Nordstrom page - tries API first, falls back to HTML."""
        # Try API method first
        try:
            products = self.scrape_products_from_api(url, max_products, api_key, country, proxy_pool)
            if products:
                return products
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'   API method failed: {str(e)}, trying HTML fallback...'))
        
        # Fallback to HTML scraping
        self.stdout.write(self.style.SUCCESS(f'🔍 Scraping HTML: {url}'))
        
        # Initialize Scrapfly client
        client = ScrapflyClient(key=api_key)
        
        try:
            # Build ScrapeConfig with optional proxy pool
            config_params = {
                'url': url,
                'render_js': True,                  # Headless browser (JS rendering)
                'country': country,                 # Country IP for best results
                'asp': True,                        # Anti Scraping Protection bypass
            }
            
            # Add proxy_pool if provided (use None string to disable)
            if proxy_pool and proxy_pool.lower() not in ['none', 'null', '']:
                config_params['proxy_pool'] = proxy_pool
                self.stdout.write(f'   Using proxy pool: {proxy_pool}')
            
            # Scrape the page with Scrapfly
            result = client.scrape(ScrapeConfig(**config_params))
            
            html = result.content
            self.stdout.write(self.style.SUCCESS(f'   ✓ Fetched {len(html)} bytes'))
            
            # Parse HTML with BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            
            products = []
            seen_urls = set()
            
            # Strategy 1: Extract products using data-testid selectors (primary method)
            product_cards = soup.select("[data-testid='product-card']")
            self.stdout.write(f'   Found {len(product_cards)} product cards')
            
            for item in product_cards[:max_products]:
                try:
                    # Extract product title
                    name_elem = item.select_one("[data-testid='product-title']")
                    name = name_elem.get_text(strip=True) if name_elem else None
                    
                    # Extract price
                    price_elem = item.select_one("[data-testid='price']")
                    price_text = price_elem.get_text(strip=True) if price_elem else None
                    price = self.extract_price(price_text)
                    
                    # Extract product URL
                    link = item.select_one("a")
                    if link and link.get('href'):
                        href = link['href']
                        if not href.startswith('http'):
                            href = urljoin('https://www.nordstrom.com', href)
                        
                        # Extract product ID
                        product_id = self.extract_product_id(href)
                        
                        # Skip if we've already seen this URL
                        if href in seen_urls:
                            continue
                        seen_urls.add(href)
                        
                        # Extract brand (try multiple selectors)
                        brand = None
                        brand_elem = (
                            item.select_one("[data-testid='product-brand']") or
                            item.select_one(".product-brand") or
                            item.select_one("[class*='brand']")
                        )
                        if brand_elem:
                            brand = brand_elem.get_text(strip=True)[:255]
                        
                        # Extract image URL - try multiple strategies
                        image_url = None
                        # Strategy 1: Look for img tag with product image attributes
                        img_elem = (
                            item.select_one("img[data-testid='product-image']") or
                            item.select_one("img[alt*='product']") or
                            item.select_one("img[src*='image']") or
                            item.select_one("img")
                        )
                        if img_elem:
                            image_url = (
                                img_elem.get('src') or 
                                img_elem.get('data-src') or 
                                img_elem.get('data-lazy-src') or
                                img_elem.get('data-image-url')
                            )
                            if image_url:
                                # Clean up image URL
                                if image_url.startswith('//'):
                                    image_url = 'https:' + image_url
                                elif not image_url.startswith('http'):
                                    image_url = urljoin('https://www.nordstrom.com', image_url)
                                
                                # Remove query parameters that might reduce image quality
                                if '?' in image_url:
                                    base_url = image_url.split('?')[0]
                                    # Keep high-quality image parameters if present
                                    if 'w=' in image_url or 'h=' in image_url:
                                        image_url = image_url
                                    else:
                                        image_url = base_url
                        
                        # Extract original price if on sale
                        original_price = None
                        original_price_elem = item.select_one("[data-testid='original-price']") or item.select_one(".original-price")
                        if original_price_elem:
                            original_price = self.extract_price(original_price_elem.get_text(strip=True))
                        
                        # Extract category from URL or page context
                        category = None
                        if '/s/' in url:
                            # Extract category from URL pattern like /s/gucci-men-shoes
                            category_match = re.search(r'/s/([^/]+)', url)
                            if category_match:
                                category = category_match.group(1).replace('-', ' ').title()[:255]
                        
                        if name and product_id:
                            products.append({
                                'product_id': str(product_id),
                                'title': name[:500],
                                'brand': brand,
                                'price': price,
                                'original_price': original_price if original_price and original_price != price else None,
                                'url': href[:1000],
                                'image_url': image_url[:1000] if image_url else None,
                                'category': category,
                                'in_stock': True,
                                'currency': 'USD',
                            })
                            
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'   ⚠️  Error extracting product: {str(e)}'))
                    continue
            
            # Strategy 2: Fallback to alternative selectors if no products found
            if not products:
                self.stdout.write(self.style.WARNING('   No products found with primary method, trying alternative selectors...'))
                
                # Try different selectors
                alternative_selectors = [
                    '.product-card',
                    '[class*="ProductCard"]',
                    '[class*="product-tile"]',
                    '.product-item',
                ]
                
                for selector in alternative_selectors:
                    cards = soup.select(selector)
                    if cards:
                        self.stdout.write(f'   Found {len(cards)} items with selector: {selector}')
                        
                        for item in cards[:max_products]:
                            try:
                                link = item.find('a', href=True)
                                if not link:
                                    continue
                                
                                href = link.get('href')
                                if not href.startswith('http'):
                                    href = urljoin('https://www.nordstrom.com', href)
                                
                                if href in seen_urls:
                                    continue
                                seen_urls.add(href)
                                
                                product_id = self.extract_product_id(href)
                                name = link.get_text(strip=True) or item.get_text(strip=True)
                                
                                if name and product_id and len(name) > 3:
                                    products.append({
                                        'product_id': str(product_id),
                                        'title': name[:500],
                                        'url': href[:1000],
                                        'category': category,
                                        'in_stock': True,
                                        'currency': 'USD',
                                    })
                                    
                                    if len(products) >= max_products:
                                        break
                            except Exception as e:
                                continue
                        
                        if products:
                            break
            
            self.stdout.write(self.style.SUCCESS(f'   ✓ Extracted {len(products)} products'))
            return products
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'   ✗ Error scraping: {str(e)}'))
            raise

    def save_products_to_db(self, products):
        """Save products to the knowledge base."""
        saved = 0
        updated = 0
        
        with transaction.atomic():
            for product in products:
                try:
                    obj, created = NordstromProduct.objects.update_or_create(
                        product_id=product['product_id'],
                        defaults={
                            'title': product['title'],
                            'brand': product.get('brand'),
                            'price': product.get('price'),
                            'original_price': product.get('original_price'),
                            'url': product.get('url'),
                            'image_url': product.get('image_url'),
                            'category': product.get('category'),
                            'colors': product.get('colors', []),
                            'sizes': product.get('sizes', []),
                            'in_stock': product.get('in_stock', True),
                            'currency': product.get('currency', 'USD'),
                            'additional_data': product.get('additional_data', {}),
                        }
                    )
                    if created:
                        saved += 1
                        price_str = f"${obj.price:.2f}" if obj.price else "N/A"
                        self.stdout.write(f'    ✓ Saved: {obj.title[:55]}... ({price_str})')
                    else:
                        updated += 1
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'    ⚠️  Error saving product: {str(e)}'))
                    continue
        
        return saved, updated

    def get_random_product_urls(self):
        """Get a list of popular Nordstrom product pages for random scraping."""
        return [
            "https://www.nordstrom.com/browse/women/clothing/dresses",
            "https://www.nordstrom.com/browse/women/clothing/tops",
            "https://www.nordstrom.com/browse/women/clothing/jeans",
            "https://www.nordstrom.com/browse/women/shoes",
            "https://www.nordstrom.com/browse/women/handbags",
            "https://www.nordstrom.com/browse/men/clothing/shirts",
            "https://www.nordstrom.com/browse/men/clothing/jeans",
            "https://www.nordstrom.com/browse/men/shoes",
            "https://www.nordstrom.com/browse/men/new",
            "https://www.nordstrom.com/browse/men/accessories",
            "https://www.nordstrom.com/browse/kids/clothing",
            "https://www.nordstrom.com/browse/home/decor",
            "https://www.nordstrom.com/browse/beauty/makeup",
            "https://www.nordstrom.com/browse/women/jewelry",
            "https://www.nordstrom.com/browse/men/watches",
            "https://www.nordstrom.com/s/women-running-shoes",
            "https://www.nordstrom.com/s/men-dress-shirts",
            "https://www.nordstrom.com/s/women-handbags",
            "https://www.nordstrom.com/s/men-sneakers",
            "https://www.nordstrom.com/s/women-jackets",
            "https://www.nordstrom.com/s/men-jackets",
        ]

    def handle(self, *args, **options):
        """Main command handler."""
        self.stdout.write(self.style.SUCCESS('\n' + '='*70))
        self.stdout.write(self.style.SUCCESS('🚀 NORDSTROM SCRAPFLY SCRAPER'))
        self.stdout.write(self.style.SUCCESS('='*70 + '\n'))
        
        # Get API key
        api_key = options.get('api_key') or os.getenv('SCRAPFLY_API_KEY')
        if not api_key:
            self.stdout.write(self.style.ERROR('✗ Error: Scrapfly API key not found!'))
            self.stdout.write(self.style.WARNING('   Set SCRAPFLY_API_KEY environment variable or use --api-key option'))
            return
        
        # Determine URL(s) to scrape
        url = options.get('url')
        search_term = options.get('search_term')
        max_products = options.get('max_products', 50)
        country = options.get('country', 'us')
        
        # Get proxy pool setting
        if options.get('no_proxy'):
            proxy_pool = None
        else:
            proxy_pool = options.get('proxy_pool', 'public_residential_pool')
        
        # If no URL or search term provided, use random popular pages
        urls_to_scrape = []
        products_per_url = max_products  # Default for single URL
        
        if url:
            urls_to_scrape = [url]
        elif search_term:
            urls_to_scrape = [f"https://www.nordstrom.com/s/{quote_plus(search_term)}"]
        else:
            # Random mode: scrape multiple popular pages
            self.stdout.write(self.style.SUCCESS('🎲 Random mode: Scraping from popular Nordstrom pages...\n'))
            import random
            random_urls = self.get_random_product_urls()
            # Randomly select a few URLs to scrape (3-5 URLs)
            num_urls = min(5, len(random_urls))
            urls_to_scrape = random.sample(random_urls, num_urls)
            self.stdout.write(f'   Selected {len(urls_to_scrape)} random pages to scrape\n')
            # Adjust max_products per URL
            products_per_url = max(10, max_products // len(urls_to_scrape))
        
        all_products = []
        
        # Scrape products from all URLs
        try:
            for idx, url in enumerate(urls_to_scrape, 1):
                if len(urls_to_scrape) > 1:
                    self.stdout.write(self.style.SUCCESS(f'\n[{idx}/{len(urls_to_scrape)}] Scraping page {idx}...'))
                
                products_per_url_for_this = products_per_url
                products = self.scrape_products(url, products_per_url_for_this, api_key, country, proxy_pool)
                
                if products:
                    all_products.extend(products)
                    self.stdout.write(self.style.SUCCESS(f'   ✓ Got {len(products)} products from this page'))
                else:
                    self.stdout.write(self.style.WARNING(f'   ⚠️  No products found on this page'))
                
                # Stop if we've collected enough products
                if len(all_products) >= max_products:
                    all_products = all_products[:max_products]
                    break
            
            if not all_products:
                self.stdout.write(self.style.WARNING('\n⚠️  No products found'))
                return
            
            # Remove duplicates by URL
            seen_urls = set()
            unique_products = []
            for product in all_products:
                product_url = product.get('url')
                if product_url and product_url not in seen_urls:
                    seen_urls.add(product_url)
                    unique_products.append(product)
            
            self.stdout.write(self.style.SUCCESS(f'\n📦 Total unique products collected: {len(unique_products)}'))
            
            # Save to knowledge base
            self.stdout.write(self.style.SUCCESS(f'\n💾 Saving {len(unique_products)} products to knowledge base...'))
            self.stdout.write('='*70)
            
            saved, updated = self.save_products_to_db(unique_products)
            
            # Summary
            self.stdout.write(self.style.SUCCESS(f'\n📊 SUMMARY'))
            self.stdout.write(self.style.SUCCESS('='*70))
            self.stdout.write(self.style.SUCCESS(f'✅ Products Saved: {saved}'))
            self.stdout.write(self.style.SUCCESS(f'🔄 Products Updated: {updated}'))
            self.stdout.write(self.style.SUCCESS(f'📦 Total Products in KB: {NordstromProduct.objects.count()}'))
            self.stdout.write(self.style.SUCCESS('='*70 + '\n'))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\n✗ Fatal error: {str(e)}'))
            raise

