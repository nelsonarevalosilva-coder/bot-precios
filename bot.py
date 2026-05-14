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
    # Tecnología
    ("iPhone 16",                    900_000),
    ("iPhone 15",                    750_000),
    ("Samsung Galaxy S25",           800_000),
    ("MacBook Air M3",             1_200_000),
    ("MacBook Pro M3",             1_800_000),
    ("iPad Pro",                     800_000),
    ("AirPods Pro",                  200_000),
    ("PlayStation 5",                550_000),
    ("Nintendo Switch 2",            400_000),
    ("Samsung TV 65 QLED",           600_000),
    ("LG TV 55 OLED",                700_000),
    ("Samsung TV 50",                350_000),
    ("Dyson V15",                    600_000),
    ("Dyson V12",                    450_000),

    # Muebles - Sillas
    ("silla escritorio gamer",       150_000),
    ("silla oficina ergonomica",     200_000),
    ("silla comedor",                 80_000),
    ("silla plastica apilable",       15_000),
    ("silla mecedora",               120_000),
    ("silla plegable",                25_000),

    # Muebles - Sillones y sofás
    ("sillon individual",            200_000),
    ("sofa 3 cuerpos",               400_000),
    ("sofa cama",                    350_000),
    ("sillon reclinable",            250_000),
    ("sofa esquinero",               600_000),
    ("sillon lactancia",             150_000),

    # Muebles - Camas y dormitorio
    ("cama 2 plazas",                300_000),
    ("cama plaza y media",           200_000),
    ("cama king",                    500_000),
    ("camarote niños",               250_000),
    ("velador",                       60_000),
    ("comoda cajones",               150_000),
    ("closet 4 puertas",             400_000),
    ("colchon 2 plazas",             300_000),
    ("colchon king",                 500_000),
    ("almohada memory foam",          40_000),

    # Muebles - Mesas
    ("mesa comedor 6 personas",      300_000),
    ("mesa centro living",           100_000),
    ("mesa escritorio",              120_000),
    ("mesa noche",                    50_000),
    ("mesa jardin plastico",          40_000),
    ("mesa plegable",                 60_000),

    # Electrohogar - Cocina
    ("refrigerador no frost",        500_000),
    ("lavadora 10 kilos",            350_000),
    ("lavavajillas",                 400_000),
    ("microondas",                    80_000),
    ("cocina 4 platos",              300_000),
    ("horno empotrado",              400_000),
    ("cafetera",                      60_000),
    ("licuadora",                     40_000),
    ("freidora aire",                 80_000),
    ("aspiradora robot",             200_000),

    # Electrohogar - Climatización
    ("aire acondicionado split",     500_000),
    ("calefactor electrico",          80_000),
    ("ventilador torre",              60_000),
    ("purificador aire",             150_000),
    ("deshumidificador",             200_000),

    # Herramientas y jardín
    ("taladro percutor",              80_000),
    ("sierra circular",              120_000),
    ("cortacesped electrico",        150_000),
    ("manguera jardín",               20_000),
    ("estante metalico",              60_000),
    ("escalera aluminio",             80_000),

    # Deportes
    ("bicicleta montaña",            300_000),
    ("bicicleta electrica",        1_000_000),
    ("cinta correr",                 500_000),
    ("banca pesas",                  150_000),
    ("mancuernas ajustables",         80_000),
    ("colchoneta yoga",               20_000),

    # Bebé y niños
    ("coche bebe",                   200_000),
    ("cuna bebe",                    150_000),
    ("silla alta bebe",               80_000),
    ("andador bebe",                  50_000),

    # Ropa y calzado
    ("zapatillas Nike",               80_000),
    ("zapatillas Adidas",             80_000),
    ("zapatillas New Balance",        90_000),
    ("chaqueta polar",                40_000),
    ("parka invierno",               100_000),
    # Perfumes Hombre
    ("perfume Dior Sauvage",         120_000),
    ("perfume Bleu de Chanel",       130_000),
    ("perfume Acqua di Gio",         100_000),
    ("perfume 212 Men Carolina Herrera", 90_000),
    ("perfume Polo Ralph Lauren",     80_000),
    ("perfume Hugo Boss Bottled",     80_000),
    ("perfume Paco Rabanne 1 Million", 100_000),
    ("perfume Invictus Paco Rabanne", 100_000),
    ("perfume Versace Eros",          90_000),
    ("perfume Armani Code",           110_000),
    ("perfume Jean Paul Gaultier Le Male", 95_000),
    ("perfume Burberry Her",          85_000),
    ("perfume Dolce Gabbana Light Blue hombre", 90_000),
    ("perfume Yves Saint Laurent Y",  110_000),
    ("perfume Givenchy Gentleman",    100_000),

    # Perfumes Mujer
    ("perfume Chanel N5",            150_000),
    ("perfume Coco Mademoiselle",    140_000),
    ("perfume Miss Dior",            120_000),
    ("perfume Good Girl Carolina Herrera", 100_000),
    ("perfume 212 VIP Carolina Herrera", 95_000),
    ("perfume Lancôme La Vie Est Belle", 110_000),
    ("perfume Dolce Gabbana Light Blue mujer", 90_000),
    ("perfume Viktor Rolf Flowerbomb", 130_000),
    ("perfume Versace Bright Crystal", 85_000),
    ("perfume Yves Saint Laurent Black Opium", 110_000),
    ("perfume Gucci Bloom",          100_000),
    ("perfume Paco Rabanne Olympea",  95_000),
    ("perfume Narciso Rodriguez For Her", 105_000),
    ("perfume Jimmy Choo",            80_000),
    ("perfume Thierry Mugler Angel", 120_000),
    ("perfume Marc Jacobs Daisy",     90_000),
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
def scrape_lider(query: str, precio_ref: int) -> list[Producto]:
    resultados = []
    try:
        url = f"https://www.lider.cl/catalogo/search?q={requests.utils.quote(query)}"
        r = requests.get(url, headers=HEADERS, timeout=12)
        soup = BeautifulSoup(r.text, "html.parser")
        for item in soup.select(".product-card, .shelf-item")[:5]:
            try:
                nombre_el = item.select_one(".product-card__name, .shelf-item__title")
                precio_el = item.select_one(".product-card__price, .shelf-item__price")
                link_el   = item.select_one("a[href]")
                if not (nombre_el and precio_el): continue
                nombre = nombre_el.get_text(strip=True)
                precio = limpiar_precio(precio_el.get_text(strip=True))
                link   = "https://www.lider.cl" + link_el["href"] if link_el else url
                if precio and precio > 0:
                    resultados.append(crear_producto(nombre, "Lider", precio, precio_ref, link))
            except Exception:
                continue
    except Exception as e:
        log.warning(f"Lider error: {e}")
    return resultados


def scrape_sodimac(query: str, precio_ref: int) -> list[Producto]:
    resultados = []
    try:
        url = f"https://www.sodimac.cl/sodimac-cl/search?Ntt={requests.utils.quote(query)}"
        r = requests.get(url, headers=HEADERS, timeout=12)
        soup = BeautifulSoup(r.text, "html.parser")
        for item in soup.select(".product-card, .pod")[:5]:
            try:
                nombre_el = item.select_one(".product-card__name, .pod-subTitle")
                precio_el = item.select_one(".product-card__price, .price")
                link_el   = item.select_one("a[href]")
                if not (nombre_el and precio_el): continue
                nombre = nombre_el.get_text(strip=True)
                precio = limpiar_precio(precio_el.get_text(strip=True))
                link   = "https://www.sodimac.cl" + link_el["href"] if link_el else url
                if precio and precio > 0:
                    resultados.append(crear_producto(nombre, "Sodimac", precio, precio_ref, link))
            except Exception:
                continue
    except Exception as e:
        log.warning(f"Sodimac error: {e}")
    return resultados


def scrape_easy(query: str, precio_ref: int) -> list[Producto]:
    resultados = []
    try:
        url = f"https://www.easy.cl/tienda/search?q={requests.utils.quote(query)}"
        r = requests.get(url, headers=HEADERS, timeout=12)
        soup = BeautifulSoup(r.text, "html.parser")
        for item in soup.select(".product-card, .shelf-item")[:5]:
            try:
                nombre_el = item.select_one(".product-name, .shelf-item__title")
                precio_el = item.select_one(".price-best, .shelf-item__price")
                link_el   = item.select_one("a[href]")
                if not (nombre_el and precio_el): continue
                nombre = nombre_el.get_text(strip=True)
                precio = limpiar_precio(precio_el.get_text(strip=True))
                link   = "https://www.easy.cl" + link_el["href"] if link_el else url
                if precio and precio > 0:
                    resultados.append(crear_producto(nombre, "Easy", precio, precio_ref, link))
            except Exception:
                continue
    except Exception as e:
        log.warning(f"Easy error: {e}")
    return resultados


def scrape_hites(query: str, precio_ref: int) -> list[Producto]:
    resultados = []
    try:
        url = f"https://www.hites.com/search?q={requests.utils.quote(query)}"
        r = requests.get(url, headers=HEADERS, timeout=12)
        soup = BeautifulSoup(r.text, "html.parser")
        for item in soup.select(".product-item, .product-card")[:5]:
            try:
                nombre_el = item.select_one(".product-item-name, .product-name")
                precio_el = item.select_one(".price, .product-price")
                link_el   = item.select_one("a[href]")
                if not (nombre_el and precio_el): continue
                nombre = nombre_el.get_text(strip=True)
                precio = limpiar_precio(precio_el.get_text(strip=True))
                link   = "https://www.hites.com" + link_el["href"] if link_el else url
                if precio and precio > 0:
                    resultados.append(crear_producto(nombre, "Hites", precio, precio_ref, link))
            except Exception:
                continue
    except Exception as e:
        log.warning(f"Hites error: {e}")
    return resultados


def scrape_lapolar(query: str, precio_ref: int) -> list[Producto]:
    resultados = []
    try:
        url = f"https://www.lapolar.cl/search?q={requests.utils.quote(query)}"
        r = requests.get(url, headers=HEADERS, timeout=12)
        soup = BeautifulSoup(r.text, "html.parser")
        for item in soup.select(".product-card, .product-item")[:5]:
            try:
                nombre_el = item.select_one(".product-card__name, .product-name")
                precio_el = item.select_one(".product-card__price, .price")
                link_el   = item.select_one("a[href]")
                if not (nombre_el and precio_el): continue
                nombre = nombre_el.get_text(strip=True)
                precio = limpiar_precio(precio_el.get_text(strip=True))
                link   = "https://www.lapolar.cl" + link_el["href"] if link_el else url
                if precio and precio > 0:
                    resultados.append(crear_producto(nombre, "La Polar", precio, precio_ref, link))
            except Exception:
                continue
    except Exception as e:
        log.warning(f"La Polar error: {e}")
    return resultados


def scrape_jumbo(query: str, precio_ref: int) -> list[Producto]:
    resultados = []
    try:
        url = f"https://www.jumbo.cl/search?q={requests.utils.quote(query)}"
        r = requests.get(url, headers=HEADERS, timeout=12)
        soup = BeautifulSoup(r.text, "html.parser")
        for item in soup.select(".product-item, .shelf-item")[:5]:
            try:
                nombre_el = item.select_one(".product-item__name, .shelf-item__title")
                precio_el = item.select_one(".product-item__price, .shelf-item__price")
                link_el   = item.select_one("a[href]")
                if not (nombre_el and precio_el): continue
                nombre = nombre_el.get_text(strip=True)
                precio = limpiar_precio(precio_el.get_text(strip=True))
                link   = "https://www.jumbo.cl" + link_el["href"] if link_el else url
                if precio and precio > 0:
                    resultados.append(crear_producto(nombre, "Jumbo", precio, precio_ref, link))
            except Exception:
                continue
    except Exception as e:
        log.warning(f"Jumbo error: {e}")
    return resultados


def scrape_dafiti(query: str, precio_ref: int) -> list[Producto]:
    resultados = []
    try:
        url = f"https://www.dafiti.cl/catalog/?q={requests.utils.quote(query)}"
        r = requests.get(url, headers=HEADERS, timeout=12)
        soup = BeautifulSoup(r.text, "html.parser")
        for item in soup.select(".catalog-grid__item, .product-card")[:5]:
            try:
                nombre_el = item.select_one(".product-card__name, .catalog-grid__name")
                precio_el = item.select_one(".catalog-grid__price, .product-card__price")
                link_el   = item.select_one("a[href]")
                if not (nombre_el and precio_el): continue
                nombre = nombre_el.get_text(strip=True)
                precio = limpiar_precio(precio_el.get_text(strip=True))
                link   = link_el["href"] if link_el else url
                if precio and precio > 0:
                    resultados.append(crear_producto(nombre, "Dafiti", precio, precio_ref, link))
            except Exception:
                continue
    except Exception as e:
        log.warning(f"Dafiti error: {e}")
    return resultados


def scrape_perfumeria_europea(query: str, precio_ref: int) -> list[Producto]:
    resultados = []
    try:
        url = f"https://www.perfumeriaeuropea.cl/search?q={requests.utils.quote(query)}"
        r = requests.get(url, headers=HEADERS, timeout=12)
        soup = BeautifulSoup(r.text, "html.parser")
        for item in soup.select(".product-item, .grid__item")[:5]:
            try:
                nombre_el = item.select_one(".product-item__title, .grid-product__title")
                precio_el = item.select_one(".product-item__price, .grid-product__price")
                link_el   = item.select_one("a[href]")
                if not (nombre_el and precio_el): continue
                nombre = nombre_el.get_text(strip=True)
                precio = limpiar_precio(precio_el.get_text(strip=True))
                link   = "https://www.perfumeriaeuropea.cl" + link_el["href"] if link_el else url
                if precio and precio > 0:
                    resultados.append(crear_producto(nombre, "Perfumería Europea", precio, precio_ref, link))
            except Exception:
                continue
    except Exception as e:
        log.warning(f"Perfumería Europea error: {e}")
    return resultados


def scrape_tricot(query: str, precio_ref: int) -> list[Producto]:
    resultados = []
    try:
        url = f"https://www.tricot.cl/search?q={requests.utils.quote(query)}"
        r = requests.get(url, headers=HEADERS, timeout=12)
        soup = BeautifulSoup(r.text, "html.parser")
        for item in soup.select(".product-item, .product-card")[:5]:
            try:
                nombre_el = item.select_one(".product-item-name, .product-card__name")
                precio_el = item.select_one(".price, .product-card__price")
                link_el   = item.select_one("a[href]")
                if not (nombre_el and precio_el): continue
                nombre = nombre_el.get_text(strip=True)
                precio = limpiar_precio(precio_el.get_text(strip=True))
                link   = "https://www.tricot.cl" + link_el["href"] if link_el else url
                if precio and precio > 0:
                    resultados.append(crear_producto(nombre, "Tricot", precio, precio_ref, link))
            except Exception:
                continue
    except Exception as e:
        log.warning(f"Tricot error: {e}")
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
        todos += scrape_falabella(query, precio_ref)
        todos += scrape_ripley(query, precio_ref)
        todos += scrape_mercadolibre(query, precio_ref)
        todos += scrape_paris(query, precio_ref)
        todos += scrape_lider(query, precio_ref)
        todos += scrape_sodimac(query, precio_ref)
        todos += scrape_easy(query, precio_ref)
        todos += scrape_hites(query, precio_ref)
        todos += scrape_lapolar(query, precio_ref)
        todos += scrape_jumbo(query, precio_ref)
        todos += scrape_dafiti(query, precio_ref)
        todos += scrape_perfumeria_europea(query, precio_ref)
        todos += scrape_tricot(query, precio_ref)

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



