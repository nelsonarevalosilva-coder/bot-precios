"""
Scraper para Decathlon Chile — Playwright + in-browser fetch a VTEX API.
La URL de búsqueda no soporta paginación con &page=N; usamos la API de VTEX directamente.
"""
import json
import logging
import re
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
    image_url: str = ""


def _clean_price(val) -> int | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return int(val)
    digits = re.sub(r"[^\d]", "", str(val))
    return int(digits) if digits and 2 < len(digits) < 9 else None


def _parse_vtex(data, category_name: str, min_discount: float, seen: set) -> list[Product]:
    results = []
    if isinstance(data, dict):
        products = (data.get("products") or
                    data.get("data", {}).get("productSearch", {}).get("products") or [])
    elif isinstance(data, list):
        products = data
    else:
        return results

    for p in products:
        try:
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
            if not link:
                continue
            pr = p.get("priceRange") or {}
            normal = _clean_price((pr.get("listPrice") or {}).get("highPrice") or
                                  (pr.get("listPrice") or {}).get("lowPrice"))
            sale = _clean_price((pr.get("sellingPrice") or {}).get("lowPrice") or
                                (pr.get("sellingPrice") or {}).get("highPrice"))
            if not normal or not sale:
                offer = (p.get("items") or [{}])[0].get("sellers", [{}])[0].get("commertialOffer", {})
                normal = _clean_price(offer.get("ListPrice"))
                sale = _clean_price(offer.get("Price"))
            items = p.get("items") or [{}]
            image_url = (items[0].get("images") or [{}])[0].get("imageUrl", "")
            if not normal or not sale or normal <= sale:
                continue
            disc = (normal - sale) / normal * 100
            if disc < min_discount:
                continue
            results.append(Product(name=name[:120], url=link, normal_price=normal,
                                   sale_price=sale, discount_pct=round(disc, 1),
                                   category=category_name, store="Decathlon", image_url=image_url))
        except Exception:
            continue
    return results


def scrape_category(url: str, category_name: str, min_discount: float = 40.0,
                    max_pages: int = 3, debug: bool = False) -> list[Product]:
    all_products: list[Product] = []
    seen: set = set()
    api_responses: list = []

    def handle_response(resp):
        try:
            if (resp.status == 200 and "json" in resp.headers.get("content-type", "")
                    and "decathlon.cl" in resp.url
                    and any(k in resp.url for k in ["intelligent-search", "product_search", "catalog_system", "graphql"])):
                body = resp.json()
                if isinstance(body, (dict, list)) and body:
                    api_responses.append(body)
        except Exception:
            pass

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=[
                "--no-sandbox", "--disable-blink-features=AutomationControlled", "--disable-dev-shm-usage"
            ])
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                locale="es-CL",
                viewport={"width": 1920, "height": 1080},
                extra_http_headers={"Accept-Language": "es-CL,es;q=0.9"},
            )
            page = context.new_page()
            if _HAS_STEALTH:
                stealth_sync(page)
            page.on("response", handle_response)

            try:
                # Navegar con domcontentloaded (networkidle siempre timeout en Decathlon)
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(4000)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.5)")
                page.wait_for_timeout(2000)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(3000)

                title = page.title()
                if debug:
                    print(f"  [decathlon] p1: {title[:60]} | interceptadas: {len(api_responses)}")

                # In-browser fetch a VTEX API para obtener productos con descuento
                endpoints = [
                    '/api/intelligent-search/product_search?sort=discount%3Adesc&count=50&page=1&locale=es-CL',
                    '/api/intelligent-search/product_search?sort=discount%3Adesc&count=50&page=1',
                ]
                for ep in endpoints:
                    try:
                        api_json = page.evaluate(f"""async () => {{
                            const r = await fetch('{ep}', {{credentials:'include'}});
                            if (!r.ok) return JSON.stringify({{error: r.status}});
                            return r.text();
                        }}""")
                        if debug:
                            print(f"  [decathlon] fetch {ep[:60]}: {str(api_json)[:80]}")
                        if api_json and '"error"' not in api_json[:20]:
                            data = json.loads(api_json)
                            api_responses.append(data)
                            break
                    except Exception as e:
                        if debug:
                            print(f"  [decathlon] fetch error: {e}")

                # Página 2+ via in-browser fetch
                for pg in range(2, max_pages + 1):
                    try:
                        ep2 = f'/api/intelligent-search/product_search?sort=discount%3Adesc&count=50&page={pg}&locale=es-CL'
                        api_json2 = page.evaluate(f"""async () => {{
                            const r = await fetch('{ep2}', {{credentials:'include'}});
                            if (!r.ok) return JSON.stringify({{error: r.status}});
                            return r.text();
                        }}""")
                        if not api_json2 or '"error"' in api_json2[:20]:
                            break
                        data2 = json.loads(api_json2)
                        products_in_page = data2.get("products", []) if isinstance(data2, dict) else (data2 if isinstance(data2, list) else [])
                        if not products_in_page:
                            break
                        api_responses.append(data2)
                    except Exception:
                        break

            except PlaywrightTimeout:
                logging.warning("[decathlon] Timeout — usando respuestas interceptadas")
            except Exception as e:
                logging.error("[decathlon] Error: %s", e)

            browser.close()

    except Exception as e:
        logging.error("[decathlon] Error general: %s", e)

    for data in api_responses:
        found = _parse_vtex(data, category_name, min_discount, seen)
        all_products.extend(found)

    if debug:
        print(f"  [decathlon] Total: {len(all_products)} productos >= {min_discount:.0f}%")
    return all_products
