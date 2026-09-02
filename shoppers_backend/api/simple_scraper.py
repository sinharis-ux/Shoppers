"""
Simple, robust scraper using requests + BeautifulSoup as primary method.
Works even when JavaScript-heavy scraping fails.
"""
import re
import logging
import time
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin, quote_plus
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

class SimpleNordstromScraper:
    """Simple scraper that uses requests + BeautifulSoup for reliable extraction."""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
    
    def extract_filters(self, base_url: str = "https://www.nordstrom.com/") -> Dict[str, List[str]]:
        """Extract filters from Nordstrom homepage."""
        filters = {
            'categories': [],
            'brands': []
        }
        
        try:
            response = self.session.get(base_url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract all navigation links
            nav_links = soup.find_all('a', href=True)
            
            # Common Nordstrom categories
            common_categories = [
                'Women', 'Men', 'Kids', 'Home', 'Beauty', 'Sale', 'New', 
                'Designer', 'Shoes', 'Handbags', 'Jewelry', 'Watches',
                'Activewear', 'Dresses', 'Tops', 'Bottoms', 'Outerwear',
                'Accessories', 'Gifts', 'Wedding'
            ]
            
            for link in nav_links:
                href = link.get('href', '').lower()
                text = link.get_text(strip=True)
                
                if text and len(text) > 2 and len(text) < 100:
                    # Check if it matches common categories
                    text_lower = text.lower()
                    for cat in common_categories:
                        if cat.lower() in text_lower or text_lower in cat.lower():
                            if text not in filters['categories']:
                                filters['categories'].append(text)
                                break
                    
                    # Extract from href patterns
                    if any(pattern in href for pattern in ['/browse/', '/c/', '/category/']):
                        if text and text not in filters['categories']:
                            filters['categories'].append(text)
            
            # Also extract from navigation structure
            nav_elements = soup.find_all(['nav', 'ul', 'div'], class_=re.compile(r'nav|menu|category', re.I))
            for nav in nav_elements:
                links = nav.find_all('a', href=True)
                for link in links:
                    text = link.get_text(strip=True)
                    if text and 3 < len(text) < 50:
                        # Common category keywords
                        if any(keyword in text.lower() for keyword in 
                               ['women', 'men', 'kids', 'home', 'beauty', 'sale', 'new', 
                                'designer', 'shoes', 'handbag', 'jewelry', 'watch']):
                            if text not in filters['categories']:
                                filters['categories'].append(text)
            
            # Extract brands from common locations
            brand_elements = soup.find_all(['a', 'span', 'div'], 
                                         string=re.compile(r'nike|adidas|levis|calvin klein|tommy hilfiger', re.I))
            for elem in brand_elements[:20]:
                brand = elem.get_text(strip=True)
                if brand and len(brand) < 50:
                    if brand not in filters['brands']:
                        filters['brands'].append(brand)
            
            logger.info(f"Extracted {len(filters['categories'])} categories and {len(filters['brands'])} brands")
            
        except Exception as e:
            logger.error(f"Error extracting filters: {str(e)}")
        
        return filters
    
    def scrape_products_simple(self, search_term: str, max_items: int = 20) -> List[Dict[str, Any]]:
        """
        Simple product scraping that works with any page structure.
        Extracts basic product information from any links/patterns found.
        """
        products = []
        
        try:
            # Try different URL patterns
            search_urls = [
                f"https://www.nordstrom.com/browse/search?query={quote_plus(search_term)}",
                f"https://www.nordstrom.com/search?query={quote_plus(search_term)}",
                f"https://www.nordstrom.com/sr?query={quote_plus(search_term)}",
            ]
            
            for search_url in search_urls:
                try:
                    logger.info(f"Trying URL: {search_url}")
                    response = self.session.get(search_url, timeout=30)
                    response.raise_for_status()
                    
                    soup = BeautifulSoup(response.content, 'html.parser')
                    
                    # Extract all links - be more aggressive
                    all_links = soup.find_all('a', href=True)
                    
                    # Filter for product-related links
                    product_links = []
                    for link in all_links:
                        href = link.get('href', '').lower()
                        text = link.get_text(strip=True)
                        
                        # Check if it looks like a product link
                        if any(pattern in href for pattern in ['/p/', '/browse/', '/product/', '/item/', '/sku/']):
                            if text and len(text) > 5:  # Has meaningful text
                                product_links.append(link)
                        # Or if it has product-like text
                        elif text and len(text) > 10 and len(text) < 200:
                            if any(word in text.lower() for word in ['jeans', 'shirt', 'top', 'dress', 'shoes', 'jacket']):
                                product_links.append(link)
                    
                    seen_urls = set()
                    
                    for link in product_links[:max_items * 3]:
                        try:
                            href = link.get('href', '')
                            if not href or href in seen_urls:
                                continue
                            
                            # Normalize URL
                            if not href.startswith('http'):
                                href = urljoin('https://www.nordstrom.com', href)
                            
                            seen_urls.add(href)
                            
                            # Extract text content
                            text_parts = []
                            
                            # Get text from link
                            link_text = link.get_text(strip=True)
                            if link_text and len(link_text) > 5:
                                text_parts.append(link_text)
                            
                            # Get text from parent elements
                            parent = link.parent
                            if parent:
                                parent_text = parent.get_text(strip=True)
                                if parent_text and len(parent_text) > len(link_text or ''):
                                    text_parts.append(parent_text[:200])
                            
                            # Try to extract price
                            price_text = None
                            price_elem = link.find_next(string=re.compile(r'\$\d+'))
                            if price_elem:
                                price_text = price_elem.strip()
                            
                            # Create product
                            if text_parts:
                                title = text_parts[0][:500]
                                
                                # Extract product ID from URL
                                product_id = href.split('/')[-1] or href.split('/')[-2] or f"{search_term}_{hash(href) % 10000}"
                                
                                # Extract price
                                price = None
                                if price_text:
                                    price_match = re.search(r'[\d,]+\.?\d*', price_text.replace(',', ''))
                                    if price_match:
                                        try:
                                            price = float(price_match.group())
                                        except:
                                            pass
                                
                                products.append({
                                    'product_id': str(product_id),
                                    'title': title,
                                    'brand': None,  # Will be extracted later if available
                                    'price': price,
                                    'original_price': None,
                                    'url': href[:1000],
                                    'image_url': None,
                                    'category': search_term,
                                    'in_stock': True,
                                    'rating': None,
                                    'review_count': 0
                                })
                        
                        except Exception as e:
                            logger.debug(f"Error processing link: {str(e)}")
                            continue
                    
                    if products:
                        logger.info(f"Found {len(products)} products from {search_url}")
                        break
                        
                except Exception as e:
                    logger.debug(f"URL {search_url} failed: {str(e)}")
                    continue
            
            # If still no products, try extracting from any structured data in the page
            if not products:
                try:
                    # Look for JSON-LD data
                    json_ld_scripts = soup.find_all('script', type='application/ld+json')
                    for script in json_ld_scripts:
                        try:
                            import json
                            data = json.loads(script.string)
                            if isinstance(data, dict) and '@type' in str(data):
                                # Try to extract products from structured data
                                if 'itemListElement' in data:
                                    for item in data.get('itemListElement', [])[:max_items]:
                                        name = item.get('name') or item.get('title')
                                        url = item.get('url')
                                        if name:
                                            products.append({
                                                'product_id': f"jsonld_{hash(name) % 100000}",
                                                'title': name[:500],
                                                'brand': None,
                                                'price': None,
                                                'url': url if url and url.startswith('http') else None,
                                                'category': search_term,
                                                'in_stock': True
                                            })
                        except:
                            continue
                            
                    # Look for any data-attributes that might contain product info
                    elements_with_data = soup.find_all(attrs=lambda x: x and any(k.startswith('data-') for k in x.keys()))
                    for elem in elements_with_data[:max_items * 2]:
                        try:
                            text = elem.get_text(strip=True)
                            if text and len(text) > 10 and len(text) < 200:
                                # Check if it looks like a product name
                                if not any(skip in text.lower() for skip in ['cookie', 'privacy', 'terms', 'sign in', 'cart']):
                                    products.append({
                                        'product_id': f"data_{hash(text) % 100000}",
                                        'title': text[:500],
                                        'brand': None,
                                        'price': None,
                                        'url': None,
                                        'category': search_term,
                                        'in_stock': True
                                    })
                        except:
                            continue
                except Exception as e:
                    logger.debug(f"Advanced extraction failed: {str(e)}")
            
            # Deduplicate by title
            seen_titles = set()
            unique_products = []
            for product in products:
                title = product.get('title', '').lower().strip()
                if title and title not in seen_titles and len(title) > 5:
                    seen_titles.add(title)
                    unique_products.append(product)
            
            products = unique_products
        
        except Exception as e:
            logger.error(f"Error in simple scraping: {str(e)}")
            import traceback
            traceback.print_exc()
        
        return products[:max_items]

