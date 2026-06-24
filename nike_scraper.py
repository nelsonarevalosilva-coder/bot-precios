"""
Scraper para Nike Chile — Playwright con intercepción VTEX.
Cloudflare bloquea requests directos; Playwright bypasea con browser real.
"""
import logging
import re
from dataclasses import dataclass

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

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


def _parse_vtex(data, category_name, min_discount, seen):
    results = []
    products = data if isinstance(data, list) else data.get("products", [])
    if not products:
        products = data.get("data", {}).get("productSearch", {}).get("products", [])
    for p in products:
        try:
            pid = str(p.get("productId") or p.get("productReference") or "")
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
            if not image_url:
                image_url = (p.get("items") or [{}])[0].get("images", [{}])[0].get("imageUrl", "") if p.get("items") else ""
            if not normal or not sale or normal <= sale:
                continue
            disc = (normal - sale) / normal * 100
            if disc < min_discount:
                continue
            results.append(Product(name=name[:120], url=url, normal_price=normal,
                                   sale_price=sale, discount_pct=round(disc, 1),
                                   category=category_name, store="Nike", image_url=image_url))
        except Exception:
            continue
    return results


def scrape_category(url, category_name, min_discount=25.0, max_pages=5, debug=False):
    all_products, seen, api_responses = [], set(), []

    sale_url = f"{BASE_URL}/oferta"

    def handle_response(resp):
        try:
            ct = resp.headers.get("content-type", "")
            if resp.status == 200 and "json" in ct and "nike.cl" in resp.url:
                if any(k in resp.url for k in ["catalog_system", "intelligent-search", "product_search", "search"]):
                    body = resp.json()
                    if body:
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
                page.goto(sale_url, wait_until="networkidle", timeout=60000)
                page.wait_for_timeout(4000)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.5)")
                page.wait_for_timeout(2000)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(2000)
                if debug:
                    print(f"  [nike] {page.title()[:60]} | responses: {len(api_responses)}")
            except PlaywrightTimeout:
                logging.warning("[nike] Timeout navegando")
            except Exception as e:
                logging.error("[nike] Error: %s", e)
            browser.close()
    except Exception as e:
        logging.error("[nike] Error general: %s", e)

    for data in api_responses:
        all_products.extend(_parse_vtex(data, category_name, min_discount, seen))

    if debug:
        print(f"  [nike] Total: {len(all_products)} productos >= {min_discount:.0f}%")
    return all_products
