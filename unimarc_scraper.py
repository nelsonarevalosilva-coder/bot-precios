"""
Scraper de Unimarc Chile.
Extrae productos de la página de ofertas usando __NEXT_DATA__ (dehydratedState).
"""
import re
import json
import time
from dataclasses import dataclass

from curl_cffi import requests as cf_requests

BASE_URL = "https://www.unimarc.cl"


@dataclass
class Product:
    name: str
    url: str
    normal_price: int
    sale_price: int
    discount_pct: float
    category: str
    store: str = "Unimarc"
    image_url: str = ""
    seller: str = ""


def _get_session():
    session = cf_requests.Session(impersonate="chrome124")
    session.headers.update({
        "Accept-Language": "es-CL,es;q=0.9",
        "Referer": "https://www.unimarc.cl/",
    })
    return session


def _extract_products(html: str, category_name: str, min_discount: float) -> list[Product]:
    nd = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        html, re.DOTALL
    )
    if not nd:
        return []

    try:
        data = json.loads(nd.group(1))
    except Exception:
        return []

    queries = (
        data.get("props", {})
            .get("pageProps", {})
            .get("dehydratedState", {})
            .get("queries", [])
    )

    products_raw = []
    for q in queries:
        state_data = q.get("state", {}).get("data", {})
        if not isinstance(state_data, dict):
            continue
        # Intentar primero directo, luego anidado en "data"
        available = state_data.get("availableProducts", [])
        if not available:
            inner = state_data.get("data", {})
            if isinstance(inner, dict):
                available = inner.get("availableProducts", [])
        if available:
            products_raw = available
            break

    result = []
    seen_ids: set = set()

    for p in products_raw:
        try:
            name = p.get("nameComplete") or p.get("name", "")
            if not name:
                continue

            slug = p.get("slug") or p.get("detailUrl", "")
            url = f"{BASE_URL}{slug}" if slug.startswith("/") else slug
            if not url or url in seen_ids:
                continue

            sellers = p.get("sellers", [])
            if not sellers:
                continue

            s = sellers[0]
            sale_price = int(float(s.get("price", 0)))
            normal_price = int(float(s.get("listPrice", 0)))

            if not sale_price:
                continue
            if normal_price <= sale_price:
                normal_price = sale_price

            discount_pct = 0.0
            if normal_price > sale_price:
                discount_pct = (normal_price - sale_price) / normal_price * 100

            is_price_error = sale_price < 1000 and normal_price > 5000

            if discount_pct < min_discount and not is_price_error:
                continue

            seen_ids.add(url)

            images = p.get("images", [])
            image_url = images[0] if images and isinstance(images[0], str) else ""

            result.append(Product(
                name=name[:120],
                url=url,
                normal_price=normal_price,
                sale_price=sale_price,
                discount_pct=round(discount_pct, 1),
                category=category_name,
                store="Unimarc",
                image_url=image_url,
                seller="Unimarc",
            ))
        except Exception:
            continue

    return result


def scrape_category(
    url: str,
    category_name: str,
    min_discount: float = 20.0,
    max_pages: int = 1,
    debug: bool = False,
) -> list[Product]:
    session = _get_session()
    all_products: list[Product] = []
    seen_ids: set = set()

    for page_num in range(1, max_pages + 1):
        try:
            page_url = url if page_num == 1 else f"{url}?page={page_num}"
            resp = session.get(page_url, timeout=30)

            if resp.status_code != 200:
                if debug:
                    print(f"    [unimarc] {category_name} p{page_num}: status {resp.status_code}")
                break

            found = _extract_products(resp.text, category_name, min_discount)
            unique = [p for p in found if p.url not in seen_ids]
            for p in unique:
                seen_ids.add(p.url)
            all_products.extend(unique)

            if debug:
                print(f"    [unimarc] {category_name} p{page_num}: {len(found)} productos, >={min_discount:.0f}%: {len(unique)}")

            if len(found) < 49:
                break

            time.sleep(1)

        except Exception as e:
            if debug:
                print(f"    [unimarc] Error en {category_name} p{page_num}: {e}")
            break

    return all_products
