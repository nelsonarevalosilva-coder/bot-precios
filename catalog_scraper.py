"""
Scraper de catálogo para Ripley Chile.
Estrategia: navega home primero (cookies Cloudflare) → categoría → extrae
__NEXT_DATA__.props.pageProps.findabilityProps.data.products
"""

import json
import re
import time
from dataclasses import dataclass

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from playwright_stealth import Stealth

BASE_URL = "https://simple.ripley.cl"
PRODUCTS_PER_PAGE = 56  # el sitio carga 56 productos por página


@dataclass
class Product:
    name: str
    url: str
    normal_price: int
    sale_price: int
    discount_pct: float
    category: str


def _clean_price(text: str) -> int | None:
    digits = re.sub(r"[^\d]", "", str(text))
    return int(digits) if digits and 3 < len(digits) < 10 else None


def _product_url(parent_product_id: str, description: str) -> str:
    # Patrón real: /description-slug-parentProductIDlower
    # parentProductID = "2000408286592P" → "2000408286592p"
    # parentProductID = "mpm10003242728"  → "mpm10003242728"
    slug = re.sub(r"[^a-z0-9]+", "-", description.lower()).strip("-")
    pid = parent_product_id.lower()
    return f"{BASE_URL}/{slug}-{pid}"


def _extract_products(next_data_json: str, category_name: str, min_discount: float) -> list[Product]:
    try:
        data = json.loads(next_data_json)
        raw = (
            data.get("props", {})
            .get("pageProps", {})
            .get("findabilityProps", {})
            .get("data", {})
            .get("products", [])
        )
    except Exception:
        return []

    products = []
    for item in raw:
        try:
            name = item.get("name") or item.get("description", "")
            if not name:
                continue

            old_price = _clean_price(item.get("oldPrice", ""))
            sale_price = _clean_price(item.get("price", ""))

            if not sale_price:
                continue

            discount = item.get("discount", 0) or 0

            # Si Ripley no entrega oldPrice, estimamos desde el descuento
            if not old_price and discount > 0:
                old_price = int(sale_price / (1 - discount / 100))

            # Calcular descuento real nosotros (no confiar solo en Ripley)
            if old_price and old_price > sale_price:
                real_discount = (old_price - sale_price) / old_price * 100
            else:
                real_discount = float(discount)

            # Atrapar errores de precio extremos: precio < $1.000 con precio normal > $5.000
            # o cualquier descuento >= min_discount calculado por nosotros
            is_price_error = old_price and sale_price < 1000 and old_price > 5000
            if real_discount < min_discount and not is_price_error:
                continue

            # Si es error extremo, forzar el descuento real
            if is_price_error and old_price:
                real_discount = (old_price - sale_price) / old_price * 100

            parent_id = item.get("parentProductID", "") or item.get("sku", "")
            description = item.get("description", name)
            url = _product_url(parent_id, description)

            products.append(Product(
                name=name[:120],
                url=url,
                normal_price=old_price or sale_price,
                sale_price=sale_price,
                discount_pct=round(real_discount, 1),
                category=category_name,
            ))
        except Exception:
            continue

    return products


def _get_total_products(next_data_json: str) -> int:
    try:
        data = json.loads(next_data_json)
        meta = (
            data.get("props", {})
            .get("pageProps", {})
            .get("findabilityProps", {})
            .get("data", {})
            .get("meta", {})
        )
        return int(meta.get("total", 0))
    except Exception:
        return 0


def _load_home_cookies(browser) -> object:
    """Carga el home de Ripley para obtener cookies de Cloudflare."""
    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        locale="es-CL",
        viewport={"width": 1920, "height": 1080},
        extra_http_headers={
            "Accept-Language": "es-CL,es;q=0.9,en;q=0.8",
        },
    )
    page = context.new_page()
    try:
        page.goto(f"{BASE_URL}/", wait_until="load", timeout=30000)
        time.sleep(3)
    except Exception:
        pass
    finally:
        page.close()
    return context


def scrape_category(
    url: str,
    category_name: str,
    min_discount: float = 50.0,
    max_pages: int = 3,
    debug: bool = False,
    _shared_context=None,
) -> list[Product]:
    """
    Scrape una categoría de Ripley y retorna productos con descuento >= min_discount%.
    Si se pasa _shared_context, reutiliza la sesión existente (más eficiente).
    """
    # Extraer el slug de la URL
    slug = url.rstrip("/").split("/")[-1]
    all_products: list[Product] = []

    with Stealth().use_sync(sync_playwright()) as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )

        # Cargar home primero para obtener cookies CF
        context = _load_home_cookies(browser)
        page = context.new_page()

        for page_num in range(max_pages):
            offset = page_num * PRODUCTS_PER_PAGE
            page_url = f"{BASE_URL}/{slug}" if page_num == 0 else f"{BASE_URL}/{slug}?offset={offset}"

            try:
                page.goto(page_url, wait_until="load", timeout=40000)
                time.sleep(3)

                # Scroll para cargar contenido
                page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.5)")
                time.sleep(1)

                if debug:
                    print(f"    [scraper] {category_name} p{page_num+1}: {page.title()[:50]}")

                # Extraer __NEXT_DATA__
                next_data = page.eval_on_selector(
                    "script#__NEXT_DATA__",
                    "el => el.textContent",
                )

                if not next_data:
                    if debug:
                        print(f"    [scraper] No __NEXT_DATA__ en página {page_num+1}")
                    break

                found = _extract_products(next_data, category_name, min_discount)
                if debug:
                    total = _get_total_products(next_data)
                    print(f"    [scraper] Total en cat: {total} | Con >={min_discount:.0f}% desc: {len(found)}")

                all_products.extend(found)

                # Si hay menos de una página completa, no hay más páginas
                total = _get_total_products(next_data)
                if total <= PRODUCTS_PER_PAGE or (page_num + 1) * PRODUCTS_PER_PAGE >= total:
                    break

                time.sleep(2)  # pausa entre páginas

            except PlaywrightTimeout:
                print(f"    [scraper] Timeout en {page_url}")
                break
            except Exception as e:
                print(f"    [scraper] Error: {e}")
                break

        browser.close()

    # Deduplicar por URL
    seen = set()
    unique = []
    for p in all_products:
        if p.url not in seen:
            seen.add(p.url)
            unique.append(p)

    return unique
