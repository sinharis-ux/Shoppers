
import requests
import logging
from django.db import transaction
from .models import AmazonProduct

logger = logging.getLogger(__name__)

# API Configuration
RAPIDAPI_KEY = "2bb7bd937bmsh70612b3e4bd8ed9p13b5b1jsn5fbf6454cdab"
RAPIDAPI_HOST = "real-time-amazon-data.p.rapidapi.com"
BASE_URL = "https://real-time-amazon-data.p.rapidapi.com/search"

# Search queries mapped to categories
CATEGORY_QUERIES = {
    'Men': 'mens clothes',
    'Women': 'womens clothes',
    'Children': 'kids clothes',
}

# Number of pages to fetch per category (more pages = more products)
MAX_PAGES = 50


class AmazonAPIRequestError(Exception):
    """Raised when the RapidAPI Amazon request fails."""

    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


def search_amazon_products_raw(query, page=1, country="US", sort_by="RELEVANCE", category=""):
    """
    Raw search function to get products from Amazon RapidAPI.
    Returns a list of clean product dictionaries.
    """
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": RAPIDAPI_HOST
    }
    
    # If category is provided and valid, append it to the query for better filtering
    search_query = query
    if category and category in CATEGORY_QUERIES:
        search_query = f"{query} {CATEGORY_QUERIES[category]}"
    elif category:
        search_query = f"{query} {category} clothes"
        
    params = {
        "query": search_query,
        "page": str(page),
        "country": country,
        "sort_by": sort_by,
        # "product_condition": "ALL" # Removing this constraint as it might be too strict
    }
    
    clean_products = []
    
    try:
        print(f"DEBUG: Searching Amazon for '{query}' (Page {page})...")
        print(f"DEBUG: URL: {BASE_URL}")
        print(f"DEBUG: Params: {params}")
        
        response = requests.get(BASE_URL, headers=headers, params=params, timeout=30)
        
        print(f"DEBUG: Status Code: {response.status_code}")
        # print(f"DEBUG: Response: {response.text[:500]}...") # Print first 500 chars
        
        if response.status_code == 429:
            raise AmazonAPIRequestError("RapidAPI rate limit exceeded.", status_code=429)

        try:
            response.raise_for_status()
        except requests.HTTPError as e:
            raise AmazonAPIRequestError(
                f"RapidAPI request failed with status {response.status_code}.",
                status_code=response.status_code
            ) from e

        try:
            data = response.json()
        except ValueError as e:
            raise AmazonAPIRequestError("RapidAPI returned invalid JSON.") from e
        
        products = data.get('data', {}).get('products', [])
        if not products:
            logger.info(f"No products found for '{query}' on page {page}")
            return []
            
        logger.info(f"Fetched {len(products)} products from page {page} for '{query}'")
        
        for item in products:
            try:
                asin = item.get('asin')
                if not asin:
                    continue
                
                # Extract all available fields
                product_data = {
                    'asin': asin,
                    'title': (item.get('product_title') or '')[:500],
                    'price': item.get('product_price') or None,
                    'original_price': item.get('product_original_price') or None,
                    'currency': item.get('currency') or 'USD',
                    'image_url': item.get('product_photo') or None,
                    'product_url': item.get('product_url') or None,
                    'rating': _safe_float(item.get('product_star_rating')),
                    'review_count': _safe_int(item.get('product_num_ratings')),
                    # Category will be set by caller if needed
                    'is_prime': bool(item.get('is_prime', False)),
                    'is_best_seller': bool(item.get('is_best_seller', False)),
                    'is_amazon_choice': bool(item.get('is_amazon_choice', False)),
                    'sales_volume': (item.get('sales_volume') or '')[:100] or None,
                    'delivery': (item.get('delivery') or '')[:255] or None,
                    'coupon_text': (item.get('coupon_text') or '')[:255] or None,
                    'minimum_offer_price': item.get('product_minimum_offer_price') or None,
                }
                
                clean_products.append(product_data)
                
            except Exception as e:
                logger.error(f"Error parsing product {item.get('asin')}: {e}")
                continue
                
    except AmazonAPIRequestError:
        raise
    except requests.RequestException as e:
        logger.error(f"API request failed for page {page}: {e}")
        raise AmazonAPIRequestError(f"RapidAPI request failed: {e}") from e
    except Exception as e:
        logger.error(f"Error fetching page {page} for '{query}': {e}")
        raise AmazonAPIRequestError(f"RapidAPI search failed: {e}") from e

    return clean_products


def fetch_amazon_products(query, category_label, max_pages=MAX_PAGES):
    """
    Fetches products from Amazon via RapidAPI and replaces old data in DB.
    """
    all_products = []
    
    # Fetch multiple pages
    for page in range(1, max_pages + 1):
        try:
            products = search_amazon_products_raw(query, page=page)
        except AmazonAPIRequestError as e:
            logger.warning(f"Stopping Amazon fetch for '{query}' on page {page}: {e}")
            break
        if not products:
            break
            
        # Add category label
        for p in products:
            p['category'] = category_label
            all_products.append(p)
    
    if not all_products:
        logger.warning(f"No products fetched for '{query}'. Old data kept intact.")
        return 0
    
    # DELETE old data and SAVE fresh data atomically
    try:
        with transaction.atomic():
            deleted_count, _ = AmazonProduct.objects.filter(category=category_label).delete()
            logger.info(f"Deleted {deleted_count} old '{category_label}' products")
            
            # Bulk create new products
            product_objects = [AmazonProduct(**p) for p in all_products]
            AmazonProduct.objects.bulk_create(product_objects, ignore_conflicts=True)
            
            logger.info(f"Saved {len(product_objects)} fresh '{category_label}' products")
        
        return len(product_objects)
        
    except Exception as e:
        logger.error(f"Database error for '{category_label}': {e}")
        return 0


def refresh_all_categories():
    """
    Refresh Amazon products for all categories (Men, Women, Children).
    Called by Celery Beat task.
    
    Returns:
        dict: Summary of products saved per category.
    """
    results = {}
    total = 0
    
    for category, query in CATEGORY_QUERIES.items():
        logger.info(f"🔄 Refreshing Amazon products: {category} (query: '{query}')")
        count = fetch_amazon_products(query, category)
        results[category] = count
        total += count
        logger.info(f"✅ {category}: {count} products saved")
    
    logger.info(f"🏁 Total Amazon products refreshed: {total}")
    return results


def _safe_float(value):
    """Safely convert value to float."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _safe_int(value):
    """Safely convert value to int."""
    if value is None:
        return 0
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0
