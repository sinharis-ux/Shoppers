"""
Django management command to scrape Nordstrom products using Playwright
Saves products to NordstromProduct model in the database
"""
import asyncio
import random
import re
import hashlib
from decimal import Decimal, InvalidOperation
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from playwright.async_api import async_playwright
from api.models import NordstromProduct


# CONFIGURATION
URLS_TO_SCRAPE = [
    ("Women tops", "https://www.nordstrom.com/sr?origin=keywordsearch&keyword=women%20tops", "Women"),
    ("Women bottoms", "https://www.nordstrom.com/sr?origin=keywordsearch&keyword=women%20bottoms", "Women"),
    ("Men bottoms", "https://www.nordstrom.com/sr?origin=keywordsearch&keyword=mens%20bottoms", "Men"),
    ("Men tops", "https://www.nordstrom.com/sr?origin=keywordsearch&keyword=mens%20tops", "Men"),
    ("Men coats and jackets", "https://www.nordstrom.com/sr?origin=keywordsearch&keyword=mens%20coats%20and%20jackets", "Men"),
    ("Women coats and jackets", "https://www.nordstrom.com/sr?origin=keywordsearch&keyword=women%20coats%20and%20jackets", "Women"),
    ("Women dresses", "https://www.nordstrom.com/sr?origin=keywordsearch&keyword=dress", "Women"),
]

MAX_PAGES_TO_CRAWL = 3  # Keep this low initially to test


async def human_delay(min_seconds=2, max_seconds=5):
    """Waits for a random amount of time to mimic human behavior."""
    wait_time = random.uniform(min_seconds, max_seconds)
    print(f"   ...waiting {wait_time:.2f} seconds...")
    await asyncio.sleep(wait_time)


async def apply_stealth(page):
    """Apply stealth techniques to avoid bot detection."""
    await page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined,
        });
        
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5],
        });
        
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en'],
        });
        
        window.chrome = {
            runtime: {},
        };
        
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );
    """)


def extract_price(price_text):
    """Extract numeric price from text."""
    if not price_text or price_text == "N/A":
        return None
    
    # Remove currency symbols and extract numbers
    price_clean = re.sub(r'[^\d.]', '', price_text)
    try:
        return Decimal(price_clean)
    except (InvalidOperation, ValueError):
        return None


def extract_rating(rating_text):
    """Extract numeric rating from text."""
    if not rating_text or rating_text == "N/A":
        return None
    
    # Extract number from "Rated X out of 5" or similar
    match = re.search(r'(\d+\.?\d*)', rating_text)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


def extract_review_count(review_text):
    """Extract review count from text."""
    if not review_text or review_text == "N/A":
        return 0
    
    # Extract number from "(123)" or "123 reviews"
    match = re.search(r'(\d+)', review_text)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return 0
    return 0


def generate_product_id(url, title):
    """Generate a unique product ID from URL and title."""
    if url and url != "N/A":
        # Use URL as base for ID
        url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
        return f"nord_{url_hash}"
    elif title and title != "N/A":
        # Fallback to title hash
        title_hash = hashlib.md5(title.encode()).hexdigest()[:12]
        return f"nord_{title_hash}"
    else:
        # Last resort
        import uuid
        return f"nord_{uuid.uuid4().hex[:12]}"


async def extract_product_details(card):
    """Extract all product details from a product card on listing page."""
    product_data = {
        "title": "N/A",
        "brand": "N/A",
        "current_price": "N/A",
        "original_price": "N/A",
        "discount": "N/A",
        "rating": "N/A",
        "review_count": "N/A",
        "url": "N/A"
    }
    
    try:
        # 1. Title - Look for h3 or product title
        title_selectors = ["h3", "h2", "[aria-label*='Open']"]
        for selector in title_selectors:
            title_el = card.locator(selector).first
            if await title_el.count() > 0:
                title_text = (await title_el.inner_text(timeout=2000)).strip()
                if title_text and len(title_text) > 3:
                    product_data["title"] = title_text
                    break
        
        # 2. Brand - Look for brand text
        brand_selectors = ["[itemprop='brand']", "h3 + div", ".dls-ihm460"]
        for selector in brand_selectors:
            brand_el = card.locator(selector).first
            if await brand_el.count() > 0:
                brand_text = (await brand_el.inner_text(timeout=2000)).strip()
                # Filter out price-like text
                if brand_text and not any(c in brand_text for c in ['$', '₹', '%', 'off']):
                    if len(brand_text) < 50:  # Brand names are typically short
                        product_data["brand"] = brand_text
                        break
        
        # 3. Current Price
        price_selectors = [
            "span:has-text('$')",
            "span:has-text('₹')",
            "[aria-label*='Current']",
            ".dls-ihm460:has-text('$')",
            ".dls-ihm460:has-text('₹')"
        ]
        for selector in price_selectors:
            price_el = card.locator(selector).first
            if await price_el.count() > 0:
                price_text = (await price_el.inner_text(timeout=2000)).strip()
                if price_text and ('$' in price_text or '₹' in price_text):
                    # Get the visible price (not aria-label)
                    if not price_text.startswith('Current') and not price_text.startswith('Previous'):
                        product_data["current_price"] = price_text
                        break
        
        # 4. Original Price (strikethrough)
        orig_price_el = card.locator("s, [style*='line-through']").first
        if await orig_price_el.count() > 0:
            orig_text = (await orig_price_el.inner_text(timeout=2000)).strip()
            if '$' in orig_text or '₹' in orig_text:
                product_data["original_price"] = orig_text
        
        # 5. Discount
        discount_selectors = [
            "span:has-text('off')",
            "span:has-text('%')",
            "[aria-label*='off']"
        ]
        for selector in discount_selectors:
            disc_el = card.locator(selector).first
            if await disc_el.count() > 0:
                disc_text = (await disc_el.inner_text(timeout=2000)).strip()
                if 'off' in disc_text.lower() or '%' in disc_text:
                    product_data["discount"] = disc_text
                    break
        
        # 6. Rating
        rating_el = card.locator("span[aria-label*='Rated']").first
        if await rating_el.count() > 0:
            rating_aria = await rating_el.get_attribute("aria-label", timeout=2000)
            if rating_aria:
                product_data["rating"] = rating_aria.strip()
        
        # 7. Review Count - look for text in parentheses
        review_texts = await card.locator(".dls-ihm460").all()
        for review_el in review_texts:
            try:
                text = (await review_el.inner_text(timeout=1000)).strip()
                if '(' in text and ')' in text and text.count('(') == 1:
                    product_data["review_count"] = text
                    break
            except:
                continue
        
        # 8. Product URL
        link_el = card.locator("a").first
        if await link_el.count() > 0:
            href = await link_el.get_attribute("href", timeout=2000)
            if href:
                if href.startswith('http'):
                    product_data["url"] = href
                elif href.startswith('/'):
                    product_data["url"] = f"https://www.nordstrom.com{href}"
        
    except Exception as e:
        print(f"   Error extracting: {str(e)[:50]}")
    
    return product_data


async def extract_detailed_product_info(page, url, product_data):
    """Visit individual product page and extract detailed info from .xW9R2 div."""
    detailed_data = product_data.copy()
    detailed_data.update({
        "current_color": "N/A",
        "colors_available": "N/A",
        "all_colors": [],
        "fit_feedback": "N/A",
        "size_guide": "N/A",
        "people_viewing": "N/A",
        "sold_by": "N/A",
        "returns_info": "N/A",
        "images": []
    })
    
    try:
        print(f"      → Visiting product page...")
        await page.goto(url, timeout=30000, wait_until="domcontentloaded")
        await human_delay(1, 2)
        
        # Target the .xW9R2 div
        main_div = page.locator(".xW9R2").first
        if await main_div.count() == 0:
            print(f"      ⚠ .xW9R2 div not found, using basic data")
            return detailed_data
        
        # Title from h1
        title_el = main_div.locator("h1.dls-10bl3hy").first
        if await title_el.count() > 0:
            detailed_data["title"] = (await title_el.inner_text(timeout=2000)).strip()
        
        # Brand from .NzMku.dls-5erg28
        brand_el = main_div.locator(".NzMku.dls-5erg28").first
        if await brand_el.count() > 0:
            detailed_data["brand"] = (await brand_el.inner_text(timeout=2000)).strip()
        
        # Rating from .dOblV
        rating_el = main_div.locator(".dOblV span[aria-label*='Rated']").first
        if await rating_el.count() > 0:
            rating_aria = await rating_el.get_attribute("aria-label", timeout=2000)
            if rating_aria:
                detailed_data["rating"] = rating_aria.strip()
        
        # Review count
        review_el = main_div.locator("[itemprop='reviewCount']").first
        if await review_el.count() > 0:
            detailed_data["review_count"] = (await review_el.inner_text(timeout=2000)).strip()
        
        # Current Price from .qHz0a.BkySr.EhCiu
        price_el = main_div.locator(".qHz0a.BkySr.EhCiu").first
        if await price_el.count() > 0:
            detailed_data["current_price"] = (await price_el.inner_text(timeout=2000)).strip()
        
        # Original Price from .fj69a.EhCiu
        orig_el = main_div.locator(".fj69a.EhCiu").first
        if await orig_el.count() > 0:
            detailed_data["original_price"] = (await orig_el.inner_text(timeout=2000)).strip()
        
        # Discount from .R5iiX
        disc_el = main_div.locator(".R5iiX span").first
        if await disc_el.count() > 0:
            detailed_data["discount"] = (await disc_el.inner_text(timeout=2000)).strip()
        
        # Current Color from .LocmU
        color_el = main_div.locator(".LocmU").first
        if await color_el.count() > 0:
            color_text = await color_el.inner_text(timeout=2000)
            if "Color:" in color_text:
                detailed_data["current_color"] = color_text.replace("Color:", "").strip()
        
        # All Colors from color swatches
        color_swatches = main_div.locator("li[id*='color-swatch-item']")
        color_count = await color_swatches.count()
        if color_count > 0:
            detailed_data["colors_available"] = str(color_count)
            
            all_colors = []
            for i in range(color_count):
                try:
                    img = color_swatches.nth(i).locator("img").first
                    if await img.count() > 0:
                        title = await img.get_attribute("title", timeout=1000)
                        if title:
                            clean = title.replace("selected ", "").strip()
                            all_colors.append(clean)
                except:
                    continue
            
            if all_colors:
                detailed_data["all_colors"] = all_colors
        
        # Fit Feedback from .cNI4i.eT_Tq
        fit_el = main_div.locator(".cNI4i.eT_Tq").first
        if await fit_el.count() > 0:
            detailed_data["fit_feedback"] = (await fit_el.inner_text(timeout=2000)).strip()
        
        # Size Guide
        size_guide_el = main_div.locator("button:has-text('Size guide')").first
        if await size_guide_el.count() > 0:
            detailed_data["size_guide"] = "Available"
        
        # People Viewing from #active-viewer
        viewing_el = main_div.locator("#active-viewer").first
        if await viewing_el.count() > 0:
            detailed_data["people_viewing"] = (await viewing_el.inner_text(timeout=2000)).strip()
        
        # Sold By from .sRCP7
        seller_el = main_div.locator(".sRCP7").first
        if await seller_el.count() > 0:
            detailed_data["sold_by"] = (await seller_el.inner_text(timeout=2000)).strip()
        
        # Returns Info
        returns_el = main_div.locator(".dls-ihm460:has-text('Free returns')").first
        if await returns_el.count() > 0:
            detailed_data["returns_info"] = (await returns_el.inner_text(timeout=2000)).strip()
        
        # Product Images from .PegOI div
        image_container = page.locator(".PegOI").first
        if await image_container.count() > 0:
            image_urls = []
            
            # Get all image elements inside the PegOI div
            images = image_container.locator("img")
            image_count = await images.count()
            
            for i in range(image_count):
                try:
                    img = images.nth(i)
                    # Try to get src or data-src attribute
                    img_url = await img.get_attribute("src", timeout=1000)
                    if not img_url:
                        img_url = await img.get_attribute("data-src", timeout=1000)
                    
                    if img_url and img_url.startswith('http'):
                        # Clean URL - remove size parameters if needed for full size
                        image_urls.append(img_url)
                except:
                    continue
            
            if image_urls:
                detailed_data["images"] = image_urls
                print(f"      ✓ Found {len(image_urls)} images")
        
    except Exception as e:
        print(f"      ⚠ Error on product page: {str(e)[:50]}")
    
    return detailed_data


def save_product_to_db(product_data, category_name, gender):
    """Save or update product in database."""
    try:
        # Generate product ID
        product_id = generate_product_id(product_data.get("url"), product_data.get("title"))
        
        # Extract and clean data
        title = product_data.get("title", "Unknown Product")
        if title == "N/A" or not title:
            return None, False
        
        brand = product_data.get("brand", None)
        if brand == "N/A" or not brand:
            brand = None
        
        # Extract prices
        price = extract_price(product_data.get("current_price"))
        original_price = extract_price(product_data.get("original_price"))
        
        # Extract rating and reviews
        rating = extract_rating(product_data.get("rating"))
        review_count = extract_review_count(product_data.get("review_count"))
        
        # Get image URL (first image if multiple)
        images = product_data.get("images", [])
        image_url = images[0] if images else None
        
        # Get colors
        all_colors = product_data.get("all_colors", [])
        if isinstance(all_colors, str):
            # If it's a string, try to parse it
            all_colors = [c.strip() for c in all_colors.split(",") if c.strip()]
        
        # Prepare additional data
        additional_data = {
            "discount": product_data.get("discount", "N/A"),
            "current_color": product_data.get("current_color", "N/A"),
            "colors_available": product_data.get("colors_available", "N/A"),
            "fit_feedback": product_data.get("fit_feedback", "N/A"),
            "size_guide": product_data.get("size_guide", "N/A"),
            "people_viewing": product_data.get("people_viewing", "N/A"),
            "sold_by": product_data.get("sold_by", "N/A"),
            "returns_info": product_data.get("returns_info", "N/A"),
            "all_images": images,
            "scraped_category": category_name,
            "gender": gender
        }
        
        # Determine subcategory from category name
        subcategory = None
        if "tops" in category_name.lower():
            subcategory = "Tops"
        elif "bottoms" in category_name.lower():
            subcategory = "Bottoms"
        elif "dresses" in category_name.lower() or "dress" in category_name.lower():
            subcategory = "Dresses"
        elif "coats" in category_name.lower() or "jackets" in category_name.lower():
            subcategory = "Outerwear"
        
        # Create or update product
        product, created = NordstromProduct.objects.update_or_create(
            product_id=product_id,
            defaults={
                'title': title[:500],
                'brand': brand[:255] if brand else None,
                'price': price,
                'original_price': original_price,
                'currency': 'USD',
                'url': product_data.get("url", None),
                'image_url': image_url[:1000] if image_url else None,
                'description': None,
                'category': f"{gender} {subcategory or category_name}"[:255],
                'subcategory': subcategory[:255] if subcategory else None,
                'sizes': [],
                'colors': all_colors,
                'in_stock': True,
                'rating': rating,
                'review_count': review_count,
                'additional_data': additional_data
            }
        )
        
        return product, created
        
    except Exception as e:
        print(f"   ⚠ Error saving product to DB: {str(e)[:50]}")
        return None, False


async def run(category_name, url, gender):
    """Run scraping for a single category."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, 
            slow_mo=100,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized",
                "--disable-dev-shm-usage",
                "--no-sandbox"
            ]
        )
        
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="en-US"
        )
        
        page = await context.new_page()
        await apply_stealth(page)
        print(f"\n{'='*60}")
        print(f"SCRAPING: {category_name}")
        print(f"{'='*60}")
        print(f"Opening {url}...")
        try:
            await page.goto(url, timeout=60000, wait_until="domcontentloaded")
        except Exception as e:
            print(f"Error loading page: {e}")
            await browser.close()
            return 0, 0
        
        await human_delay(4, 8)
        await page.keyboard.press("Escape")
        await human_delay(1, 2)
        
        created_count = 0
        updated_count = 0
        
        for current_page in range(1, MAX_PAGES_TO_CRAWL + 1):
            print(f"\n{'='*60}")
            print(f"--- PAGE {current_page} ---")
            print(f"{'='*60}")
            
            # Scroll to load all products
            previous_height = 0
            for scroll_attempt in range(15):
                await page.mouse.wheel(0, 800)
                await human_delay(1, 2)
                
                current_height = await page.evaluate("document.body.scrollHeight")
                if current_height == previous_height:
                    print(f"   ✓ Reached bottom after {scroll_attempt + 1} scrolls")
                    break
                previous_height = current_height
            await asyncio.sleep(2)
            
            # Find product cards
            product_cards = []
            card_selectors = ["article", ".product-module", "[data-comp='ProductCard']"]
            
            for selector in card_selectors:
                product_cards = await page.locator(selector).all()
                if len(product_cards) > 0:
                    print(f"   Found {len(product_cards)} products using selector: {selector}")
                    break
            
            if len(product_cards) == 0:
                print("   ✗ No product cards found")
                continue
            
            print(f"   Extracting product information...")
            for idx, card in enumerate(product_cards, 1):
                basic_data = await extract_product_details(card)
                
                if basic_data["title"] != "N/A" and basic_data["url"] != "N/A":
                    # Visit product page for detailed info
                    detailed_data = await extract_detailed_product_info(page, basic_data["url"], basic_data)
                    
                    # Save to database
                    product, created = save_product_to_db(detailed_data, category_name, gender)
                    if product:
                        if created:
                            created_count += 1
                            print(f"   [{created_count + updated_count}] ✓ CREATED: {detailed_data['title'][:35]}... | {detailed_data.get('current_price', 'N/A')}")
                        else:
                            updated_count += 1
                            print(f"   [{created_count + updated_count}] ↻ UPDATED: {detailed_data['title'][:35]}... | {detailed_data.get('current_price', 'N/A')}")
                    
                    # Go back to listing page
                    await page.goto(url if current_page == 1 else page.url, wait_until="domcontentloaded")
                    await human_delay(2, 3)
                    
                    # Re-scroll to position
                    for _ in range(scroll_attempt):
                        await page.mouse.wheel(0, 800)
                        await asyncio.sleep(0.5)
            
            print(f"\n   📊 Total: {created_count} created, {updated_count} updated")
            
            # Pagination
            if current_page < MAX_PAGES_TO_CRAWL:
                next_selectors = ["a:has-text('Next')", "button:has-text('Next')", "[aria-label*='Next']"]
                
                for selector in next_selectors:
                    next_button = page.locator(selector).last
                    if await next_button.count() > 0:
                        try:
                            if await next_button.is_visible(timeout=2000):
                                print(f"\n   → Clicking Next...")
                                await next_button.click()
                                await human_delay(5, 10)
                                break
                        except:
                            continue
                else:
                    print("\n   ✗ No Next button found")
                    break
        
        await human_delay(2, 3)
        await browser.close()
        
        return created_count, updated_count


class Command(BaseCommand):
    help = 'Scrape Nordstrom products using Playwright and save to database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--max-pages',
            type=int,
            default=3,
            help='Maximum number of pages to crawl per category (default: 3)',
        )
        parser.add_argument(
            '--category',
            type=str,
            help='Scrape only a specific category (e.g., "Women tops")',
        )

    def handle(self, *args, **options):
        global MAX_PAGES_TO_CRAWL
        MAX_PAGES_TO_CRAWL = options.get('max_pages', 3)
        
        category_filter = options.get('category')
        
        print("\n" + "="*60)
        print("NORDSTROM MULTI-CATEGORY SCRAPER")
        print(f"Total categories to scrape: {len(URLS_TO_SCRAPE)}")
        print(f"Max pages per category: {MAX_PAGES_TO_CRAWL}")
        print("="*60)
        
        total_created = 0
        total_updated = 0
        
        urls_to_process = URLS_TO_SCRAPE
        if category_filter:
            urls_to_process = [u for u in URLS_TO_SCRAPE if category_filter.lower() in u[0].lower()]
            if not urls_to_process:
                self.stdout.write(self.style.ERROR(f'No category found matching: {category_filter}'))
                return
        
        for idx, (category_name, url, gender) in enumerate(urls_to_process, 1):
            print(f"\n[{idx}/{len(urls_to_process)}] Starting scrape for: {category_name}")
            try:
                created, updated = asyncio.run(run(category_name, url, gender))
                total_created += created
                total_updated += updated
                self.stdout.write(self.style.SUCCESS(f'✓ Completed {category_name}: {created} created, {updated} updated'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'❌ ERROR scraping {category_name}: {str(e)}'))
        
        print("\n" + "="*60)
        print(f"ALL SCRAPING COMPLETE!")
        print(f"Total: {total_created} created, {total_updated} updated")
        print("="*60 + "\n")
        
        self.stdout.write(self.style.SUCCESS(
            f'Successfully scraped products: {total_created} created, {total_updated} updated'
        ))


