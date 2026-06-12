"""
Scraper para Adidas Chile — Playwright con intercepción de red.
Adidas usa Akamai Bot Manager; playwright-stealth lo ayuda a pasar.
Captura las respuestas de la API interna (/api/plp/content-engine) durante
la navegación para obtener productos con descuento.
"""
import time
import re
from dataclasses import dataclass

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from playwright_stealth import Stealth

BASE_URL = "https://www.adidas.cl"


@dataclass
class Product:
    name: str
    url: str
    normal_price: int
    sale_price: int
    discount_pct: float
    category: str
    store: str = "Adidas"


def _clean_price(val) -> int | None:
    if val is None:
        return None
    digits = re.sub(r"[^\d]", "", str(val))
    return int(digits) if digits and 3 <= len(digits) <= 8 else None


def _parse_products(data: dict, category_name: str, min_discount: float) -> list[Product]:
    """Extrae productos desde la respuesta JSON de la API de Adidas."""
    results = []

    # Adidas devuelve los productos en distintas rutas según la versión de la API
    items = (
        data.get("raw", {}).get("itemList", {}).get("items", [])
        or data.get("itemList", {}).get("items", [])
        or data.get("products", [])
        or []
    )

    for item in items:
        try:
            name = item.get("displayName") or item.get("name") or item.get("title", "")
            if not name:
                continue

            model_id = item.get("modelId") or item.get("id") or item.get("productId", "")
            product_url = f"{BASE_URL}/{model_id}.html" if model_id else ""
            if not product_url:
                url_slug = item.get("url") or item.get("link") or ""
                product_url = url_slug if url_slug.startswith("http") else f"{BASE_URL}{url_slug}"

            # Buscar precios en distintas estructuras
            pricing = item.get("pricing") or item.get("price") or {}
            sale = _clean_price(
                pricing.get("currentPrice")
                or pricing.get("sale")
                or pricing.get("salePrice")
                or item.get("salePrice")
            )
            normal = _clean_price(
                pricing.get("standardPrice")
                or pricing.get("original")
                or pricing.get("originalPrice")
                or item.get("originalPrice")
            )

            if not sale or not normal or normal <= sale:
                continue

            discount_pct = (normal - sale) / normal * 100
            if discount_pct < min_discount:
                continue

            results.append(Product(
                name=name[:120],
                url=product_url,
                normal_price=normal,
                sale_price=sale,
                discount_pct=round(discount_pct, 1),
                category=category_name,
                store="Adidas",
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
    api_responses: list[dict] = []

    def handle_response(resp):
        try:
            if (
                "adidas.cl" in resp.url
                and resp.status == 200
                and "json" in resp.headers.get("content-type", "")
                and any(k in resp.url for k in ["/api/plp", "/api/products", "content-engine", "search", "plp"])
            ):
                body = resp.json()
                if isinstance(body, dict):
                    api_responses.append(body)
        except Exception:
            pass

    try:
        with Stealth().use_sync(sync_playwright()) as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
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

            # Cargar home primero para obtener cookies de Akamai
            home_page = context.new_page()
            try:
                home_page.goto(BASE_URL + "/", wait_until="load", timeout=30000)
                home_page.wait_for_timeout(3000)
            except Exception:
                pass
            finally:
                home_page.close()

            page = context.new_page()
            page.on("response", handle_response)

            for page_num in range(max_pages):
                page_url = url if page_num == 0 else f"{url}?start={page_num * 48}"
                try:
                    page.goto(page_url, wait_until="load", timeout=40000)
                    page.wait_for_timeout(4000)
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.5)")
                    page.wait_for_timeout(2000)

                    if debug:
                        print(f"  [adidas] p{page_num+1}: {page.title()[:60]} | URL: {page.url[:80]}")

                    # Intentar extraer __NEXT_DATA__ o window state
                    for selector in ["script#__NEXT_DATA__", "script[type='application/ld+json']"]:
                        try:
                            raw = page.eval_on_selector(selector, "el => el.textContent")
                            if raw and "price" in raw.lower():
                                import json
                                data = json.loads(raw)
                                found = _parse_products(data, category_name, min_discount)
                                if found:
                                    all_products.extend(found)
                                    if debug:
                                        print(f"  [adidas] {len(found)} productos extraídos desde {selector}")
                        except Exception:
                            pass

                except PlaywrightTimeout:
                    if debug:
                        print(f"  [adidas] Timeout en {page_url}")
                    break
                except Exception as e:
                    if debug:
                        print(f"  [adidas] Error p{page_num+1}: {e}")
                    break

            browser.close()

    except Exception as e:
        if debug:
            print(f"  [adidas] Error general: {e}")

    # Procesar respuestas API interceptadas
    for resp_data in api_responses:
        found = _parse_products(resp_data, category_name, min_discount)
        all_products.extend(found)
        if debug and found:
            print(f"  [adidas] {len(found)} productos desde API interceptada")

    # Deduplicar por URL
    seen: set = set()
    unique = []
    for p in all_products:
        if p.url not in seen:
            seen.add(p.url)
            unique.append(p)

    return unique
