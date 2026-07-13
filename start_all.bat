@echo off
title Cazador de Precios — Servidor

cd /d "C:\Users\narev\Desktop\OPEN\ripley-monitor"

echo Iniciando monitor de catalogo...
start "Catalog Monitor" python catalog_monitor.py

echo Iniciando payment server...
start "Payment Server" python payment_server.py

echo Esperando 3 segundos...
timeout /t 3 /nobreak >nul

echo Iniciando ngrok (URL permanente)...
start "ngrok Tunnel" C:\Users\narev\ngrok.exe http --domain=seventy-shopping-rinsing.ngrok-free.dev 8080

echo Iniciando bot de suscripciones...
start "Sub Bot" python sub_bot.py

echo Iniciando verificador de vencimientos...
start "Expiry Checker" python expiry_checker.py

echo Iniciando bot buscador de ofertas...
start "Search Bot" python search_bot.py

echo.
echo Todo iniciado. No cierres estas ventanas.
pause
