"""
Scraper para Decathlon Chile — Playwright con intercepción de red.
La API VTEX requiere auth; Playwright la resuelve vía sesión de navegador.
"""
import json
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

BASE_URL = "https://www.decathlon.cl"


@dataclass
class Product:
    name: str
    url: str
    normal_price: int
    sale_price: int
    discount_pct: float
    category: str
    store: str = "Decathlon"


def _clean_price(val) -> int | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return int(val)
    digits = re.sub(r"[^\d]", "", str(val))
    return int(digits) if digits and 2 < len(digits) < 9 else None


def _parse_vtex_products(data, category_name: str, min_discount: float, seen: set) -> list[Product]:
    results = []

    # VTEX intelligent-search retorna {"products": [...]}
    products = []
    if isinstance(data, dict):
        products = (
            data.get("products") or
            data.get("data", {}).get("productSearch", {}).get("products") or
            data.get("data", {}).get("search", {}).get("products", {}).get("edges", []) or
            []
        )
    elif isinstance(data, list):
        products = data

    for p in products:
        try:
            # Soporte para formato edges (GraphQL)
            if "node" in p:
                p = p["node"]

            pid = str(p.get("productId") or p.get("id") or p.get("cacheId") or "")
            if not pid or pid in seen:
                continue
            seen.add(pid)

            name = (p.get("productName") or p.get("name") or "").strip()
            if not name:
                continue

            link = p.get("link") or p.get("linkText") or ""
            if link and not link.startswith("http"):
                link = f"{BASE_URL}/{link.lstrip('/')}/p"
            product_url = link or ""
            if not product_url:
                continue

            # Precios desde priceRange
            price_range = p.get("priceRange") or {}
            normal = _clean_price(
                (price_range.get("listPrice") or {}).get("highPrice") or
                (price_range.get("listPrice") or {}).get("lowPrice")
            )
            sale = _clean_price(
                (price_range.get("sellingPrice") or {}).get("lowPrice") or
                (price_range.get("sellingPrice") or {}).get("highPrice")
            )

            # Fallback: commertialOffer
            if not normal or not sale:
                offer = (p.get("items") or [{}])[0].get("sellers", [{}])[0].get("commertialOffer", {})
                normal = _clean_price(offer.get("ListPrice"))
                sale = _clean_price(offer.get("Price"))

            if not normal or not sale or normal <= sale:
                continue

            discount_pct = (normal - sale) / normal * 100
            if discount_pct < min_discount:
                continue

            results.append(Product(
                name=name[:120], url=product_url,
                normal_price=normal, sale_price=sale,
                discount_pct=round(discount_pct, 1),
                category=category_name, store="Decathlon",
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
                and any(k in resp.url for k in [
                    "intelligent-search", "product_search",
                    "graphql", "catalog_system", "search",
                ])
                and "decathlon.cl" in resp.url
            ):
                body = resp.json()
                if isinstance(body, (dict, list)):
                    api_responses.append(body)
        except Exception:
            pass

    nav_url = url if url.startswith("http") else f"{BASE_URL}/search?q=oferta&sort=discount-desc"

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

            for page_num in range(max_pages):
                page_url = nav_url if page_num == 0 else f"{nav_url}&page={page_num + 1}"
                try:
                    page.goto(page_url, wait_until="networkidle", timeout=45000)
                    page.wait_for_timeout(3000)
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.7)")
                    page.wait_for_timeout(2000)

                    if debug:
                        print(f"  [decathlon] p{page_num+1}: {page.title()[:60]}")

                except PlaywrightTimeout:
                    logging.warning("[decathlon] Timeout p%d — usando lo capturado", page_num + 1)
                except Exception as e:
                    logging.error("[decathlon] Error p%d: %s", page_num + 1, e)
                    break

                time.sleep(1)

            browser.close()

    except Exception as e:
        logging.error("[decathlon] Error general: %s", e)

    # Procesar todas las respuestas interceptadas
    for data in api_responses:
        found = _parse_vtex_products(data, category_name, min_discount, seen)
        if found and debug:
            print(f"  [decathlon] {len(found)} productos desde API interceptada")
        all_products.extend(found)

    if debug:
        print(f"  [decathlon] Total: {len(all_products)} productos >= {min_discount:.0f}%")

    return all_products
