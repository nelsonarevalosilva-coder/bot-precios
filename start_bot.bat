@echo off
cd /d "C:\Users\Nelson Arévalo\bot-precios"
:loop
echo.
echo [%date% %time%] Actualizando codigo...
git pull
echo [%date% %time%] Iniciando bot...
python catalog_monitor.py
echo [%date% %time%] Bot detenido. Reiniciando en 15 segundos...
timeout /t 15 /nobreak
goto loop
