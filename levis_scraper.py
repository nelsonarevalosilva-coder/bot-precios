import logging
import re
from dataclasses import dataclass

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

try:
    from playwright_stealth import stealth_sync
    _HAS_STEALTH = True
except ImportError:
    _HAS_STEALTH = False

BASE_URL = "https://www.levi.cl"


@dataclass
class Product:
    name: str
    url: str
    normal_price: int
    sale_price: int
    discount_pct: float
    category: str
    store: str = "Levi's"
    image_url: str = ""


def _clean_price(val) -> int | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return int(val)
    digits = re.sub(r"[^\d]", "", str(val))
    return int(digits) if digits and 2 < len(digits) < 10 else None


def _parse_vtex(data, category_name: str, min_discount: float, seen: set) -> list[Product]:
    results = []
    if isinstance(data, list):
        products = data
    elif isinstance(data, dict):
        products = (
            data.get("products")
            or (data.get("data") or {}).get("productSearch", {}).get("products")
            or []
        )
    else:
        return results

    for p in products:
        try:
            name = (p.get("productName") or p.get("name") or "").strip()
            if not name:
                continue

            link = p.get("link") or p.get("detailUrl") or ""
            if not link:
                slug = p.get("linkText") or ""
                link = f"{BASE_URL}/{slug}/p" if slug else ""
            if not link or link in seen:
                continue
            if not link.startswith("http"):
                link = BASE_URL + link

            normal = sale = None
            pr = p.get("priceRange") or {}
            if pr:
                normal = _clean_price((pr.get("listPrice") or {}).get("highPrice"))
                sale = _clean_price((pr.get("sellingPrice") or {}).get("lowPrice"))

            if not normal or not sale:
                items = p.get("items") or []
                if items:
                    offer = (items[0].get("sellers") or [{}])[0].get("commertialOffer", {})
                    normal = _clean_price(offer.get("ListPrice"))
                    sale = _clean_price(offer.get("Price"))

            if not normal or not sale or normal <= sale:
                continue

            disc = (normal - sale) / normal * 100
            if disc < min_discount:
                continue

            img = ""
            items = p.get("items") or []
            if items:
                img = (items[0].get("images") or [{}])[0].get("imageUrl", "")

            seen.add(link)
            results.append(Product(
                name=name[:120], url=link,
                normal_price=normal, sale_price=sale,
                discount_pct=round(disc, 1),
                category=category_name, store="Levi's",
                image_url=img,
            ))
        except Exception:
            continue

    return results


def scrape_category(
    url: str,
    category_name: str,
    min_discount: float = 20.0,
    max_pages: int = 8,
    debug: bool = False,
) -> list[Product]:
    all_products: list[Product] = []
    seen: set = set()

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

            api_data: list = []

            def handle_response(resp):
                try:
                    if resp.status == 200 and "json" in resp.headers.get("content-type", ""):
                        if any(k in resp.url for k in [
                            "catalog_system", "intelligent-search", "product_search"
                        ]):
                            body = resp.json()
                            if body:
                                api_data.append(body)
                except Exception:
                    pass

            page.on("response", handle_response)

            for page_num in range(max_pages):
                api_data.clear()
                sep = "&" if "?" in url else "?"
                page_url = url if page_num == 0 else f"{url}{sep}page={page_num + 1}"

                try:
                    page.goto(page_url, wait_until="networkidle", timeout=45000)
                    page.wait_for_timeout(3000)
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.6)")
                    page.wait_for_timeout(2000)

                    batch = []
                    for data in api_data:
                        batch.extend(_parse_vtex(data, category_name, min_discount, seen))

                    all_products.extend(batch)

                    if debug:
                        print(f"  [levis] {category_name} p{page_num+1}: {len(api_data)} resp → {len(batch)} prods")

                    if not batch and page_num > 0:
                        break

                except PlaywrightTimeout:
                    logging.warning("[levis] Timeout en %s", page_url)
                    break
                except Exception as e:
                    logging.error("[levis] Error: %s", e)
                    break

            browser.close()

    except Exception as e:
        logging.error("[levis] Error general: %s", e)

    return all_products
