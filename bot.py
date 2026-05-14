"""
Bot Cazador de Errores de Precio - Tiendas Chile
Busca en Falabella, Ripley, Paris, Mercado Libre
Envía alertas por Telegram cuando detecta precios anómalos
"""

import os
import time
import logging
import json
import hashlib
import requests
from datetime import datetime
from bs4 import BeautifulSoup
from dataclasses import dataclass, field
from typing import Optional
import schedule

# ─── Configuración (editar aquí o usar variables de entorno) ───────────────────
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN", "8610517346:AAHhLtK809u44etid2bo1f_pMKHkywXCDAc")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "5700067936")
UMBRAL_DESCUENTO = int(os.getenv("UMBRAL_DESCUENTO", "40"))   # % mínimo para alertar
INTERVALO_MIN    = int(os.getenv("INTERVALO_MIN", "60"))       # cada cuántos minutos buscar
DATA_FILE        = "alertas_enviadas.json"                     # evita repetir alertas

# Productos a monitorear: (nombre_búsqueda, precio_referencia_CLP)
PRODUCTOS = [
    ("iPhone 16",           900_000),
    ("Samsung TV 65",       500_000),
    ("PlayStation 5",       550_000),
    ("MacBook Air M3",    1_200_000),
    ("AirPods Pro",         200_000),
    ("Samsung Galaxy S25",  800_000),
    ("Nintendo Switch 2",   400_000),
    ("Dyson V15",           600_000),
]
# ──────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("bot.log")]
)
log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-CL,es;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


@dataclass
class Producto:
    nombre: str
    tienda: str
    precio: int
    precio_normal: int
    url: str
    descuento_pct: float = 0.0
    es_error: bool = False
    razon: str = ""

    def id(self) -> str:
        raw = f"{self.tienda}:{self.nombre}:{self.precio}"
        return hashlib.md5(raw.encode()).hexdigest()[:12]


# ─── Scrapers por tienda ──────────────────────────────────────────────────────

def scrape_falabella(query: str, precio_ref: int) -> list[Producto]:
    resultados = []
    try:
        url = f"https://www.falabella.com/falabella-cl/search?Ntt={requests.utils.quote(query)}"
        r = requests.get(url, headers=HEADERS, timeout=12)
        soup = BeautifulSoup(r.text, "html.parser")

        for item in soup.select(".product-card")[:5]:
            try:
                nombre_el = item.select_one(".pod-subTitle, .pod-title")
                precio_el = item.select_one(".copy10, .prices-0")
                link_el   = item.select_one("a[href]")
                if not (nombre_el and precio_el): continue

                nombre = nombre_el.get_text(strip=True)
                precio = limpiar_precio(precio_el.get_text(strip=True))
                link   = "https://www.falabella.com" + link_el["href"] if link_el else url

                if precio and precio > 0:
                    p = crear_producto(nombre, "Falabella", precio, precio_ref, link)
                    resultados.append(p)
            except Exception:
                continue
    except Exception as e:
        log.warning(f"Falabella error: {e}")
    return resultados


def scrape_ripley(query: str, precio_ref: int) -> list[Producto]:
    resultados = []
    try:
        url = f"https://simple.ripley.cl/search?q={requests.utils.quote(query)}"
        r = requests.get(url, headers=HEADERS, timeout=12)
        soup = BeautifulSoup(r.text, "html.parser")

        for item in soup.select(".catalog-item")[:5]:
            try:
                nombre_el = item.select_one(".catalog-item__title, .item-name")
                precio_el = item.select_one(".catalog-prices__offer-price, .item-price")
                link_el   = item.select_one("a[href]")
                if not (nombre_el and precio_el): continue

                nombre = nombre_el.get_text(strip=True)
                precio = limpiar_precio(precio_el.get_text(strip=True))
                link   = "https://simple.ripley.cl" + link_el["href"] if link_el else url

                if precio and precio > 0:
                    p = crear_producto(nombre, "Ripley", precio, precio_ref, link)
                    resultados.append(p)
            except Exception:
                continue
    except Exception as e:
        log.warning(f"Ripley error: {e}")
    return resultados


def scrape_mercadolibre(query: str, precio_ref: int) -> list[Producto]:
    resultados = []
    try:
        url = f"https://listado.mercadolibre.cl/{requests.utils.quote(query.replace(' ','-'))}"
        r = requests.get(url, headers=HEADERS, timeout=12)
        soup = BeautifulSoup(r.text, "html.parser")

        for item in soup.select(".ui-search-result__wrapper")[:5]:
            try:
                nombre_el = item.select_one(".poly-component__title, .ui-search-item__title")
                precio_el = item.select_one(".andes-money-amount__fraction")
                link_el   = item.select_one("a.poly-component__title, a.ui-search-link")
                if not (nombre_el and precio_el): continue

                nombre = nombre_el.get_text(strip=True)
                precio = limpiar_precio(precio_el.get_text(strip=True))
                link   = link_el["href"] if link_el else url

                if precio and precio > 0:
                    p = crear_producto(nombre, "Mercado Libre", precio, precio_ref, link)
                    resultados.append(p)
            except Exception:
                continue
    except Exception as e:
        log.warning(f"MercadoLibre error: {e}")
    return resultados


def scrape_paris(query: str, precio_ref: int) -> list[Producto]:
    resultados = []
    try:
        url = f"https://www.paris.cl/search/?q={requests.utils.quote(query)}"
        r = requests.get(url, headers=HEADERS, timeout=12)
        soup = BeautifulSoup(r.text, "html.parser")

        for item in soup.select(".product-tile, .plp-product-tile")[:5]:
            try:
                nombre_el = item.select_one(".product-name, .tile-product-name")
                precio_el = item.select_one(".sales .value, .price-sales")
                link_el   = item.select_one("a[href]")
                if not (nombre_el and precio_el): continue

                nombre = nombre_el.get_text(strip=True)
                precio = limpiar_precio(precio_el.get_text(strip=True))
                link   = "https://www.paris.cl" + link_el["href"] if link_el else url

                if precio and precio > 0:
                    p = crear_producto(nombre, "Paris", precio, precio_ref, link)
                    resultados.append(p)
            except Exception:
                continue
    except Exception as e:
        log.warning(f"Paris error: {e}")
    return resultados


# ─── Utilidades ───────────────────────────────────────────────────────────────

def limpiar_precio(texto: str) -> Optional[int]:
    """Extrae número entero de un string de precio en CLP."""
    import re
    texto = texto.replace(".", "").replace(",", "").replace("$", "").strip()
    nums = re.findall(r"\d+", texto)
    if nums:
        val = int("".join(nums[:2]))
        # Filtra precios absurdos (< 1000 o > 50M CLP)
        if 1_000 <= val <= 50_000_000:
            return val
    return None


def crear_producto(nombre: str, tienda: str, precio: int, precio_ref: int, url: str) -> Producto:
    descuento = max(0.0, (precio_ref - precio) / precio_ref * 100) if precio_ref else 0.0
    es_error = descuento >= UMBRAL_DESCUENTO
    razon = ""
    if es_error:
        if descuento >= 80:
            razon = f"Precio {descuento:.0f}% bajo referencia — posible error tipográfico"
        elif descuento >= UMBRAL_DESCUENTO:
            razon = f"Descuento de {descuento:.0f}% supera umbral de alerta ({UMBRAL_DESCUENTO}%)"
    return Producto(
        nombre=nombre, tienda=tienda, precio=precio,
        precio_normal=precio_ref, url=url,
        descuento_pct=descuento, es_error=es_error, razon=razon
    )


# ─── Telegram ─────────────────────────────────────────────────────────────────

def enviar_telegram(mensaje: str):
    if TELEGRAM_TOKEN == "TU_TOKEN_AQUI":
        log.info(f"[MODO TEST] Mensaje Telegram:\n{mensaje}")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": mensaje,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }, timeout=10)
        r.raise_for_status()
        log.info("Alerta enviada por Telegram ✓")
    except Exception as e:
        log.error(f"Error enviando Telegram: {e}")


def formatear_alerta(p: Producto) -> str:
    ahorro = p.precio_normal - p.precio
    return (
        f"🚨 <b>POSIBLE ERROR DE PRECIO</b>\n\n"
        f"📦 <b>{p.nombre}</b>\n"
        f"🏪 Tienda: {p.tienda}\n"
        f"💸 Precio actual: <b>${p.precio:,.0f}</b>\n"
        f"📋 Precio referencia: ${p.precio_normal:,.0f}\n"
        f"📉 Descuento: <b>{p.descuento_pct:.0f}%</b> (ahorras ${ahorro:,.0f})\n"
        f"⚠️ {p.razon}\n\n"
        f"🔗 <a href='{p.url}'>Ver producto ahora →</a>\n\n"
        f"⏰ {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    )


# ─── Control de duplicados ────────────────────────────────────────────────────

def cargar_alertas() -> set:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            return set(json.load(f))
    return set()


def guardar_alerta(alerta_id: str, alertas: set):
    alertas.add(alerta_id)
    # Mantener solo últimas 500 alertas
    lista = list(alertas)[-500:]
    with open(DATA_FILE, "w") as f:
        json.dump(lista, f)


# ─── Ciclo principal ──────────────────────────────────────────────────────────

def run_scan():
    log.info(f"=== Iniciando escaneo ({datetime.now().strftime('%H:%M:%S')}) ===")
    alertas_enviadas = cargar_alertas()
    nuevas_alertas = 0

    for query, precio_ref in PRODUCTOS:
        log.info(f"Buscando: {query}")
        todos = []
        todos += scrape_falabella(query, precio_ref)
        todos += scrape_ripley(query, precio_ref)
        todos += scrape_mercadolibre(query, precio_ref)
        todos += scrape_paris(query, precio_ref)

        errores = [p for p in todos if p.es_error]
        log.info(f"  → {len(todos)} resultados, {len(errores)} posibles errores")

        for p in errores:
            pid = p.id()
            if pid not in alertas_enviadas:
                mensaje = formatear_alerta(p)
                enviar_telegram(mensaje)
                guardar_alerta(pid, alertas_enviadas)
                nuevas_alertas += 1
                time.sleep(2)  # evitar spam

        time.sleep(3)  # pausa entre productos

    log.info(f"=== Escaneo completo. {nuevas_alertas} nuevas alertas enviadas ===\n")


def main():
    log.info("🤖 Bot Cazador de Precios iniciado")
    log.info(f"   Umbral de descuento: {UMBRAL_DESCUENTO}%")
    log.info(f"   Intervalo: cada {INTERVALO_MIN} minutos")
    log.info(f"   Productos monitoreados: {len(PRODUCTOS)}")

    # Primer escaneo inmediato
    run_scan()

    # Programar escaneos periódicos
    schedule.every(INTERVALO_MIN).minutes.do(run_scan)

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
