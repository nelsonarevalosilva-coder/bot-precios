# Setup del agente de monitoreo de precios Ripley
# Ejecutar con: .\setup.ps1

Write-Host "=== Setup: Monitor de Precios Ripley ===" -ForegroundColor Cyan

# Crear entorno virtual
if (-not (Test-Path "venv")) {
    Write-Host "Creando entorno virtual..." -ForegroundColor Yellow
    python -m venv venv
}

# Activar entorno virtual
.\venv\Scripts\Activate.ps1

# Instalar dependencias
Write-Host "Instalando dependencias..." -ForegroundColor Yellow
pip install -r requirements.txt

# Instalar navegador Chromium para Playwright
Write-Host "Instalando Chromium para Playwright..." -ForegroundColor Yellow
playwright install chromium

Write-Host ""
Write-Host "=== Setup completo ===" -ForegroundColor Green
Write-Host ""
Write-Host "Proximos pasos:" -ForegroundColor Cyan
Write-Host "1. Edita el archivo .env con tu token de Telegram y Chat ID"
Write-Host "2. Edita products.json con los productos que quieres monitorear"
Write-Host "3. Prueba la conexion: python monitor.py --test-telegram"
Write-Host "4. Agrega un producto: python monitor.py --add-product"
Write-Host "5. Inicia el monitoreo: python monitor.py"
Write-Host ""
Write-Host "Comandos utiles:"
Write-Host "  python monitor.py --once       # Chequear ahora"
Write-Host "  python monitor.py --debug      # Ver detalles del scraping"
Write-Host "  python monitor.py              # Monitoreo continuo"
