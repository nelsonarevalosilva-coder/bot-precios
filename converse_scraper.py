"""
Scraper para Converse Chile — Playwright con intercepción VTEX.
Converse usa VTEX pero requiere sesión de navegador (auth por cookies).
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

BASE_URL = "https://www.converse.com/cl"


@dataclass
class Product:
    name: str
    url: str
    normal_price: int
    sale_price: int
    discount_pct: float
    category: str
    store: str = "Converse"
    image_url: str = ""


def _clean_price(val) -> int | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return int(val)
    digits = re.sub(r"[^\d]", "", str(val))
    return int(digits) if digits and 2 < len(digits) < 9 else None


def _parse_vtex(data, category_name, min_discount, seen):
    results = []
    products = data if isinstance(data, list) else data.get("products", [])
    for p in products:
        try:
            pid = str(p.get("productId") or "")
            if not pid or pid in seen:
                continue
            seen.add(pid)
            name = p.get("productName", "").strip()
            link = p.get("link", "")
            url = link if link.startswith("http") else f"{BASE_URL}{link}"
            if not name or not url:
                continue
            pr = p.get("priceRange", {})
            normal = _clean_price((pr.get("listPrice") or {}).get("highPrice"))
            sale = _clean_price((pr.get("sellingPrice") or {}).get("lowPrice"))
            item0 = (p.get("items") or [{}])[0]
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
            results.append(Product(name=name[:120], url=url, normal_price=normal,
                                   sale_price=sale, discount_pct=round(disc, 1),
                                   category=category_name, store="Converse", image_url=image_url))
        except Exception:
            continue
    return results


def scrape_category(url, category_name, min_discount=40.0, max_pages=3, debug=False):
    all_products, seen, api_responses = [], set(), []

    def handle_response(resp):
        try:
            if (resp.status == 200 and "json" in resp.headers.get("content-type", "")
                    and "converse.com" in resp.url
                    and any(k in resp.url for k in ["catalog_system", "intelligent-search", "product_search"])):
                body = resp.json()
                if body:
                    api_responses.append(body)
        except Exception:
            pass

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-blink-features=AutomationControlled"])
            context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36", locale="es-CL", viewport={"width": 1920, "height": 1080})
            page = context.new_page()
            if _HAS_STEALTH:
                stealth_sync(page)
            page.on("response", handle_response)
            try:
                page.goto(url, wait_until="networkidle", timeout=45000)
                page.wait_for_timeout(4000)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.7)")
                page.wait_for_timeout(2000)
                if debug:
                    print(f"  [converse] {page.title()[:60]} | responses: {len(api_responses)}")
            except PlaywrightTimeout:
                logging.warning("[converse] Timeout")
            except Exception as e:
                logging.error("[converse] Error: %s", e)
            browser.close()
    except Exception as e:
        logging.error("[converse] Error general: %s", e)

    for data in api_responses:
        all_products.extend(_parse_vtex(data, category_name, min_discount, seen))
    return all_products
