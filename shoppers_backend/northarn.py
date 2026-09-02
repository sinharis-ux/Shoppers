import asyncio
import random
import os
from playwright.async_api import async_playwright
import pandas as pd

# CONFIGURATION
URL = "https://www.nordstrom.com/browse/women/clothing/dresses?breadcrumb=Home%2FWomen%2FClothing%2FDresses&origin=topnav"
OUTPUT_FILE = "nordstrom_dresses.xlsx"
MAX_PAGES_TO_CRAWL = 3  # Keep this low initially to test
COOKIES_FILE = "nordstrom_cookies.json"  # Persist session

# Realistic user agents
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]

async def human_delay(min_seconds=3, max_seconds=8):
    """Waits for a random amount of time to mimic human behavior."""
    wait_time = random.uniform(min_seconds, max_seconds)
    print(f"   ...waiting {wait_time:.2f} seconds...")
    await asyncio.sleep(wait_time)

async def random_mouse_movement(page):
    """Simulate random mouse movements like a real user."""
    try:
        for _ in range(random.randint(2, 5)):
            x = random.randint(100, 800)
            y = random.randint(100, 600)
            await page.mouse.move(x, y, steps=random.randint(10, 25))
            await asyncio.sleep(random.uniform(0.1, 0.3))
    except:
        pass

async def check_for_block(page):
    """Check if we hit a block/captcha page."""
    try:
        content = await page.content()
        block_indicators = [
            "unusual activity",
            "automated traffic",
            "Access Denied",
            "captcha",
            "verify you are human",
            "Please verify",
            "robot"
        ]
        for indicator in block_indicators:
            if indicator.lower() in content.lower():
                return True
        return False
    except:
        return False

async def apply_stealth(page):
    """Apply comprehensive stealth techniques to avoid bot detection."""
    await page.add_init_script("""
        // Overwrite webdriver
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined,
        });
        
        // Overwrite plugins length
        Object.defineProperty(navigator, 'plugins', {
            get: () => {
                const plugins = [
                    { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
                    { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                    { name: 'Native Client', filename: 'internal-nacl-plugin' },
                ];
                plugins.length = 3;
                return plugins;
            },
        });
        
        // Overwrite languages
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en'],
        });
        
        // Add chrome object
        window.chrome = {
            runtime: {},
            loadTimes: function() {},
            csi: function() {},
            app: {},
        };
        
        // Overwrite permissions
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );
        
        // Override hardware concurrency
        Object.defineProperty(navigator, 'hardwareConcurrency', {
            get: () => 8,
        });
        
        // Override device memory
        Object.defineProperty(navigator, 'deviceMemory', {
            get: () => 8,
        });
        
        // Override platform to match user agent
        Object.defineProperty(navigator, 'platform', {
            get: () => 'Win32',
        });
        
        // Prevent iframe detection
        Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', {
            get: function() {
                return window;
            }
        });
        
        // Spoof WebGL vendor/renderer
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
            if (parameter === 37445) {
                return 'Intel Inc.';
            }
            if (parameter === 37446) {
                return 'Intel Iris OpenGL Engine';
            }
            return getParameter.apply(this, arguments);
        };
    """)

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
        "all_colors": "N/A",
        "fit_feedback": "N/A",
        "size_guide": "N/A",
        "people_viewing": "N/A",
        "sold_by": "N/A",
        "returns_info": "N/A",
        "images": "N/A"
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
                detailed_data["all_colors"] = ", ".join(all_colors)
        
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
                detailed_data["images"] = " | ".join(image_urls)
                print(f"      ✓ Found {len(image_urls)} images")
        
    except Exception as e:
        print(f"      ⚠ Error on product page: {str(e)[:50]}")
    
    return detailed_data

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False, 
            slow_mo=random.randint(50, 150),
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-infobars",
                "--disable-extensions",
                "--disable-gpu",
                "--lang=en-US,en"
            ]
        )
        
        # Load cookies if they exist
        context_options = {
            "user_agent": random.choice(USER_AGENTS),
            "viewport": {"width": 1920, "height": 1080},
            "locale": "en-US",
            "timezone_id": "America/New_York",
            "geolocation": {"longitude": -73.935242, "latitude": 40.730610},
            "permissions": ["geolocation"],
        }
        
        if os.path.exists(COOKIES_FILE):
            print(f"📂 Loading saved session from {COOKIES_FILE}")
            context_options["storage_state"] = COOKIES_FILE
        
        context = await browser.new_context(**context_options)
        
        page = await context.new_page()
        await apply_stealth(page)

        print(f"Opening {URL}...")
        try:
            await page.goto(URL, timeout=60000, wait_until="domcontentloaded")
        except Exception as e:
            print(f"Error loading page: {e}")
            await browser.close()
            return
        
        await human_delay(5, 10)
        
        # Check if we're blocked
        if await check_for_block(page):
            print("\n" + "="*60)
            print("⚠️  BOT DETECTION TRIGGERED!")
            print("="*60)
            print("The website has detected automated access.")
            print("Please solve any CAPTCHA or verification in the browser window.")
            print("Once done, press ENTER here to continue...")
            print("="*60 + "\n")
            input()  # Wait for user to solve captcha manually
            await human_delay(2, 4)
        
        # Random mouse movements to seem human
        await random_mouse_movement(page)
        
        try:
            await page.keyboard.press("Escape")
        except:
            pass
        
        await human_delay(2, 4)
        
        # Save cookies for future runs
        await context.storage_state(path=COOKIES_FILE)
        print(f"💾 Session saved to {COOKIES_FILE}")

        all_products = []

        for current_page in range(1, MAX_PAGES_TO_CRAWL + 1):
            print(f"\n{'='*60}")
            print(f"--- SCRAPING PAGE {current_page} ---")
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
                    
                    all_products.append(detailed_data)
                    print(f"   [{len(all_products)}] {detailed_data['title'][:35]}... | {detailed_data['current_price']}")
                    
                    # Go back to listing page
                    await page.goto(URL if current_page == 1 else page.url, wait_until="domcontentloaded")
                    await human_delay(2, 3)
                    
                    # Re-scroll to position
                    for _ in range(scroll_attempt):
                        await page.mouse.wheel(0, 800)
                        await asyncio.sleep(0.5)

            print(f"\n   📊 Total products: {len(all_products)}")

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
        
        # Save to Excel
        print(f"\n{'='*60}")
        if all_products:
            df = pd.DataFrame(all_products)
            
            column_order = ["title", "brand", "current_price", "original_price", "discount", 
                          "rating", "review_count", "current_color", "colors_available", "all_colors",
                          "fit_feedback", "size_guide", "people_viewing", "sold_by", "returns_info", "images", "url"]
            
            # Only include columns that exist
            column_order = [col for col in column_order if col in df.columns]
            df = df[column_order]
            
            with pd.ExcelWriter(OUTPUT_FILE, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Nordstrom Dresses')
                worksheet = writer.sheets['Nordstrom Dresses']
                
                for idx, col in enumerate(df.columns):
                    max_length = max(df[col].astype(str).apply(len).max(), len(col)) + 2
                    max_length = min(max_length, 60 if col == 'url' else 50)
                    worksheet.column_dimensions[chr(65 + idx)].width = max_length
                
                for cell in worksheet[1]:
                    cell.font = cell.font.copy(bold=True)
            
            print(f"✅ SUCCESS! Saved {len(all_products)} items to {OUTPUT_FILE}")
            print(f"{'='*60}\n")
        else:
            print("✗ No data collected")
        
        await human_delay(2, 3)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())