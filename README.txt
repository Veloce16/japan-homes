============================================================
  JAPAN REAL ESTATE SCRAPER — README
============================================================

What this does:
  Searches Suumo, Homes.co.jp, and AtHome.co.jp every 6 hours
  for residential properties for sale matching your criteria,
  then emails you a summary and updates a browser dashboard.

Search criteria:
  Areas:    Gotemba & Oyama (Shizuoka) · Suzuka & Tsu (Mie)
  Max price: ¥15,000,000
  Min building: 100 m²
  Min land:     300 m²

Files in this folder:
  scraper.py          — Main script (do not edit unless noted)
  config.json         — YOUR settings (email password, filters)
  listings.html       — Browser dashboard (auto-generated)
  listings.json       — Raw data (auto-generated)
  setup_windows.bat   — One-click Windows setup & scheduler
  setup_mac.sh        — Mac/Linux setup & cron job
  run_now.bat         — Windows: run the scraper immediately

============================================================
  QUICK START (Windows)
============================================================

Step 1 — Install Python (if not already installed):
  Download from: https://www.python.org/downloads/
  IMPORTANT: During install, check "Add Python to PATH"

Step 2 — Set up Gmail App Password:
  a. Go to: https://myaccount.google.com/security
  b. Make sure 2-Step Verification is ON
  c. Click "App passwords" (search for it if not visible)
  d. Choose app: "Mail", device: "Windows Computer" → Generate
  e. Copy the 16-character password shown

Step 3 — Edit config.json:
  Open config.json in Notepad and replace:
    "YOUR_GMAIL_APP_PASSWORD_HERE"
  with the 16-character app password you just copied.
  (Keep the quotes around it.)

Step 4 — Run setup:
  Double-click: setup_windows.bat
  This installs the required packages and sets up the
  automatic 6-hour schedule.

Step 5 — Run your first search:
  Double-click: run_now.bat
  Then open listings.html in your browser to see results.

============================================================
  QUICK START (Mac / Linux)
============================================================

Step 1 — Get Gmail App Password (same as Windows Step 2 above)

Step 2 — Edit config.json with your app password

Step 3 — In Terminal, run:
  chmod +x setup_mac.sh
  ./setup_mac.sh

Step 4 — Run your first search:
  python3 scraper.py
  Then open listings.html in your browser.

============================================================
  CUSTOMIZING FILTERS
============================================================

Edit config.json to change filters:

  "max_price_yen": 15000000     ← Max price in yen
  "min_building_sqm": 100       ← Min building floor area (m²)
  "min_land_sqm": 300           ← Min land area (m²)

To add more areas, edit scraper.py and find SEARCH_TARGETS.
Follow the same format to add cities.

============================================================
  TROUBLESHOOTING
============================================================

"No listings found" — The site may have changed its layout.
  This is common with Japanese real estate sites.
  Try running with headless=False in scraper.py to watch
  the browser and see what's happening.

Email not sending — Check your Gmail App Password in config.json.
  Also make sure 2-Step Verification is enabled on your account.

Playwright error — Run: python -m playwright install chromium

Fewer results than expected — Some listings may not appear
  depending on the site's pagination. The scraper checks
  up to 3 pages per site per area.

============================================================
  CHANGING THE SCHEDULE
============================================================

Windows: Open Task Scheduler, find "JapanRealEstateScraper"
  → Right-click → Properties → Triggers

Mac/Linux: Edit crontab with: crontab -e
  Change "0 */6 * * *" to your preferred schedule.
  (0 */6 = every 6 hours, 0 8 * * * = 8am daily, etc.)

============================================================
  QUESTIONS?
============================================================

The scraper uses a headless Chrome browser (Playwright) to
navigate the Japanese real estate sites just like a human
would. This makes it more reliable than simple scrapers and
works even on JavaScript-heavy pages.

If a site changes its layout, the scraper may need updating.
Feel free to reach out for help.

============================================================
