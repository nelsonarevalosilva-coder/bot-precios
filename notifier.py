import os
import requests
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")  # canal principal / fallback
PRICE_ERROR_CHANNEL = -1004295138538     # canal especial errores de precio extremo

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# IDs de los 12 canales por categoría
CHANNEL_IDS = {
    "tecnologia":    -1003633911277,
    "muebles_hogar": -1003804002653,
    "electro":       -1003911147571,
    "perfumes":      -1003980648018,
    "gaming":        -1004290755569,
    "zapatillas":    -1003900467811,
    "outdoor":       -1003907913373,
    "deportes":      -1003998383372,
    "ropa":          -1003932337515,
    "automotriz":    -1003962932016,
    "ferreteria":    -1003848024596,
    "licores":       -1004053668233,
}

# Tiendas que siempre van a un canal específico
STORE_CHANNEL = {
    "PC Factory":           "tecnologia",
    "Multimarcas Perfumes": "perfumes",
    "Columbia":             "outdoor",
    "Doite":                "outdoor",
    "Wild Lama":            "outdoor",
    "El Mundo del Vino":   "licores",
    "Liquidos":            "licores",
    "Booz":               "licores",
    "Hush Puppies":         "zapatillas",
}

# Keywords de categoría → canal (el primer match gana)
CATEGORY_KEYWORDS = [
    ("zapatilla",       "zapatillas"),
    ("zapatos",         "zapatillas"),
    ("calzado",         "zapatillas"),
    ("consola",         "gaming"),
    ("gaming",          "gaming"),
    ("electrodom",      "electro"),
    ("refriger",        "electro"),
    ("lavadora",        "electro"),
    ("microondas",      "electro"),
    ("electro",         "electro"),
    ("televisi",        "tecnologia"),
    ("television",      "tecnologia"),
    ("televisor",       "tecnologia"),
    ("computador",      "tecnologia"),
    ("celular",         "tecnologia"),
    ("smartphone",      "tecnologia"),
    ("notebook",        "tecnologia"),
    ("monitor",         "tecnologia"),
    ("tablet",          "tecnologia"),
    ("audio",           "tecnologia"),
    ("tecno",           "tecnologia"),
    ("almacenamiento",  "tecnologia"),
    ("memorias",        "tecnologia"),
    ("impresora",       "tecnologia"),
    ("componente",      "tecnologia"),
    ("perfume",         "perfumes"),
    ("belleza",         "perfumes"),
    ("deporte",         "deportes"),
    ("ferreteria",      "ferreteria"),
    ("ferretería",      "ferreteria"),
    ("herramienta",     "ferreteria"),
    ("electricidad",    "ferreteria"),
    ("jardín",          "ferreteria"),
    ("jardin",          "ferreteria"),
    ("pintura",         "ferreteria"),
    ("plomería",        "ferreteria"),
    ("plomeria",        "ferreteria"),
    ("climatizaci",     "ferreteria"),
    ("seguridad",       "ferreteria"),
    ("mueble",          "muebles_hogar"),
    ("dormitorio",      "muebles_hogar"),
    ("baño",            "muebles_hogar"),
    ("bano",            "muebles_hogar"),
    ("cocina",          "muebles_hogar"),
    ("decoraci",        "muebles_hogar"),
    ("iluminaci",       "muebles_hogar"),
    ("hogar",           "muebles_hogar"),
    ("ropa",            "ropa"),
    ("moda",            "ropa"),
    ("hombre",          "ropa"),
    ("mujer",           "ropa"),
    ("automotriz",      "automotriz"),
    ("licor",           "licores"),
    ("vino",            "licores"),
    ("cerveza",         "licores"),
    ("whisky",          "licores"),
]


def get_channel_for_product(product) -> int:
    """Retorna el chat_id del canal correcto para el producto."""
    store = getattr(product, "store", "")
    category = getattr(product, "category", "").lower()

    # 1. Override por tienda
    if store in STORE_CHANNEL:
        return CHANNEL_IDS[STORE_CHANNEL[store]]

    # 2. Reebok: por categoría
    if store == "Reebok":
        if "zapatilla" in category:
            return CHANNEL_IDS["zapatillas"]
        return CHANNEL_IDS["deportes"]

    # 3. Bold: por categoría
    if store == "Bold":
        if "zapatilla" in category:
            return CHANNEL_IDS["zapatillas"]
        return CHANNEL_IDS["ropa"]

    # 4. Keyword de categoría
    for keyword, channel_key in CATEGORY_KEYWORDS:
        if keyword in category:
            return CHANNEL_IDS[channel_key]

    # 5. Fallback: canal principal
    return int(CHAT_ID)


def _send(text: str, chat_id=None) -> bool:
    if not BOT_TOKEN or not CHAT_ID:
        print("[notifier] TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID no configurados.")
        return False
    target = chat_id if chat_id is not None else int(CHAT_ID)
    resp = requests.post(
        f"{TELEGRAM_API}/sendMessage",
        json={"chat_id": target, "text": text, "parse_mode": "HTML"},
        timeout=10,
    )
    return resp.status_code == 200


def notify_price_drop(product_name: str, url: str, old_price: int, new_price: int):
    diff = old_price - new_price
    pct = (diff / old_price) * 100
    text = (
        f"🔻 <b>BAJA DE PRECIO en Ripley</b>\n\n"
        f"📦 <b>{product_name}</b>\n"
        f"💰 Antes: <s>${old_price:,}</s>\n"
        f"✅ Ahora: <b>${new_price:,}</b>\n"
        f"📉 Ahorro: ${diff:,} ({pct:.1f}%)\n\n"
        f"🔗 <a href=\"{url}\">Ver producto</a>"
    )
    ok = _send(text)
    if ok:
        print(f"[notifier] Alerta enviada: {product_name} bajó ${diff:,}")
    else:
        print(f"[notifier] Error al enviar alerta para {product_name}")


def notify_target_reached(product_name: str, url: str, price: int, target: int):
    text = (
        f"🎯 <b>PRECIO OBJETIVO ALCANZADO en Ripley</b>\n\n"
        f"📦 <b>{product_name}</b>\n"
        f"✅ Precio actual: <b>${price:,}</b>\n"
        f"🎯 Tu objetivo: ${target:,}\n\n"
        f"🔗 <a href=\"{url}\">Comprar ahora</a>"
    )
    ok = _send(text)
    if ok:
        print(f"[notifier] Alerta objetivo enviada: {product_name} en ${price:,}")


def _min_price_line(sale_price: int, min_price: int | None) -> str:
    """Genera la línea de mínimo histórico para incluir en el mensaje."""
    if min_price is None:
        return "\n📊 <i>Primera vez registrado en el sistema</i>"
    if sale_price < min_price:
        return f"\n🟢 <b>¡Mínimo histórico!</b> Antes lo más barato era <s>${min_price:,}</s>"
    if sale_price == min_price:
        return f"\n📊 Mínimo histórico: <b>${min_price:,}</b> (igual al más barato registrado)"
    diff_pct = (sale_price - min_price) / min_price * 100
    return f"\n📊 Mínimo histórico: <b>${min_price:,}</b> ({diff_pct:.0f}% más caro que el menor precio registrado)"


def notify_price_error(product, min_price: int | None = None) -> bool:
    """Alerta especial para posibles errores de precio (>= 70% descuento)."""
    savings = product.normal_price - product.sale_price
    store = getattr(product, "store", "Ripley")
    channel = get_channel_for_product(product)
    hist = _min_price_line(product.sale_price, min_price)

    if product.sale_price < 1000 and product.normal_price > 5000:
        text = (
            f"🆘 <b>ERROR DE PRECIO EXTREMO en {store}</b>\n\n"
            f"📦 <b>{product.name}</b>\n"
            f"🏷️ Categoría: {product.category}\n"
            f"💰 Precio normal: <s>${product.normal_price:,}</s>\n"
            f"🔴 Precio actual: <b>${product.sale_price:,}</b>\n"
            f"📉 Descuento: <b>{product.discount_pct:.0f}%</b>"
            f"{hist}\n\n"
            f"⚠️ <i>Precio probablemente incorrecto — compra ahora antes de que lo corrijan</i>\n"
            f"🔗 <a href=\"{product.url}\">Comprar ahora</a>"
        )
        ok = _send(text, chat_id=channel)
        _send(text, chat_id=PRICE_ERROR_CHANNEL)
        if ok:
            print(f"  → ERROR EXTREMO enviado: {product.name} ({product.discount_pct:.0f}% off) → canal {channel} + productos")
        return ok
    else:
        text = (
            f"🚨 <b>POSIBLE ERROR DE PRECIO en {store}</b>\n\n"
            f"📦 <b>{product.name}</b>\n"
            f"🏷️ Categoría: {product.category}\n"
            f"💰 Precio normal: <s>${product.normal_price:,}</s>\n"
            f"🔴 Precio actual: <b>${product.sale_price:,}</b>\n"
            f"📉 Descuento: <b>{product.discount_pct:.0f}%</b> — ahorras ${savings:,}"
            f"{hist}\n\n"
            f"⚡ <i>Compra antes de que lo corrijan</i>\n"
            f"🔗 <a href=\"{product.url}\">Comprar ahora</a>"
        )
    ok = _send(text, chat_id=channel)
    _send(text, chat_id=PRICE_ERROR_CHANNEL)
    if ok:
        print(f"  → ERROR PRECIO enviado: {product.name} ({product.discount_pct:.0f}% off) → canal {channel} + productos")
    return ok


def notify_big_discount(product, min_price: int | None = None) -> bool:
    """Alerta de descuento encontrado en el catálogo."""
    savings = product.normal_price - product.sale_price
    store = getattr(product, "store", "Ripley")
    channel = get_channel_for_product(product)
    hist = _min_price_line(product.sale_price, min_price)
    text = (
        f"🔥 <b>OFERTA {product.discount_pct:.0f}% DESCUENTO en {store}</b>\n\n"
        f"📦 <b>{product.name}</b>\n"
        f"🏷️ Categoría: {product.category}\n"
        f"💰 Precio normal: <s>${product.normal_price:,}</s>\n"
        f"✅ Precio oferta: <b>${product.sale_price:,}</b>\n"
        f"📉 Descuento: <b>{product.discount_pct:.0f}%</b> (ahorras ${savings:,})"
        f"{hist}\n\n"
        f"🔗 <a href=\"{product.url}\">Ver oferta</a>"
    )
    ok = _send(text, chat_id=channel)
    if ok:
        print(f"  → Alerta enviada: {product.name} ({product.discount_pct:.0f}% off) → canal {channel}")
    return ok


def notify_catalog_summary(total_found: int, categories_scanned: int, errors_found: int = 0):
    """Resumen del escaneo — va al canal principal."""
    error_line = f"\n🚨 Errores de precio (+70%): <b>{errors_found}</b>" if errors_found > 0 else ""
    text = (
        f"✅ <b>Escaneo completado — 18 tiendas</b>\n"
        f"📂 Categorías revisadas: {categories_scanned}\n"
        f"🔥 Ofertas enviadas: {total_found}"
        f"{error_line}"
    )
    _send(text)


def notify_error(product_name: str, url: str, error: str):
    text = (
        f"⚠️ <b>Error al monitorear producto</b>\n\n"
        f"📦 {product_name}\n"
        f"❌ {error}\n"
        f"🔗 {url}"
    )
    _send(text)


def test_connection() -> bool:
    resp = requests.get(f"{TELEGRAM_API}/getMe", timeout=10)
    if resp.status_code == 200:
        bot_name = resp.json()["result"]["username"]
        print(f"[notifier] Conectado al bot: @{bot_name}")
        return True
    print(f"[notifier] Error de conexión: {resp.text}")
    return False
