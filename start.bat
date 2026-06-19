@echo off
cd /d "%~dp0"
echo Starting Zapret GUI...
echo Opening browser on http://127.0.0.1:8080
start "" http://127.0.0.1:8080
python zapret_gui.py
