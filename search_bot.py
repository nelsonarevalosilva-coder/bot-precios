"""
Bot de búsqueda de ofertas para usuarios.
Uso: python search_bot.py
"""

import logging
import os
import sqlite3
import sys
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

load_dotenv()
TOKEN = os.getenv("SEARCH_BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_TELEGRAM_ID", "0"))
DB_PATH = Path(__file__).parent / "prices.db"

sys.path.insert(0, str(Path(__file__).parent))
from sub_db import get_active_subscriptions

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

STORE_EMOJI = {
    "buscalibre": "📚",
    "ripley": "🛍️",
    "falabella": "🛒",
    "paris": "🏬",
    "sodimac": "🔨",
    "easy": "🔧",
    "jumbo": "🛒",
    "nike": "👟",
    "adidas": "👟",
    "zara": "👗",
    "mercadolibre": "📦",
}


def _store_from_url(url: str) -> str:
    for key in STORE_EMOJI:
        if key in url.lower():
            return key.capitalize()
    return "Tienda"


def _emoji_from_url(url: str) -> str:
    for key, emoji in STORE_EMOJI.items():
        if key in url.lower():
            return emoji
    return "🏷️"


def search_db(query: str, channel_keys: list[str], limit: int = 8) -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    if "all" in channel_keys:
        # Suscripción a todos los canales → sin filtro
        cur.execute(
            """
            SELECT product_name, url, discount_pct, sale_price, notified_at
            FROM notified_discounts
            WHERE LOWER(product_name) LIKE LOWER(?)
            ORDER BY discount_pct DESC, notified_at DESC
            LIMIT ?
            """,
            (f"%{query}%", limit),
        )
    else:
        placeholders = ",".join("?" * len(channel_keys))
        cur.execute(
            f"""
            SELECT product_name, url, discount_pct, sale_price, notified_at
            FROM notified_discounts
            WHERE LOWER(product_name) LIKE LOWER(?)
              AND (channel_key IN ({placeholders}) OR channel_key IS NULL)
            ORDER BY discount_pct DESC, notified_at DESC
            LIMIT ?
            """,
            (f"%{query}%", *channel_keys, limit),
        )
    rows = cur.fetchall()
    conn.close()

    return [
        {
            "name": r[0],
            "url": r[1],
            "discount_pct": r[2],
            "price": r[3],
            "notified_at": r[4][:10] if r[4] else "",
        }
        for r in rows
    ]


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *¡Hola! Soy el buscador de ofertas.*\n\n"
        "Escríbeme el nombre de cualquier producto y te muestro "
        "las mejores ofertas encontradas en todas las tiendas.\n\n"
        "Ejemplo: `samsung`, `zapatillas`, `libro`",
        parse_mode="Markdown",
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔍 *Cómo usar el bot:*\n\n"
        "Solo escribe lo que buscas y te respondo con las ofertas disponibles.\n\n"
        "• Las ofertas son de 70%+ de descuento\n"
        "• Busca por nombre, marca o categoría\n"
        "• Los precios corresponden al momento en que se detectó la oferta",
        parse_mode="Markdown",
    )


async def handle_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id == OWNER_ID:
        channel_keys = ["all"]
    else:
        subs = get_active_subscriptions(user_id)
        if not subs:
            await update.message.reply_text(
                "🔒 <b>Acceso exclusivo para suscriptores</b>\n\n"
                "Este buscador es solo para clientes con suscripción activa.\n\n"
                "👉 Escribe /suscribir en @Cazador_precios_cl_chile_bot para activar tu acceso.",
                parse_mode="HTML",
            )
            return
        channel_keys = list({s["channel_key"] for s in subs})

    query = update.message.text.strip()

    if len(query) < 2:
        await update.message.reply_text("✏️ Escribe al menos 2 caracteres.")
        return

    results = search_db(query, channel_keys)

    if not results:
        await update.message.reply_text(
            f"😕 No encontré ofertas para *{query}*.\n"
            "Intenta con otra palabra o revisa los canales directamente.",
            parse_mode="Markdown",
        )
        return

    lines = [f"🔍 *{len(results)} resultado(s) para \"{query}\":*\n"]
    for r in results:
        emoji = _emoji_from_url(r["url"])
        store = _store_from_url(r["url"])
        lines.append(
            f"{emoji} *{r['name'][:60]}*\n"
            f"   💰 ${r['price']:,} — {r['discount_pct']:.0f}% OFF — {store}\n"
            f"   🔗 [Ver oferta]({r['url']})\n"
        )

    text = "\n".join(lines)

    # Telegram limita a 4096 caracteres
    if len(text) > 4000:
        text = text[:3990] + "\n\n_... y más resultados_"

    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )


def main():
    if not TOKEN:
        print("ERROR: SEARCH_BOT_TOKEN no configurado en .env")
        sys.exit(1)

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search))

    print("Bot de búsqueda iniciado. Presiona Ctrl+C para detener.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
