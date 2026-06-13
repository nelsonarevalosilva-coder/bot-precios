@echo off
cd /d "%~dp0"
echo Sincronizando con el repositorio...
git pull origin main
echo.
echo Listo. Para correr el bot manualmente:
echo   python catalog_monitor.py --once
echo   python catalog_monitor.py --once --store ripley --debug
pause
