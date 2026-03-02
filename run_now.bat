@echo off
title Japan Real Estate Scraper

echo.
echo Running Japan Real Estate Scraper...
echo.

cd /d "%~dp0"
python scraper.py

echo.
echo Done! Open listings.html in your browser to see results.
echo.
pause
