import logging
import re
from dataclasses import dataclass

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from playwright_stealth import Stealth

BASE_URL = "https://www.pullandbear.com"


@dataclass
class Product:
    name: str
    url: str
    normal_price: int
    sale_price: int
    discount_pct: float
    category: str
    store: str = "Pull&Bear"
    image_url: str = ""


def _clean_price(val) -> int | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        v = int(val)
        return v // 100 if v > 1_000_000 else v
    digits = re.sub(r"[^\d]", "", str(val))
    if not digits or not (2 < len(digits) < 12):
        return None
    v = int(digits)
    return v // 100 if v > 1_000_000 else v


def _parse_response(data, category_name: str, min_discount: float, seen: set) -> list[Product]:
    results = []
    if not isinstance(data, dict):
        return results

    raw = data.get("products") or data.get("items") or data.get("hits") or []

    for item in raw:
        try:
            name = (item.get("name") or "").strip()
            if not name:
                continue

            sale = _clean_price(item.get("price"))
            normal = _clean_price(item.get("oldPrice"))

            if not sale or not normal or normal <= sale:
                continue

            discount_pct = (normal - sale) / normal * 100
            if discount_pct < min_discount:
                continue

            url = item.get("productPage", "")
            if not url or url in seen:
                continue

            image = item.get("mainImage", "")
            if image.startswith("//"):
                image = "https:" + image

            seen.add(url)
            results.append(Product(
                name=name[:120], url=url,
                normal_price=normal, sale_price=sale,
                discount_pct=round(discount_pct, 1),
                category=category_name,
                image_url=image,
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
                and "pullandbear.com" in resp.url
            ):
                body = resp.json()
                if isinstance(body, dict) and (
                    body.get("products") or body.get("items") or
                    body.get("hits") or body.get("productGroups") or
                    body.get("elements")
                ):
                    api_responses.append(body)
        except Exception:
            pass

    try:
        with Stealth().use_sync(sync_playwright()) as pw:
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
            page.on("response", handle_response)

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
                    print(f"  [pullandbear] {category_name}: {page.title()[:60]} | respuestas: {len(api_responses)}")

            except PlaywrightTimeout:
                logging.warning("[pullandbear] Timeout en %s — usando lo capturado", category_name)
            except Exception as e:
                logging.error("[pullandbear] Error en %s: %s", category_name, e)

            browser.close()

    except Exception as e:
        logging.error("[pullandbear] Error general: %s", e)

    for data in api_responses:
        found = _parse_response(data, category_name, min_discount, seen)
        if found and debug:
            print(f"  [pullandbear] {len(found)} productos desde respuesta interceptada")
        all_products.extend(found)

    if debug:
        print(f"  [pullandbear] Total: {len(all_products)} productos >= {min_discount:.0f}%")

    return all_products
