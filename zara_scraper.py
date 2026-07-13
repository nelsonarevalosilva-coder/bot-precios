"""
Scraper para Zara Chile — Playwright con intercepción de red.
La plataforma Inditex requiere sesión de navegador para servir productos.
"""
import logging
import re
import time
from dataclasses import dataclass

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

try:
    from playwright_stealth import stealth_sync
    _HAS_STEALTH = True
except ImportError:
    _HAS_STEALTH = False

BASE_URL = "https://www.zara.com"


@dataclass
class Product:
    name: str
    url: str
    normal_price: int
    sale_price: int
    discount_pct: float
    category: str
    store: str = "Zara"
    image_url: str = ""


def _clean_price(val) -> int | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        v = int(val)
        # Zara devuelve precios en centavos (ej: 2990000 = $29.900)
        return v // 100 if v > 1_000_000 else v
    digits = re.sub(r"[^\d]", "", str(val))
    if not digits or not (2 < len(digits) < 12):
        return None
    v = int(digits)
    return v // 100 if v > 1_000_000 else v


def _parse_zara_response(data, category_name: str, min_discount: float, seen: set) -> list[Product]:
    results = []
    if not isinstance(data, dict):
        return results

    # Zara devuelve productos en varias estructuras según el endpoint
    raw_products = (
        data.get("productGroups") or
        data.get("products") or
        data.get("items") or
        []
    )

    items = []
    for entry in raw_products:
        if isinstance(entry, dict):
            # productGroups tiene elementos anidados con commercialComponents
            for elem in (entry.get("elements") or []):
                items.extend(elem.get("commercialComponents") or [elem])
            # O directamente es un producto
            if "name" in entry or "productName" in entry:
                items.append(entry)
    if not items:
        items = raw_products

    for item in items:
        try:
            name = (item.get("name") or item.get("productName") or "").strip()
            if not name:
                continue

            detail = item.get("detail") or {}
            seo = item.get("seo") or {}

            # URL del producto
            link = (detail.get("link") or item.get("link") or {})
            if isinstance(link, dict):
                product_url = link.get("url") or link.get("href") or ""
            else:
                product_url = str(link)

            if not product_url:
                slug = seo.get("keyword") or item.get("seoKeyword") or ""
                if slug:
                    product_url = f"{BASE_URL}/cl/es/{slug}.html"
            if not product_url:
                continue
            if not product_url.startswith("http"):
                product_url = f"{BASE_URL}{product_url}"
            if product_url in seen:
                continue

            # Precios: displayPrice = actual, oldPrice = original
            display = detail.get("displayPrice") or item.get("price") or {}
            old = detail.get("oldPrice") or item.get("originalPrice") or {}

            sale = _clean_price(display.get("value") or display.get("price") or display)
            normal = _clean_price(old.get("value") or old.get("price") or old)

            # Fallback: buscar en colors/sizes
            if not sale:
                for color in (item.get("detail", {}).get("colors") or item.get("colors") or []):
                    prices = color.get("sizes", [{}])[0].get("price") or {}
                    sale = _clean_price(prices.get("price"))
                    normal = _clean_price(prices.get("oldPrice"))
                    if sale:
                        break

            if not sale or not normal or normal <= sale:
                continue

            discount_pct = (normal - sale) / normal * 100
            if discount_pct < min_discount:
                continue

            seen.add(product_url)
            results.append(Product(
                name=name[:120], url=product_url,
                normal_price=normal, sale_price=sale,
                discount_pct=round(discount_pct, 1),
                category=category_name, store="Zara",
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
    seen: set = set()
    api_responses: list[dict] = []

    def handle_response(resp):
        try:
            if (
                resp.status == 200
                and "json" in resp.headers.get("content-type", "")
                and "zara.com" in resp.url
                and any(k in resp.url for k in [
                    "product", "category", "search", "catalog",
                    "itxrest", "ajax", "section",
                ])
            ):
                body = resp.json()
                if isinstance(body, dict) and (
                    body.get("productGroups") or body.get("products") or
                    body.get("items") or body.get("sections")
                ):
                    api_responses.append(body)
        except Exception:
            pass

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled", "--disable-dev-shm-usage"],
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
            page.on("response", handle_response)

            # Calentar sesión en el home de Zara Chile
            try:
                page.goto(f"{BASE_URL}/cl/es/", wait_until="load", timeout=30000)
                page.wait_for_timeout(2000)
            except Exception:
                pass

            try:
                page.goto(url, wait_until="networkidle", timeout=50000)
                page.wait_for_timeout(3000)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.5)")
                page.wait_for_timeout(2000)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(2000)

                if debug:
                    print(f"  [zara] {category_name}: {page.title()[:60]} | respuestas: {len(api_responses)}")

            except PlaywrightTimeout:
                logging.warning("[zara] Timeout en %s — usando lo capturado", category_name)
            except Exception as e:
                logging.error("[zara] Error en %s: %s", category_name, e)

            browser.close()

    except Exception as e:
        logging.error("[zara] Error general: %s", e)

    for data in api_responses:
        found = _parse_zara_response(data, category_name, min_discount, seen)
        if found and debug:
            print(f"  [zara] {len(found)} productos desde respuesta interceptada")
        all_products.extend(found)

    if debug:
        print(f"  [zara] Total: {len(all_products)} productos >= {min_discount:.0f}%")

    return all_products
