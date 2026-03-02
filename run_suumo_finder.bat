@echo off
title Suumo URL Finder
cd /d "%~dp0"
echo.
echo Finding correct Suumo URL...
echo A browser window will open - watch what it does.
echo.
python find_suumo_url.py
echo.
echo Done! Check suumo_urls.txt for results.
pause
