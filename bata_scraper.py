"""
Scraper para Bata Chile — Playwright con intercepción de red.
"""
import logging
import re
import time
from dataclasses import dataclass

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from bs4 import BeautifulSoup

try:
    from playwright_stealth import stealth_sync
    _HAS_STEALTH = True
except ImportError:
    _HAS_STEALTH = False

BASE_URL = "https://www.bata.cl"


@dataclass
class Product:
    name: str
    url: str
    normal_price: int
    sale_price: int
    discount_pct: float
    category: str
    store: str = "Bata"


def _clean_price(val) -> int | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return int(val)
    digits = re.sub(r"[^\d]", "", str(val))
    return int(digits) if digits and 2 < len(digits) < 9 else None


def _parse_shopify_json(data, category_name: str, min_discount: float, seen: set) -> list[Product]:
    """Parsea respuesta JSON de Shopify /products.json."""
    results = []
    products = data.get("products", []) if isinstance(data, dict) else []
    for p in products:
        try:
            handle = p.get("handle", "")
            if not handle or handle in seen:
                continue
            name = p.get("title", "")
            product_url = f"{BASE_URL}/products/{handle}"

            best_sale = best_normal = 0
            best_discount = 0.0
            for v in p.get("variants", []):
                price = int(float(v.get("price") or 0))
                compare = v.get("compare_at_price")
                if not compare:
                    continue
                compare = int(float(compare))
                if compare <= price or price <= 0:
                    continue
                discount = (compare - price) / compare * 100
                if discount > best_discount:
                    best_discount = discount
                    best_sale = price
                    best_normal = compare

            if not best_sale or best_discount < min_discount:
                continue

            seen.add(handle)
            results.append(Product(
                name=name[:120], url=product_url,
                normal_price=best_normal, sale_price=best_sale,
                discount_pct=round(best_discount, 1),
                category=category_name, store="Bata",
            ))
        except Exception:
            continue
    return results


def _parse_html(html: str, category_name: str, min_discount: float, seen: set) -> list[Product]:
    """Parsea HTML de la página como fallback."""
    soup = BeautifulSoup(html, "html.parser")
    results = []

    for card in soup.find_all(class_=re.compile(r"product|card|item", re.I)):
        try:
            link_tag = card.find("a", href=True)
            if not link_tag:
                continue
            href = link_tag["href"]
            product_url = href if href.startswith("http") else f"{BASE_URL}{href}"
            if product_url in seen:
                continue

            name_tag = card.find(class_=re.compile(r"title|name", re.I))
            name = name_tag.get_text(strip=True) if name_tag else link_tag.get_text(strip=True)
            if not name:
                continue

            sale_tag = card.find(class_=re.compile(r"sale|discount|oferta|precio.*sale", re.I))
            normal_tag = card.find(class_=re.compile(r"compare|original|before|antes|regular", re.I))
            if not sale_tag:
                continue

            sale = _clean_price(sale_tag.get_text())
            normal = _clean_price(normal_tag.get_text()) if normal_tag else None
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
                category=category_name, store="Bata",
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
    page_html: list[str] = []

    def handle_response(resp):
        try:
            ct = resp.headers.get("content-type", "")
            if resp.status == 200 and "json" in ct and "bata.cl" in resp.url:
                body = resp.json()
                if isinstance(body, dict) and ("products" in body or "items" in body):
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

            try:
                page.goto(url, wait_until="networkidle", timeout=45000)
                page.wait_for_timeout(3000)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.7)")
                page.wait_for_timeout(2000)
                page_html.append(page.content())

                if debug:
                    print(f"  [bata] {page.title()[:60]} | API responses: {len(api_responses)}")

            except PlaywrightTimeout:
                logging.warning("[bata] Timeout — usando lo capturado")
                if page:
                    try:
                        page_html.append(page.content())
                    except Exception:
                        pass
            except Exception as e:
                logging.error("[bata] Error: %s", e)

            browser.close()

    except Exception as e:
        logging.error("[bata] Error general: %s", e)

    # Primero intentar JSON de API interceptada
    for data in api_responses:
        found = _parse_shopify_json(data, category_name, min_discount, seen)
        if found and debug:
            print(f"  [bata] {len(found)} productos desde API")
        all_products.extend(found)

    # Fallback: parsear HTML
    if not all_products:
        for html in page_html:
            found = _parse_html(html, category_name, min_discount, seen)
            if found and debug:
                print(f"  [bata] {len(found)} productos desde HTML")
            all_products.extend(found)

    if debug:
        print(f"  [bata] Total: {len(all_products)} productos >= {min_discount:.0f}%")

    return all_products
