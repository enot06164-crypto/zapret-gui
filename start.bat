@echo off
cd /d "%~dp0"
echo Starting Zapret GUI...
start /b python zapret_gui.py
timeout /t 3 /nobreak >nul
echo Opening browser on http://127.0.0.1:8080
start "" http://127.0.0.1:8080
