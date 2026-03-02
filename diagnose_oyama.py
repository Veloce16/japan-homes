#!/usr/bin/env python3
"""
diagnose_oyama.py  v2
=====================
Runs EXTRACT_JS on the actual Oyama AtHome results page so we can see
exactly what the scraper sees — and why property 6987579731 isn't being
extracted.  Also diagnoses the Suumo situation for all 4 cities.

Usage:  python diagnose_oyama.py
"""

import asyncio, sys

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("playwright not installed.  Run:  pip install playwright && playwright install chromium")
    sys.exit(1)

TARGET_ID   = "6987579731"
OYAMA_URL   = "https://www.athome.co.jp/kodate/shizuoka/list/?pref=22&cities=oyama&basic=kb206,kb208&pricemax=1600"

# All Suumo URL variants for each city — we'll find which ones return 200 + results
SUUMO_URLS = [
    # Gotemba
    ("Gotemba", "https://suumo.jp/jj/chuko_ikko/ichiran/RS12AC001/?ar=050&ta=22&sc=22213"),
    ("Gotemba", "https://suumo.jp/jj/chuko_ikko/ichiran/RS12AC001/?ar=050&ta=22&sc=22213&mb=1500"),
    ("Gotemba", "https://suumo.jp/ikkodate/shizuoka/sc_gotemba/"),
    ("Gotemba", "https://suumo.jp/chuko_ikkodate/shizuoka/sc_gotemba/"),
    ("Gotemba", "https://suumo.jp/chuko/ikkodate/shizuoka/city_gotemba/"),
    ("Gotemba", "https://suumo.jp/ikkodate/chuko/shizuoka/city_gotemba/"),
    # Oyama
    ("Oyama",   "https://suumo.jp/jj/chuko_ikko/ichiran/RS12AC001/?ar=050&ta=22&sc=22429"),
    ("Oyama",   "https://suumo.jp/jj/chuko_ikko/ichiran/RS12AC001/?ar=050&ta=22&sc=22429&mb=1500"),
    ("Oyama",   "https://suumo.jp/ikkodate/shizuoka/sc_oyama/"),
    ("Oyama",   "https://suumo.jp/chuko/ikkodate/shizuoka/city_oyama/"),
    # Suzuka
    ("Suzuka",  "https://suumo.jp/jj/chuko_ikko/ichiran/RS12AC001/?ar=050&ta=24&sc=24205"),
    ("Suzuka",  "https://suumo.jp/jj/chuko_ikko/ichiran/RS12AC001/?ar=050&ta=24&sc=24205&mb=1500"),
    ("Suzuka",  "https://suumo.jp/ikkodate/mie/sc_suzuka/"),
    ("Suzuka",  "https://suumo.jp/chuko_ikkodate/mie/sc_suzuka/"),
    ("Suzuka",  "https://suumo.jp/chuko/ikkodate/mie/city_suzuka/"),
    # Tsu
    ("Tsu",     "https://suumo.jp/jj/chuko_ikko/ichiran/RS12AC001/?ar=050&ta=24&sc=24201"),
    ("Tsu",     "https://suumo.jp/jj/chuko_ikko/ichiran/RS12AC001/?ar=050&ta=24&sc=24201&mb=1500"),
    ("Tsu",     "https://suumo.jp/ikkodate/mie/sc_tsu/"),
    ("Tsu",     "https://suumo.jp/chuko_ikkodate/mie/sc_tsu/"),
    ("Tsu",     "https://suumo.jp/chuko/ikkodate/mie/city_tsu/"),
]

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
}
"""

LAZY_LOAD_JS = """
() => {
    const attrs = ['data-src','data-lazy','data-original','data-lazy-src',
                   'data-image','data-url','data-original-src','data-bg','data-echo','data-photo'];
    document.querySelectorAll('img').forEach(img => {
        for (const attr of attrs) {
            const val = img.getAttribute(attr);
            if (!val || val.length < 10) continue;
            const url = val.startsWith('//') ? 'https:' + val : val;
            if (url.startsWith('http')) { img.src = url; break; }
        }
    });
}
"""

# Exact copy of EXTRACT_JS from scraper.py
EXTRACT_JS = """
(sitePrefix) => {
    const results = [];
    const seen = new Set();
    const candidates = document.querySelectorAll('li, article, div');
    for (const el of candidates) {
        const text = el.textContent || '';
        const hasMan = text.includes('\u4e07\u5186');
        const hasRawYen = /\d{6,}\s*\u5186/.test(text);
        if (!hasMan && !hasRawYen) continue;
        if (!text.includes('\u33a1') && !text.includes('m\u00b2') && !text.includes('m2')) continue;
        if (text.length > 3000 || text.length < 40) continue;
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
                !h.includes('/ahcb/') && !h.includes('/ahki/') && !h.includes('/ahad/')) {
                propUrl = h;
                break;
            }
        }
        if (!propUrl) continue;
        const urlBase = propUrl.split('?')[0].replace(/\\/$/, '');
        if (seen.has(urlBase)) continue;
        seen.add(urlBase);
        const pmMan = text.match(/([\d,]+)\s*\u4e07\u5186/);
        const pmRaw = text.match(/\d[\d,]{4,}\s*\u5186/);
        const price = pmMan ? pmMan[0] : (pmRaw ? pmRaw[0] : '');
        const sqm = [...text.matchAll(/([\d]+\.?[\d]*)\s*(?:\u33a1|m[\u00b2\u00b2]|m2)/g)].map(m => m[0]);
        results.push({ price, sizes: sqm.slice(0,3).join(' / '), url: propUrl });
        if (results.length >= 60) break;
    }
    return results;
}
"""

# Debug JS: finds the element containing our target property ID and reports
# WHY it might be failing each EXTRACT_JS check
DEBUG_TARGET_JS = f"""
() => {{
    const TARGET = '{TARGET_ID}';
    const report = [];

    // Find every element that contains a link to the target property
    document.querySelectorAll('a[href*="' + TARGET + '"]').forEach(a => {{
        let el = a;
        // Walk up to find a meaningful container (li/article/div with price+size)
        for (let i = 0; i < 8; i++) {{
            if (!el.parentElement) break;
            el = el.parentElement;
            const text = el.textContent || '';
            const tag  = el.tagName.toLowerCase();
            if (!['li','article','div'].includes(tag)) continue;

            const hasMan    = text.includes('\\u4e07\\u5186');
            const hasSqm    = text.includes('\\u33a1') || text.includes('m\\u00b2') || text.includes('m2');
            const textLen   = text.length;
            const elClass   = (el.className || '').toLowerCase();
            const isAd      = elClass.includes('ad') || elClass.includes('pr-') ||
                              elClass.includes('sponsor') || elClass.includes('premium') ||
                              text.includes('\\u30b9\\u30dd\\u30f3\\u30b5\\u30fc') ||
                              text.includes('\\u5e83\\u544a');

            // Check URL filter
            let propUrl = '';
            el.querySelectorAll('a[href]').forEach(link => {{
                const h = link.href || '';
                if (!propUrl && h.includes('athome.co.jp') && h.length > 35 &&
                    !h.includes('/list/') && !h.includes('/search/') &&
                    !h.includes('/chuko/') && !h.includes('/ichiran/') &&
                    !h.includes('/ahcb/') && !h.includes('/ahki/') && !h.includes('/ahad/')) {{
                    propUrl = h;
                }}
            }});

            report.push({{
                tag, class: el.className.slice(0,60), textLen,
                hasMan, hasSqm, isAd,
                textLenOk: textLen >= 40 && textLen <= 3000,
                propUrl: propUrl.slice(0,80) || '(none — blocked by URL filter)',
                passesAll: hasMan && hasSqm && !isAd && textLen >= 40 && textLen <= 3000 && propUrl !== '',
                textSnippet: text.slice(0,200).replace(/\\s+/g,' ')
            }});
            if (hasMan && hasSqm) break;  // found the relevant container
        }}
    }});

    return report.slice(0, 5);  // top 5 containers
}}
"""

BROWSER_ARGS = [
    "--no-sandbox",
    "--disable-blink-features=AutomationControlled",
    "--disable-features=Translate",
    "--lang=ja-JP",
    "--window-size=1280,900",
]

async def make_ctx(browser):
    return await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        locale="ja-JP",
        viewport={"width": 1280, "height": 900},
        extra_http_headers={"Accept-Language": "ja-JP,ja;q=0.9"},
    )

async def main():
    async with async_playwright() as pw:

        # ══════════════════════════════════════════════════════════
        # PART 1 — AtHome Oyama: run EXTRACT_JS + debug target
        # ══════════════════════════════════════════════════════════
        print("=" * 65)
        print("PART 1: AtHome Oyama — EXTRACT_JS simulation")
        print(f"URL: {OYAMA_URL}")
        print("=" * 65)

        browser = await pw.chromium.launch(headless=True, args=BROWSER_ARGS)
        ctx  = await make_ctx(browser)
        page = await ctx.new_page()
        await page.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")

        resp   = await page.goto(OYAMA_URL, wait_until="domcontentloaded", timeout=35000)
        await asyncio.sleep(5)
        status = resp.status if resp else 0
        title  = await page.title()
        print(f"  Status : {status}")
        print(f"  Title  : {title}")

        await page.evaluate(GENTLE_SCROLL_JS)
        await asyncio.sleep(2)
        await page.evaluate(LAZY_LOAD_JS)
        await asyncio.sleep(1)

        # How many property ID links are on the page total?
        total_ids = await page.evaluate("""
            () => {
                const s = new Set();
                document.querySelectorAll('a[href]').forEach(a => {
                    const m = (a.href||'').match(/\/kodate\/(\d{10,})/);
                    if (m) s.add(m[1]);
                });
                return [...s];
            }
        """)
        has_target = TARGET_ID in total_ids
        print(f"\n  Total property IDs on page : {len(total_ids)}")
        print(f"  Target {TARGET_ID} on page: {has_target}")
        if total_ids:
            print(f"  Sample IDs: {total_ids[:5]}")

        # Run EXTRACT_JS — what does the scraper actually extract?
        extracted = await page.evaluate(EXTRACT_JS, "athome.co.jp")
        print(f"\n  EXTRACT_JS extracted       : {len(extracted)} candidates")
        target_extracted = any(TARGET_ID in r.get("url","") for r in extracted)
        print(f"  Target in extracted        : {target_extracted}")
        if extracted:
            print(f"\n  All extracted candidates:")
            for r in extracted:
                print(f"    price={r['price'][:20]:<22} sizes={r['sizes'][:30]:<32} url=...{r['url'][-30:]}")

        # If target is on page but NOT extracted, debug why
        if has_target and not target_extracted:
            print(f"\n  ★ TARGET IS ON PAGE BUT NOT EXTRACTED — running debug...")
            debug = await page.evaluate(DEBUG_TARGET_JS)
            if debug:
                for i, d in enumerate(debug):
                    print(f"\n  Container #{i+1}: <{d['tag']} class='{d['class']}'>")
                    print(f"    textLen={d['textLen']}  hasMan={d['hasMan']}  hasSqm={d['hasSqm']}")
                    print(f"    isAd={d['isAd']}  textLenOk={d['textLenOk']}")
                    print(f"    propUrl={d['propUrl']}")
                    print(f"    passesAll={d['passesAll']}")
                    print(f"    text: {d['textSnippet'][:180]}")
            else:
                print("  (no containers found containing target link)")

        await browser.close()

        # ══════════════════════════════════════════════════════════
        # PART 2 — Suumo: check all 4 city URLs
        # ══════════════════════════════════════════════════════════
        print("\n" + "=" * 65)
        print("PART 2: Suumo — all 4 cities")
        print("=" * 65)

        for city, url in SUUMO_URLS:
            browser = await pw.chromium.launch(headless=True, args=BROWSER_ARGS)
            ctx  = await make_ctx(browser)
            page = await ctx.new_page()
            await page.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
            try:
                resp   = await page.goto(url, wait_until="domcontentloaded", timeout=25000)
                await asyncio.sleep(4)
                status = resp.status if resp else 0
                title  = await page.title()
                await page.evaluate(GENTLE_SCROLL_JS)
                await asyncio.sleep(1.5)
                await page.evaluate(LAZY_LOAD_JS)
                await asyncio.sleep(0.5)
                extracted = await page.evaluate(EXTRACT_JS, "suumo.jp")
                print(f"\n  [{city}] {url}")
                print(f"    Status={status}  Title={title[:55]}")
                print(f"    EXTRACT_JS found: {len(extracted)} candidates")
                if extracted:
                    for r in extracted[:3]:
                        print(f"      price={r['price'][:20]:<22} sizes={r['sizes'][:25]:<27} url=...{r['url'][-25:]}")
            except Exception as e:
                print(f"\n  [{city}]  ERROR: {e}")
            finally:
                await browser.close()
            await asyncio.sleep(3)

        print("\n" + "=" * 65)
        print("DONE — paste the full output above.")
        print("=" * 65)

asyncio.run(main())
