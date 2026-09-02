"""
Robust scraping utilities with retry mechanisms, error handling, and rate limiting.
"""
import os
import time
import logging
import random
import re
from functools import wraps
from typing import Optional, Dict, Any, List
from urllib.parse import urljoin, urlparse
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from requests.exceptions import (
    RequestException, 
    Timeout, 
    ConnectionError, 
    HTTPError,
    TooManyRedirects
)
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    retry_if_result,
    before_sleep_log
)
logger = logging.getLogger(__name__)

try:
    from playwright.sync_api import sync_playwright, Browser, Page, TimeoutError as PlaywrightTimeoutError
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("Playwright not installed. Install with: pip install playwright && playwright install")
    # Define dummy classes for type hinting if Playwright is missing
    Page = Any
    Browser = Any
    PlaywrightTimeoutError = Exception

from django.db import transaction
from django.core.exceptions import ValidationError

# Rate limiting
class RateLimiter:
    """Simple rate limiter to prevent overwhelming target servers."""
    def __init__(self, min_delay: float = 1.0, max_delay: float = 3.0):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.last_request_time = 0
    
    def wait(self):
        """Wait if necessary to respect rate limits."""
        elapsed = time.time() - self.last_request_time
        delay = random.uniform(self.min_delay, self.max_delay)
        
        if elapsed < delay:
            sleep_time = delay - elapsed
            logger.debug(f"Rate limiting: sleeping for {sleep_time:.2f} seconds")
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()


# Create session with retry strategy
def create_robust_session(max_retries: int = 3, backoff_factor: float = 0.3) -> requests.Session:
    """
    Create a requests session with automatic retries and connection pooling.
    """
    session = requests.Session()
    
    # Retry strategy
    retry_strategy = Retry(
        total=max_retries,
        backoff_factor=backoff_factor,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"],
        respect_retry_after_header=True
    )
    
    adapter = HTTPAdapter(
        max_retries=retry_strategy,
        pool_connections=10,
        pool_maxsize=20
    )
    
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    # Default headers
    session.headers.update({
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
    })
    
    return session


# Global session instance
_http_session = None

def get_http_session() -> requests.Session:
    """Get or create global HTTP session."""
    global _http_session
    if _http_session is None:
        _http_session = create_robust_session()
    return _http_session


# Retry decorator for HTTP requests
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((RequestException, ConnectionError, Timeout)),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True
)
def fetch_with_retry(
    url: str,
    session: Optional[requests.Session] = None,
    timeout: int = 30,
    rate_limiter: Optional[RateLimiter] = None,
    **kwargs
) -> requests.Response:
    """
    Fetch URL with automatic retries and error handling.
    
    Args:
        url: URL to fetch
        session: Requests session (uses global if not provided)
        timeout: Request timeout in seconds
        rate_limiter: Optional rate limiter
        **kwargs: Additional arguments for requests.get()
    
    Returns:
        Response object
    
    Raises:
        RequestException: If all retries fail
    """
    if session is None:
        session = get_http_session()
    
    if rate_limiter:
        rate_limiter.wait()
    
    try:
        response = session.get(url, timeout=timeout, **kwargs)
        response.raise_for_status()
        return response
    except HTTPError as e:
        logger.warning(f"HTTP error for {url}: {e.response.status_code}")
        raise
    except Timeout:
        logger.warning(f"Timeout fetching {url}")
        raise
    except ConnectionError as e:
        logger.warning(f"Connection error for {url}: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error fetching {url}: {str(e)}")
        raise RequestException(f"Error fetching {url}: {str(e)}")


# Playwright-based scraper for JavaScript-heavy sites
class PlaywrightScraper:
    """Robust web scraper using Playwright with retry logic and error handling."""
    
    def __init__(self, headless: bool = True, timeout: int = 30000):
        if not PLAYWRIGHT_AVAILABLE:
            raise ImportError(
                "Playwright not installed. Install with: "
                "pip install playwright && playwright install chromium"
            )
        self.headless = headless
        self.timeout = timeout
        self.rate_limiter = RateLimiter(min_delay=2.0, max_delay=5.0)
        self.playwright = None
        self.browser = None
        self.context = None
    
    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
    
    def start(self):
        """Start Playwright browser."""
        if self.playwright is None:
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.launch(
                headless=self.headless,
                args=['--disable-blink-features=AutomationControlled']
            )
            self.context = self.browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080}
            )
    
    def close(self):
        """Close browser and cleanup."""
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=4, max=30),
        retry=retry_if_exception_type((ConnectionError, RequestException)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True
    )
    def scrape_page(self, url: str, wait_for_selector: Optional[str] = None) -> Page:
        """
        Scrape a page with retry logic.
        
        Args:
            url: URL to scrape
            wait_for_selector: Optional CSS selector to wait for (non-blocking)
        
        Returns:
            Playwright Page object
        """
        if not self.context:
            self.start()
        
        self.rate_limiter.wait()
        
        try:
            page = self.context.new_page()
            page.set_default_timeout(self.timeout)
            
            logger.info(f"Loading page: {url}")
            page.goto(url, wait_until='networkidle', timeout=self.timeout)
            
            # Try to wait for selector, but don't fail if it doesn't appear
            if wait_for_selector:
                try:
                    page.wait_for_selector(wait_for_selector, timeout=5000)  # Shorter timeout
                except PlaywrightTimeoutError:
                    logger.debug(f"Selector {wait_for_selector} not found, continuing anyway")
            
            return page
            
        except PlaywrightTimeoutError as e:
            logger.warning(f"Timeout loading {url}: {str(e)}")
            # Return page anyway - it might still have content
            if 'page' in locals():
                return page
            raise
        except Exception as e:
            logger.error(f"Error loading {url}: {str(e)}")
            raise
    
    def scrape_nordstrom_search(self, search_term: str, max_items: int = 50) -> List[Dict[str, Any]]:
        """
        Scrape Nordstrom search results using multiple strategies.
        
        Args:
            search_term: Search query
            max_items: Maximum number of products to scrape
        
        Returns:
            List of product dictionaries
        """
        products = []
        
        try:
            # Construct search URL
            search_url = f"https://www.nordstrom.com/browse/search?query={search_term.replace(' ', '+')}"
            
            logger.info(f"Scraping Nordstrom search: {search_term}")
            
            # Load page without strict selector requirement
            page = self.scrape_page(search_url, wait_for_selector=None)
            
            # Wait for page to fully load
            page.wait_for_load_state('networkidle', timeout=30000)
            page.wait_for_timeout(5000)  # Wait for React/Vue to render
            
            # Strategy 1: Try to extract from JSON-LD structured data
            try:
                json_ld_products = self._extract_from_json_ld(page, search_term)
                if json_ld_products:
                    logger.info(f"Found {len(json_ld_products)} products from JSON-LD")
                    products.extend(json_ld_products[:max_items])
            except Exception as e:
                logger.debug(f"JSON-LD extraction failed: {str(e)}")
            
            # Strategy 2: Try to extract from JavaScript variables/state
            if len(products) < max_items:
                try:
                    js_products = self._extract_from_javascript_state(page, search_term)
                    if js_products:
                        logger.info(f"Found {len(js_products)} products from JS state")
                        products.extend(js_products[:max_items])
                except Exception as e:
                    logger.debug(f"JS state extraction failed: {str(e)}")
            
            # Scroll to trigger lazy loading
            page.evaluate("""
                () => {
                    window.scrollTo(0, document.body.scrollHeight / 2);
                }
            """)
            page.wait_for_timeout(2000)
            
            page.evaluate("""
                () => {
                    window.scrollTo(0, document.body.scrollHeight);
                }
            """)
            page.wait_for_timeout(3000)  # Wait for lazy loading
            
            # Try multiple selector strategies
            product_cards = []
            selectors_to_try = [
                '[data-testid="product-card"]',
                '.ProductCard',
                '[class*="ProductCard"]',
                '[class*="product-card"]',
                'article[class*="product"]',
                '[data-item-id]',
                '.fashion-item',
                '[href*="/p/"]',
                'a[href*="/browse/"]',
                'div[class*="ProductTile"]',
                '[data-product-id]'
            ]
            
            for selector in selectors_to_try:
                try:
                    cards = page.query_selector_all(selector)
                    if cards and len(cards) > 0:
                        logger.info(f"Found {len(cards)} items using selector: {selector}")
                        product_cards = cards
                        break
                except Exception as e:
                    logger.debug(f"Selector {selector} failed: {str(e)}")
                    continue
            
            # If no cards found, try extracting from links
            if not product_cards:
                logger.warning("No product cards found with standard selectors, trying link-based extraction")
                links = page.query_selector_all('a[href*="/p/"], a[href*="/browse/"]')
                if links:
                    logger.info(f"Found {len(links)} product links")
                    product_cards = links[:max_items * 2]  # Get more links to filter
            
            logger.info(f"Processing {len(product_cards)} potential products")
            
            # Extract products
            for idx, card in enumerate(product_cards[:max_items * 2]):  # Get more to filter
                try:
                    product = self._extract_product_from_card(card, page, search_term)
                    if product and product.get('title'):
                        product['search_term'] = search_term
                        products.append(product)
                        if len(products) >= max_items:
                            break
                except Exception as e:
                    logger.debug(f"Error extracting product {idx}: {str(e)}")
                    continue
            
            # Strategy 3: Traditional DOM-based extraction (existing code continues here)
            # ... (keep existing code)
            
            page.close()
            
        except Exception as e:
            logger.error(f"Error scraping Nordstrom search: {str(e)}")
            # Don't raise - return what we have or empty list
            if 'page' in locals():
                try:
                    page.close()
                except:
                    pass
        
        # Remove duplicates based on product_id or URL
        seen = set()
        unique_products = []
        for product in products:
            product_id = product.get('product_id') or product.get('url', '')
            if product_id and product_id not in seen:
                seen.add(product_id)
                unique_products.append(product)
        
        products = unique_products[:max_items]
        
        # If no products found, try a simpler approach with direct HTML parsing
        if len(products) == 0:
            logger.warning("No products found with Playwright, trying simpler extraction")
            try:
                page = self.scrape_page(search_url, wait_for_selector=None)
                html_content = page.content()
                page.close()
                
                # Parse with BeautifulSoup as fallback
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html_content, 'html.parser')
                
                # Try to find product links
                product_links = soup.find_all('a', href=re.compile(r'/p/|/browse/'))
                
                for link in product_links[:max_items]:
                    try:
                        href = link.get('href', '')
                        text = link.get_text(strip=True)
                        
                        if href and text and len(text) > 5:
                            product_url = normalize_url(href, 'https://www.nordstrom.com')
                            product_id = product_url.split('/')[-1] or text[:30].replace(' ', '_')
                            
                            products.append({
                                'product_id': product_id,
                                'title': text[:500],
                                'brand': None,
                                'price': None,
                                'original_price': None,
                                'url': product_url,
                                'image_url': None,
                                'rating': None,
                                'in_stock': True
                            })
                            
                            if len(products) >= max_items:
                                break
                    except:
                        continue
                        
                if products:
                    logger.info(f"Fallback extraction found {len(products)} products")
            except Exception as e:
                logger.warning(f"Fallback extraction also failed: {str(e)}")
        
        logger.info(f"Successfully scraped {len(products)} products")
        return products
    
    def _extract_product_from_card(self, card, page: Page, search_term: str = '') -> Optional[Dict[str, Any]]:
        """Extract product data from a product card element with flexible parsing."""
        try:
            # Try multiple strategies to extract title
            title = None
            title_selectors = [
                'h3', 'h2', 'h4',
                '[data-testid="product-title"]',
                '.ProductCard-title',
                '[class*="title"]',
                '[class*="name"]',
                'a[aria-label]'
            ]
            
            for selector in title_selectors:
                try:
                    title_elem = card.query_selector(selector)
                    if title_elem:
                        title = title_elem.inner_text().strip()
                        if title and len(title) > 3:
                            break
                except:
                    continue
            
            # If still no title, try getting text from the card itself
            if not title:
                try:
                    title = card.inner_text().strip().split('\n')[0][:100]
                    if len(title) < 5:
                        title = None
                except:
                    pass
            
            # If link element, try to get title from aria-label or title attribute
            if not title:
                try:
                    if card.tag_name.lower() == 'a':
                        title = card.get_attribute('aria-label') or card.get_attribute('title')
                except:
                    pass
            
            if not title or len(title) < 3:
                return None
            
            # Extract price with multiple strategies
            price = None
            price_selectors = [
                '[data-testid="product-price"]',
                '.Price-current',
                '.ProductCard-price',
                '[class*="price"]',
                '[class*="Price"]'
            ]
            
            for selector in price_selectors:
                try:
                    price_elem = card.query_selector(selector)
                    if price_elem:
                        price_text = price_elem.inner_text().strip()
                        price = extract_price(price_text)
                        if price:
                            break
                except:
                    continue
            
            # Extract original price
            original_price = None
            orig_price_selectors = ['.Price-original', '.ProductCard-originalPrice', '[class*="original"]']
            for selector in orig_price_selectors:
                try:
                    orig_price_elem = card.query_selector(selector)
                    if orig_price_elem:
                        orig_price_text = orig_price_elem.inner_text().strip()
                        original_price = extract_price(orig_price_text)
                        if original_price:
                            break
                except:
                    continue
            
            # Extract brand
            brand = None
            brand_selectors = [
                '[data-testid="product-brand"]',
                '.ProductCard-brand',
                '[class*="brand"]'
            ]
            for selector in brand_selectors:
                try:
                    brand_elem = card.query_selector(selector)
                    if brand_elem:
                        brand = brand_elem.inner_text().strip()
                        if brand:
                            break
                except:
                    continue
            
            # Extract image
            image_url = None
            img_selectors = [
                'img[data-testid="product-image"]',
                '.ProductCard-image img',
                'img[src*="nordstrom"]',
                'img'
            ]
            for selector in img_selectors:
                try:
                    img_elem = card.query_selector(selector)
                    if img_elem:
                        image_url = img_elem.get_attribute('src') or img_elem.get_attribute('data-src')
                        if image_url and 'nordstrom' in image_url.lower():
                            break
                except:
                    continue
            
            # Extract product URL - try multiple strategies
            product_url = None
            
            # If card itself is a link
            try:
                if card.tag_name.lower() == 'a':
                    href = card.get_attribute('href')
                    if href:
                        product_url = normalize_url(href, 'https://www.nordstrom.com')
            except:
                pass
            
            # Try finding link inside card
            if not product_url:
                link_selectors = [
                    'a[href*="/p/"]',
                    'a[href*="/browse/"]',
                    'a[href*="nordstrom"]'
                ]
                for selector in link_selectors:
                    try:
                        link_elem = card.query_selector(selector)
                        if link_elem:
                            href = link_elem.get_attribute('href')
                            if href:
                                product_url = normalize_url(href, 'https://www.nordstrom.com')
                                break
                    except:
                        continue
            
            # Extract product ID from URL
            product_id = None
            if product_url:
                parts = product_url.rstrip('/').split('/')
                product_id = parts[-1] if parts else None
                if not product_id or len(product_id) < 3:
                    product_id = parts[-2] if len(parts) > 1 else None
            
            # Generate ID from title if no URL
            if not product_id:
                product_id = f"{search_term}_{title[:30]}".replace(' ', '_').replace('/', '_')[:100]
            
            # Extract rating (optional)
            rating = None
            try:
                rating_elem = card.query_selector('[data-testid="rating"], .ProductCard-rating, [class*="rating"]')
                if rating_elem:
                    rating_text = rating_elem.inner_text().strip()
                    rating_match = re.search(r'(\d+\.?\d*)', rating_text)
                    if rating_match:
                        try:
                            rating = float(rating_match.group(1))
                            if rating > 5:
                                rating = None
                        except:
                            pass
            except:
                pass
            
            return {
                'product_id': product_id,
                'title': title[:500],
                'brand': brand[:255] if brand else None,
                'price': price,
                'original_price': original_price,
                'url': product_url[:1000] if product_url else None,
                'image_url': image_url[:1000] if image_url else None,
                'rating': rating,
                'in_stock': True  # Assume in stock if shown
            }
            
        except Exception as e:
            logger.warning(f"Error extracting product data: {str(e)}")
            return None
    
    def scrape_nordstrom_filters(self, url: str = "https://www.nordstrom.com/") -> Dict[str, List[str]]:
        """
        Scrape filters from Nordstrom homepage.
        
        Args:
            url: Nordstrom URL to scrape
        
        Returns:
            Dictionary of filter types and values
        """
        filters = {
            'categories': [],
            'brands': [],
            'sizes': [],
            'colors': []
        }
        
        try:
            page = self.scrape_page(url)
            
            # Extract navigation categories
            nav_items = page.query_selector_all('nav a, [data-testid="navigation"] a, .Navigation-link')
            for item in nav_items:
                text = item.inner_text().strip()
                if text and len(text) > 2 and len(text) < 100:
                    filters['categories'].append(text)
            
            # Extract brands (from footer or brand section)
            brand_items = page.query_selector_all('[data-testid="brand"], .Brand-link')
            for item in brand_items:
                text = item.inner_text().strip()
                if text:
                    filters['brands'].append(text)
            
            page.close()
            
        except Exception as e:
            logger.error(f"Error scraping filters: {str(e)}")
        
        return filters
    
    def _extract_from_json_ld(self, page: Page, search_term: str) -> List[Dict[str, Any]]:
        """Extract products from JSON-LD structured data."""
        products = []
        
        try:
            # Get all JSON-LD scripts
            scripts = page.query_selector_all('script[type="application/ld+json"]')
            
            for script in scripts:
                try:
                    json_text = script.inner_text()
                    if not json_text:
                        continue
                    
                    data = safe_json_parse(json_text)
                    if not data:
                        continue
                    
                    # Handle array of items
                    if isinstance(data, list):
                        for item in data:
                            products.extend(self._parse_json_ld_item(item, search_term))
                    # Handle single object
                    elif isinstance(data, dict):
                        products.extend(self._parse_json_ld_item(data, search_term))
                        
                        # Check for itemListElement (breadcrumbs/navigation)
                        if 'itemListElement' in data:
                            for element in data.get('itemListElement', []):
                                products.extend(self._parse_json_ld_item(element, search_term))
                        
                        # Check for mainEntity (products)
                        if 'mainEntity' in data:
                            products.extend(self._parse_json_ld_item(data['mainEntity'], search_term))
                            
                except Exception as e:
                    logger.debug(f"Error parsing JSON-LD: {str(e)}")
                    continue
                    
        except Exception as e:
            logger.debug(f"Error extracting JSON-LD: {str(e)}")
        
        return products
    
    def _parse_json_ld_item(self, item: Dict[str, Any], search_term: str) -> List[Dict[str, Any]]:
        """Parse a JSON-LD item into product format."""
        products = []
        
        try:
            # Check if this is a Product type
            item_type = item.get('@type', '')
            if 'Product' not in str(item_type):
                return products
            
            title = item.get('name') or item.get('title')
            if not title:
                return products
            
            # Extract product data
            product_id = item.get('sku') or item.get('productID') or item.get('@id', '').split('/')[-1]
            
            # Extract price
            price = None
            offers = item.get('offers')
            if offers:
                if isinstance(offers, dict):
                    price = extract_price(offers.get('price'))
                elif isinstance(offers, list) and offers:
                    price = extract_price(offers[0].get('price'))
            
            # Extract URL
            url = item.get('url') or item.get('sameAs')
            
            # Extract image
            image_url = None
            image = item.get('image')
            if isinstance(image, str):
                image_url = image
            elif isinstance(image, list) and image:
                image_url = image[0] if isinstance(image[0], str) else image[0].get('url')
            elif isinstance(image, dict):
                image_url = image.get('url')
            
            # Extract brand
            brand = None
            brand_obj = item.get('brand')
            if isinstance(brand_obj, dict):
                brand = brand_obj.get('name')
            elif isinstance(brand_obj, str):
                brand = brand_obj
            
            # Extract rating
            rating = None
            aggregate_rating = item.get('aggregateRating') or item.get('ratingValue')
            if aggregate_rating:
                if isinstance(aggregate_rating, dict):
                    rating = aggregate_rating.get('ratingValue')
                elif isinstance(aggregate_rating, (int, float)):
                    rating = float(aggregate_rating)
            
            if title:
                products.append({
                    'product_id': product_id or f"jsonld_{title[:30].replace(' ', '_')}",
                    'title': title[:500],
                    'brand': brand[:255] if brand else None,
                    'price': price,
                    'original_price': None,
                    'url': url[:1000] if url else None,
                    'image_url': image_url[:1000] if image_url else None,
                    'rating': float(rating) if rating else None,
                    'in_stock': True
                })
                
        except Exception as e:
            logger.debug(f"Error parsing JSON-LD item: {str(e)}")
        
        return products
    
    def _extract_from_javascript_state(self, page: Page, search_term: str) -> List[Dict[str, Any]]:
        """Extract products from JavaScript variables/state in the page."""
        products = []
        
        try:
            # Try to find product data in window variables
            js_code = """
            () => {
                const products = [];
                
                // Try common variable names
                const possibleVars = [
                    window.__INITIAL_STATE__,
                    window.__PRELOADED_STATE__,
                    window.initialData,
                    window.productData,
                    window.searchResults,
                    window.products,
                    window.items
                ];
                
                for (const data of possibleVars) {
                    if (data && typeof data === 'object') {
                        try {
                            const json = JSON.stringify(data);
                            if (json.includes('product') || json.includes('item')) {
                                products.push(json);
                                break;
                            }
                        } catch(e) {}
                    }
                }
                
                // Also try to get from React/Vue props
                const reactRoot = document.querySelector('#root') || document.querySelector('[data-reactroot]');
                if (reactRoot && reactRoot.__reactInternalInstance) {
                    try {
                        const props = reactRoot.__reactInternalInstance.memoizedProps;
                        if (props) {
                            products.push(JSON.stringify(props));
                        }
                    } catch(e) {}
                }
                
                return products;
            }
            """
            
            js_data = page.evaluate(js_code)
            
            for json_str in js_data:
                try:
                    data = safe_json_parse(json_str)
                    if data and isinstance(data, dict):
                        # Try to find products in various structures
                        items = (
                            data.get('products') or
                            data.get('items') or
                            data.get('results') or
                            data.get('data', {}).get('products') or
                            data.get('searchResults', {}).get('products') or
                            []
                        )
                        
                        if isinstance(items, list):
                            for item in items:
                                if isinstance(item, dict):
                                    product = self._parse_js_item(item, search_term)
                                    if product:
                                        products.append(product)
                                        
                except Exception as e:
                    logger.debug(f"Error parsing JS state: {str(e)}")
                    continue
                    
        except Exception as e:
            logger.debug(f"Error extracting from JS state: {str(e)}")
        
        return products
    
    def _parse_js_item(self, item: Dict[str, Any], search_term: str) -> Optional[Dict[str, Any]]:
        """Parse a JavaScript state item into product format."""
        try:
            title = (
                item.get('title') or 
                item.get('name') or 
                item.get('productName') or
                item.get('displayName')
            )
            
            if not title:
                return None
            
            product_id = (
                item.get('id') or
                item.get('productId') or
                item.get('sku') or
                item.get('itemId') or
                f"js_{title[:30].replace(' ', '_')}"
            )
            
            price = extract_price(
                item.get('price') or 
                item.get('currentPrice') or 
                item.get('salePrice') or
                item.get('priceValue')
            )
            
            original_price = extract_price(
                item.get('originalPrice') or 
                item.get('listPrice') or
                item.get('wasPrice')
            )
            
            brand = item.get('brand') or item.get('manufacturer')
            
            url = item.get('url') or item.get('productUrl') or item.get('link')
            if url and not url.startswith('http'):
                url = normalize_url(url, 'https://www.nordstrom.com')
            
            image_url = item.get('image') or item.get('imageUrl') or item.get('thumbnail')
            
            rating = None
            rating_val = item.get('rating') or item.get('averageRating')
            if rating_val:
                try:
                    rating = float(rating_val)
                except:
                    pass
            
            return {
                'product_id': str(product_id),
                'title': str(title)[:500],
                'brand': str(brand)[:255] if brand else None,
                'price': price,
                'original_price': original_price,
                'url': url[:1000] if url else None,
                'image_url': image_url[:1000] if image_url else None,
                'rating': rating,
                'in_stock': item.get('inStock', True)
            }
            
        except Exception as e:
            logger.debug(f"Error parsing JS item: {str(e)}")
            return None


# Data validation utilities
def validate_url(url: str) -> bool:
    """Validate URL format."""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False


def normalize_url(url: str, base_url: str = "https://www.nordstrom.com") -> str:
    """Normalize URL to absolute format."""
    if not url:
        return ""
    
    if url.startswith('http://') or url.startswith('https://'):
        return url
    
    if url.startswith('/'):
        return urljoin(base_url, url)
    
    return urljoin(base_url, '/' + url)


def extract_price(price_str: Any) -> Optional[float]:
    """Extract numeric price from various formats."""
    if price_str is None:
        return None
    
    import re
    
    # Convert to string
    price_text = str(price_str)
    
    # Remove currency symbols and extract number
    price_text = re.sub(r'[^\d.,]', '', price_text)
    price_text = price_text.replace(',', '')
    
    try:
        return float(price_text)
    except (ValueError, TypeError):
        return None


def extract_text(element, max_length: int = None) -> Optional[str]:
    """Safely extract text from BeautifulSoup element."""
    if element is None:
        return None
    
    try:
        text = element.get_text(strip=True)
        if max_length and len(text) > max_length:
            text = text[:max_length]
        return text if text else None
    except Exception:
        return None


def safe_json_parse(json_str: str) -> Optional[Dict[str, Any]]:
    """Safely parse JSON string."""
    try:
        import json
        return json.loads(json_str)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


# Batch database operations
def batch_update_objects(model_class, items: List[Dict[str, Any]], unique_fields: List[str], batch_size: int = 100):
    """
    Efficiently batch update/create objects in database.
    
    Args:
        model_class: Django model class
        items: List of dictionaries with data
        unique_fields: Fields used for uniqueness check
        batch_size: Number of items to process per transaction
    """
    created_count = 0
    updated_count = 0
    
    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        
        try:
            with transaction.atomic():
                for item_data in batch:
                    # Build filter kwargs from unique fields
                    filter_kwargs = {
                        field: item_data.get(field) 
                        for field in unique_fields 
                        if item_data.get(field) is not None
                    }
                    
                    if not filter_kwargs:
                        logger.warning(f"Skipping item with no unique fields: {item_data}")
                        continue
                    
                    obj, created = model_class.objects.update_or_create(
                        **filter_kwargs,
                        defaults=item_data
                    )
                    
                    if created:
                        created_count += 1
                    else:
                        updated_count += 1
                        
        except Exception as e:
            logger.error(f"Error in batch update: {str(e)}")
            # Continue with next batch
            continue
    
    return created_count, updated_count

