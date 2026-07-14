@echo off
title Cazador de Precios — Servidor

cd /d "C:\Users\narev\Desktop\OPEN\ripley-monitor"

echo Cerrando procesos anteriores...
taskkill /f /im ngrok.exe >nul 2>&1
taskkill /f /fi "WINDOWTITLE eq Catalog Monitor" >nul 2>&1
taskkill /f /fi "WINDOWTITLE eq Payment Server" >nul 2>&1
taskkill /f /fi "WINDOWTITLE eq Sub Bot" >nul 2>&1
taskkill /f /fi "WINDOWTITLE eq Expiry Checker" >nul 2>&1
taskkill /f /fi "WINDOWTITLE eq Search Bot" >nul 2>&1
timeout /t 2 /nobreak >nul

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
