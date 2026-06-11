@echo off
cd /d "%~dp0"

git fetch origin main >nul 2>&1
git diff --quiet HEAD origin/main >nul 2>&1
if %errorlevel% == 1 (
    echo Actualizacion disponible, aplicando...
    git pull origin main
    taskkill /f /im python.exe >nul 2>&1
    timeout /t 5 /nobreak >nul
    start /min cmd /c "python catalog_monitor.py"
    echo Bot reiniciado.
) else (
    echo Sin cambios nuevos.
)
