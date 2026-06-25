"""
Scraper para Under Armour Chile — Playwright con intercepción de red.
Under Armour bloquea requests con 418; necesita browser real.
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

BASE_URL = "https://www.underarmour.com"


@dataclass
class Product:
    name: str
    url: str
    normal_price: int
    sale_price: int
    discount_pct: float
    category: str
    store: str = "Under Armour"
    image_url: str = ""


def _clean_price(val) -> int | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return int(val)
    digits = re.sub(r"[^\d]", "", str(val))
    return int(digits) if digits and 2 < len(digits) < 9 else None


def _parse_json_response(data, category_name: str, min_discount: float, seen: set) -> list[Product]:
    """Parsea distintos formatos JSON que UA puede devolver."""
    results = []
    items = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = (data.get("hits") or data.get("products") or data.get("items") or
                 data.get("data", {}).get("products") or data.get("result", {}).get("hits") or [])
    for p in items:
        try:
            pid = str(p.get("productId") or p.get("id") or p.get("objectID") or "")
            if not pid or pid in seen:
                continue
            name = (p.get("name") or p.get("productName") or p.get("title") or "").strip()
            if not name:
                continue
            link = p.get("url") or p.get("link") or p.get("pdpUrl") or ""
            if not link:
                slug = p.get("slug") or p.get("seoKeyword") or pid
                link = f"/es-cl/{slug}"
            url = link if link.startswith("http") else f"{BASE_URL}{link}"
            price_obj = p.get("price") or p.get("prices") or p.get("priceRange") or {}
            if isinstance(price_obj, dict):
                sale = _clean_price(price_obj.get("sale") or price_obj.get("current") or
                                    price_obj.get("salePrice") or price_obj.get("min"))
                normal = _clean_price(price_obj.get("original") or price_obj.get("regular") or
                                      price_obj.get("list") or price_obj.get("max") or
                                      price_obj.get("msrp"))
            else:
                sale = _clean_price(price_obj)
                normal = None
            if not sale or not normal or normal <= sale:
                continue
            disc = (normal - sale) / normal * 100
            if disc < min_discount:
                continue
            imgs = p.get("images") or p.get("image") or []
            image_url = (imgs[0].get("src") or imgs[0].get("url") or "") if imgs and isinstance(imgs, list) else ""
            seen.add(pid)
            results.append(Product(name=name[:120], url=url, normal_price=normal,
                                   sale_price=sale, discount_pct=round(disc, 1),
                                   category=category_name, store="Under Armour", image_url=image_url))
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
            ct = resp.headers.get("content-type", "")
            if resp.status == 200 and "json" in ct and "underarmour.com" in resp.url:
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
                # Warmup en home para obtener cookies
                page.goto(f"{BASE_URL}/es-cl/", wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(2000)

                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(4000)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.5)")
                page.wait_for_timeout(2000)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(3000)

                title = page.title()
                if debug:
                    print(f"  [under armour] {category_name}: {title[:60]} | responses: {len(api_responses)}")

                # In-browser fetch si no se interceptaron respuestas útiles
                if not all_products:
                    path = url.replace(BASE_URL, "")
                    try:
                        api_json = page.evaluate("""async () => {
                            const r = await fetch('/es-cl/search?q=&sz=48&format=ajax&srule=Most-Discounted', {credentials:'include'});
                            return r.ok ? await r.text() : JSON.stringify({error: r.status});
                        }""")
                        if debug:
                            print(f"  [under armour] fetch ajax: {str(api_json)[:80]}")
                    except Exception:
                        pass

            except PlaywrightTimeout:
                logging.warning("[under armour] Timeout en %s", category_name)
            except Exception as e:
                logging.error("[under armour] Error: %s", e)

            browser.close()

    except Exception as e:
        logging.error("[under armour] Error general: %s", e)

    for data in api_responses:
        found = _parse_json_response(data, category_name, min_discount, seen)
        if found and debug:
            print(f"  [under armour] {len(found)} productos desde API")
        all_products.extend(found)

    if debug:
        print(f"  [under armour] Total: {len(all_products)} productos >= {min_discount:.0f}%")
    return all_products
