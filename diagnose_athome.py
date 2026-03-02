#!/usr/bin/env python3
"""
AtHome Diagnostic Script
========================
Checks whether specific property IDs appear on AtHome list and map pages.
Run this on your Windows machine and copy the full output back to Claude.

Usage:  python diagnose_athome.py
"""

import asyncio, re, sys, os

# ── The two missing property IDs from user screenshots ──────────
MISSING_IDS = [
    "6987579731",   # Oyama 6DK, 15 million yen
    "6987974187",   # Tsu 9DK,   6 million yen
]

PAGES_TO_CHECK = [
    # (label,                    base_url,                                                          max_pg)
    ("Oyama — list",  "https://www.athome.co.jp/kodate/chuko/shizuoka/oyama-town/list/",           6),
    ("Oyama — map",   "https://www.athome.co.jp/kodate/chuko/shizuoka/oyama-town/map/",            1),
    ("Tsu   — list",  "https://www.athome.co.jp/kodate/chuko/mie/tsu-city/list/",                  6),
    ("Tsu   — map",   "https://www.athome.co.jp/kodate/chuko/mie/tsu-city/map/",                   1),
]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

SEP = "=" * 65


async def check_page(page, label, url, pg):
    paged_url = url if pg == 1 else f"{url}?page={pg}"
    tag = f"{label}  pg={pg}"
    print(f"\n  URL : {paged_url}")
    try:
        resp = await page.goto(paged_url, wait_until="domcontentloaded", timeout=35000)
        # Extra wait for map pages
        wait = 7 if "/map/" in url else 5
        await asyncio.sleep(wait)

        html    = await page.content()
        title   = await page.title()
        status  = resp.status if resp else 0

        print(f"  HTTP: {status}  |  Title: {title[:70]}")
        print(f"  HTML length: {len(html):,} chars")

        # ── Check for each missing property ID ─────────────────
        for pid in MISSING_IDS:
            if pid in html:
                print(f"  ✅  FOUND  {pid}  ← this property IS on this page")
            else:
                print(f"  ❌  MISSING {pid}")

        # ── List ALL property IDs found on the page ─────────────
        ids = list(dict.fromkeys(re.findall(r"/kodate/(\d{7,12})/", html)))
        print(f"  Property IDs found ({len(ids)}): {ids[:30]}")
        if len(ids) > 30:
            print(f"    ... and {len(ids)-30} more")

        # ── Check if 万円 is present (our price detector) ───────
        man_count = html.count("万円")
        sqm_count = html.count("㎡") + html.count("m²") + html.count("m2")
        print(f"  '万円' appearances: {man_count}   |   m² appearances: {sqm_count}")

        return len(ids)

    except Exception as e:
        print(f"  ⚠️  Error: {e}")
        return 0


async def main():
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("Playwright not installed. Run:  pip install playwright && playwright install chromium")
        sys.exit(1)

    print(SEP)
    print("  AtHome Diagnostic — looking for missing properties")
    print(SEP)
    print(f"  Searching for: {MISSING_IDS}")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=False,   # visible so you can watch what loads
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=Translate",
                "--lang=ja",
                "--window-size=1280,900",
            ],
        )
        ctx = await browser.new_context(
            user_agent=UA,
            locale="ja-JP",
            viewport={"width": 1280, "height": 900},
        )
        ctx.add_init_script = ctx.add_init_script  # no-op reference
        page = await ctx.new_page()
        await page.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
        )

        for (label, base_url, max_pg) in PAGES_TO_CHECK:
            print(f"\n{SEP}")
            print(f"  Checking: {label}")
            print(SEP)
            for pg in range(1, max_pg + 1):
                count = await check_page(page, label, base_url, pg)
                if count == 0 and pg > 1:
                    print(f"  → No property IDs on page {pg}, stopping.")
                    break
                if pg < max_pg:
                    await asyncio.sleep(3)

        await browser.close()

    print(f"\n{SEP}")
    print("  Diagnostic complete — copy ALL output above and send to Claude")
    print(SEP)


if __name__ == "__main__":
    asyncio.run(main())
