"""
Scraper para Nike Chile — Playwright + extracción de window.__STATE__ (VTEX IO).
"""
import json
import logging
import re
from dataclasses import dataclass

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from bs4 import BeautifulSoup

try:
    from playwright_stealth import stealth_sync
    _HAS_STEALTH = True
except ImportError:
    _HAS_STEALTH = False

BASE_URL = "https://www.nike.cl"


@dataclass
class Product:
    name: str
    url: str
    normal_price: int
    sale_price: int
    discount_pct: float
    category: str
    store: str = "Nike"
    image_url: str = ""


def _clean_price(val) -> int | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return int(val)
    digits = re.sub(r"[^\d]", "", str(val))
    return int(digits) if digits and 2 < len(digits) < 9 else None


def _parse_state(state: dict, category_name: str, min_discount: float, seen: set) -> list[Product]:
    """Extrae productos del window.__STATE__ de VTEX IO."""
    results = []
    for key, val in state.items():
        if not isinstance(val, dict):
            continue
        # Buscar entradas Product con link y priceRange
        product = val.get("product") or (val if "productId" in val else None)
        if not product:
            continue
        try:
            pid = str(product.get("productId") or "")
            if not pid or pid in seen:
                continue
            name = product.get("productName", "").strip()
            link = product.get("link", "") or product.get("linkText", "")
            if not name or not link:
                continue
            url = link if link.startswith("http") else f"{BASE_URL}/{link}/p"
            pr = product.get("priceRange", {})
            normal = _clean_price((pr.get("listPrice") or {}).get("highPrice"))
            sale = _clean_price((pr.get("sellingPrice") or {}).get("lowPrice"))
            items = product.get("items") or []
            item0 = items[0] if items else {}
            if not normal or not sale:
                offer = (item0.get("sellers") or [{}])[0].get("commertialOffer", {})
                normal = _clean_price(offer.get("ListPrice"))
                sale = _clean_price(offer.get("Price"))
            image_url = (item0.get("images") or [{}])[0].get("imageUrl", "")
            if not normal or not sale or normal <= sale:
                continue
            disc = (normal - sale) / normal * 100
            if disc < min_discount:
                continue
            seen.add(pid)
            results.append(Product(name=name[:120], url=url, normal_price=normal,
                                   sale_price=sale, discount_pct=round(disc, 1),
                                   category=category_name, store="Nike", image_url=image_url))
        except Exception:
            continue
    return results


def _parse_html_cards(html: str, category_name: str, min_discount: float, seen: set) -> list[Product]:
    """Fallback: parsea cards del HTML buscando precios tachados."""
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for card in soup.find_all(class_=re.compile(r"product-card|product_card|vtex-product", re.I)):
        try:
            link = card.find("a", href=True)
            if not link:
                continue
            href = link["href"]
            url = href if href.startswith("http") else f"{BASE_URL}{href}"
            if url in seen:
                continue
            name_tag = card.find(class_=re.compile(r"title|name|subtitle", re.I))
            name = name_tag.get_text(strip=True) if name_tag else link.get_text(strip=True)
            normal_tag = card.find(class_=re.compile(r"strike|list|before|original|compare", re.I))
            sale_tag = card.find(class_=re.compile(r"sale|selling|offer|current.*price", re.I))
            if not normal_tag or not sale_tag:
                continue
            normal = _clean_price(normal_tag.get_text())
            sale = _clean_price(sale_tag.get_text())
            if not normal or not sale or normal <= sale:
                continue
            disc = (normal - sale) / normal * 100
            if disc < min_discount:
                continue
            img = card.find("img")
            image_url = (img.get("src") or img.get("data-src") or "") if img else ""
            seen.add(url)
            results.append(Product(name=name[:120], url=url, normal_price=normal,
                                   sale_price=sale, discount_pct=round(disc, 1),
                                   category=category_name, store="Nike", image_url=image_url))
        except Exception:
            continue
    return results


def scrape_category(url, category_name, min_discount=25.0, max_pages=5, debug=False):
    all_products, seen = [], set()
    sale_url = f"{BASE_URL}/oferta"
    page_html = []

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
            try:
                try:
                    page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(3000)
                except Exception:
                    pass
                page.goto(sale_url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(5000)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.4)")
                page.wait_for_timeout(2000)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.7)")
                page.wait_for_timeout(2000)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(3000)
                if debug:
                    print(f"  [nike] {page.title()[:60]}")

                # 1. Intentar window.__STATE__
                try:
                    state_json = page.evaluate("() => JSON.stringify(window.__STATE__ || null)")
                    if state_json and state_json != "null":
                        state = json.loads(state_json)
                        found = _parse_state(state, category_name, min_discount, seen)
                        if debug:
                            print(f"  [nike] __STATE__: {len(state)} keys, {len(found)} productos")
                        all_products.extend(found)
                except Exception as e:
                    if debug:
                        print(f"  [nike] __STATE__ error: {e}")

                # 2. Fetch API desde dentro del browser (usa cookies Cloudflare ya establecidas)
                try:
                    # Probar múltiples endpoints hasta encontrar productos
                    endpoints = [
                        '/api/intelligent-search/product_search?sort=discount%3Adesc&count=50&page=1&locale=es-CL&selectedFacets=%5B%5D',
                        '/api/intelligent-search/product_search?query=descuento&sort=discount%3Adesc&count=50&page=1&locale=es-CL',
                        '/api/catalog_system/pub/products/search?O=OrderByBestDiscountDESC&_from=0&_to=49',
                    ]
                    for ep in endpoints:
                        api_json = page.evaluate(f"""async () => {{
                            try {{
                                const r = await fetch('{ep}', {{credentials:'include'}});
                                if (!r.ok) return JSON.stringify({{error: r.status}});
                                return r.text();
                            }} catch(e) {{ return JSON.stringify({{error: e.message}}); }}
                        }}""")
                        if debug:
                            print(f"  [nike] fetch {ep[:60]}: {str(api_json)[:80]}")
                        if not api_json or '"error"' in api_json[:20]:
                            continue
                        data = json.loads(api_json)
                        products = data.get("products", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                        if products:
                            found = _parse_vtex({"products": products} if not isinstance(data, list) else data, category_name, min_discount, seen)
                            if debug:
                                print(f"  [nike] {len(products)} raw, {len(found)} con desc >= {min_discount}%")
                            all_products.extend(found)
                            break
                except Exception as e:
                    if debug:
                        print(f"  [nike] fetch error: {e}")

            except PlaywrightTimeout:
                logging.warning("[nike] Timeout — usando lo capturado")
                try:
                    page_html.append(page.content())
                except Exception:
                    pass
            except Exception as e:
                logging.error("[nike] Error: %s", e)

            browser.close()
    except Exception as e:
        logging.error("[nike] Error general: %s", e)

    # Fallback HTML si __STATE__ no dio resultados
    if not all_products:
        for html in page_html:
            all_products.extend(_parse_html_cards(html, category_name, min_discount, seen))

    if debug:
        print(f"  [nike] Total: {len(all_products)} productos >= {min_discount:.0f}%")
    return all_products
