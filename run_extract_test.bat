@echo off
title Japan RE - Extraction Test
cd /d "%~dp0"
echo Running extraction test...
echo A browser window will open - watch what happens.
echo.
python extract_test.py
echo.
echo Done! Check extract_results.txt for the output.
pause
