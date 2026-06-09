@echo off
cd /d "C:\Users\Nelson Arévalo\bot-precios"

git fetch origin main 2>nul
git diff --quiet HEAD origin/main 2>nul
if %errorlevel% == 1 (
    echo Actualizacion disponible, aplicando...
    git pull origin main
    taskkill /f /im python.exe >nul 2>&1
    timeout /t 3 /nobreak >nul
    start /min python catalog_monitor.py
    echo Bot reiniciado con nueva version.
) else (
    echo Sin cambios.
)
