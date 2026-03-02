#!/usr/bin/env python3
"""
diagnose_oyama_v3.py
====================
Targeted diagnostic: loads the Oyama AtHome page and reports exactly what
EXTRACT_JS finds for every candidate — price string, sizes string, URL — so
we can see whether property 6987579731 is being found and why it passes/fails.

Also directly searches the raw page HTML for "6987579731" so we know for
certain whether the property is on the page at all.

Usage:  python diagnose_oyama_v3.py
"""

import asyncio, re, sys

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("playwright not installed.  Run:  pip install playwright && playwright install chromium")
    sys.exit(1)

TARGET_ID = "6987579731"
OYAMA_URL = "https://www.athome.co.jp/kodate/shizuoka/list/?pref=22&cities=oyama&pricemax=1500"

# Identical to scraper.py — do NOT simplify
EXTRACT_JS = """
(sitePrefix) => {
    const results = [];
    const seen = new Set();
    const candidates = document.querySelectorAll('li, article, div');

    for (const el of candidates) {
        const text = el.textContent || '';
        const hasMan = text.includes('\u4e07\u5186');
        const hasRawYen = /[0-9]{6,}\\s*\u5186/.test(text);
        if (!hasMan && !hasRawYen) continue;
        if (text.length > 3000 || text.length < 40) continue;
        const hasSqm = text.includes('\u33a1') || text.includes('m\u00b2') || text.includes('m2');
        if (!hasSqm && text.length < 200) continue;

        const elClass = (el.className || '').toLowerCase();
        const elId    = (el.id || '').toLowerCase();
        if (elClass.includes('ad') || elClass.includes('pr-') || elClass.includes('sponsor')
            || elClass.includes('cassette--pr') || elClass.includes('premium')
            || elId.includes('ad') || elId.includes('sponsor')
            || text.includes('\u30b9\u30dd\u30f3\u30b5\u30fc')
            || text.includes('\u5e83\u544a')
        ) continue;

        const isHomes = sitePrefix.includes('homes.co.jp');
        const anchors = el.querySelectorAll('a[href]');
        let propUrl = '';
        for (const a of anchors) {
            const h = a.href || '';
            if (h.includes(sitePrefix) && h.length > 35 &&
                !h.includes('/list/') && !h.includes('/search/') &&
                (isHomes || !h.includes('/chuko/')) &&
                !h.includes('/ichiran/') &&
                !h.includes('/ahcb/')  &&
                !h.includes('/ahki/')  &&
                !h.includes('/ahad/')) {
                propUrl = h;
                break;
            }
        }
        if (!propUrl) continue;

        const urlBase = propUrl.split('?')[0].replace(/\/$/, '');
        if (seen.has(urlBase)) continue;
        seen.add(urlBase);

        const pmMan = text.match(/([\d,]+)\s*\u4e07\u5186/);
        const pmRaw = text.match(/[0-9][0-9,]{4,}\s*\u5186/);
        const price = pmMan ? pmMan[0] : (pmRaw ? pmRaw[0] : '');

        const sqm = [...text.matchAll(/([\d]+\.?[\d]*)\s*(?:\u33a1|m[\u00b2\u00b2]|m2)/g)].map(m => m[0]);

        results.push({
            price:   price,
            sizes:   sqm.slice(0, 3).join(' / '),
            url:     propUrl,
        });
        if (results.length >= 60) break;
    }
    return results;
}
"""

# Direct page search — scan ALL hrefs on the page for our target
FIND_TARGET_JS = f"""
() => {{
    const targetId = '{TARGET_ID}';
    // 1) Search all links
    const links = Array.from(document.querySelectorAll('a[href]'))
        .map(a => a.href)
        .filter(h => h.includes(targetId));

    // 2) Search raw HTML
    const inHtml = document.documentElement.innerHTML.includes(targetId);

    // 3) Count total property cards AtHome uses (look for kodate links)
    const propLinks = Array.from(document.querySelectorAll('a[href]'))
        .map(a => a.href)
        .filter(h => h.includes('athome.co.jp/kodate/') && /kodate\\/[0-9]{{7,}}/.test(h));
    const uniquePropUrls = [...new Set(propLinks.map(h => h.split('?')[0]))];

    return {{
        targetInLinks: links,
        targetInHtml:  inHtml,
        totalPropLinksOnPage: uniquePropUrls.length,
        samplePropUrls: uniquePropUrls.slice(0, 5),
    }};
}}
"""

def passes_price(price_text, max_man=1500):
    price_text = price_text.replace(",","").replace("，","").replace("\u3000","").replace(" ","")
    m = re.search(r"(\d+(?:\.\d+)?)\s*万", price_text)
    if m:
        return int(float(m.group(1))) <= max_man
    m = re.search(r"(\d{6,})\s*円", price_text)
    if m:
        return int(m.group(1)) // 10000 <= max_man
    return True  # unknown → keep

def passes_size(sizes_text, min_land=300, min_bld=100):
    if not sizes_text:
        return True
    nums = re.findall(r"([\d.]+)\s*(?:\u33a1|m[\u00b2\xb2]|m2)", sizes_text)
    if len(nums) < 2:
        return True
    vals = sorted([float(n) for n in nums[:2]], reverse=True)
    return vals[0] >= min_land and vals[1] >= min_bld

GENTLE_SCROLL_JS = """
async () => {
    const maxY = Math.floor(document.body.scrollHeight * 0.60);
    const step = Math.floor(window.innerHeight * 0.85);
    let pos = 0;
    while (pos < maxY) {
        pos = Math.min(pos + step, maxY);
        window.scrollTo(0, pos);
        await new Promise(r => setTimeout(r, 450));
    }
    return pos;
}
"""

LAZY_LOAD_JS = """
() => {
    const attrs = ['data-src','data-lazy','data-original','data-lazy-src','data-image','data-url'];
    document.querySelectorAll('img').forEach(img => {
        for (const attr of attrs) {
            const val = img.getAttribute(attr);
            if (val && val.length > 10) { img.src = val.startsWith('//') ? 'https:' + val : val; break; }
        }
    });
}
"""

async def main():
    print(f"\n{'='*60}")
    print(f"  Oyama AtHome Diagnostic v3")
    print(f"  Target: {TARGET_ID}")
    print(f"  URL: {OYAMA_URL}")
    print(f"{'='*60}\n")

    async with async_playwright() as pw:
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

        print("Loading Oyama AtHome page...")
        resp = await page.goto(OYAMA_URL, wait_until="domcontentloaded", timeout=35000)
        await asyncio.sleep(5)
        status = resp.status if resp else 0
        title = await page.title()
        print(f"Status: {status}  Title: {title[:70]}")

        print("\nScrolling to trigger lazy-loads...")
        await page.evaluate(GENTLE_SCROLL_JS)
        await asyncio.sleep(2)
        await page.evaluate(LAZY_LOAD_JS)
        await asyncio.sleep(1)

        # ── STEP 1: Direct search for target ID ──────────────────────
        print(f"\n{'─'*50}")
        print(f"STEP 1: Is property {TARGET_ID} on this page at all?")
        print(f"{'─'*50}")
        found = await page.evaluate(FIND_TARGET_JS)
        print(f"  Target in links:  {found['targetInLinks']}")
        print(f"  Target in HTML:   {found['targetInHtml']}")
        print(f"  Total property links on page: {found['totalPropLinksOnPage']}")
        print(f"  Sample property URLs:")
        for u in found['samplePropUrls']:
            print(f"    {u}")

        # ── STEP 2: Run EXTRACT_JS and show all candidates ────────────
        print(f"\n{'─'*50}")
        print(f"STEP 2: All EXTRACT_JS candidates (same logic as scraper)")
        print(f"{'─'*50}")
        raw = await page.evaluate(EXTRACT_JS, "athome.co.jp")
        print(f"  Total candidates extracted: {len(raw)}\n")

        target_found_in_candidates = False
        for i, item in enumerate(raw):
            price_pass = passes_price(item["price"])
            size_pass  = passes_size(item["sizes"])
            verdict    = "✅ PASSES" if (price_pass and size_pass) else "❌ REJECTED"
            reason     = ""
            if not price_pass: reason += " [price too high]"
            if not size_pass:  reason += " [size fails]"
            is_target  = TARGET_ID in item["url"]
            marker     = " ◄ TARGET PROPERTY!" if is_target else ""

            print(f"  [{i+1:2d}] {verdict}{reason}{marker}")
            print(f"       URL:   {item['url'][:70]}")
            print(f"       Price: {repr(item['price'])}  →  passes_price={price_pass}")
            print(f"       Sizes: {repr(item['sizes'])}  →  passes_size={size_pass}")
            print()

            if is_target:
                target_found_in_candidates = True

        # ── STEP 3: Summary ──────────────────────────────────────────
        print(f"{'─'*50}")
        print(f"SUMMARY")
        print(f"{'─'*50}")
        print(f"  Property {TARGET_ID} on page HTML: {found['targetInHtml']}")
        print(f"  Property {TARGET_ID} in EXTRACT_JS candidates: {target_found_in_candidates}")
        passing = sum(1 for item in raw if passes_price(item["price"]) and passes_size(item["sizes"]))
        print(f"  Candidates passing both filters: {passing} / {len(raw)}")

        if found['targetInHtml'] and not target_found_in_candidates:
            print(f"\n  ⚠️  PROPERTY IS ON PAGE but EXTRACT_JS is MISSING it.")
            print(f"      Need to investigate why its card isn't being extracted.")

        elif not found['targetInHtml']:
            print(f"\n  ℹ️  Property {TARGET_ID} is NOT on this page.")
            print(f"      It may have been sold, delisted, or is on a different search page.")

        elif target_found_in_candidates and passing == 0:
            print(f"\n  ⚠️  Property found in candidates but REJECTED by filters!")

        elif target_found_in_candidates and passing > 0:
            print(f"\n  ✅  Property found AND passes filters. Check listings.json!")

        await browser.close()

asyncio.run(main())
