import re
import time
from dataclasses import dataclass

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

BASE_URL = "https://cl.hm.com"
SLUG_BASE = f"{BASE_URL}/es_cl"


@dataclass
class Product:
    name: str
    url: str
    normal_price: int
    sale_price: int
    discount_pct: float
    category: str
    store: str = "H&M"
    image_url: str = ""


def _clean_price(val) -> int | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        v = int(val)
        return v if v > 0 else None
    digits = re.sub(r"[^\d]", "", str(val))
    return int(digits) if digits and 2 < len(digits) < 10 else None


def _extract_edges(body: dict, category_name: str, min_discount: float, seen: set) -> list[Product]:
    edges = (
        body.get("pageProps", {})
            .get("data", {})
            .get("search", {})
            .get("products", {})
            .get("edges", [])
    )
    results = []
    for edge in edges:
        node = edge.get("node", {})
        try:
            name = (node.get("name") or "").strip()
            if not name:
                continue

            offers_root = node.get("offers") or {}
            sale_price = _clean_price(offers_root.get("lowPrice"))
            offers_list = offers_root.get("offers") or []
            normal_price = _clean_price(offers_list[0].get("listPrice")) if offers_list else None

            if not sale_price or not normal_price or normal_price <= sale_price:
                continue

            discount_pct = (normal_price - sale_price) / normal_price * 100
            if discount_pct < min_discount:
                continue

            slug = node.get("slug") or ""
            if not slug:
                continue
            product_url = f"{SLUG_BASE}/{slug}/p"
            if product_url in seen:
                continue

            images = node.get("image") or []
            image_url = images[0].get("url", "") if images else ""

            seen.add(product_url)
            results.append(Product(
                name=name[:120],
                url=product_url,
                normal_price=normal_price,
                sale_price=sale_price,
                discount_pct=round(discount_pct, 1),
                category=category_name,
                image_url=image_url,
            ))
        except Exception:
            continue
    return results


def scrape_category(
    url: str,
    category_name: str,
    min_discount: float = 25.0,
    max_pages: int = 3,
    debug: bool = False,
) -> list[Product]:
    all_products: list[Product] = []
    seen: set = set()
    captured_bodies: list[dict] = []

    def handle_response(resp):
        try:
            if (
                resp.status == 200
                and "_next/data" in resp.url
                and "json" in resp.headers.get("content-type", "")
            ):
                body = resp.json()
                edges = (
                    body.get("pageProps", {})
                        .get("data", {})
                        .get("search", {})
                        .get("products", {})
                        .get("edges", [])
                )
                if edges:
                    captured_bodies.append(body)
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
            page.on("response", handle_response)

            # Calentar sesión
            try:
                page.goto(f"{BASE_URL}/es_cl/", wait_until="load", timeout=30000)
                page.wait_for_timeout(2000)
            except Exception:
                pass

            try:
                page.goto(url, wait_until="networkidle", timeout=50000)
                page.wait_for_timeout(4000)

                if debug:
                    print(f"  [hm] {category_name} p1: {page.title()[:60]}")
                    print(f"  [hm] Respuestas capturadas: {len(captured_bodies)}")

                # Scroll para cargar más productos (paginación infinita)
                for scroll_round in range(max_pages - 1):
                    prev_count = len(captured_bodies)
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(3000)
                    if debug:
                        new = len(captured_bodies) - prev_count
                        print(f"  [hm] {category_name} scroll {scroll_round + 2}: +{new} respuestas")
                    if len(captured_bodies) == prev_count:
                        break  # No llegaron más datos

            except PlaywrightTimeout:
                pass
            except Exception as e:
                import logging
                logging.warning("[hm] Error en %s: %s", category_name, e)

            browser.close()

    except Exception as e:
        import logging
        logging.error("[hm] Error general: %s", e)

    for body in captured_bodies:
        found = _extract_edges(body, category_name, min_discount, seen)
        if found and debug:
            print(f"  [hm] Con >={min_discount:.0f}% desc: {len(found)}")
        all_products.extend(found)

    if debug:
        print(f"  [hm] Total únicos: {len(all_products)}")

    return all_products
