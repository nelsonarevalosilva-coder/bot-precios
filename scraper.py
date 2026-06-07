import re
import time
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from playwright_stealth import Stealth

# Selectores conocidos de Ripley Chile (en orden de prioridad)
PRICE_SELECTORS = [
    "[data-testid='product-price']",
    ".product-price .price",
    ".catalog-detail-price .price",
    ".price-normal",
    ".buy-price",
    "span.price",
    "[class*='price'][class*='offer']",
    "[class*='ProductPrice']",
    "[class*='product-price']",
    "meta[property='product:price:amount']",  # fallback Open Graph
]


def _clean_price(text: str) -> int | None:
    """Extrae un entero desde un string de precio como '$199.990' o '199990'."""
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


def _try_meta_price(page) -> int | None:
    """Intenta extraer el precio desde metaetiquetas Open Graph."""
    try:
        content = page.get_attribute("meta[property='product:price:amount']", "content", timeout=2000)
        if content:
            return _clean_price(content)
    except Exception:
        pass
    return None


def scrape_price(url: str, custom_selector: str | None = None, debug: bool = False) -> int | None:
    """
    Extrae el precio de un producto en Ripley Chile.
    Retorna el precio como entero (en pesos) o None si falla.
    """
    selectors = ([custom_selector] if custom_selector else []) + PRICE_SELECTORS

    with Stealth().use_sync(sync_playwright()) as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="es-CL",
            viewport={"width": 1920, "height": 1080},
        )
        page = context.new_page()

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            # Esperar a que cargue el contenido dinámico
            time.sleep(3)

            if debug:
                print(f"[scraper] URL: {url}")
                print(f"[scraper] Título: {page.title()}")

            # Intentar cada selector
            for selector in selectors:
                if selector.startswith("meta"):
                    price = _try_meta_price(page)
                    if price:
                        if debug:
                            print(f"[scraper] Precio encontrado vía meta: {price}")
                        return price
                    continue
                try:
                    el = page.wait_for_selector(selector, timeout=3000)
                    if el:
                        text = el.inner_text()
                        price = _clean_price(text)
                        if price and price > 0:
                            if debug:
                                print(f"[scraper] Selector '{selector}' → '{text}' → {price}")
                            return price
                except PlaywrightTimeout:
                    if debug:
                        print(f"[scraper] Selector '{selector}' no encontrado")
                    continue

            # Último recurso: buscar en todo el texto de la página
            if debug:
                print("[scraper] Intentando extracción por regex en el DOM...")
            body = page.inner_text("body")
            matches = re.findall(r"\$\s?(\d{1,3}(?:\.\d{3})+)", body)
            if matches:
                prices = [int(m.replace(".", "")) for m in matches]
                # El precio del producto suele ser el primero en rango razonable
                valid = [p for p in prices if 1000 < p < 50_000_000]
                if valid:
                    if debug:
                        print(f"[scraper] Precios encontrados en DOM: {valid[:5]}")
                    return valid[0]

            print(f"[scraper] No se encontró precio en {url}")
            return None

        except Exception as e:
            print(f"[scraper] Error al cargar {url}: {e}")
            return None
        finally:
            browser.close()
