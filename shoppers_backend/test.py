import asyncio
import json
import pandas as pd
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
import os

# --- SETTINGS ---
URL = "https://www.nordstrom.com/browse/women/clothing/dresses"
OUTPUT_FILE = "nordstrom_results.xlsx"
USER_DATA_DIR = "./nordstrom_user_data" # Cookies store karne ke liye

async def scrape_nordstrom():
    if not os.path.exists(USER_DATA_DIR):
        os.makedirs(USER_DATA_DIR)

    async with async_playwright() as p:
        # Persistent context use kar rahe hain taaki hum 'human' lagein
        context = await p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
            ],
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )

        page = context.pages[0] if context.pages else await context.new_page()

        print(f"🚀 Opening Nordstrom...")
        try:
            # 1. Page Load
            await page.goto(URL, wait_until="domcontentloaded", timeout=60000)
            
            # 2. Human Behavior: Random Scrolling & Waiting
            print("⏳ Mimicking human behavior...")
            await asyncio.sleep(7) # Nordstrom ko thoda waqt dein block check karne ke liye
            await page.mouse.wheel(0, 500)
            await asyncio.sleep(2)
            await page.mouse.wheel(0, 1000)

            # 3. Diagnostic: Save HTML for debugging
            content = await page.content()
            with open("debug_nordstrom.html", "w", encoding="utf-8") as f:
                f.write(content)
            print("📝 Debug HTML saved to 'debug_nordstrom.html'")

            soup = BeautifulSoup(content, 'html.parser')
            
            # 4. Check multiple potential data tags
            script_tag = (
                soup.find('script', id='initial-state') or 
                soup.find('script', id='__NEXT_DATA__')
            )

            if not script_tag:
                print("❌ Blocked: JSON data tag nahi mila. 'debug_nordstrom.html' check karein.")
                # Agar 'Access Denied' likha hai, toh proxy ki zaroorat hai.
                return

            # 5. Parse JSON
            data = json.loads(script_tag.string)
            
            # Nordstrom's nested structure varies, try both common paths
            products = (
                data.get('api', {}).get('search', {}).get('results', {}).get('products', []) or
                data.get('props', {}).get('pageProps', {}).get('results', [])
            )

            if products:
                df = pd.DataFrame([{
                    "Name": p.get('name'),
                    "Brand": p.get('brandName'),
                    "Price": p.get('price', {}).get('currentPrice'),
                    "URL": f"https://www.nordstrom.com{p.get('url')}"
                } for p in products])
                
                df.to_excel(OUTPUT_FILE, index=False)
                print(f"✨ SUCCESS! {len(products)} products saved.")
            else:
                print("⚠ JSON mila par products ki list khali hai.")

        except Exception as e:
            print(f"⚠ Error: {e}")
        finally:
            await context.close()

if __name__ == "__main__":
    asyncio.run(scrape_nordstrom())