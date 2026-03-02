#!/usr/bin/env python3
"""
diagnose_oyama_url.py
=====================
Tests several AtHome URL variants for Oyama to find which one shows
USED homes (中古) under 1500万 — specifically property 6987579731.

The current URL (no basic filter) is returning new construction at
2000-7000万 and ignoring pricemax entirely.

Usage:  python diagnose_oyama_url.py
"""

import asyncio, re, sys

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("playwright not installed.")
    sys.exit(1)

TARGET_ID = "6987579731"

# URL variants to test — ordered from most to least specific
OYAMA_VARIANTS = [
    ("4codes_no_q", "https://www.athome.co.jp/kodate/shizuoka/list/?pref=22&cities=oyama&basic=kb206,kb208,kt118,kf012&pricemax=1600"),
    ("used_only_3codes", "https://www.athome.co.jp/kodate/shizuoka/list/?pref=22&cities=oyama&basic=kb206,kt118,kf012&pricemax=1600"),
    ("used_only_minimal", "https://www.athome.co.jp/kodate/shizuoka/list/?pref=22&cities=oyama&basic=kb206&pricemax=1600"),
    ("chuko_path",  "https://www.athome.co.jp/chuko/kodate/shizuoka/oyama/list/?pricemax=1600"),
    ("chuko_path2", "https://www.athome.co.jp/kodate/chuko/shizuoka/list/?pref=22&cities=oyama&pricemax=1600"),
    ("current_broken", "https://www.athome.co.jp/kodate/shizuoka/list/?pref=22&cities=oyama&pricemax=1500"),
]

FIND_JS = f"""
() => {{
    const targetId = '{TARGET_ID}';
    const propLinks = Array.from(document.querySelectorAll('a[href]'))
        .map(a => a.href)
        .filter(h => h.includes('athome.co.jp/kodate/') && /kodate\\/[0-9]{{7,}}/.test(h));
    const unique = [...new Set(propLinks.map(h => h.split('?')[0]))];
    const targetFound = unique.some(u => u.includes(targetId));

    // Sample prices from the page text
    const priceMatches = [...(document.body.innerText.matchAll(/([\d,]{{3,}})万円/g))]
        .map(m => parseInt(m[1].replace(/,/g, '')))
        .filter(p => p > 0)
        .slice(0, 10);

    return {{
        totalPropLinks: unique.length,
        targetFound: targetFound,
        samplePrices: priceMatches,
        sampleUrls: unique.slice(0, 3),
    }};
}}
"""

GENTLE_SCROLL_JS = """
async () => {
    const maxY = Math.floor(document.body.scrollHeight * 0.6);
    const step = Math.floor(window.innerHeight * 0.8);
    let pos = 0;
    while (pos < maxY) {
        pos = Math.min(pos + step, maxY);
        window.scrollTo(0, pos);
        await new Promise(r => setTimeout(r, 300));
    }
}
"""

async def test_url(page, label, url):
    print(f"\n  [{label}]")
    print(f"  URL: {url}")
    try:
        resp = await page.goto(url, wait_until="domcontentloaded", timeout=25000)
        await asyncio.sleep(4)
        status = resp.status if resp else 0
        title = await page.title()
        final = page.url
        print(f"  Status: {status}  Final: {final[:80]}")
        print(f"  Title: {title[:70]}")

        if status == 404 or "見つかりません" in title:
            print(f"  → 404 / No results page")
            return False

        await page.evaluate(GENTLE_SCROLL_JS)
        await asyncio.sleep(2)

        info = await page.evaluate(FIND_JS)
        prices = info['samplePrices']
        min_p = min(prices) if prices else 0
        max_p = max(prices) if prices else 0
        print(f"  Property links: {info['totalPropLinks']}  |  Prices: {min_p}万~{max_p}万  |  Target found: {info['targetFound']}")
        print(f"  Sample URLs: {info['sampleUrls']}")

        # Classify: new construction (新築) has prices 2000万+, used homes are lower
        is_new = title and ("新築" in title or "建売" in title)
        is_used = title and "中古" in title
        classification = "NEW CONSTRUCTION ❌" if is_new else ("USED HOMES ✅" if is_used else "MIXED/UNKNOWN")
        print(f"  Classification: {classification}")

        if info['targetFound']:
            print(f"  ★★★ TARGET PROPERTY FOUND! ★★★")
            return True
        return False

    except Exception as e:
        print(f"  ERROR: {e}")
        return False

async def main():
    print(f"\n{'='*65}")
    print(f"  Oyama AtHome URL Finder")
    print(f"  Looking for property: {TARGET_ID} (1500万, used, 1967)")
    print(f"{'='*65}")

    winner = None

    async with async_playwright() as pw:
        for label, url in OYAMA_VARIANTS:
            browser = await pw.chromium.launch(
                headless=True,
                args=["--no-sandbox","--disable-blink-features=AutomationControlled","--lang=ja-JP"]
            )
            ctx = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                locale="ja-JP",
                viewport={"width": 1280, "height": 900},
            )
            page = await ctx.new_page()
            await page.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")

            found = await test_url(page, label, url)
            await browser.close()

            if found:
                winner = (label, url)
                break  # Stop as soon as we find it

            await asyncio.sleep(5)

    print(f"\n{'='*65}")
    if winner:
        print(f"  ✅ WINNER: {winner[0]}")
        print(f"  URL: {winner[1]}")
        print(f"\n  Update scraper.py Oyama athome_url to this URL!")
    else:
        print(f"  ❌ Property {TARGET_ID} not found in any URL variant.")
        print(f"  The property may have been sold or temporarily unlisted.")
        print(f"  Check the price/size classification above to find the")
        print(f"  correct URL for used homes — look for 'USED HOMES ✅' label.")
    print(f"{'='*65}\n")

asyncio.run(main())
