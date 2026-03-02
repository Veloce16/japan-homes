#!/bin/bash
# Japan Real Estate Scraper — Mac/Linux Setup

echo ""
echo "================================================"
echo " Japan Real Estate Scraper — Mac/Linux Setup"
echo "================================================"
echo ""

# Get the directory of this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_PATH="$SCRIPT_DIR/scraper.py"

# ── Check Python ──────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found."
    echo "Install it from https://www.python.org/downloads/ or via Homebrew: brew install python3"
    exit 1
fi
echo "[1/4] Python3 found: $(python3 --version)"

# ── Install packages ──────────────────────────────
echo "[2/4] Installing required packages..."
pip3 install playwright --quiet
python3 -m playwright install chromium
echo "[3/4] Packages installed."

# ── Cron job (every 6 hours) ──────────────────────
echo "[4/4] Setting up cron job (every 6 hours)..."

CRON_JOB="0 */6 * * * cd \"$SCRIPT_DIR\" && python3 \"$SCRIPT_PATH\" >> \"$SCRIPT_DIR/scraper.log\" 2>&1"

# Add to crontab if not already there
( crontab -l 2>/dev/null | grep -v "japan_realestate"; echo "$CRON_JOB" ) | crontab -

echo ""
echo "================================================"
echo " NEXT STEPS:"
echo "================================================"
echo ""
echo " 1. Open config.json and replace YOUR_GMAIL_APP_PASSWORD_HERE"
echo "    with your Gmail App Password (see README.txt)"
echo ""
echo " 2. Run the scraper now:"
echo "    python3 \"$SCRIPT_PATH\""
echo ""
echo " 3. Open listings.html in your browser"
echo ""
echo " Cron job set to run every 6 hours automatically."
echo "================================================"
