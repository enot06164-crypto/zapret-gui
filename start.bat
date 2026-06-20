@echo off
cd /d "%~dp0"
echo Starting Zapret GUI...
start "" python zapret_gui.py
echo Waiting for server...
:loop
timeout /t 1 /nobreak >nul
curl -s http://127.0.0.1:8080/api/setup/status >nul 2>&1
if errorlevel 1 goto loop
echo Opening browser on http://127.0.0.1:8080
start "" http://127.0.0.1:8080
