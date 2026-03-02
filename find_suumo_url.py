#!/usr/bin/env python3
"""
Navigate Suumo step by step to find the real search URL
for used single-family homes (中古一戸建て) in Shizuoka and Mie.
"""
import asyncio, sys, os
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    os.system(f"{sys.executable} -m playwright install chromium")
    from playwright.async_api import async_playwright

SCRIPT_DIR = Path(__file__).parent
SS_DIR = SCRIPT_DIR / "debug_screenshots"
SS_DIR.mkdir(exist_ok=True)
LOG = SCRIPT_DIR / "suumo_urls.txt"
lines = []

def log(s):
    print(s)
    lines.append(str(s))

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=Translate",
                "--lang=ja",
                "--window-size=1280,900",
            ]
        )
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            locale="ja-JP",
            viewport={"width": 1280, "height": 900},
            extra_http_headers={"Accept-Language": "ja-JP,ja;q=0.9"},
        )
        page = await ctx.new_page()
        await page.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")

        # ── Step 1: go to Suumo homepage ──
        log("Step 1: Loading suumo.jp...")
        await page.goto("https://suumo.jp/", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
        log(f"  Title: {await page.title()}")
        await page.screenshot(path=str(SS_DIR / "suumo_1_home.png"))

        # ── Step 2: find all links containing 中古 ──
        log("\nStep 2: Finding links to used homes (中古)...")
        links = await page.evaluate("""
            () => {
                const results = [];
                document.querySelectorAll('a').forEach(a => {
                    const txt = a.textContent.trim();
                    if ((txt.includes('中古') || txt.includes('一戸建')) && a.href && a.href.includes('suumo')) {
                        results.push({text: txt.substring(0,40), href: a.href.substring(0,120)});
                    }
                });
                return results.slice(0, 20);
            }
        """)
        for l in links:
            log(f"  '{l['text']}' -> {l['href']}")

        # ── Step 3: try to click 中古 under 一戸建てを買う ──
        log("\nStep 3: Clicking 'Used houses for sale' section...")
        clicked = False

        # Try various selectors for the 中古一戸建て link on the homepage
        selectors_to_try = [
            "a:has-text('中古一戸建')",
            "a[href*='chuko_ikko']",
            "a[href*='chuko'][href*='ikko']",
            "a[href*='bs=040010']",
            "a[href*='JJ012']",
        ]
        for sel in selectors_to_try:
            try:
                el = await page.query_selector(sel)
                if el:
                    href = await el.get_attribute("href")
                    txt  = await el.inner_text()
                    log(f"  Found with '{sel}': '{txt}' -> {href}")
                    await el.click()
                    await asyncio.sleep(3)
                    log(f"  URL after click: {page.url}")
                    await page.screenshot(path=str(SS_DIR / "suumo_2_chuko.png"))
                    clicked = True
                    break
            except Exception as e:
                log(f"  '{sel}' failed: {e}")

        if not clicked:
            log("  Could not find a clickable 中古一戸建て link on homepage")
            log("  Trying direct URL patterns instead...")

            # Try a list of candidate URLs directly
            candidates = [
                "https://suumo.jp/jj/chuko_ikko/ichiran/RS12AC001/?ar=050&ta=22",
                "https://suumo.jp/jj/chuko_ikko/ichiran/RS12AC001/",
                "https://suumo.jp/jj/kodate/ichiran/?ar=050&bs=040010&ta=22",
                "https://suumo.jp/jj/bukken/ichiran/JJ012FJ001/?ar=050&bs=040010&ta=22",
                "https://suumo.jp/ikkodate/shizuoka/",
                "https://suumo.jp/chuko_ikkodate/shizuoka/",
            ]
            for url in candidates:
                try:
                    resp = await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                    await asyncio.sleep(2)
                    status = resp.status if resp else 0
                    title  = await page.title()
                    log(f"  {url}")
                    log(f"    status={status}  title={title[:70]}")
                    if status == 200 and ("件" in title or "一覧" in title or "物件" in title or "一戸建" in title):
                        log(f"  *** WORKING URL FOUND: {url}")
                        await page.screenshot(path=str(SS_DIR / "suumo_working.png"))
                except Exception as e:
                    log(f"    error: {e}")
            await asyncio.sleep(1)
        else:
            # ── Step 4: now on results or area-select page — log current URL ──
            current_url = page.url
            log(f"\nStep 4: Current URL = {current_url}")
            title = await page.title()
            log(f"  Title: {title}")

            # Look for Shizuoka link
            log("\nStep 5: Looking for Shizuoka (静岡) link...")
            shizuoka = await page.query_selector("a:has-text('静岡')")
            if shizuoka:
                href = await shizuoka.get_attribute("href")
                log(f"  Found Shizuoka link: {href}")
                await shizuoka.click()
                await asyncio.sleep(3)
                log(f"  URL after selecting Shizuoka: {page.url}")
                log(f"  Title: {await page.title()}")
                await page.screenshot(path=str(SS_DIR / "suumo_3_shizuoka.png"))

                # ── Step 6: look for Gotemba ──
                log("\nStep 6: Looking for Gotemba (御殿場) link...")
                gotemba = await page.query_selector("a:has-text('御殿場')")
                if gotemba:
                    href = await gotemba.get_attribute("href")
                    log(f"  Found Gotemba link: {href}")
                else:
                    log("  No direct Gotemba link on this page")
                    # Log all city links visible
                    city_links = await page.evaluate("""
                        () => document.querySelectorAll('a[href]') &&
                        [...document.querySelectorAll('a[href]')]
                        .filter(a => a.href.includes('suumo'))
                        .slice(0,10)
                        .map(a => ({text: a.textContent.trim().substring(0,30), href: a.href.substring(0,100)}))
                    """)
                    for cl in city_links:
                        log(f"    '{cl['text']}' -> {cl['href']}")

            final_url = page.url
            log(f"\n*** KEY FINDING: Search URL pattern = {final_url}")

        await browser.close()

    with open(LOG, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    log(f"\nLog saved to: {LOG}")

asyncio.run(main())
