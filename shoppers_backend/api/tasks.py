"""
Celery tasks for API operations with robust error handling and retry mechanisms.
"""
import os
import time
import logging
from celery import shared_task
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup
import json
import re
from django.utils import timezone
from django.db import transaction

# Import robust scraping utilities
from .scraping_utils import (
    fetch_with_retry,
    get_http_session,
    PlaywrightScraper,
    RateLimiter,
    normalize_url,
    extract_text,
    safe_json_parse,
    batch_update_objects,
    validate_url,
    extract_price
)
from .simple_scraper import SimpleNordstromScraper

logger = logging.getLogger(__name__)


@shared_task
def scrape_nordstrom_products():
    """
    Celery task to scrape Nordstrom products using Apify.
    Searches for jeans, tops, shirts, and shoes, then saves to Excel.
    """
    # Get API token from environment variable
    api_token = os.getenv('APIFY_API_TOKEN')
    
    if not api_token:
        raise ValueError("APIFY_API_TOKEN environment variable is not set. Please set it before running the task.")
    
    # Initialize the ApifyClient
    client = ApifyClient(api_token)
    
    # Actor ID - can be configured via environment variable or use default
    # If test.py uses a different actor ID, set APIFY_ACTOR_ID environment variable
    actor_id = os.getenv('APIFY_ACTOR_ID', 'trudax/actor-nordstrom-scraper')
    
    # Search terms - starting with smaller scope
    search_terms = ["Jeans", "Tops", "Shirts", "Shoes"]
    country = "United States"
    max_items = 50  # Reduced to limit search scope and avoid blocks
    
    # Nordstrom-specific headers to mimic browser behavior
    custom_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Cache-Control": "max-age=0",
        "Referer": "https://www.nordstrom.com/",
    }
    
    all_results = []
    
    # Scrape data for each search term
    for search_term in search_terms:
        print(f"🔍 Searching for: {search_term}")
        
        # Prepare the Actor input - using minimal configuration that matches test.py
        # Note: Some actors may not support all anti-blocking parameters
        # We'll use the basic required fields first to ensure it works
        run_input = {
            "search": search_term,
            "country": country,
            "maxItems": max_items,
            "getDescription": False,
            "debugMode": False,
        }
        
        # Only add startUrls if the actor requires it
        # Some actors may accept None, others require empty array
        # Try empty array first (most common requirement)
        run_input["startUrls"] = []
        
        # Print run_input for debugging
        print(f"📋 Run input: {run_input}")
        print(f"📋 startUrls type: {type(run_input['startUrls'])}, value: {run_input['startUrls']}")
        
        try:
            # Run the Actor and wait for it to finish
            print(f"🎭 Using actor: {actor_id}")
            run = client.actor(actor_id).call(run_input=run_input)
            
            # Fetch Actor results from the run's dataset
            dataset_id = run["defaultDatasetId"]
            print(f"Dataset ID: {dataset_id}")
            print(f"Check your data here: https://console.apify.com/storage/datasets/{dataset_id}")
            
            # Collect all items
            for item in client.dataset(dataset_id).iterate_items():
                # Add search term to each item for tracking
                item['search_term'] = search_term
                item['scraped_at'] = datetime.now().isoformat()
                all_results.append(item)
                
        except Exception as e:
            print(f"❌ Error scraping {search_term}: {str(e)}")
            continue
        
        # Add delay between search terms to mimic human behavior and avoid rate limiting
        if search_term != search_terms[-1]:  # Don't delay after the last search term
            delay_seconds = 5
            print(f"⏳ Waiting {delay_seconds} seconds before next search to avoid rate limiting...")
            time.sleep(delay_seconds)
    
    if not all_results:
        print("No results found")
        return {"status": "error", "message": "No results found"}
    
    # Analyze fields and create DataFrame
    print(f"Total items collected: {len(all_results)}")
    
    # Get all unique keys from all items
    all_keys = set()
    for item in all_results:
        all_keys.update(item.keys())
    
    print(f"Fields found: {sorted(all_keys)}")
    
    # Create DataFrame with all fields
    df = pd.DataFrame(all_results)
    
    # Sort by search_term and then by a relevant field (if available)
    # Common fields might be: title, name, price, etc.
    sort_columns = ['search_term']
    
    # Try to find a price or title field for secondary sorting
    price_fields = [col for col in df.columns if 'price' in col.lower()]
    title_fields = [col for col in df.columns if 'title' in col.lower() or 'name' in col.lower()]
    
    if price_fields:
        sort_columns.append(price_fields[0])
    elif title_fields:
        sort_columns.append(title_fields[0])
    
    # Sort the dataframe
    df = df.sort_values(by=sort_columns, ascending=[True, True])
    
    # Reorder columns: put search_term and scraped_at first, then others
    column_order = ['search_term', 'scraped_at']
    other_columns = [col for col in df.columns if col not in column_order]
    df = df[column_order + other_columns]
    
    # Create output directory if it doesn't exist
    output_dir = Path('knowledgebase')
    output_dir.mkdir(exist_ok=True)
    
    # Generate filename with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = output_dir / f'nordstrom_products_{timestamp}.xlsx'
    
    # Save to Excel with proper formatting
    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Products')
        
        # Get the worksheet to adjust column widths
        worksheet = writer.sheets['Products']
        
        # Auto-adjust column widths
        from openpyxl.utils import get_column_letter
        for idx, col in enumerate(df.columns, start=1):
            max_length = max(
                df[col].astype(str).map(len).max(),
                len(str(col))
            )
            # Set a reasonable max width
            adjusted_width = min(max_length + 2, 50)
            column_letter = get_column_letter(idx)
            worksheet.column_dimensions[column_letter].width = adjusted_width
    
    print(f"Data saved to: {filename}")
    print(f"Total rows: {len(df)}")
    print(f"Columns: {list(df.columns)}")
    
    return {
        "status": "success",
        "filename": str(filename),
        "total_items": len(df),
        "columns": list(df.columns),
        "search_terms": search_terms
    }


@shared_task(bind=True, max_retries=3)
def extract_nordstrom_filters(self, base_url="https://www.nordstrom.com/"):
    """
    Extract filters and information from Nordstrom dashboard with robust error handling.
    This includes categories, brands, sizes, colors, and other filter options.
    Saves to NordstromFilter knowledge base.
    """
    from .models import NordstromFilter
    
    filters_extracted = []
    errors = []
    rate_limiter = RateLimiter(min_delay=1.0, max_delay=3.0)
    session = get_http_session()
    
    try:
        logger.info(f"Starting filter extraction from {base_url}")
        
        # Method 1: Use simple scraper for reliable filter extraction
        try:
            simple_scraper = SimpleNordstromScraper()
            filters_dict = simple_scraper.extract_filters(base_url)
            
            # Save filters from simple scraper
            for category in filters_dict.get('categories', []):
                if category and len(category) < 255:
                    filter_items.append({
                        'filter_type': 'category',
                        'filter_name': category,
                        'url': None,
                        'filter_data': {'extracted_from': 'simple_scraper'},
                        'parent_category': None
                    })
                    filters_extracted.append(f"category: {category}")
            
            for brand in filters_dict.get('brands', []):
                if brand and len(brand) < 255:
                    filter_items.append({
                        'filter_type': 'brand',
                        'filter_name': brand,
                        'url': None,
                        'filter_data': {'extracted_from': 'simple_scraper'},
                        'parent_category': None
                    })
                    filters_extracted.append(f"brand: {brand}")
        except Exception as e:
            logger.warning(f"Simple scraper filter extraction failed: {str(e)}")
        
        # Method 2: Fetch and parse main page with retries (additional extraction)
        try:
            response = fetch_with_retry(base_url, session=session, rate_limiter=rate_limiter)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract navigation categories
            nav_elements = soup.find_all(['nav', 'ul'], class_=re.compile(r'nav|menu|category', re.I))
            filter_items = []
            
            for nav in nav_elements:
                links = nav.find_all('a', href=True)
                for link in links:
                    text = extract_text(link, max_length=100)
                    href = link.get('href', '')
                    
                    if text and len(text) > 2:
                        normalized_url = normalize_url(href, base_url) if href else None
                        
                        filter_items.append({
                            'filter_type': 'category',
                            'filter_name': text,
                            'url': normalized_url if validate_url(normalized_url) else None,
                            'filter_data': {'extracted_from': 'navigation'},
                            'parent_category': None
                        })
                        filters_extracted.append(f"category: {text}")
            
            # Extract from JSON-LD structured data
            scripts = soup.find_all('script', type='application/ld+json')
            for script in scripts:
                if not script.string:
                    continue
                    
                data = safe_json_parse(script.string)
                if data and isinstance(data, dict):
                    if 'itemListElement' in data:
                        for item in data.get('itemListElement', []):
                            name = item.get('name')
                            if name:
                                url = item.get('url', '')
                                filter_items.append({
                                    'filter_type': 'category',
                                    'filter_name': name,
                                    'url': url if validate_url(url) else None,
                                    'filter_data': {'extracted_from': 'json-ld'},
                                    'parent_category': None
                                })
                                filters_extracted.append(f"category: {name}")
            
            # Extract filter sections (brands, sizes, colors, etc.)
            filter_sections = soup.find_all(['div', 'section'], class_=re.compile(r'filter|facet|refine', re.I))
            
            for section in filter_sections:
                filter_label = section.find(['label', 'h3', 'span'], class_=re.compile(r'title|label|heading', re.I))
                if filter_label:
                    filter_type_text = extract_text(filter_label).lower() if filter_label else ''
                    
                    # Determine filter type
                    filter_type = 'other'
                    if 'brand' in filter_type_text:
                        filter_type = 'brand'
                    elif 'size' in filter_type_text:
                        filter_type = 'size'
                    elif 'color' in filter_type_text:
                        filter_type = 'color'
                    elif 'price' in filter_type_text:
                        filter_type = 'price_range'
                    elif 'category' in filter_type_text or 'department' in filter_type_text:
                        filter_type = 'category'
                    
                    # Extract filter options
                    options = section.find_all(['a', 'button', 'label', 'span'], 
                                             class_=re.compile(r'option|value|item', re.I))
                    for option in options:
                        text = extract_text(option, max_length=100)
                        if text:
                            filter_items.append({
                                'filter_type': filter_type,
                                'filter_name': text,
                                'url': None,
                                'filter_data': {'extracted_from': 'filter_section'},
                                'parent_category': None
                            })
                            filters_extracted.append(f"{filter_type}: {text}")
            
            # Batch save filters to database
            if filter_items:
                try:
                    with transaction.atomic():
                        for item in filter_items:
                            NordstromFilter.objects.update_or_create(
                                filter_type=item['filter_type'],
                                filter_name=item['filter_name'],
                                defaults={
                                    'url': item.get('url'),
                                    'filter_data': item['filter_data'],
                                    'parent_category': item.get('parent_category')
                                }
                            )
                except Exception as e:
                    logger.error(f"Database error saving filters: {str(e)}")
                    errors.append(f"Database error: {str(e)}")
                    
        except Exception as e:
            error_msg = f"Error in page parsing: {str(e)}"
            logger.error(error_msg)
            errors.append(error_msg)
        
        # Method 2: Use Playwright for comprehensive filter extraction
        try:
            with PlaywrightScraper(headless=True) as scraper:
                logger.info("Using Playwright to extract additional filters...")
                
                # Scrape filters from homepage
                playwright_filters = scraper.scrape_nordstrom_filters(base_url)
                
                # Add categories from Playwright
                for category in playwright_filters.get('categories', []):
                    if category and len(category) < 255:
                        filter_items.append({
                            'filter_type': 'category',
                            'filter_name': category,
                            'url': None,
                            'filter_data': {'extracted_from': 'playwright'},
                            'parent_category': None
                        })
                
                # Add brands from Playwright
                for brand in playwright_filters.get('brands', []):
                    if brand and len(brand) < 255:
                        filter_items.append({
                            'filter_type': 'brand',
                            'filter_name': brand,
                            'url': None,
                            'filter_data': {'extracted_from': 'playwright'},
                            'parent_category': None
                        })
                
                # Batch save Playwright-extracted filters
                if filter_items:
                    with transaction.atomic():
                        for item in filter_items[-50:]:  # Process last 50 to avoid duplicates
                            try:
                                filter_obj, created = NordstromFilter.objects.update_or_create(
                                    filter_type=item['filter_type'],
                                    filter_name=item['filter_name'],
                                    defaults={
                                        'filter_data': item['filter_data']
                                    }
                                )
                                if created:
                                    filters_extracted.append(f"{item['filter_type']}: {item['filter_name']}")
                            except Exception as e:
                                logger.warning(f"Error saving filter {item['filter_name']}: {str(e)}")
                                
        except Exception as e:
            error_msg = f"Playwright filter extraction failed: {str(e)}"
            logger.warning(error_msg)
            errors.append(error_msg)
        
        total_in_db = NordstromFilter.objects.count()
        
        result = {
            "status": "success" if not errors or len(filters_extracted) > 0 else "partial",
            "filters_extracted": len(filters_extracted),
            "filters": filters_extracted[:100],  # Return first 100
            "total_in_db": total_in_db,
            "errors": errors[:5] if errors else []
        }
        
        logger.info(f"Filter extraction completed: {result['filters_extracted']} filters extracted, {total_in_db} total in DB")
        return result
        
    except Exception as e:
        error_msg = f"Critical error in filter extraction: {str(e)}"
        logger.error(error_msg, exc_info=True)
        
        # Retry if not max retries
        if self.request.retries < self.max_retries:
            logger.info(f"Retrying filter extraction (attempt {self.request.retries + 1}/{self.max_retries})")
            raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))
        
        return {
            "status": "error",
            "message": error_msg,
            "filters_extracted": len(filters_extracted),
            "errors": errors
        }


def _process_product_batch(batch_items):
    """
    Helper function to process a batch of products in a transaction.
    """
    from .models import NordstromProduct
    
    created_count = 0
    updated_count = 0
    
    try:
        with transaction.atomic():
            for product_data in batch_items:
                try:
                    product, created = NordstromProduct.objects.update_or_create(
                        product_id=product_data['product_id'],
                        defaults={
                            k: v for k, v in product_data.items() 
                            if k != 'product_id'
                        }
                    )
                    
                    if created:
                        created_count += 1
                    else:
                        updated_count += 1
                        
                except Exception as e:
                    logger.warning(f"Error saving product {product_data.get('product_id')}: {str(e)}")
                    continue
                    
    except Exception as e:
        logger.error(f"Error in batch transaction: {str(e)}")
        raise
    
    return created_count, updated_count


@shared_task(bind=True, max_retries=2)
def scrape_nordstrom_products_to_db(self, search_terms=None, max_items_per_term=50):
    """
    Scrape Nordstrom products and save to NordstromProduct knowledge base with robust error handling.
    Uses batch processing and validation for optimal performance.
    """
    from .models import NordstromProduct
    
    if search_terms is None:
        search_terms = ["Jeans", "Tops", "Shirts", "Shoes", "Dresses", "Jackets"]
    
    products_saved = 0
    products_updated = 0
    errors = []
    batch_items = []
    batch_size = 50  # Process in batches for efficiency
    
    try:
        # Initialize Playwright scraper
        try:
            scraper = PlaywrightScraper(headless=True)
            scraper.start()
        except Exception as e:
            logger.error(f"Failed to initialize Playwright: {str(e)}")
            return {
                "status": "error",
                "message": f"Playwright initialization failed: {str(e)}",
                "products_saved": 0,
                "products_updated": 0
            }
        
        try:
            for search_term in search_terms:
                logger.info(f"🔍 Scraping products for: {search_term}")
                
                try:
                    # Try Playwright first
                    items = scraper.scrape_nordstrom_search(search_term, max_items=max_items_per_term)
                    logger.info(f"Retrieved {len(items)} items for {search_term} using Playwright")
                    
                    # If no items, try simple scraper as fallback
                    if not items:
                        logger.info(f"Playwright found no products, trying simple scraper...")
                        simple_scraper = SimpleNordstromScraper()
                        items = simple_scraper.scrape_products_simple(search_term, max_items=max_items_per_term)
                        logger.info(f"Retrieved {len(items)} items for {search_term} using simple scraper")
                    
                    if not items:
                        logger.warning(f"No products found for {search_term} with any method")
                        continue
                    
                    # Process items
                    for item in items:
                        try:
                            # Product data from Playwright scraper
                            product_id = item.get('product_id')
                            if not product_id:
                                logger.warning(f"Skipping item with no product ID: {item.get('title', 'Unknown')}")
                                continue
                            
                            # Prepare product data for batch save
                            product_data = {
                                'product_id': product_id,
                                'title': item.get('title', 'Unknown Product')[:500],
                                'brand': (item.get('brand') or None)[:255] if item.get('brand') else None,
                                'price': item.get('price'),
                                'original_price': item.get('original_price'),
                                'currency': 'USD',
                                'url': item.get('url', '')[:1000] if item.get('url') else None,
                                'image_url': item.get('image_url', '')[:1000] if item.get('image_url') else None,
                                'description': None,  # Will be filled from detail page if needed
                                'category': search_term[:255],
                                'subcategory': None,
                                'sizes': [],
                                'colors': [],
                                'in_stock': item.get('in_stock', True),
                                'rating': item.get('rating'),
                                'review_count': 0,
                                'additional_data': {'search_term': item.get('search_term')}
                            }
                            
                            batch_items.append(product_data)
                            
                            # Process batch when size reached
                            if len(batch_items) >= batch_size:
                                created, updated = _process_product_batch(batch_items)
                                products_saved += created
                                products_updated += updated
                                batch_items = []
                                
                        except Exception as e:
                            error_msg = f"Error processing product: {str(e)}"
                            logger.warning(error_msg)
                            errors.append(error_msg)
                            continue
                    
                    logger.info(f"✅ Completed scraping {search_term}")
                    
                except Exception as e:
                    error_msg = f"Error scraping {search_term}: {str(e)}"
                    logger.error(error_msg, exc_info=True)
                    errors.append(error_msg)
                    continue
            
            # Process remaining batch items
            if batch_items:
                created, updated = _process_product_batch(batch_items)
                products_saved += created
                products_updated += updated
                
        finally:
            # Cleanup Playwright
            try:
                scraper.close()
            except:
                pass
        
        total_products = NordstromProduct.objects.count()
        
        result = {
            "status": "success",
            "products_saved": products_saved,
            "products_updated": products_updated,
            "total_products": total_products,
            "errors": errors[:10] if errors else []
        }
        
        logger.info(f"Product scraping completed: {products_saved} saved, {products_updated} updated, {total_products} total")
        return result
        
    except Exception as e:
        error_msg = f"Critical error in product scraping: {str(e)}"
        logger.error(error_msg, exc_info=True)
        
        # Retry if not max retries
        if self.request.retries < self.max_retries:
            logger.info(f"Retrying product scraping (attempt {self.request.retries + 1}/{self.max_retries})")
            raise self.retry(exc=e, countdown=120 * (self.request.retries + 1))
        
        return {
            "status": "error",
            "message": error_msg,
            "products_saved": products_saved,
            "products_updated": products_updated,
            "errors": errors[:10]
        }


def _process_product_batch(batch_items):
    """
    Helper function to process a batch of products in a transaction.
    """
    from .models import NordstromProduct
    
    created_count = 0
    updated_count = 0
    
    try:
        with transaction.atomic():
            for product_data in batch_items:
                try:
                    product, created = NordstromProduct.objects.update_or_create(
                        product_id=product_data['product_id'],
                        defaults={
                            k: v for k, v in product_data.items() 
                            if k != 'product_id'
                        }
                    )
                    
                    if created:
                        created_count += 1
                    else:
                        updated_count += 1
                        
                except Exception as e:
                    logger.warning(f"Error saving product {product_data.get('product_id')}: {str(e)}")
                    continue
                    
    except Exception as e:
        logger.error(f"Error in batch transaction: {str(e)}")
        raise
    
    return created_count, updated_count




@shared_task(bind=True, max_retries=2)
def scrape_nordstrom_playwright_daily(self):
    """
    Daily Celery task to scrape Nordstrom products using Playwright.
    Runs the management command to scrape all categories and save to database.
    """
    from django.core.management import call_command
    
    try:
        logger.info("Starting daily Nordstrom Playwright scraping task...")
        
        # Call the management command
        call_command('scrape_nordstrom_playwright', max_pages=3)
        
        logger.info("Daily Nordstrom Playwright scraping completed successfully")
        return {
            "status": "success",
            "message": "Daily scraping completed"
        }
        
    except Exception as e:
        error_msg = f"Error in daily Playwright scraping: {str(e)}"
        logger.error(error_msg, exc_info=True)
        
        # Retry if not max retries
        if self.request.retries < self.max_retries:
            logger.info(f"Retrying daily scraping (attempt {self.request.retries + 1}/{self.max_retries})")
            raise self.retry(exc=e, countdown=3600 * (self.request.retries + 1))  # Retry after 1 hour
        
        return {
            "status": "error",
            "message": error_msg
        }


@shared_task(bind=True, max_retries=2)
def refresh_amazon_products(self):
    """
    Celery Beat task to refresh Amazon product data every 2 hours.
    Deletes old data and saves fresh data from the API for all categories.
    """
    from .amazon_service import refresh_all_categories
    
    try:
        logger.info("🔄 Starting Amazon product refresh...")
        results = refresh_all_categories()
        
        total = sum(results.values())
        logger.info(f"✅ Amazon refresh complete: {total} total products. Details: {results}")
        
        return {
            "status": "success",
            "total_products": total,
            "categories": results
        }
        
    except Exception as e:
        error_msg = f"Error refreshing Amazon products: {str(e)}"
        logger.error(error_msg, exc_info=True)
        
        if self.request.retries < self.max_retries:
            logger.info(f"Retrying Amazon refresh (attempt {self.request.retries + 1}/{self.max_retries})")
            raise self.retry(exc=e, countdown=300 * (self.request.retries + 1))
        
        return {
            "status": "error",
            "message": error_msg
        }
