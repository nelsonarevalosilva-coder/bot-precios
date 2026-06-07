import os
import requests
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"


def _send(text: str) -> bool:
    if not BOT_TOKEN or not CHAT_ID:
        print("[notifier] TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID no configurados.")
        return False
    resp = requests.post(
        f"{TELEGRAM_API}/sendMessage",
        json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"},
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


def notify_price_error(product) -> bool:
    """Alerta especial para posibles errores de precio (>= 70% descuento)."""
    savings = product.normal_price - product.sale_price
    store = getattr(product, "store", "Ripley")

    if product.sale_price < 1000 and product.normal_price > 5000:
        text = (
            f"🆘 <b>ERROR DE PRECIO EXTREMO en {store}</b>\n\n"
            f"📦 <b>{product.name}</b>\n"
            f"🏷️ Categoría: {product.category}\n"
            f"💰 Precio normal: <s>${product.normal_price:,}</s>\n"
            f"🔴 Precio actual: <b>${product.sale_price:,}</b>\n"
            f"📉 Descuento: <b>{product.discount_pct:.0f}%</b>\n\n"
            f"⚠️ <i>Precio probablemente incorrecto — compra ahora antes de que lo corrijan</i>\n"
            f"🔗 <a href=\"{product.url}\">Comprar ahora</a>"
        )
    else:
        text = (
            f"🚨 <b>POSIBLE ERROR DE PRECIO en {store}</b>\n\n"
            f"📦 <b>{product.name}</b>\n"
            f"🏷️ Categoría: {product.category}\n"
            f"💰 Precio normal: <s>${product.normal_price:,}</s>\n"
            f"🔴 Precio actual: <b>${product.sale_price:,}</b>\n"
            f"📉 Descuento: <b>{product.discount_pct:.0f}%</b> — ahorras ${savings:,}\n\n"
            f"⚡ <i>Compra antes de que lo corrijan</i>\n"
            f"🔗 <a href=\"{product.url}\">Comprar ahora</a>"
        )
    ok = _send(text)
    if ok:
        print(f"  → ERROR PRECIO enviado: {product.name} ({product.discount_pct:.0f}% off)")
    return ok


def notify_big_discount(product) -> bool:
    """Alerta de descuento >= 50% (pero < 70%) encontrado en el catálogo."""
    savings = product.normal_price - product.sale_price
    store = getattr(product, "store", "Ripley")
    text = (
        f"🔥 <b>OFERTA +70% DESCUENTO en {store}</b>\n\n"
        f"📦 <b>{product.name}</b>\n"
        f"🏷️ Categoría: {product.category}\n"
        f"💰 Precio normal: <s>${product.normal_price:,}</s>\n"
        f"✅ Precio oferta: <b>${product.sale_price:,}</b>\n"
        f"📉 Descuento: <b>{product.discount_pct:.0f}%</b> (ahorras ${savings:,})\n\n"
        f"🔗 <a href=\"{product.url}\">Ver oferta</a>"
    )
    ok = _send(text)
    if ok:
        print(f"  → Alerta enviada: {product.name} ({product.discount_pct:.0f}% off)")
    return ok


def notify_catalog_summary(total_found: int, categories_scanned: int, errors_found: int = 0):
    """Resumen del escaneo del catálogo."""
    error_line = f"\n🚨 Errores de precio (+70%): <b>{errors_found}</b>" if errors_found > 0 else ""
    text = (
        f"✅ <b>Escaneo Ripley + Falabella + Paris + Easy + Sodimac completado</b>\n"
        f"📂 Categorías revisadas: {categories_scanned}\n"
        f"🔥 Ofertas encontradas: {total_found}"
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
