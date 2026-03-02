@echo off
title Japan Real Estate Scraper — Setup

echo.
echo ================================================
echo  Japan Real Estate Scraper — Windows Setup
echo ================================================
echo.

REM ── Check Python ─────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH.
    echo Download it from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during install.
    pause
    exit /b 1
)

echo [1/4] Python found.

REM ── Install pip packages ─────────────────────────
echo [2/4] Installing required packages...
pip install playwright --quiet
python -m playwright install chromium

echo [3/4] Packages installed.

REM ── Schedule the task ────────────────────────────
echo [4/4] Creating Windows Scheduled Task (every 6 hours)...

set SCRIPT_DIR=%~dp0
set SCRIPT_PATH=%SCRIPT_DIR%scraper.py
set TASK_NAME=JapanRealEstateScraper

REM Delete old task if it exists
schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1

REM Create new task: runs at 6am, noon, 6pm, midnight
schtasks /create /tn "%TASK_NAME%" ^
  /tr "python \"%SCRIPT_PATH%\"" ^
  /sc HOURLY /mo 6 ^
  /st 06:00 ^
  /ru "%USERNAME%" ^
  /rl HIGHEST ^
  /f

if errorlevel 1 (
    echo.
    echo WARNING: Could not create scheduled task automatically.
    echo You can run it manually by double-clicking run_now.bat
) else (
    echo.
    echo Scheduled task created: runs every 6 hours starting at 6:00 AM.
)

echo.
echo ================================================
echo  NEXT STEPS:
echo ================================================
echo.
echo  1. Open config.json in this folder
echo  2. Replace YOUR_GMAIL_APP_PASSWORD_HERE with your
echo     Gmail App Password (see README.txt for how to get one)
echo  3. Double-click run_now.bat to do your first search
echo  4. Open listings.html in your browser to see results
echo.
echo ================================================
pause
