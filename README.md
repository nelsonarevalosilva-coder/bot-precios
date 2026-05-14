# 🤖 Bot Cazador de Errores de Precio — Chile

Monitorea Falabella, Ripley, Paris y Mercado Libre cada X minutos.
Te avisa por Telegram cuando detecta un precio anómalo.

---

## PASO 1 — Crear tu bot de Telegram (5 minutos)

1. Abre Telegram y busca: **@BotFather**
2. Escríbele: `/newbot`
3. Ponle un nombre, por ejemplo: `Mi Bot Precios`
4. BotFather te dará un **token** como este:
   ```
   7312456789:AAGx-abcDEFghijkLMNopqrSTUvwxyz12345
   ```
5. Guarda ese token — lo necesitas más adelante

### Obtener tu Chat ID
1. Busca en Telegram: **@userinfobot**
2. Escríbele cualquier cosa
3. Te responde con tu **ID numérico** (ejemplo: `123456789`)

---

## PASO 2 — Configurar el bot

Abre `bot.py` y edita estas líneas al inicio:

```python
TELEGRAM_TOKEN   = "7312456789:AAGx-abcDEFghijkLMNopqrSTUvwxyz12345"
TELEGRAM_CHAT_ID = "123456789"
UMBRAL_DESCUENTO = 40    # Alerta si el descuento supera este %
INTERVALO_MIN    = 60    # Buscar cada 60 minutos
```

### Agregar o quitar productos a monitorear

Edita la lista `PRODUCTOS` en `bot.py`:

```python
PRODUCTOS = [
    ("iPhone 16",        900_000),   # (nombre búsqueda, precio normal CLP)
    ("Samsung TV 65",    500_000),
    ("PlayStation 5",    550_000),
    # Agrega los que quieras...
]
```

---

## PASO 3 — Instalación local (para probar)

```bash
# Instalar dependencias
pip install -r requirements.txt

# Probar el bot (sin Telegram, solo muestra en consola)
python bot.py
```

---

## PASO 4 — Desplegar 24/7 GRATIS en Railway

Railway es gratuito hasta 500 horas/mes (suficiente para correr siempre).

### 4.1 — Crear cuenta
- Ve a https://railway.app
- Regístrate con GitHub (gratis)

### 4.2 — Subir el bot
```bash
# Instalar Railway CLI
npm install -g @railway/cli

# En la carpeta del bot:
railway login
railway init
railway up
```

### 4.3 — Configurar variables de entorno en Railway
En el dashboard de Railway → tu proyecto → Variables:

```
TELEGRAM_TOKEN   = tu_token_aqui
TELEGRAM_CHAT_ID = tu_chat_id_aqui
UMBRAL_DESCUENTO = 40
INTERVALO_MIN    = 60
```

### 4.4 — Alternativa: Render.com (también gratis)
- Ve a https://render.com
- New → Background Worker
- Conecta tu repo de GitHub con los archivos
- En "Build Command": `pip install -r requirements.txt`
- En "Start Command": `python bot.py`
- Agrega las variables de entorno igual que en Railway

---

## PASO 5 — Alternativa: correr en tu PC siempre encendida

Si tienes una PC o Raspberry Pi encendida todo el día:

```bash
# En Linux/Mac — correr en segundo plano:
nohup python bot.py > bot.log 2>&1 &

# En Windows — crear una tarea programada o usar:
pythonw bot.py
```

---

## ¿Cómo se ve la alerta en Telegram?

```
🚨 POSIBLE ERROR DE PRECIO

📦 Samsung Smart TV 65" QLED 4K
🏪 Tienda: Falabella
💸 Precio actual: $189.990
📋 Precio referencia: $650.000
📉 Descuento: 71% (ahorras $460.010)
⚠️ Precio 71% bajo referencia — posible error tipográfico

🔗 Ver producto ahora →

⏰ 14/05/2026 03:42
```

---

## Agregar más tiendas

El bot incluye scrapers para Falabella, Ripley, Paris y Mercado Libre.
Para agregar Lider, Sodimac u otras, copia el patrón de cualquier función
`scrape_X()` en `bot.py` e inspeccionas los selectores CSS con F12 en el navegador.

---

## Solución de problemas

| Problema | Solución |
|---|---|
| No llegan alertas | Verifica el token y chat_id con @userinfobot |
| 0 resultados | Las tiendas cambian sus selectores CSS — revisa con F12 |
| Error de conexión | La tienda bloqueó el bot, espera unos minutos |
| Muchas falsas alarmas | Sube el UMBRAL_DESCUENTO a 60% o 70% |
