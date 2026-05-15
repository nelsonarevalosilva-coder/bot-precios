import os
import time
import logging
import json
import hashlib
import requests
from datetime import datetime
from dataclasses import dataclass
from typing import Optional
import schedule

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN", "TU_TOKEN_AQUI")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "TU_CHAT_ID_AQUI")
UMBRAL_DESCUENTO = int(os.getenv("UMBRAL_DESCUENTO", "40"))
INTERVALO_MIN    = int(os.getenv("INTERVALO_MIN", "30"))
DATA_FILE        = "alertas_enviadas.json"

PRODUCTOS = [
    ("Fragrance World Liquid Brun EDP 100 ML (H)", 60_000),
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
    ("silla escritorio gamer",       150_000),
    ("silla oficina ergonomica",     200_000),
    ("silla comedor",                 80_000),
    ("silla plegable",                25_000),
    ("sillon individual",            200_000),
    ("sofa 3 cuerpos",               400_000),
    ("sofa cama",                    350_000),
    ("sillon reclinable",            250_000),
    ("sofa esquinero",               600_000),
    ("cama 2 plazas",                300_000),
    ("cama king",                    500_000),
    ("camarote ninos",               250_000),
    ("colchon 2 plazas",             300_000),
    ("colchon king",                 500_000),
    ("closet 4 puertas",             400_000),
    ("comoda cajones",               150_000),
    ("mesa comedor 6 personas",      300_000),
    ("mesa centro living",           100_000),
    ("mesa escritorio",              120_000),
    ("refrigerador no frost",        500_000),
    ("lavadora 10 kilos",            350_000),
    ("microondas",                    80_000),
    ("cocina 4 platos",              300_000),
    ("freidora aire",                 80_000),
    ("aspiradora robot",             200_000),
    ("aire acondicionado split",     500_000),
    ("bicicleta montana",            300_000),
    ("bicicleta electrica",        1_000_000),
    ("cinta correr",                 500_000),
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
    ("perfume Chanel N5",            150_000),
    ("perfume Coco Mademoiselle",    140_000),
    ("perfume Miss Dior",            120_000),
    ("perfume Good Girl Carolina Herrera", 100_000),
    ("perfume 212 VIP Carolina Herrera", 95_000),
    ("perfume Lancome La Vie Est Belle", 110_000),
    ("perfume Dolce Gabbana Light Blue", 90_000),
    ("perfume Viktor Rolf Flowerbomb", 130_000),
    ("perfume Versace Bright Crystal", 85_000),
    ("perfume Yves Saint Laurent Black Opium", 110_000),
    ("perfume Gucci Bloom",          100_000),
    ("perfume Paco Rabanne Olympea",  95_000),
    ("perfume Narciso Rodriguez",    105_000),
    ("perfume Marc Jacobs Daisy",     90_000),
    ("zapatillas Nike",               80_000),
    ("zapatillas Adidas",             80_000),
    ("zapatillas New Balance",        90_000),
    ("parka invierno",               100_000),
]

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", handlers=[logging.StreamHandler()])
log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "es-CL,es;q=0.9",
    "Accept": "application/json, text/html, */*",
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

    def id(self):
        raw = f"{self.tienda}:{self.nombre}:{self.precio}"
        return hashlib.md5(raw.encode()).hexdigest()[:12]


def limpiar_precio(texto: str) -> Optional[int]:
    import re
    texto = str(texto).replace(".", "").replace(",", "").replace("$", "").strip()
    nums = re.findall(r"\d+", texto)
    if nums:
        val = int("".join(nums[:2]))
        if 1_000 <= val <= 50_000_000:
            return val
    return None


def crear_producto(nombre, tienda, precio, precio_ref, url):
    descuento = max(0.0, (precio_ref - precio) / precio_ref * 100) if precio_ref else 0.0
    es_error = descuento >= UMBRAL_DESCUENTO
    razon = ""
    if es_error:
        if descuento >= 80:
            razon = f"Precio {descuento:.0f}% bajo referencia - posible error tipografico"
        else:
            razon = f"Descuento de {descuento:.0f}% supera umbral ({UMBRAL_DESCUENTO}%)"
    return Producto(nombre=nombre, tienda=tienda, precio=precio, precio_normal=precio_ref, url=url, descuento_pct=descuento, es_error=es_error, razon=razon)


# ── Falabella API ─────────────────────────────────────────────────────────────
def scrape_falabella(query, precio_ref):
    resultados = []
    try:
        url = f"https://www.falabella.com/s/browse/v1/listing/cl?zone=13&store=falabella&currentPage=1&sortBy=relevance&query={requests.utils.quote(query)}"
        r = requests.get(url, headers=HEADERS, timeout=12)
        data = r.json()
        items = data.get("data", {}).get("results", [])
        for item in items[:5]:
            try:
                nombre = item.get("displayName", "")
                precios = item.get("prices", [])
                precio = None
                for p in precios:
                    if p.get("type") in ("offerPrice", "normalPrice"):
                        precio = limpiar_precio(str(p.get("price", 0)))
                        if precio:
                            break
                link = "https://www.falabella.com/falabella-cl/product/" + item.get("productId", "")
                if nombre and precio:
                    resultados.append(crear_producto(nombre, "Falabella", precio, precio_ref, link))
            except Exception:
                continue
    except Exception as e:
        log.warning(f"Falabella error: {e}")
    return resultados


# ── Ripley API ────────────────────────────────────────────────────────────────
def scrape_ripley(query, precio_ref):
    resultados = []
    try:
        url = f"https://simple.ripley.cl/api/search?q={requests.utils.quote(query)}&page=1&limit=5"
        r = requests.get(url, headers=HEADERS, timeout=12)
        data = r.json()
        items = data.get("products", data.get("items", []))
        for item in items[:5]:
            try:
                nombre = item.get("name", item.get("displayName", ""))
                precio = limpiar_precio(str(item.get("offerPrice", item.get("price", 0))))
                link = "https://simple.ripley.cl" + item.get("url", "")
                if nombre and precio:
                    resultados.append(crear_producto(nombre, "Ripley", precio, precio_ref, link))
            except Exception:
                continue
    except Exception as e:
        log.warning(f"Ripley error: {e}")
    return resultados


# ── Paris API ─────────────────────────────────────────────────────────────────
def scrape_paris(query, precio_ref):
    resultados = []
    try:
        url = f"https://www.paris.cl/api/catalog_system/pub/products/search/{requests.utils.quote(query)}?_from=0&_to=4"
        r = requests.get(url, headers=HEADERS, timeout=12)
        data = r.json()
        for item in data[:5]:
            try:
                nombre = item.get("productName", "")
                items_list = item.get("items", [])
                precio = None
                link = f"https://www.paris.cl/{item.get('linkText', '')}/p"
                for it in items_list:
                    for seller in it.get("sellers", []):
                        p = seller.get("commertialOffer", {}).get("Price", 0)
                        if p:
                            precio = limpiar_precio(str(p))
                            break
                    if precio:
                        break
                if nombre and precio:
                    resultados.append(crear_producto(nombre, "Paris", precio, precio_ref, link))
            except Exception:
                continue
    except Exception as e:
        log.warning(f"Paris error: {e}")
    return resultados


# ── Mercado Libre API ─────────────────────────────────────────────────────────
def scrape_mercadolibre(query, precio_ref):
    resultados = []
    try:
        url = f"https://api.mercadolibre.com/sites/MLC/search?q={requests.utils.quote(query)}&limit=5"
        r = requests.get(url, headers=HEADERS, timeout=12)
        data = r.json()
        for item in data.get("results", [])[:5]:
            try:
                nombre = item.get("title", "")
                precio = limpiar_precio(str(item.get("price", 0)))
                link = item.get("permalink", "")
                if nombre and precio:
                    resultados.append(crear_producto(nombre, "Mercado Libre", precio, precio_ref, link))
            except Exception:
                continue
    except Exception as e:
        log.warning(f"MercadoLibre error: {e}")
    return resultados


# ── Lider API ─────────────────────────────────────────────────────────────────
def scrape_lider(query, precio_ref):
    resultados = []
    try:
        url = f"https://www.lider.cl/api/catalog_system/pub/products/search/{requests.utils.quote(query)}?_from=0&_to=4"
        r = requests.get(url, headers=HEADERS, timeout=12)
        data = r.json()
        for item in data[:5]:
            try:
                nombre = item.get("productName", "")
                link = f"https://www.lider.cl/{item.get('linkText', '')}/p"
                precio = None
                for it in item.get("items", []):
                    for seller in it.get("sellers", []):
                        p = seller.get("commertialOffer", {}).get("Price", 0)
                        if p:
                            precio = limpiar_precio(str(p))
                            break
                    if precio:
                        break
                if nombre and precio:
                    resultados.append(crear_producto(nombre, "Lider", precio, precio_ref, link))
            except Exception:
                continue
    except Exception as e:
        log.warning(f"Lider error: {e}")
    return resultados


# ── Sodimac API ───────────────────────────────────────────────────────────────
def scrape_sodimac(query, precio_ref):
    resultados = []
    try:
        url = f"https://www.sodimac.cl/sodimac-cl/search?Ntt={requests.utils.quote(query)}&start=0&sz=5&format=json"
        r = requests.get(url, headers=HEADERS, timeout=12)
        data = r.json()
        items = data.get("results", {}).get("products", [])
        for item in items[:5]:
            try:
                nombre = item.get("displayName", item.get("name", ""))
                precio = limpiar_precio(str(item.get("offerPrice", item.get("price", 0))))
                link = "https://www.sodimac.cl" + item.get("url", "")
                if nombre and precio:
                    resultados.append(crear_producto(nombre, "Sodimac", precio, precio_ref, link))
            except Exception:
                continue
    except Exception as e:
        log.warning(f"Sodimac error: {e}")
    return resultados


# ── Easy API ──────────────────────────────────────────────────────────────────
def scrape_easy(query, precio_ref):
    resultados = []
    try:
        url = f"https://www.easy.cl/api/catalog_system/pub/products/search/{requests.utils.quote(query)}?_from=0&_to=4"
        r = requests.get(url, headers=HEADERS, timeout=12)
        data = r.json()
        for item in data[:5]:
            try:
                nombre = item.get("productName", "")
                link = f"https://www.easy.cl/{item.get('linkText', '')}/p"
                precio = None
                for it in item.get("items", []):
                    for seller in it.get("sellers", []):
                        p = seller.get("commertialOffer", {}).get("Price", 0)
                        if p:
                            precio = limpiar_precio(str(p))
                            break
                    if precio:
                        break
                if nombre and precio:
                    resultados.append(crear_producto(nombre, "Easy", precio, precio_ref, link))
            except Exception:
                continue
    except Exception as e:
        log.warning(f"Easy error: {e}")
    return resultados


# ── Hites API ─────────────────────────────────────────────────────────────────
def scrape_hites(query, precio_ref):
    resultados = []
    try:
        url = f"https://www.hites.com/api/catalog_system/pub/products/search/{requests.utils.quote(query)}?_from=0&_to=4"
        r = requests.get(url, headers=HEADERS, timeout=12)
        data = r.json()
        for item in data[:5]:
            try:
                nombre = item.get("productName", "")
                link = f"https://www.hites.com/{item.get('linkText', '')}/p"
                precio = None
                for it in item.get("items", []):
                    for seller in it.get("sellers", []):
                        p = seller.get("commertialOffer", {}).get("Price", 0)
                        if p:
                            precio = limpiar_precio(str(p))
                            break
                    if precio:
                        break
                if nombre and precio:
                    resultados.append(crear_producto(nombre, "Hites", precio, precio_ref, link))
            except Exception:
                continue
    except Exception as e:
        log.warning(f"Hites error: {e}")
    return resultados


# ── La Polar API ──────────────────────────────────────────────────────────────
def scrape_lapolar(query, precio_ref):
    resultados = []
    try:
        url = f"https://www.lapolar.cl/api/catalog_system/pub/products/search/{requests.utils.quote(query)}?_from=0&_to=4"
        r = requests.get(url, headers=HEADERS, timeout=12)
        data = r.json()
        for item in data[:5]:
            try:
                nombre = item.get("productName", "")
                link = f"https://www.lapolar.cl/{item.get('linkText', '')}/p"
                precio = None
                for it in item.get("items", []):
                    for seller in it.get("sellers", []):
                        p = seller.get("commertialOffer", {}).get("Price", 0)
                        if p:
                            precio = limpiar_precio(str(p))
                            break
                    if precio:
                        break
                if nombre and precio:
                    resultados.append(crear_producto(nombre, "La Polar", precio, precio_ref, link))
            except Exception:
                continue
    except Exception as e:
        log.warning(f"La Polar error: {e}")
    return resultados


# ── Jumbo API ─────────────────────────────────────────────────────────────────
def scrape_jumbo(query, precio_ref):
    resultados = []
    try:
        url = f"https://www.jumbo.cl/api/catalog_system/pub/products/search/{requests.utils.quote(query)}?_from=0&_to=4"
        r = requests.get(url, headers=HEADERS, timeout=12)
        data = r.json()
        for item in data[:5]:
            try:
                nombre = item.get("productName", "")
                link = f"https://www.jumbo.cl/{item.get('linkText', '')}/p"
                precio = None
                for it in item.get("items", []):
                    for seller in it.get("sellers", []):
                        p = seller.get("commertialOffer", {}).get("Price", 0)
                        if p:
                            precio = limpiar_precio(str(p))
                            break
                    if precio:
                        break
                if nombre and precio:
                    resultados.append(crear_producto(nombre, "Jumbo", precio, precio_ref, link))
            except Exception:
                continue
    except Exception as e:
        log.warning(f"Jumbo error: {e}")
    return resultados


# ── Dafiti API ────────────────────────────────────────────────────────────────
def scrape_dafiti(query, precio_ref):
    resultados = []
    try:
        url = f"https://www.dafiti.cl/catalog/?q={requests.utils.quote(query)}&page=1&ajaxCall=1"
        r = requests.get(url, headers=HEADERS, timeout=12)
        data = r.json()
        items = data.get("products", {}).get("hits", [])
        for item in items[:5]:
            try:
                nombre = item.get("name", "")
                precio = limpiar_precio(str(item.get("price", 0)))
                link = item.get("url", "https://www.dafiti.cl")
                if nombre and precio:
                    resultados.append(crear_producto(nombre, "Dafiti", precio, precio_ref, link))
            except Exception:
                continue
    except Exception as e:
        log.warning(f"Dafiti error: {e}")
    return resultados


# ── Tricot API ────────────────────────────────────────────────────────────────
def scrape_tricot(query, precio_ref):
    resultados = []
    try:
        url = f"https://www.tricot.cl/search/suggest.json?q={requests.utils.quote(query)}&resources[type]=product&resources[limit]=5"
        r = requests.get(url, headers=HEADERS, timeout=12)
        data = r.json()
        productos = data.get("resources", {}).get("results", {}).get("products", [])
        for item in productos:
            try:
                nombre = item.get("title", "")
                precio = limpiar_precio(str(int(float(item.get("price", "0").replace(",", "."))) // 100))
                handle = item.get("handle", "")
                link = f"https://www.tricot.cl/products/{handle}"
                if nombre and precio:
                    resultados.append(crear_producto(nombre, "Tricot", precio, precio_ref, link))
            except Exception:
                continue
    except Exception as e:
        log.warning(f"Tricot error: {e}")
    return resultados


# ── Elite Perfumes API (Shopify) ──────────────────────────────────────────────
def scrape_eliteperfumes(query, precio_ref):
    resultados = []
    try:
        url = f"https://www.eliteperfumes.cl/search/suggest.json?q={requests.utils.quote(query)}&resources[type]=product&resources[limit]=5"
        r = requests.get(url, headers=HEADERS, timeout=12)
        data = r.json()
        productos = data.get("resources", {}).get("results", {}).get("products", [])
        for item in productos:
            try:
                nombre = item.get("title", "")
                precio = limpiar_precio(str(int(float(item.get("price", "0").replace(",", "."))) // 100))
                handle = item.get("handle", "")
                link = f"https://www.eliteperfumes.cl/products/{handle}"
                if nombre and precio:
                    resultados.append(crear_producto(nombre, "Elite Perfumes", precio, precio_ref, link))
            except Exception:
                continue
    except Exception as e:
        log.warning(f"Elite Perfumes error: {e}")
    return resultados


# ── Telegram ──────────────────────────────────────────────────────────────────
def enviar_telegram(mensaje):
    if TELEGRAM_TOKEN == "TU_TOKEN_AQUI":
        log.info(f"[MODO TEST] {mensaje}")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": mensaje, "parse_mode": "HTML", "disable_web_page_preview": False}, timeout=10)
        r.raise_for_status()
        log.info("Alerta enviada por Telegram")
    except Exception as e:
        log.error(f"Error enviando Telegram: {e}")


def formatear_alerta(p):
    ahorro = p.precio_normal - p.precio
    return (
        f"Posible ERROR DE PRECIO\n\n"
        f"Producto: <b>{p.nombre}</b>\n"
        f"Tienda: {p.tienda}\n"
        f"Precio actual: <b>${p.precio:,.0f}</b>\n"
        f"Precio referencia: ${p.precio_normal:,.0f}\n"
        f"Descuento: <b>{p.descuento_pct:.0f}%</b> (ahorras ${ahorro:,.0f})\n"
        f"{p.razon}\n\n"
        f"<a href='{p.url}'>Ver producto ahora</a>\n\n"
        f"{datetime.now().strftime('%d/%m/%Y %H:%M')}"
    )


def cargar_alertas():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            return set(json.load(f))
    return set()


def guardar_alerta(alerta_id, alertas):
    alertas.add(alerta_id)
    lista = list(alertas)[-500:]
    with open(DATA_FILE, "w") as f:
        json.dump(lista, f)


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
        todos += scrape_lider(query, precio_ref)
        todos += scrape_sodimac(query, precio_ref)
        todos += scrape_easy(query, precio_ref)
        todos += scrape_hites(query, precio_ref)
        todos += scrape_lapolar(query, precio_ref)
        todos += scrape_jumbo(query, precio_ref)
        todos += scrape_dafiti(query, precio_ref)
        todos += scrape_tricot(query, precio_ref)
        todos += scrape_eliteperfumes(query, precio_ref)

        errores = [p for p in todos if p.es_error]
        log.info(f"  -> {len(todos)} resultados, {len(errores)} posibles errores")

        for p in errores:
            pid = p.id()
            if pid not in alertas_enviadas:
                enviar_telegram(formatear_alerta(p))
                guardar_alerta(pid, alertas_enviadas)
                nuevas_alertas += 1
                time.sleep(2)

        time.sleep(2)

    log.info(f"=== Escaneo completo. {nuevas_alertas} nuevas alertas ===")


def main():
    log.info("Bot Cazador de Precios iniciado")
    log.info(f"   Umbral de descuento: {UMBRAL_DESCUENTO}%")
    log.info(f"   Intervalo: cada {INTERVALO_MIN} minutos")
    log.info(f"   Productos monitoreados: {len(PRODUCTOS)}")

    enviar_telegram(
        "Bot Cazador de Precios activo\n\n"
        f"Monitoreando {len(PRODUCTOS)} productos en 13 tiendas\n"
        f"Umbral de alerta: {UMBRAL_DESCUENTO}% de descuento\n"
        f"Escaneo cada {INTERVALO_MIN} minutos\n\n"
        "Recibiras alertas aqui cuando se detecte un error de precio."
    )

    run_scan()
    schedule.every(INTERVALO_MIN).minutes.do(run_scan)

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
