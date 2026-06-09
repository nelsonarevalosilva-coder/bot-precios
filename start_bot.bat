@echo off
cd /d "%~dp0"
taskkill /f /im python.exe >nul 2>&1
timeout /t 2 /nobreak >nul
start /min cmd /c "python catalog_monitor.py"
echo Bot iniciado.
