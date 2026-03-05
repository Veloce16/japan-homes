#!/usr/bin/env python3
"""
Japan Real Estate Scraper  v2
==============================
Scrapes AtHome, Suumo, and Yahoo Real Estate for residential
properties for sale in:
  - Gotemba (御殿場市) & Oyama (小山町), Shizuoka Prefecture
  - Suzuka (鈴鹿市) & Tsu (津市), Mie Prefecture

Filters:  Max ¥15,000,000  |  Building >= 100m2  |  Land >= 300m2
Output:   listings.html (browser dashboard)  +  email summary
"""

import asyncio, json, os, re, smtplib, datetime, sys, time
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ── auto-install ──────────────────────────────────────────────
def ensure_deps():
    try:
        import playwright
    except ImportError:
        print("Installing playwright...")
        os.system(f"{sys.executable} -m pip install playwright")
        os.system(f"{sys.executable} -m playwright install chromium")
        print("Done. Re-run the script.")
        sys.exit(0)
    try:
        import deep_translator
    except ImportError:
        print("Installing deep-translator...")
        os.system(f"{sys.executable} -m pip install deep-translator")
ensure_deps()

from playwright.async_api import async_playwright
from deep_translator import GoogleTranslator

# ── paths ─────────────────────────────────────────────────────
SCRIPT_DIR  = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "config.json"
HTML_FILE   = SCRIPT_DIR / "listings.html"
JSON_FILE   = SCRIPT_DIR / "listings.json"
DOCS_DIR    = SCRIPT_DIR / "docs"
DOCS_JSON   = DOCS_DIR   / "listings.json"   # read by GitHub Pages dashboard

# GitHub Pages dashboard URL — update repo name if different
DASHBOARD_URL = "https://veloce16.github.io/japan-homes"

DEFAULT_CONFIG = {
    "email": {
        "from_address": "veloce16@gmail.com",
        "to_address":   "veloce16@gmail.com",
        "gmail_app_password": "YOUR_GMAIL_APP_PASSWORD_HERE"
    },
    "filters": {
        "max_price_yen":    15000000,
        "min_building_sqm": 100,
        "min_land_sqm":     300
    }
}

def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, encoding="utf-8") as f:
            cfg = json.load(f)
    else:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)
        cfg = DEFAULT_CONFIG
    # Allow GitHub Actions secret to override config.json password
    env_pw = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    if env_pw:
        cfg["email"]["gmail_app_password"] = env_pw
    return cfg

# ── translation ───────────────────────────────────────────────
def translate_listings(listings):
    """Translate all Japanese title and address fields to English."""
    if not listings:
        return listings

    print("  Translating Japanese text to English...")
    translator = GoogleTranslator(source="ja", target="en")

    # Strip any stray HTML tags that occasionally leak from Lifull Homes card text
    _html_tag = re.compile(r'<[^>]+>')
    for l in listings:
        for field in ("title", "address"):
            raw = l.get(field, "") or ""
            l[field] = _html_tag.sub('', raw).strip()

    # Batch titles and addresses together to minimise API calls
    to_translate = []
    for l in listings:
        to_translate.append(l.get("title", "") or "")
        to_translate.append(l.get("address", "") or "")

    translated = []
    for text in to_translate:
        if not text or not any(ord(c) > 127 for c in text):
            # Already ASCII / empty — no need to translate
            translated.append(text)
        else:
            try:
                result = translator.translate(text)
                translated.append(result or text)
                time.sleep(0.15)   # be polite to the free API
            except Exception:
                translated.append(text)   # fall back to original

    # Put translated text back; strip trailing newline+price noise from titles
    for i, l in enumerate(listings):
        raw_title = translated[i * 2] or ""
        l["title"]   = raw_title.split("\n")[0].strip()   # drop everything after first newline
        l["address"] = translated[i * 2 + 1]

    print(f"  Translation complete ({len(listings)} listings)")
    return listings


def format_price_english(price_text):
    """Convert Japanese price to readable English.
    Handles '850万円' → '¥8,500,000  (~$57,333 USD)'
    Also handles raw yen '8500000円' and bare numbers.
    Uses same parse_price_man() logic so results are consistent with filter.
    """
    man = parse_price_man(price_text)
    if man is None:
        return price_text
    yen = man * 10000
    usd = int(yen / 150)          # approximate 150 yen per dollar
    return f"¥{yen:,}  (~${usd:,} USD)"


def format_size_english(size_text):
    """Convert '223.06㎡ / 70.06㎡' → '70 m² building / 223 m² land'.
    Source data is always land first, building second.
    We display building first so it stands out at a glance."""
    parts = re.findall(r"([\d.]+)\s*(?:\u33a1|m[\u00b2\xb2]|m2)", size_text)
    if not parts:
        return size_text
    if len(parts) >= 2:
        # Swap: put building (index 1) before land (index 0)
        ordered = [parts[1], parts[0]] + list(parts[2:])
        labels  = ["building", "land", "other"]
    else:
        ordered = parts
        labels  = ["land", "other"]
    return "  /  ".join(
        f"{float(p):.0f} m² {labels[i] if i < len(labels) else ''}"
        for i, p in enumerate(ordered)
    )


# ── search targets ────────────────────────────────────────────
TARGETS = [
    {
        "name_en":    "Gotemba, Shizuoka",
        "city_ja":    "御殿場市",
        # AtHome: pricemax=1600 (not 1500) because AtHome's filter is exclusive — pricemax=1500
        # silently drops properties priced at exactly ¥15M. Client-side passes_price() enforces the real ≤1500万 limit.
        "athome_url": "https://www.athome.co.jp/kodate/shizuoka/list/?pref=22&cities=gotemba&basic=kb208,kp299,kp103,kp001,kt118,kf012,ke001,kn001,kj001&kod=&q=1&sort=95&limit=50",
        # Suumo: old /jj/chuko_ikko/ and /chuko_ikkodate/ URLs are now 404 (Suumo restructured 2024).
        # /ikkodate/chuko/ = used detached homes (to verify); /ikkodate/ alone = new construction.
        "suumo_urls": [
            "https://suumo.jp/jj/bukken/ichiran/JJ010FJ001/?ar=050&bs=021&ta=22&jspIdFlg=patternShikugun&sc=22215&kb=1&kt=1500&tb=150&tt=9999999&hb=100&ht=9999999&ekTjCd=&ekTjNm=&tj=0&cnb=0&cn=9999999&srch_navi=1",
        ],
        # Lifull Homes: grnd_m_low=land>=300, bld_m_low=building>=100, pricemax=1500 (万円)
        "homes_url": "https://www.homes.co.jp/kodate/chuko/shizuoka/gotemba-city/list/?grnd_m_low=300&bld_m_low=100&pricemax=1600",
        "city_ja_list": ["御殿場"],
        # Yahoo: la_from=300 (land>=300m²), ba_from=100 (building>=100m²). No price max in URL —
        # passes_price() enforces <=1500万 client-side. geo=22215 = Gotemba city.
        "yahoo_url": "https://realestate.yahoo.co.jp/used/house/search/05/22/?min_st=99&ba_from=100&la_from=300&p_und_flg=0&group_with_cond=0&sort=-buy_default+p_from+-area&lc=05&pf=22&geo=22215",
    },
    {
        "name_en":    "Oyama, Shizuoka",
        "city_ja":    "小山町",
        # Oyama = Oyama Town, Sunto District (駿東郡小山町).
        # AtHome city code is "sunto_oyama" — NOT "oyama" (which doesn't exist in AtHome's system
        # and caused weeks of incorrect results). URL copied directly from AtHome map search.
        "athome_url": "https://www.athome.co.jp/kodate/shizuoka/list/?pref=22&cities=sunto_oyama&basic=kb208,kp299,kp103,kp001,kt101,kf012,ke001,kn001,kj001&q=1&pricemax=1600",
        # Suumo: Oyama Town is not listed in Suumo's city search — no Suumo URL available.
        "suumo_urls": [],
        "homes_url": "https://www.homes.co.jp/kodate/chuko/shizuoka/oyama-town/list/?grnd_m_low=300&bld_m_low=100&pricemax=1600",
        "city_ja_list": ["小山"],
        # Yahoo: geo=22344 = Oyama town (Sunto District). Same filter logic as other cities.
        "yahoo_url": "https://realestate.yahoo.co.jp/used/house/search/05/22/?min_st=99&ba_from=100&la_from=300&p_und_flg=0&group_with_cond=0&sort=-buy_default+p_from+-area&lc=05&pf=22&geo=22344",
    },
    {
        "name_en":    "Suzuka, Mie",
        "city_ja":    "鈴鹿市",
        "athome_url": "https://www.athome.co.jp/kodate/mie/list/?pref=24&cities=suzuka&basic=kb208,kp299,kp103,kp001,kt118,kf012,ke001,kn001,kj001&kod=&q=1&sort=95&limit=50",
        # Suumo: sc=24207 (Suzuka). tb=150 is Suumo's max land filter; passes_size() enforces >=300m² client-side.
        "suumo_urls": [
            "https://suumo.jp/jj/bukken/ichiran/JJ012FC001/?ar=050&bs=021&cn=9999999&cnb=0&ekTjCd=&ekTjNm=&hb=100&ht=9999999&kb=1&kt=1500&sc=24207&ta=24&tb=150&tj=0&tt=9999999&pc=50&po=0&pj=1",
        ],
        "homes_url": "https://www.homes.co.jp/kodate/chuko/mie/suzuka-city/list/?grnd_m_low=300&bld_m_low=100&pricemax=1600",
        "city_ja_list": ["鈴鹿"],
        # Yahoo: geo=24207 = Suzuka city.
        "yahoo_url": "https://realestate.yahoo.co.jp/used/house/search/05/24/?min_st=99&ba_from=100&la_from=300&p_und_flg=0&group_with_cond=0&sort=-buy_default+p_from+-area&lc=05&pf=24&geo=24207",
    },
    {
        "name_en":    "Tsu, Mie",
        "city_ja":    "津市",
        "athome_url": "https://www.athome.co.jp/kodate/mie/list/?pref=24&cities=tsu&basic=kb208,kp299,kp103,kp001,kt118,kf012,ke001,kn001,kj001&kod=&q=1&sort=95&limit=50",
        # Suumo: sc=24201 (Tsu). tb=150 is Suumo's max land filter; passes_size() enforces >=300m² client-side.
        "suumo_urls": [
            "https://suumo.jp/jj/bukken/ichiran/JJ012FC001/?ar=050&bs=021&cn=9999999&cnb=0&ekTjCd=&ekTjNm=&hb=100&ht=9999999&kb=1&kt=1500&sc=24201&ta=24&tb=150&tj=0&tt=9999999&po=0&pj=1&pc=50",
        ],
        "homes_url": "https://www.homes.co.jp/kodate/chuko/mie/tsu-city/list/?grnd_m_low=300&bld_m_low=100&pricemax=1600",
        "city_ja_list": ["津市", "津　"],
        # Yahoo: geo=24201 = Tsu city.
        "yahoo_url": "https://realestate.yahoo.co.jp/used/house/search/05/24/?min_st=99&ba_from=100&la_from=300&p_und_flg=0&group_with_cond=0&sort=-buy_default+p_from+-area&lc=05&pf=24&geo=24201",
    },
]

# ── helpers ───────────────────────────────────────────────────
def parse_price_man(text):
    """Return price in 万円 units, handling multiple formats:
      '980万円'       → 980   (most common Japanese RE format)
      '1,500万円'     → 1500
      '9,800,000円'   → 980   (raw yen, no 万 — seen on some portals)
      '9800000'       → 980   (bare number, 7+ digits assumed yen)
    Returns None if no price can be detected (caller lets listing through).
    """
    text = text.replace(",", "").replace("，", "").replace("\u3000", "").replace(" ", "")
    # 1) 万円 format — primary
    m = re.search(r"(\d+(?:\.\d+)?)\s*万", text)
    if m:
        return int(float(m.group(1)))
    # 2) Raw yen with 円 suffix (e.g. 9800000円)
    m = re.search(r"(\d{6,})\s*円", text)
    if m:
        return int(m.group(1)) // 10000
    # 3) Bare 7-digit+ number with no unit (last resort)
    m = re.search(r"\b(\d{7,})\b", text)
    if m:
        return int(m.group(1)) // 10000
    return None

def passes_price(price_text, cfg):
    max_man = cfg["filters"]["max_price_yen"] // 10000
    p = parse_price_man(price_text)
    return p is None or p <= max_man

def passes_size(size_text, cfg):
    """Return True if the largest measurement >= min_land_sqm AND second-largest >= min_building_sqm.

    Different sites put measurements in different orders, and some (e.g. Suumo) include
    THREE values on the card: building coverage area, total floor area, and land area —
    with land area LAST. Checking only the first two values would miss the land figure
    entirely and reject valid listings.

    Fix: sort ALL parsed values descending. Largest = land, second-largest = building.
    This works because land is almost always the biggest number on a Japanese property card.

    Examples:
      AtHome  2 values: [142㎡, 498㎡] → sorted [498, 142] → 498>=300 ✅ 142>=100 ✅ PASS
      Suumo   3 values: [85㎡, 120㎡, 450㎡] → sorted [450, 120, 85] → 450>=300 ✅ 120>=100 ✅ PASS
      Suumo   3 values: [85㎡, 120㎡, 250㎡] → sorted [250, 120, 85] → 250<300 ❌ FAIL (correct)

    If we can't parse it we let the listing through rather than silently drop it.
    """
    if not size_text:
        return True   # no size info — don't discard
    nums = re.findall(r"([\d.]+)\s*(?:\u33a1|m[\u00b2\xb2]|m2)", size_text)
    if len(nums) < 2:
        return True   # can't determine, keep it
    vals = sorted([float(n) for n in nums], reverse=True)  # all values, largest=land
    min_land = cfg["filters"].get("min_land_sqm", 300)
    min_bld  = cfg["filters"].get("min_building_sqm", 100)
    return vals[0] >= min_land and vals[1] >= min_bld

def browser_args():
    return [
        "--disable-blink-features=AutomationControlled",
        "--disable-features=Translate",   # stop auto-translate to English
        "--lang=ja",
        "--window-size=1280,900",
        "--no-sandbox",
        "--disable-dev-shm-usage",
    ]

async def make_context(browser):
    return await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        locale="ja-JP",
        viewport={"width": 1280, "height": 900},
        extra_http_headers={
            "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
        },
    )

# ── gentle scroll — triggers IntersectionObserver without hitting pagination ──
# Scrolls to 60 % of page height in small viewport-sized steps so AtHome's
# lazy-load callbacks fire for all visible listing cards.  We stop at 60 % so
# we never reach the "load next page" trigger at the very bottom.
GENTLE_SCROLL_JS = """
async () => {
    const maxY   = Math.floor(document.body.scrollHeight * 0.60);
    const step   = Math.floor(window.innerHeight * 0.85);
    let   pos    = 0;
    while (pos < maxY) {
        pos = Math.min(pos + step, maxY);
        window.scrollTo(0, pos);
        await new Promise(r => setTimeout(r, 450));
    }
    return pos;
}
"""

# ── lazy-attr forcer — copies data-src → src for sites that use it ────────────
# AtHome uses IntersectionObserver (handled by GENTLE_SCROLL_JS above).
# Suumo / Yahoo may use data-src attributes instead; this handles both.
LAZY_LOAD_JS = """
() => {
    const attrs = [
        'data-src','data-lazy','data-original','data-lazy-src',
        'data-image','data-url','data-original-src','data-bg',
        'data-echo','data-photo'
    ];
    let count = 0;
    document.querySelectorAll('img').forEach(img => {
        // ALWAYS prefer a lazy attribute over whatever is currently in src.
        // AtHome sets src to a small HTTP placeholder gif before lazy-loading,
        // so the old "skip if src already starts with http" check was keeping
        // the placeholder and never installing the real property photo.
        for (const attr of attrs) {
            const val = img.getAttribute(attr);
            if (!val || val.length < 10) continue;
            const url = val.startsWith('//') ? 'https:' + val : val;
            if (url.startsWith('http')) {
                img.src = url;
                img.removeAttribute('loading');   // cancel lazy="lazy" if set
                count++;
                break;
            }
        }
    });
    // Also handle <picture><source data-srcset=...> patterns
    document.querySelectorAll('source[data-srcset],source[data-src]').forEach(s => {
        const val = s.getAttribute('data-srcset') || s.getAttribute('data-src') || '';
        if (val) { s.srcset = val; }
    });
    return count;
}
"""

# ── content-based extractor ───────────────────────────────────
# Finds elements containing both a yen price AND area measurements,
# plus a link to an individual property page.
# This is resilient to class name changes on any of the sites.
EXTRACT_JS = """
(sitePrefix) => {
    const results = [];
    const seen = new Set();
    const candidates = document.querySelectorAll('li, article, div');

    for (const el of candidates) {
        const text = el.textContent || '';
        // Must have a price indicator: 万円 (standard) OR a raw yen number (6+ digits + 円)
        const hasMan = text.includes('\u4e07\u5186');                // 万円
        const hasRawYen = /[0-9]{6,}[ \t]*\u5186/.test(text);        // e.g. 9800000円
        if (!hasMan && !hasRawYen) continue;
        if (text.length > 3000 || text.length < 40) continue;
        // Size data (m²/㎡) is preferred but NOT required — older rural listings (e.g. 1967
        // builds) often omit m² from the search-result card.  passes_size() returns True
        // when sizes are unknown, so those listings still get filtered correctly downstream.
        const hasSqm = text.includes('\u33a1') || text.includes('m\u00b2') || text.includes('m2');
        // Skip ONLY if: no size AND very short text (likely a UI label, not a property card)
        if (!hasSqm && text.length < 200) continue;

        // Skip sponsored / ad elements — AtHome injects these between real listings.
        // They duplicate a nearby organic result but have tracking query params and
        // no proper thumbnail, producing the "every other blank" pattern.
        const elClass = (el.className || '').toLowerCase();
        const elId    = (el.id || '').toLowerCase();
        if (elClass.includes('ad') || elClass.includes('pr-') || elClass.includes('sponsor')
            || elClass.includes('cassette--pr') || elClass.includes('premium')
            || elId.includes('ad') || elId.includes('sponsor')
            || text.includes('\u30b9\u30dd\u30f3\u30b5\u30fc')   // スポンサー
            || text.includes('\u5e83\u544a')                       // 広告
        ) continue;

        // Must link to an individual property detail page.
        // Note: homes.co.jp property detail URLs contain /chuko/ so we cannot
        // use that as a blanket block — we skip it for homes only.
        const isHomes = sitePrefix.includes('homes.co.jp');
        const anchors = el.querySelectorAll('a[href]');
        let propUrl = '';
        for (const a of anchors) {
            const h = a.href || '';
            if (h.includes(sitePrefix) && h.length > 35 &&
                !h.includes('/list/') && !h.includes('/search/') &&
                (isHomes || !h.includes('/chuko/')) &&   // homes uses /chuko/ in detail URLs
                !h.includes('/ichiran/') &&
                !h.includes('/ahcb/')  &&   // AtHome agent-card ads (business card pages)
                !h.includes('/ahki/')  &&   // AtHome agent info pages
                !h.includes('/ahad/')) {    // AtHome ad links
                propUrl = h;
                break;
            }
        }
        if (!propUrl) continue;

        // Deduplicate by base URL (strip query-string tracking params).
        // AtHome ad slots reuse the same property path but append ?WT.srch=1&aff=…
        // so a plain propUrl comparison lets ads slip through as "new" entries.
        const urlBase = propUrl.split('?')[0].replace(/\/$/, '');
        if (seen.has(urlBase)) continue;
        seen.add(urlBase);

        // Extract price — prefer 万円 format, fall back to raw yen
        const pmMan = text.match(/([\d,]+)\s*\u4e07\u5186/);
        const pmRaw = text.match(/[0-9][0-9,]{4,}[ \t]*\u5186/);
        const price = pmMan ? pmMan[0] : (pmRaw ? pmRaw[0] : '');

        // Extract all area measurements — AtHome uses m² (m + U+00B2 superscript)
        // while Suumo/Yahoo use ㎡ (U+33A1 combined char). Catch both.
        const sqm = [...text.matchAll(/([\d]+\.?[\d]*)\s*(?:\u33a1|m[\u00b2\u00b2]|m2)/g)].map(m => m[0]);

        // Title: prefer heading or image alt
        let title = '';
        const hEl = el.querySelector('h2,h3,h4,[class*="title"],[class*="name"],[class*="bukken"]');
        if (hEl) title = hEl.textContent.trim().substring(0, 80);
        if (!title) {
            for (const img of el.querySelectorAll('img[alt]')) {
                if (img.alt && img.alt.length > 3 && img.alt.length < 100) {
                    title = img.alt; break;
                }
            }
        }

        // Address: find Japanese address patterns
        const am = text.match(/[\u90fd\u9053\u5e9c\u770c]?.{1,8}[\u5e02\u753a\u533a\u6751].{0,20}/);
        const address = am ? am[0].substring(0, 50) : '';

        // Thumbnail: first real property photo
        // Strategy: check img.src first (AtHome's IntersectionObserver sets this
        // when the element scrolls into view), then fall back to lazy data attrs.
        // Keep the badUrl filter minimal — overly broad filters ("loading", etc.)
        // were matching legitimate CDN path segments and returning empty strings.
        const lazyAttrs2 = ['data-src','data-lazy','data-original','data-lazy-src',
                            'data-image','data-url','data-original-src','data-echo',
                            'data-photo','data-bg'];
        const badUrl = u => !u || u.startsWith('data:') || u.length < 15
                         || u.includes('/icon') || u.includes('/logo')
                         || u.includes('blank.') || u.includes('noimage')
                         || u.includes('spacer.') || u.includes('.gif');
        let imgUrl = '';
        for (const img of el.querySelectorAll('img')) {
            // 1) img.src — IntersectionObserver puts the real URL here for visible items
            const src = img.src || '';
            if (!badUrl(src)) { imgUrl = src; break; }
            // 2) lazy data attributes — real URL for below-fold items
            for (const attr of lazyAttrs2) {
                const v = img.getAttribute(attr) || '';
                const url = v.startsWith('//') ? 'https:' + v : v;
                if (!badUrl(url)) { imgUrl = url; break; }
            }
            if (imgUrl) break;
            // 3) srcset attribute — Yahoo RE puts the real URL here
            const srcset = img.getAttribute('srcset') || img.srcset || '';
            if (srcset) {
                const first = srcset.split(',')[0].trim().split(' ')[0];
                const furl = first.startsWith('//') ? 'https:' + first : first;
                if (!badUrl(furl)) { imgUrl = furl; break; }
            }
        }
        // 4) <picture><source srcset/data-srcset> inside this element
        if (!imgUrl) {
            for (const s of el.querySelectorAll('source')) {
                const ss = s.srcset || s.getAttribute('data-srcset') || '';
                const first = ss.split(',')[0].trim().split(' ')[0];
                if (!badUrl(first)) { imgUrl = first; break; }
            }
        }
        // 5) CSS background-image — some sites (incl. Yahoo RE) render photos this way
        if (!imgUrl) {
            for (const child of el.querySelectorAll('[style]')) {
                const style = child.getAttribute('style') || '';
                const m = style.match(/background-image\s*:\s*url\(\s*['"]?([^'")\s]+)/i);
                if (m && !badUrl(m[1])) {
                    imgUrl = m[1].startsWith('//') ? 'https:' + m[1] : m[1];
                    break;
                }
            }
        }

        // Building year: look for 築XXXX年 (built in year) or XXXX年築
        const byFull = text.match(/築(\d{4})年|(\d{4})年築/);
        const byAge  = text.match(/築(\d{1,2})年/);
        let buildYear = '';
        if (byFull) {
            buildYear = byFull[1] || byFull[2];
        } else if (byAge) {
            buildYear = String(new Date().getFullYear() - parseInt(byAge[1]));
        }

        results.push({
            title:      title.trim() || '\u7269\u4ef6',
            price:      price,
            sizes:      sqm.slice(0, 3).join(' / '),
            address:    address,
            url:        propUrl,
            image:      imgUrl,
            build_year: buildYear,
        });
        if (results.length >= 60) break;
    }
    return results;
}
"""

# ── AtHome ────────────────────────────────────────────────────
# Paginates up to MAX_PAGES pages per city so listings buried on page 2/3
# are not missed.  AtHome uses ?page=N for additional pages.
MAX_PAGES = 5

async def scrape_athome(pw, cfg):
    listings = []
    seen_urls = set()   # global dedup across all pages for this scraper run

    for t in TARGETS:
        print(f"   AtHome -> {t['name_en']}")
        # Fresh browser context per city avoids session-based blocks
        browser = await pw.chromium.launch(headless=True, args=browser_args())
        try:
            ctx  = await make_context(browser)
            page = await ctx.new_page()
            await page.add_init_script(
                "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
            )

            # AtHome URLs: search-param style already has ?, slug style does not.
            # Pagination uses ? or & accordingly (see sep below).
            base_url = t["athome_url"]
            city_blocked = False

            for pg in range(1, MAX_PAGES + 1):
                # Use & if URL already has query params, ? otherwise
                sep = "&" if "?" in base_url else "?"
                url = base_url if pg == 1 else f"{base_url}{sep}page={pg}"
                try:
                    resp = await page.goto(url, wait_until="domcontentloaded", timeout=35000)
                    await asyncio.sleep(4)
                    status = resp.status if resp else 0
                    title  = await page.title()
                    print(f"     p{pg} status={status}  title={title[:60]}")

                    if status in (403, 405) or "\u8a8d\u8a3c" in title or "verify" in title.lower():
                        print("     Blocked - skipping city")
                        city_blocked = True
                        break

                    await page.evaluate(GENTLE_SCROLL_JS)
                    await asyncio.sleep(1.5)
                    await page.evaluate(LAZY_LOAD_JS)
                    await asyncio.sleep(0.5)

                    raw = await page.evaluate(EXTRACT_JS, "athome.co.jp")
                    print(f"     p{pg} candidates: {len(raw)}")

                    if not raw:
                        print(f"     No candidates on page {pg} — stopping")
                        break

                    new_on_page = 0
                    for item in raw:
                        url_base = item["url"].split("?")[0].rstrip("/")
                        if url_base in seen_urls:
                            continue
                        seen_urls.add(url_base)
                        new_on_page += 1
                        if not passes_price(item["price"], cfg):
                            continue
                        if not passes_size(item["sizes"], cfg):
                            continue
                        listings.append({
                            "source":      "AtHome",
                            "title":       item["title"],
                            "address":     item["address"] or t["city_ja"],
                            "price":       item["price"],
                            "size":        item["sizes"],
                            "url":         item["url"],
                            "image":       item.get("image", ""),
                            "area":        t["name_en"],
                            "build_year":  item.get("build_year", ""),
                        })

                    print(f"     p{pg} new unique: {new_on_page}")
                    # Stop when a page yields no new URLs — we've reached the end.
                    if new_on_page == 0:
                        print(f"     No new results on page {pg} — stopping pagination")
                        break

                    await asyncio.sleep(3)   # polite delay between pages

                except Exception as e:
                    print(f"     Error on page {pg}: {e}")
                    break

        finally:
            await browser.close()
        await asyncio.sleep(7)
    return listings

# ── Suumo ─────────────────────────────────────────────────────
async def scrape_suumo(pw, cfg):
    listings = []

    for t in TARGETS:
        print(f"   Suumo -> {t['name_en']}")
        browser = await pw.chromium.launch(headless=True, args=browser_args())
        try:
            ctx  = await make_context(browser)
            page = await ctx.new_page()
            await page.add_init_script(
                "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
            )
            found_url = None
            for url in t["suumo_urls"]:
                try:
                    resp = await page.goto(url, wait_until="domcontentloaded", timeout=25000)
                    await asyncio.sleep(3)
                    status = resp.status if resp else 0
                    title  = await page.title()
                    print(f"     {url[:80]}")
                    print(f"     status={status}  title={title[:65]}")
                    # Accept any 200 page that is not a clear error page
                    if status == 200 and not any(k in title.lower() for k in ["404", "not found", "\u30a8\u30e9\u30fc"]):
                        found_url = url
                        break
                except Exception as ex:
                    print(f"     error: {ex}")
                    continue

            if not found_url:
                print("     No working Suumo URL found - skipping")
                continue

            await page.evaluate(GENTLE_SCROLL_JS)
            await asyncio.sleep(1.5)
            await page.evaluate(LAZY_LOAD_JS)
            await asyncio.sleep(0.5)

            raw = await page.evaluate(EXTRACT_JS, "suumo.jp")
            print(f"     Candidates: {len(raw)}")
            # NOTE: No city keyword check for Suumo. The URL already restricts results
            # to the correct city via the sc= parameter. Suumo listing cards often show
            # abbreviated addresses (neighbourhood only, no 市 prefix), so a keyword
            # check would silently drop valid large-lot listings. sc= is sufficient.
            for item in raw:
                if not passes_price(item["price"], cfg):
                    continue
                if not passes_size(item["sizes"], cfg):
                    continue
                listings.append({
                    "source":     "Suumo",
                    "title":      item["title"],
                    "address":    item["address"] or t["city_ja"],
                    "price":      item["price"],
                    "size":       item["sizes"],
                    "url":        item["url"],
                    "image":      item.get("image", ""),
                    "area":       t["name_en"],
                    "build_year": item.get("build_year", ""),
                })
        finally:
            await browser.close()
        await asyncio.sleep(7)
    return listings

# ── Yahoo Real Estate ─────────────────────────────────────────
# URLs sourced directly from browser searches. la_from=300 and ba_from=100 filter
# at the URL level; passes_price() enforces the <=1500万 max client-side since the
# user removed the price cap from the URL to ensure all valid results appear.
# No city keyword check — geo= parameter already restricts to the correct city.
async def scrape_yahoo(pw, cfg):
    listings = []
    for t in TARGETS:
        print(f"   Yahoo RE -> {t['name_en']}")
        browser = await pw.chromium.launch(headless=True, args=browser_args())
        try:
            ctx  = await make_context(browser)
            page = await ctx.new_page()
            await page.add_init_script(
                "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
            )
            try:
                url  = t["yahoo_url"]
                resp = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(4)
                status    = resp.status if resp else 0
                title     = await page.title()
                final_url = page.url
                print(f"     {url[:80]}")
                print(f"     status={status}  title={title[:65]}")
                print(f"     final={final_url[:80]}")

                if status not in (200, 202):
                    print("     Unexpected status — skipping")
                else:
                    await page.evaluate(GENTLE_SCROLL_JS)
                    await asyncio.sleep(3)   # Yahoo is heavily JS-rendered, needs extra time
                    await page.evaluate(LAZY_LOAD_JS)
                    await asyncio.sleep(2)

                    raw = await page.evaluate(EXTRACT_JS, "realestate.yahoo.co.jp")
                    print(f"     Candidates: {len(raw)}")
                    for item in raw:
                        if not passes_price(item["price"], cfg):
                            continue
                        if not passes_size(item["sizes"], cfg):
                            continue
                        listings.append({
                            "source":     "Yahoo RE",
                            "title":      item["title"],
                            "address":    item["address"] or t["city_ja"],
                            "price":      item["price"],
                            "size":       item["sizes"],
                            "url":        item["url"],
                            "image":      item.get("image", ""),
                            "area":       t["name_en"],
                            "build_year": item.get("build_year", ""),
                        })
            except Exception as e:
                print(f"     Error: {e}")
        finally:
            await browser.close()
        await asyncio.sleep(7)
    return listings

# ── Lifull Homes (homes.co.jp) ────────────────────────────────
# URL query params apply the size/price filters server-side before we even
# see the page: grnd_m_low=land>=300m², bld_m_low=building>=100m², pricemax=1500万円.
# Property detail URLs contain /chuko/ so EXTRACT_JS is told to allow that.
async def scrape_homes(pw, cfg):
    listings = []
    seen_urls = set()

    for t in TARGETS:
        base_url = t.get("homes_url")
        if not base_url:
            continue
        print(f"   Lifull Homes -> {t['name_en']}")
        browser = await pw.chromium.launch(headless=True, args=browser_args())
        try:
            ctx  = await make_context(browser)
            page = await ctx.new_page()
            await page.add_init_script(
                "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
            )

            for pg in range(1, MAX_PAGES + 1):
                # Homes pagination: append &page=N to the filter query string
                url = base_url if pg == 1 else f"{base_url}&page={pg}"
                try:
                    resp = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    await asyncio.sleep(4)
                    status = resp.status if resp else 0
                    title  = await page.title()
                    print(f"     p{pg} status={status}  title={title[:60]}")

                    if status in (403, 405) or any(k in title.lower() for k in
                            ["verify", "captcha", "robot", "blocked", "\u8a8d\u8a3c"]):
                        print("     Blocked by CAPTCHA - skipping city")
                        break

                    await page.evaluate(GENTLE_SCROLL_JS)
                    await asyncio.sleep(1.5)
                    await page.evaluate(LAZY_LOAD_JS)
                    await asyncio.sleep(0.5)

                    raw = await page.evaluate(EXTRACT_JS, "homes.co.jp")
                    print(f"     p{pg} candidates: {len(raw)}")

                    if not raw:
                        print(f"     No candidates on page {pg} — stopping")
                        break

                    new_on_page = 0
                    for item in raw:
                        url_base = item["url"].split("?")[0].rstrip("/")
                        if url_base in seen_urls:
                            continue
                        seen_urls.add(url_base)
                        new_on_page += 1
                        if not passes_price(item["price"], cfg):
                            continue
                        if not passes_size(item["sizes"], cfg):
                            continue
                        listings.append({
                            "source":     "Lifull Homes",
                            "title":      item["title"],
                            "address":    item["address"] or t["city_ja"],
                            "price":      item["price"],
                            "size":       item["sizes"],
                            "url":        item["url"],
                            "image":      item.get("image", ""),
                            "area":       t["name_en"],
                            "build_year": item.get("build_year", ""),
                        })

                    print(f"     p{pg} new unique: {new_on_page}")
                    if new_on_page < 5:
                        print(f"     Few new results — stopping pagination")
                        break

                    await asyncio.sleep(3)

                except Exception as e:
                    print(f"     Error on page {pg}: {e}")
                    break

        finally:
            await browser.close()
        await asyncio.sleep(7)
    return listings


# ── HTML dashboard ────────────────────────────────────────────
def generate_html(listings, cfg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    by_area = {}
    for l in listings:
        by_area.setdefault(l["area"], []).append(l)

    CITY_ORDER_EMAIL = ["Gotemba, Shizuoka", "Oyama, Shizuoka", "Suzuka, Mie", "Tsu, Mie"]
    sorted_areas = sorted(by_area, key=lambda a: CITY_ORDER_EMAIL.index(a) if a in CITY_ORDER_EMAIL else 99)
    rows = ""
    for area in sorted_areas:
        group = by_area[area]
        rows += (
            f'<tr><td colspan="7" style="padding:0">'
            f'<div style="background:linear-gradient(90deg,#1a3a5c,#2755a0);color:#fff;'
            f'padding:12px 20px;font-size:1em;font-weight:700;letter-spacing:1px;'
            f'margin-top:8px;border-left:6px solid #f0b429">'
            f'&#127968; {area} &nbsp;&mdash;&nbsp; {len(group)} listing{"s" if len(group)!=1 else ""}'
            f'</div></td></tr>'
        )
        for l in group:
            import datetime as _dt
            sc    = re.sub(r"[^a-zA-Z]", "", l["source"])
            title = l.get("title", "Property")[:60]
            addr  = l.get("address", "")[:60]
            price = l.get("price_en") or l.get("price", "")
            size  = l.get("size_en")  or l.get("size", "")
            img   = l.get("image", "")
            by    = l.get("build_year", "")
            age_str = ""
            if by:
                age = _dt.datetime.now().year - int(by)
                age_str = f'<div style="font-size:.75em;color:#888;margin-top:2px">Built {by} &bull; {age} yrs old</div>'
            thumb = (
                f'<a href="{l["url"]}" target="_blank">'
                f'<img src="{img}" alt="photo" referrerpolicy="no-referrer" loading="lazy"'
                f' style="width:180px;height:136px;object-fit:cover;border-radius:5px;'
                f'display:block;border:1px solid #ddd;">'
                f'</a>'
            ) if img else '<span style="color:#ccc;font-size:.75em">no photo</span>'
            rows += (
                f'<tr>'
                f'<td class="thmb">{thumb}</td>'
                f'<td><span class="badge {sc}">{l["source"]}</span></td>'
                f'<td class="tc"><a href="{l["url"]}" target="_blank">{title}</a></td>'
                f'<td class="ac">{addr}</td>'
                f'<td class="pc">{price}{age_str}</td>'
                f'<td>{size}</td>'
                f'<td><a class="vb" href="{l["url"]}" target="_blank">View &rarr;</a></td>'
                f'</tr>'
            )

    total = len(listings)
    area_stats = "".join(
        f'<div class="sc"><strong>{len(v)}</strong><span>{k}</span></div>'
        for k, v in sorted(by_area.items())
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="21600">
<title>Japan Real Estate Listings</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Segoe UI',system-ui,Arial,sans-serif;background:#f0f4f8;color:#333}}
header{{background:linear-gradient(135deg,#1a3a5c,#0d2440);color:#fff;padding:20px 28px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px}}
header h1{{font-size:1.4em;font-weight:700}}
.ts{{font-size:.8em;opacity:.75}}
.stats{{display:flex;flex-wrap:wrap;gap:10px;padding:14px 28px;background:#fff;border-bottom:1px solid #dde2e8}}
.sc{{background:#f0f7ff;border-radius:8px;padding:9px 20px;text-align:center;min-width:100px}}
.sc strong{{display:block;font-size:1.7em;color:#1a3a5c}}
.sc span{{font-size:.75em;color:#666}}
.fb{{padding:8px 28px;background:#e4eef8;font-size:.81em;color:#445;border-bottom:1px solid #c8d8e8}}
.tw{{padding:20px 28px;overflow-x:auto}}
table{{width:100%;border-collapse:collapse;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 2px 6px rgba(0,0,0,.08)}}
thead th{{background:#1a3a5c;color:#fff;padding:11px 13px;text-align:left;font-size:.81em;font-weight:600;white-space:nowrap}}
tbody td{{padding:9px 13px;border-bottom:1px solid #eef0f3;vertical-align:top;font-size:.87em}}
tbody tr:hover td{{background:#f7faff}}
.ah td{{background:#e8f0fa;color:#1a3a5c;font-weight:700;font-size:.84em;padding:7px 13px}}
.tc a{{color:#1a3a5c;text-decoration:none}}.tc a:hover{{text-decoration:underline}}
.pc{{color:#c0392b;font-weight:700;white-space:nowrap}}
.badge{{display:inline-block;padding:2px 7px;border-radius:3px;font-size:.72em;font-weight:700;color:#fff;white-space:nowrap}}
.AtHome{{background:#e01836}}.Suumo{{background:#f05a00}}.YahooRE{{background:#720082}}.LifullHomes{{background:#1a7a3c}}
.vb{{display:inline-block;background:#1a3a5c;color:#fff;padding:3px 10px;border-radius:4px;text-decoration:none;font-size:.77em;white-space:nowrap}}
.vb:hover{{background:#2755a0}}
.thmb{{padding:6px 10px;width:190px;vertical-align:middle}}
.empty{{padding:50px 28px;text-align:center;color:#999;font-size:1.05em}}
footer{{padding:12px 28px;text-align:center;font-size:.77em;color:#aaa;border-top:1px solid #dde2e8}}
footer a{{color:#1a3a5c}}
</style>
</head>
<body>
<header>
  <div>
    <h1>&#127968; Japan Real Estate &mdash; Property Search</h1>
    <div class="ts">Last updated: {ts} &nbsp;|&nbsp; Auto-refreshes every 6 hours</div>
  </div>
</header>
<div class="stats">
  <div class="sc"><strong>{total}</strong><span>Total</span></div>
  {area_stats}
</div>
<div class="fb">&#128269;&nbsp; Max &#165;15,000,000 &nbsp;|&nbsp; Building &ge;100m&sup2; &nbsp;|&nbsp; Land &ge;300m&sup2; &nbsp;|&nbsp; Gotemba &amp; Oyama (Shizuoka) &middot; Suzuka &amp; Tsu (Mie)</div>
<div class="tw">
{"<table><thead><tr><th>Photo</th><th>Source</th><th>Title</th><th>Address</th><th>Price</th><th>Size</th><th>Link</th></tr></thead><tbody>"+rows+"</tbody></table>" if total > 0 else '<div class="empty">No listings found. Try running again or check that the sites are accessible.</div>'}
</div>
<footer>Sources: <a href="https://www.athome.co.jp" target="_blank">AtHome</a> &middot; <a href="https://suumo.jp" target="_blank">Suumo</a> &middot; <a href="https://realestate.yahoo.co.jp" target="_blank">Yahoo Real Estate</a> &middot; <a href="https://www.homes.co.jp" target="_blank">Lifull Homes</a></footer>
</body></html>
"""

# ── email ─────────────────────────────────────────────────────
def send_email(listings, cfg):
    ec = cfg["email"]
    if ec["gmail_app_password"] == "YOUR_GMAIL_APP_PASSWORD_HERE":
        print("Email skipped - add Gmail App Password to config.json")
        return

    ts    = datetime.datetime.now().strftime("%b %d, %Y  %I:%M %p")   # e.g. Mar 02, 2026  06:00 AM
    total = len(listings)

    # ── Fuji SVG banner (inline — no external images needed) ──────────────
    fuji_banner = (
        "<div style='position:relative;border-radius:8px 8px 0 0;overflow:hidden;height:160px;"
        "background:#1a3a5c'>"
        f"<img src='https://veloce16.github.io/japan-homes/fuji.jpg' "
        "width='700' style='width:100%;height:160px;object-fit:cover;object-position:center 40%;"
        "display:block' alt='Mount Fuji'>"
        "<div style='position:absolute;bottom:0;left:0;right:0;padding:12px 22px;"
        "background:linear-gradient(transparent,rgba(0,0,0,0.65))'>"
        "<div style=\"font-family:'Hiragino Mincho ProN','Yu Mincho',serif;font-size:12px;"
        "color:rgba(255,255,255,0.85);letter-spacing:3px;margin-bottom:3px\">日本の家探し</div>"
        "<div style=\"font-family:Georgia,'Times New Roman',serif;font-size:22px;font-weight:bold;"
        "color:#fff;letter-spacing:1px\">&#127968; JAPAN Home Search</div>"
        "</div></div>"
    )

    # ── Listing rows grouped by city with separator headers ─────────────────
    import datetime as _dt
    CITY_ORDER_EMAIL = ["Gotemba, Shizuoka", "Oyama, Shizuoka", "Suzuka, Mie", "Tsu, Mie"]
    by_area = {}
    for l in listings:
        by_area.setdefault(l.get("area", "Other"), []).append(l)
    sorted_areas = sorted(by_area, key=lambda a: CITY_ORDER_EMAIL.index(a) if a in CITY_ORDER_EMAIL else 99)

    rows = ""
    for area in sorted_areas:
        group = by_area[area]
        # City separator banner
        rows += (
            f"<tr><td colspan='2' style='padding:0'>"
            f"<div style='background:linear-gradient(90deg,#1a3a5c,#2755a0);color:#fff;"
            f"padding:11px 18px;font-size:13px;font-weight:700;letter-spacing:1px;"
            f"margin-top:6px;border-left:6px solid #f0b429'>"
            f"&#127968; {area} &nbsp;&mdash;&nbsp; {len(group)} listing{'s' if len(group)!=1 else ''}"
            f"</div></td></tr>"
        )
        for i, l in enumerate(group):
            bg    = "#f9f9f9" if i % 2 == 0 else "#fff"
            title = l.get("title", "Property")
            t     = (title[:48] + "…") if len(title) > 48 else title
            price = l.get("price_en") or l.get("price", "")
            size  = l.get("size_en")  or l.get("size", "")
            img   = l.get("image", "")
            date_found = l.get("date_found", "")
            by    = l.get("build_year", "")
            age_str = ""
            if by:
                age = _dt.datetime.now().year - int(by)
                age_str = f"<div style='font-size:11px;color:#888;margin-top:2px'>Built {by} &bull; {age} yrs old</div>"
            thumb_td = (
                f"<td style='padding:5px 8px;width:110px;vertical-align:top'>"
                f"<a href='{l['url']}'><img src='{img}' width='100' height='75' referrerpolicy='no-referrer'"
                f" style='object-fit:cover;border-radius:4px;border:1px solid #ddd;display:block'></a></td>"
            ) if img else (
                "<td style='padding:5px 8px;width:110px;vertical-align:top;"
                "color:#ccc;font-size:11px;text-align:center'>no photo</td>"
            )
            rows += (
                f"<tr style='background:{bg};border-bottom:1px solid #e8eaf0'>"
                f"{thumb_td}"
                f"<td style='padding:7px 10px;vertical-align:top'>"
                f"<div style='font-size:13px;font-weight:600;margin-bottom:3px'>"
                f"<a href='{l['url']}' style='color:#1a3a5c;text-decoration:none'>{t}</a></div>"
                f"<div style='font-size:12px;color:#666;margin-bottom:2px'>"
                f"{l.get('source','')} &bull; {l.get('area','')}</div>"
                f"<div style='font-size:14px;color:#c0392b;font-weight:bold;margin-bottom:2px'>{price}</div>"
                f"<div style='font-size:12px;color:#555'>{size[:50]}</div>"
                + age_str
                + (f"<div style='font-size:11px;color:#aaa;margin-top:2px'>Found: {date_found}</div>" if date_found else "")
                + "</td></tr>"
            )

    tbl = (
        "<table style='width:100%;border-collapse:collapse;border:1px solid #dde2e8'>"
        f"<tbody>{rows}</tbody></table>"
    ) if total > 0 else ""

    # ── "Open Dashboard" button ────────────────────────────────────────────
    dashboard_btn = (
        f"<div style='text-align:center;padding:18px 0 6px'>"
        f"<a href='{DASHBOARD_URL}' style='"
        f"background:#1a3a5c;color:#fff;padding:12px 28px;border-radius:6px;"
        f"text-decoration:none;font-size:15px;font-weight:600;"
        f"font-family:Arial,sans-serif;display:inline-block'>"
        f"&#127968; Open Dashboard</a></div>"
    )

    body = f"""<!DOCTYPE html>
<html>
<body style="font-family:'Segoe UI',Arial,sans-serif;max-width:700px;margin:auto;background:#f4f6fb;padding:0">
  <!-- Fuji banner -->
  {fuji_banner}

  <!-- Summary bar -->
  <div style="background:#1a3a5c;color:#fff;padding:12px 22px;border-top:2px solid #e67e22">
    <span style="font-size:1.05em;font-weight:600">
      &#127968; {total} listing{'s' if total != 1 else ''} found &mdash; {ts}
    </span>
    <span style="font-size:11px;color:#b0c4de;margin-left:14px">
      Max ¥15M &bull; Building ≥100m² &bull; Land ≥300m²
    </span>
  </div>

  <!-- Dashboard button -->
  {dashboard_btn}

  <!-- Listings table -->
  <div style="margin-top:10px;border-radius:6px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.08)">
    {tbl}
  </div>

  <!-- Footer -->
  <div style="padding:14px 22px;margin-top:12px;font-size:11px;color:#aaa;text-align:center">
    Scraper runs automatically every 6 hours via GitHub Actions.<br>
    <a href="{DASHBOARD_URL}" style="color:#1a3a5c">{DASHBOARD_URL}</a>
  </div>
</body>
</html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🏠 Japan RE: {total} listing{'s' if total != 1 else ''} — {ts}"
    msg["From"]    = ec["from_address"]
    msg["To"]      = ec["to_address"]
    msg.attach(MIMEText(body, "html", "utf-8"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as srv:
            srv.login(ec["from_address"], ec["gmail_app_password"])
            srv.sendmail(ec["from_address"], ec["to_address"], msg.as_string())
        print(f"Email sent to {ec['to_address']}")
    except Exception as e:
        print(f"Email error: {e}")

# ── main ──────────────────────────────────────────────────────
async def main():
    cfg = load_config()
    print(f"\n{'='*55}")
    print(f"  Japan Real Estate Scraper v2  {datetime.datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"{'='*55}\n")

    all_listings = []

    async with async_playwright() as pw:
        print("Scraping AtHome...")
        r = await scrape_athome(pw, cfg)
        print(f"  -> {len(r)} listings\n")
        all_listings.extend(r)

        print("Scraping Suumo...")
        r = await scrape_suumo(pw, cfg)
        print(f"  -> {len(r)} listings\n")
        all_listings.extend(r)

        print("Scraping Yahoo Real Estate...")
        r = await scrape_yahoo(pw, cfg)
        print(f"  -> {len(r)} listings\n")
        all_listings.extend(r)

        print("Scraping Lifull Homes...")
        r = await scrape_homes(pw, cfg)
        print(f"  -> {len(r)} listings\n")
        all_listings.extend(r)

    # De-duplicate by URL
    seen, unique = set(), []
    for l in all_listings:
        if l["url"] and l["url"] not in seen:
            seen.add(l["url"])
            unique.append(l)

    print(f"Total unique listings: {len(unique)}")

    # Translate all Japanese text to English
    unique = translate_listings(unique)

    # Format prices and sizes into readable English; stamp date_found
    today_str = datetime.date.today().isoformat()
    for l in unique:
        l["price_en"]   = format_price_english(l.get("price", ""))
        l["size_en"]    = format_size_english(l.get("size", ""))
        # Preserve existing date_found if we're merging with prior data
        if "date_found" not in l:
            l["date_found"] = today_str
    print("Formatting complete")

    # Merge date_found AND coordinates from previous run
    if JSON_FILE.exists():
        try:
            with open(JSON_FILE, encoding="utf-8") as f:
                prev = json.load(f)
            prev_list = prev if isinstance(prev, list) else prev.get("listings", [])
            prev_dates = {l["url"]: l["date_found"] for l in prev_list if "url" in l and "date_found" in l}
            prev_coords = {l["url"]: (l["lat"], l["lng"]) for l in prev_list
                           if "url" in l and "lat" in l and "lng" in l}
            for l in unique:
                if l["url"] in prev_dates:
                    l["date_found"] = prev_dates[l["url"]]
                if l["url"] in prev_coords:
                    l["lat"], l["lng"] = prev_coords[l["url"]]
        except Exception:
            pass

    # Fetch exact coordinates for new AtHome listings (detail page has embedded Google Maps)
    athome_no_coords = [l for l in unique
                        if l.get("source") == "AtHome"
                        and "lat" not in l
                        and l.get("url", "").startswith("http")]
    if athome_no_coords:
        print(f"\nFetching exact coordinates for {len(athome_no_coords)} new AtHome listings...")
        async with async_playwright() as pw2:
            coords_found = 0
            for l in athome_no_coords:
                try:
                    browser2 = await pw2.chromium.launch(headless=True, args=browser_args())
                    ctx2 = await make_context(browser2)
                    page2 = await ctx2.new_page()
                    await page2.goto(l["url"], wait_until="domcontentloaded", timeout=20000)
                    await asyncio.sleep(2)

                    coords = await page2.evaluate("""() => {
                        // Pattern 1: Google Maps iframe src with coordinates
                        for (const iframe of document.querySelectorAll('iframe[src*="google.com/maps"]')) {
                            const src = iframe.src || iframe.getAttribute('src') || '';
                            // q=lat,lng format
                            const q = src.match(/[?&]q=([-\d.]+),([-\d.]+)/);
                            if (q) return {lat: parseFloat(q[1]), lng: parseFloat(q[2])};
                            // !3d{lat}!4d{lng} format in embed URL
                            const pb = src.match(/!3d([-\d.]+).*?!4d([-\d.]+)/);
                            if (pb) return {lat: parseFloat(pb[1]), lng: parseFloat(pb[2])};
                        }
                        // Pattern 2: JSON-LD structured data
                        for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
                            try {
                                const d = JSON.parse(s.textContent);
                                const geo = d.geo || (d['@graph'] && d['@graph'].find(x=>x.geo) || {}).geo;
                                if (geo && geo.latitude) return {lat: parseFloat(geo.latitude), lng: parseFloat(geo.longitude)};
                            } catch(e) {}
                        }
                        // Pattern 3: JavaScript variables in page source
                        const scripts = [...document.querySelectorAll('script:not([src])')].map(s=>s.textContent).join('');
                        const m1 = scripts.match(/"latitude"\s*:\s*([-\d.]+).*?"longitude"\s*:\s*([-\d.]+)/s);
                        if (m1) return {lat: parseFloat(m1[1]), lng: parseFloat(m1[2])};
                        const m2 = scripts.match(/lat(?:itude)?\s*[=:]\s*(3[0-9]\.\d+).*?l(?:ng|on)(?:gitude)?\s*[=:]\s*(13[0-9]\.\d+)/s);
                        if (m2) return {lat: parseFloat(m2[1]), lng: parseFloat(m2[2])};
                        // Pattern 4: data-lat / data-lng attributes
                        const el = document.querySelector('[data-lat],[data-latitude]');
                        if (el) {
                            const lat = parseFloat(el.getAttribute('data-lat') || el.getAttribute('data-latitude'));
                            const lng = parseFloat(el.getAttribute('data-lng') || el.getAttribute('data-longitude'));
                            if (lat && lng) return {lat, lng};
                        }
                        return null;
                    }""")

                    if coords and 30 < coords["lat"] < 46 and 129 < coords["lng"] < 146:
                        l["lat"] = round(coords["lat"], 6)
                        l["lng"] = round(coords["lng"], 6)
                        coords_found += 1
                        print(f"   ✓ {l.get('area','')} — {l['lat']}, {l['lng']}")
                    else:
                        print(f"   – No coords: {l['url'][:60]}")

                    await browser2.close()
                    await asyncio.sleep(2)
                except Exception as e:
                    print(f"   ! Error fetching coords: {e}")
                    try: await browser2.close()
                    except: pass

        print(f"Coordinates found: {coords_found}/{len(athome_no_coords)}")

    # Build output payload with generated timestamp
    generated_ts = datetime.datetime.now().isoformat(timespec="seconds")
    payload = {"generated": generated_ts, "listings": unique}

    # Write local JSON (used by old HTML dashboard and task scheduler)
    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    # Write to docs/ for GitHub Pages dashboard
    DOCS_DIR.mkdir(exist_ok=True)
    with open(DOCS_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"listings.json written ({len(unique)} listings) → {DOCS_JSON}")

    html = generate_html(unique, cfg)
    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Legacy dashboard saved: {HTML_FILE}")

    if unique:
        print("\nSending email...")
        send_email(unique, cfg)
    else:
        print("\nNo listings found — email skipped.")
    print("\nDone!\n")

if __name__ == "__main__":
    asyncio.run(main())
