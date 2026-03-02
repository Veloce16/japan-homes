@echo off
title Japan Real Estate — Debug Mode

echo.
echo Running DEBUG scraper...
echo A browser window will open so you can see what's happening.
echo.

cd /d "%~dp0"
python debug_scraper.py

echo.
echo Debug complete!
echo Check the debug_screenshots folder and debug_log.txt
echo for results.
echo.
pause
