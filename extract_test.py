#!/usr/bin/env python3
"""
Targeted extraction test:
1. Load AtHome Gotemba page and extract real listing structure
2. Navigate Suumo homepage to find the real 中古一戸建て search URL
"""
import asyncio, json, sys, os
from pathlib import Path

def ensure():
    try: import playwright
    except ImportError:
        os.system(f"{sys.executable} -m pip install playwright")
        os.system(f"{sys.executable} -m playwright install chromium")
        sys.exit(0)
ensure()

from playwright.async_api import async_playwright

SCRIPT_DIR = Path(__file__).parent
OUT = SCRIPT_DIR / "extract_results.txt"
lines = []

def log(s):
    print(s)
    lines.append(str(s))

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, args=["--window-size=1280,900"])
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            locale="ja-JP",
            viewport={"width": 1280, "height": 900},
            extra_http_headers={"Accept-Language": "ja,en-US;q=0.9,en;q=0.8"},
        )
        page = await ctx.new_page()

        # ── TEST 1: AtHome Gotemba – extract real listing structure ──
        log("\n" + "="*60)
        log("TEST 1: AtHome Gotemba – extract listing structure")
        log("="*60)
        url = "https://www.athome.co.jp/kodate/chuko/shizuoka/gotemba-city/list/"
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(4)
        log(f"Title: {await page.title()}")
        log(f"Status URL: {page.url}")

        # Try to find individual listing containers
        # AtHome uses li elements for listings
        candidate_selectors = [
            "li.property-unit",
            "li[class*='property']",
            "li[class*='bukken']",
            "div[class*='property-unit']",
            "div[class*='bukken-item']",
            "article[class*='property']",
            ".bukken-item",
        ]
        log("\nSearching for listing container selectors:")
        best_sel = None
        best_count = 0
        for sel in candidate_selectors:
            items = await page.query_selector_all(sel)
            log(f"  {sel:<45} → {len(items)}")
            if 5 <= len(items) <= 50 and len(items) > best_count:
                best_sel = sel
                best_count = len(items)

        # If none found well, try to find containers with price info
        log("\nLooking for elements that contain price data (万円):")
        price_containing = await page.evaluate("""
            () => {
                const all = document.querySelectorAll('*');
                const results = [];
                for (const el of all) {
                    if (el.children.length === 0 && el.textContent.includes('万円') && el.textContent.length < 30) {
                        results.push({
                            tag: el.tagName,
                            className: el.className,
                            text: el.textContent.trim().substring(0, 50)
                        });
                        if (results.length >= 10) break;
                    }
                }
                return results;
            }
        """)
        for item in price_containing[:10]:
            log(f"  <{item['tag']} class='{item['className'][:50]}'> {item['text']}")

        # Get the HTML structure of what looks like a listing
        log("\nExtracting HTML of first candidate listing-like element:")
        first_li = await page.query_selector("li[class*='property']")
        if not first_li:
            first_li = await page.query_selector("li[class*='bukken']")
        if first_li:
            html = await first_li.inner_html()
            log(f"HTML (first 1500 chars):\n{html[:1500]}")
        else:
            log("No li[class*='property'] or li[class*='bukken'] found")

        # Try getting all links that look like individual property pages
        log("\nProperty page links (URLs with /kodate/ pattern):")
        links = await page.evaluate("""
            () => {
                const anchors = document.querySelectorAll('a[href]');
                const results = [];
                for (const a of anchors) {
                    const href = a.href;
                    if (href.includes('/kodate/') && href.includes('athome.co.jp') && !href.includes('/list/') && !href.includes('/chuko/')) {
                        const text = a.textContent.trim().substring(0, 60);
                        results.push({href, text});
                        if (results.length >= 5) break;
                    }
                }
                return results;
            }
        """)
        for l in links:
            log(f"  {l['href']}")
            log(f"    text: {l['text']}")

        # Screenshot
        ss = SCRIPT_DIR / "debug_screenshots" / "athome_gotemba_extract.png"
        await page.screenshot(path=str(ss), full_page=False)
        log(f"\nScreenshot: {ss}")

        # ── TEST 2: Suumo – navigate to find real URL ──
        log("\n" + "="*60)
        log("TEST 2: Suumo – find real 中古一戸建て search URL")
        log("="*60)
        await asyncio.sleep(5)  # Pause before next request

        await page.goto("https://suumo.jp/", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
        log(f"Suumo homepage title: {await page.title()}")

        # Find the link to 中古一戸建て
        chuko_link = await page.query_selector("a:has-text('中古一戸建て')")
        if not chuko_link:
            chuko_link = await page.query_selector("a:has-text('中古')")

        if chuko_link:
            href = await chuko_link.get_attribute("href")
            text = await chuko_link.inner_text()
            log(f"Found link: '{text}' → {href}")

        # Get all navigation links containing 中古
        log("\nAll links containing 中古:")
        all_chuko = await page.evaluate("""
            () => {
                const links = [];
                document.querySelectorAll('a').forEach(a => {
                    if (a.textContent.includes('中古') && a.href) {
                        links.push({text: a.textContent.trim().substring(0,30), href: a.href.substring(0,100)});
                    }
                });
                return links.slice(0,10);
            }
        """)
        for l in all_chuko:
            log(f"  '{l['text']}' → {l['href']}")

        # Try clicking the 中古一戸建て (used single family homes) link
        chuko_ikko = await page.query_selector("a:has-text('中古一戸建')")
        if chuko_ikko:
            log("\nClicking 中古一戸建て link...")
            await chuko_ikko.click()
            await asyncio.sleep(3)
            log(f"URL after click: {page.url}")
            log(f"Title: {await page.title()}")

            # Now try to select Shizuoka
            shizuoka = await page.query_selector("a:has-text('静岡')")
            if shizuoka:
                log("\nClicking 静岡 (Shizuoka)...")
                await shizuoka.click()
                await asyncio.sleep(3)
                log(f"URL after Shizuoka: {page.url}")
                log(f"Title: {await page.title()}")

        ss2 = SCRIPT_DIR / "debug_screenshots" / "suumo_navigate.png"
        await page.screenshot(path=str(ss2), full_page=False)
        log(f"Screenshot: {ss2}")

        await browser.close()

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    log(f"\nResults saved to: {OUT}")

if __name__ == "__main__":
    asyncio.run(main())
