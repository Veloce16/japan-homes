#!/usr/bin/env python3
"""
DEBUG version of Japan Real Estate Scraper
==========================================
Runs with a visible browser window and saves screenshots at each step
so you can see exactly what's happening on each site.

Run this to diagnose why listings aren't being found.
Usage: python debug_scraper.py
"""

import asyncio
import json
import os
import sys
import datetime
from pathlib import Path

def ensure_dependencies():
    try:
        import playwright
    except ImportError:
        print("Installing playwright...")
        os.system(f"{sys.executable} -m pip install playwright")
        os.system(f"{sys.executable} -m playwright install chromium")
        print("Done. Please re-run the script.")
        sys.exit(0)

ensure_dependencies()

from playwright.async_api import async_playwright

SCRIPT_DIR   = Path(__file__).parent
DEBUG_DIR    = SCRIPT_DIR / "debug_screenshots"
DEBUG_LOG    = SCRIPT_DIR / "debug_log.txt"
CONFIG_FILE  = SCRIPT_DIR / "config.json"

DEBUG_DIR.mkdir(exist_ok=True)

log_lines = []

def log(msg):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    log_lines.append(line)

async def debug_site(page, name, url, screenshot_name):
    log(f"\n{'─'*50}")
    log(f"TESTING: {name}")
    log(f"URL: {url}")
    try:
        response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)

        status = response.status if response else "unknown"
        final_url = page.url
        title = await page.title()

        log(f"HTTP status:  {status}")
        log(f"Final URL:    {final_url}")
        log(f"Page title:   {title}")

        # Screenshot
        ss_path = DEBUG_DIR / f"{screenshot_name}.png"
        await page.screenshot(path=str(ss_path), full_page=False)
        log(f"Screenshot:   {ss_path}")

        # Count elements found by various selectors
        selectors_to_try = [
            ".cassetteItem",
            "[class*='cassette']",
            "[class*='property_unit']",
            "[class*='bukken']",
            "[class*='property']",
            "[class*='listing']",
            "[class*='mod-mergeBuilding']",
            "[class*='m-cassette']",
            "li[class*='item']",
            "article",
            ".item",
        ]
        log("Selector counts:")
        for sel in selectors_to_try:
            items = await page.query_selector_all(sel)
            if items:
                log(f"  {sel:<40} → {len(items)} elements")

        # Print first 500 chars of visible text
        body_text = await page.evaluate("document.body.innerText.substring(0, 800)")
        log(f"Page text preview:\n{body_text[:800]}")

        # Check for CAPTCHA / bot detection keywords
        page_content = await page.content()
        bot_signals = ["captcha", "robot", "アクセス制限", "403", "blocked", "access denied", "アクセスが制限"]
        found_signals = [s for s in bot_signals if s.lower() in page_content.lower()]
        if found_signals:
            log(f"⚠️  BOT DETECTION SIGNALS: {found_signals}")
        else:
            log("✅ No bot detection signals found")

    except Exception as e:
        log(f"❌ ERROR: {e}")
        try:
            ss_path = DEBUG_DIR / f"{screenshot_name}_error.png"
            await page.screenshot(path=str(ss_path))
            log(f"Error screenshot: {ss_path}")
        except Exception:
            pass


async def main():
    log("=" * 55)
    log("Japan Real Estate Scraper — DEBUG MODE")
    log("=" * 55)
    log(f"Screenshots will be saved to: {DEBUG_DIR}")

    test_urls = [
        # ── SUUMO ──────────────────────────────────────────────
        (
            "Suumo — Used homes, Shizuoka (all cities)",
            "https://suumo.jp/jj/bukken/ichiran/JJ012FJ001/?ar=050&bs=030&ta=22&kb=1&mb=1500",
            "suumo_shizuoka"
        ),
        (
            "Suumo — Used homes, Mie (all cities)",
            "https://suumo.jp/jj/bukken/ichiran/JJ012FJ001/?ar=050&bs=030&ta=24&kb=1&mb=1500",
            "suumo_mie"
        ),
        # ── HOMES.CO.JP ────────────────────────────────────────
        (
            "Homes — Gotemba (URL pattern A)",
            "https://www.homes.co.jp/kodate/chuko/shizuoka/city-gotemba/list/",
            "homes_gotemba_a"
        ),
        (
            "Homes — Gotemba (URL pattern B)",
            "https://www.homes.co.jp/kodate/b-shizuoka/gotemba-city/chuko/list/",
            "homes_gotemba_b"
        ),
        (
            "Homes — Shizuoka prefecture overview",
            "https://www.homes.co.jp/kodate/chuko/shizuoka/list/",
            "homes_shizuoka"
        ),
        # ── ATHOME ─────────────────────────────────────────────
        (
            "AtHome — Gotemba (URL pattern A)",
            "https://www.athome.co.jp/kodate/chuko/shizuoka/gotemba-city/list/",
            "athome_gotemba_a"
        ),
        (
            "AtHome — Gotemba (URL pattern B)",
            "https://www.athome.co.jp/kodate/1003650035/list/",
            "athome_gotemba_b"
        ),
        (
            "AtHome — Shizuoka prefecture overview",
            "https://www.athome.co.jp/kodate/chuko/shizuoka/list/",
            "athome_shizuoka"
        ),
    ]

    async with async_playwright() as pw:
        # Run with headless=False so you can SEE the browser
        browser = await pw.chromium.launch(
            headless=False,
            args=["--window-size=1280,900"]
        )
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
            viewport={"width": 1280, "height": 900},
            extra_http_headers={"Accept-Language": "ja,en-US;q=0.9,en;q=0.8"},
        )
        page = await ctx.new_page()

        for name, url, ss_name in test_urls:
            await debug_site(page, name, url, ss_name)
            await asyncio.sleep(2)  # Polite delay between requests

        await browser.close()

    # Save log
    with open(DEBUG_LOG, "w", encoding="utf-8") as f:
        f.write("\n".join(log_lines))

    log(f"\n{'='*55}")
    log(f"Debug complete!")
    log(f"Log saved to:    {DEBUG_LOG}")
    log(f"Screenshots in:  {DEBUG_DIR}")
    log(f"\nPlease share the debug_log.txt file and any screenshots")
    log(f"that show what the browser landed on.")
    log("=" * 55)


if __name__ == "__main__":
    asyncio.run(main())
