"""
Scraper de Buscalibre.cl usando curl_cffi para bypass Cloudflare.
"""

import re
import time
from dataclasses import dataclass

from curl_cffi import requests as cf_requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.buscalibre.cl"

_SESSION_HEADERS = {
    "Accept-Language": "es-CL,es;q=0.9",
    "Referer": BASE_URL + "/",
}

# Sesión compartida para todas las categorías — evita 82 TLS handshakes
_shared_session: cf_requests.Session | None = None

def _get_session() -> cf_requests.Session:
    global _shared_session
    if _shared_session is None:
        _shared_session = cf_requests.Session(impersonate="chrome124")
        _shared_session.headers.update(_SESSION_HEADERS)
    return _shared_session


@dataclass
class Product:
    name: str
    url: str
    normal_price: int
    sale_price: int
    discount_pct: float
    category: str
    store: str = "Buscalibre"
    image_url: str = ""
    seller: str = ""


def _clean_price(text: str) -> int:
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else 0


def _parse_products(soup, category_name: str, min_discount: float, seen: set) -> list[Product]:
    products = []
    for box in soup.select(".box-producto"):
        try:
            sale_price = int(box.get("data-precio", 0) or 0)
            if not sale_price:
                continue

            # Discount % from Buscalibre's own display — authoritative (uses editorial/retail price)
            disc_div = box.select_one(".descuento-v2")
            if disc_div:
                m = re.search(r"(\d+)", disc_div.get_text())
                discount_pct = float(m.group(1)) if m else 0.0
            else:
                discount_pct = 0.0

            if discount_pct < min_discount:
                continue

            # Normal price: prefer <del> if it matches the discount %, else derive from discount
            del_el = box.select_one("del")
            del_price = _clean_price(del_el.get_text()) if del_el else 0
            if del_price > sale_price:
                computed_pct = (del_price - sale_price) / del_price * 100
                # Use <del> price only if it roughly matches the displayed discount (within 15%)
                if abs(computed_pct - discount_pct) <= 15:
                    normal_price = del_price
                else:
                    normal_price = round(sale_price / (1 - discount_pct / 100))
            else:
                normal_price = round(sale_price / (1 - discount_pct / 100))

            # Product URL
            a_el = box.select_one("a[href]")
            if not a_el:
                continue
            href = a_el.get("href", "")
            product_url = href if href.startswith("http") else BASE_URL + href

            if product_url in seen:
                continue
            seen.add(product_url)

            # Name
            h3 = box.select_one("h3.nombre")
            name = h3.get_text(strip=True) if h3 else a_el.get("title", "").strip()
            if not name:
                continue

            # Image
            img = box.select_one("img.lazyload")
            image_url = img.get("data-src", "") if img else ""

            products.append(Product(
                name=name[:120],
                url=product_url,
                normal_price=normal_price,
                sale_price=sale_price,
                discount_pct=round(discount_pct, 1),
                category=category_name,
                store="Buscalibre",
                image_url=image_url,
            ))
        except Exception:
            continue
    return products


def scrape_category(
    url: str,
    category_name: str,
    min_discount: float = 70.0,
    max_pages: int = 2,
    debug: bool = False,
) -> list[Product]:
    session = _get_session()
    all_products: list[Product] = []
    seen: set = set()

    for page_num in range(1, max_pages + 1):
        try:
            page_url = url if page_num == 1 else f"{url}&pagina={page_num}"
            resp = session.get(page_url, timeout=15)

            if resp.status_code != 200:
                if debug:
                    print(f"  [buscalibre] {category_name} p{page_num}: status {resp.status_code}")
                break

            soup = BeautifulSoup(resp.text, "html.parser")
            raw = soup.select(".box-producto")
            found = _parse_products(soup, category_name, min_discount, seen)

            if debug:
                print(f"  [buscalibre] {category_name} p{page_num}: {len(found)}/{len(raw)} productos")

            all_products.extend(found)

            if len(raw) == 0:
                break

            time.sleep(0.5)

        except Exception as e:
            if debug:
                print(f"  [buscalibre] Error {category_name} p{page_num}: {e}")
            break

    return all_products
