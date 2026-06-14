"""
Scraper para Mercado Libre Chile — Playwright + BeautifulSoup.
Carga /ofertas con Playwright (JS renderizado) y extrae productos
del HTML con BeautifulSoup. No requiere credenciales de API.

Estructura de precio en el HTML:
  <s aria-label="Antes: 72318 pesos chilenos">...</s>        <- normal
  <span aria-label="Ahora: 34099 pesos chilenos">...</span>  <- oferta
  <span class="poly-price__disc_label">52% OFF</span>        <- descuento
"""
import logging
import re
import time
from dataclasses import dataclass

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

try:
    from playwright_stealth import stealth_sync
    _HAS_STEALTH = True
except ImportError:
    _HAS_STEALTH = False

BASE_URL = "https://www.mercadolibre.cl"

# Keywords del titulo -> canal (coincide con CATEGORY_KEYWORDS del notifier)
_TITLE_KEYWORDS = [
    (["zapatilla", "zapato", "tenis", "sneaker", "calzado", "bototo", "bota"],   "zapatillas"),
    (["celular", "smartphone", "iphone", "samsung", "notebook", "laptop",
      "computador", "tablet", "monitor", "teclado", "mouse", "webcam",
      "auricular", "audifonos", "parlante", "disco duro", "ssd", "ram",
      "tarjeta grafica", "impresora", "router", "switch", "cargador"], "tecnologia"),
    (["consola", "playstation", "xbox", "nintendo", "videojuego", "gaming", "joystick"], "gaming"),
    (["perfume", "fragancia", "colonia", "eau de"],                                "perfume"),
    (["maquillaje", "crema", "serum", "labial", "base", "shampoo", "acondicionador",
      "desodorante", "gel", "locion", "antiarrugas", "protector solar"],          "belleza"),
    (["bicicleta", "pesas", "proteina", "deportivo", "ciclismo", "yoga",
      "fitness", "gym", "trotadora"],                                              "deporte"),
    (["mueble", "silla", "mesa", "sofa", "cama", "colchon", "escritorio",
      "estante", "cajonera", "lavadora", "refrigerador", "microondas",
      "cocina", "horno"],                                                          "hogar"),
    (["taladro", "sierra", "herramienta", "cemento", "pintura", "gasfiter",
      "electrodo", "extension", "alarma"],                                         "ferreteria"),
    (["vino", "whisky", "ron", "pisco", "vodka", "cerveza", "licor"],             "licor"),
    (["chaqueta", "pantalon", "poleron", "polerones", "polera", "vestido",
      "parka", "jeans", "short", "traje", "camisa", "calcetines", "ropa",
      "blusa", "falda"],                                                           "ropa"),
    (["auto", "vehiculo", "moto", "llantas", "aceite motor"],                     "automotriz"),
]


@dataclass
class Product:
    name: str
    url: str
    normal_price: int
    sale_price: int
    discount_pct: float
    category: str
    store: str = "Mercado Libre"


def _clean_price_from_aria(label: str) -> int | None:
    """Extrae precio del atributo aria-label: 'Antes: 72318 pesos chilenos'."""
    m = re.search(r":\s*([\d]+)\s+pesos", label)
    if m:
        return int(m.group(1))
    # Fallback: primer numero grande
    nums = re.findall(r"\d+", label)
    for n in nums:
        v = int(n)
        if 500 <= v <= 50_000_000:
            return v
    return None


def _clean_fraction(text: str) -> int | None:
    """Limpia '72.318' o '72,318' -> 72318."""
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits and 2 < len(digits) < 9 else None


def _infer_category(title: str) -> str:
    t = title.lower()
    for keywords, channel in _TITLE_KEYWORDS:
        for kw in keywords:
            if re.search(r"\b" + re.escape(kw) + r"\b", t):
                return channel
    return "tecnologia"  # fallback neutral para ML


def _parse_cards(html: str, category_name: str, min_discount: float, debug: bool) -> list[Product]:
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen = set()

    cards = soup.find_all("div", class_=re.compile(r"poly-card--grid"))
    if debug:
        print(f"  [ML] cards encontrados: {len(cards)}")

    for card in cards:
        try:
            # Titulo + URL
            title_tag = card.find("a", class_="poly-component__title")
            if not title_tag:
                continue
            name = title_tag.get_text(strip=True)
            url = title_tag.get("href", "")
            if not url:
                continue
            # Limpiar params de tracking
            url = url.split("#")[0]
            if url in seen:
                continue

            # Precio normal (Antes)
            before_s = card.find("s", attrs={"aria-label": re.compile(r"^Antes:", re.I)})
            if before_s:
                normal = _clean_price_from_aria(before_s.get("aria-label", ""))
                if not normal:
                    frac = before_s.find("span", class_="andes-money-amount__fraction")
                    normal = _clean_fraction(frac.get_text()) if frac else None
            else:
                normal = None

            # Precio oferta (Ahora) — dentro de poly-price__current
            current_div = card.find("div", class_="poly-price__current")
            if not current_div:
                continue
            now_span = current_div.find(
                "span", attrs={"aria-label": re.compile(r"^Ahora:", re.I)}
            )
            if now_span:
                sale = _clean_price_from_aria(now_span.get("aria-label", ""))
                if not sale:
                    frac = now_span.find("span", class_="andes-money-amount__fraction")
                    sale = _clean_fraction(frac.get_text()) if frac else None
            else:
                # Fallback: primer monto en current_div
                frac = current_div.find("span", class_="andes-money-amount__fraction")
                sale = _clean_fraction(frac.get_text()) if frac else None

            if not sale:
                continue
            if not normal or normal <= sale:
                continue

            discount_pct = (normal - sale) / normal * 100
            if discount_pct < min_discount:
                continue

            seen.add(url)
            category = _infer_category(name)

            if debug:
                print(f"    {name[:55]} | ${sale:,} (normal ${normal:,}) {discount_pct:.0f}% | {category}")

            results.append(Product(
                name=name[:120],
                url=url,
                normal_price=normal,
                sale_price=sale,
                discount_pct=round(discount_pct, 1),
                category=category,
                store="Mercado Libre",
            ))
        except Exception:
            continue

    return results


def scrape_category(
    url: str,
    category_name: str,
    min_discount: float = 40.0,
    max_pages: int = 3,
    debug: bool = False,
) -> list[Product]:
    all_products: list[Product] = []
    seen_urls: set = set()

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                ],
            )
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="es-CL",
                viewport={"width": 1920, "height": 1080},
                extra_http_headers={"Accept-Language": "es-CL,es;q=0.9"},
            )
            page = context.new_page()
            if _HAS_STEALTH:
                stealth_sync(page)

            nav_url = url if url.startswith("http") else f"{BASE_URL}/ofertas"

            for page_num in range(max_pages):
                if page_num == 0:
                    page_url = nav_url
                else:
                    sep = "&" if "?" in nav_url else "?"
                    page_url = f"{nav_url}{sep}_from={page_num * 48}"

                try:
                    page.goto(page_url, wait_until="networkidle", timeout=50000)
                    page.wait_for_timeout(3000)
                    # Scroll para activar lazy loading
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.7)")
                    page.wait_for_timeout(2000)
                except PlaywrightTimeout:
                    logging.warning("[ML] Timeout cargando pagina %d, parseando lo disponible", page_num + 1)
                except Exception as e:
                    logging.error("[ML] Error navegando pagina %d: %s", page_num + 1, e)
                    break

                html = page.content()
                if debug:
                    print(f"  [ML] p{page_num+1}: HTML {len(html):,} bytes | titulo={page.title()[:45]}")

                found = _parse_cards(html, category_name, min_discount, debug)
                page_found = 0
                for p in found:
                    if p.url not in seen_urls:
                        seen_urls.add(p.url)
                        all_products.append(p)
                        page_found += 1

                logging.info("[ML] p%d: %d productos >= %.0f%%", page_num + 1, page_found, min_discount)

                if page_found == 0 and page_num >= 1:
                    break
                time.sleep(1)

            browser.close()

    except Exception as e:
        logging.error("[ML] Error general en scraper: %s", e)

    return all_products
