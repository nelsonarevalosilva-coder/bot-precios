"""
Scraper de Santa Isabel Chile.
Extrae productos desde window.__renderData en el HTML de búsqueda.
"""
import re
import json
import time
from dataclasses import dataclass

from curl_cffi import requests as cf_requests

BASE_URL = "https://www.santaisabel.cl"


@dataclass
class Product:
    name: str
    url: str
    normal_price: int
    sale_price: int
    discount_pct: float
    category: str
    store: str = "Santa Isabel"
    image_url: str = ""
    seller: str = ""


def _get_session():
    session = cf_requests.Session(impersonate="chrome124")
    session.headers.update({
        "Accept-Language": "es-CL,es;q=0.9",
        "Referer": "https://www.santaisabel.cl/",
    })
    return session


def _extract_products(html: str, category_name: str, min_discount: float) -> list[Product]:
    m = re.search(r'window\.__renderData\s*=\s*"(.*?)";\s*</script>', html, re.DOTALL)
    if not m:
        return []

    raw = m.group(1).replace('\\"', '"').replace('\\\\', '\\').replace('\\/', '/')
    try:
        data = json.loads(raw)
    except Exception:
        return []

    products_raw = data.get("plp", {}).get("plp_products", {}).get("products", [])
    result = []
    seen_ids: set = set()

    for p in products_raw:
        try:
            name = p.get("productName", "")
            if not name:
                continue

            link_text = p.get("linkText", "")
            url = f"{BASE_URL}/{link_text}/p" if link_text else ""
            if not url or url in seen_ids:
                continue

            items = p.get("items", [])
            if not items:
                continue

            sellers = items[0].get("sellers", [])
            if not sellers:
                continue

            offer = sellers[0].get("commertialOffer", {})
            sale_price = int(offer.get("Price", 0))
            normal_price = int(offer.get("ListPrice", 0))

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

            images = items[0].get("images", [])
            image_url = images[0].get("imageUrl", "") if images and isinstance(images[0], dict) else ""

            result.append(Product(
                name=name[:120],
                url=url,
                normal_price=normal_price,
                sale_price=sale_price,
                discount_pct=round(discount_pct, 1),
                category=category_name,
                store="Santa Isabel",
                image_url=image_url,
                seller="Santa Isabel",
            ))
        except Exception:
            continue

    return result


def scrape_category(
    url: str,
    category_name: str,
    min_discount: float = 20.0,
    max_pages: int = 2,
    debug: bool = False,
) -> list[Product]:
    session = _get_session()
    all_products: list[Product] = []
    seen_ids: set = set()

    for page_num in range(1, max_pages + 1):
        try:
            if page_num == 1:
                page_url = url
            elif "?" in url:
                page_url = f"{url}&PageNumber={page_num}"
            else:
                page_url = f"{url}?PageNumber={page_num}"
            resp = session.get(page_url, timeout=20)

            if resp.status_code != 200:
                if debug:
                    print(f"    [santa_isabel] {category_name} p{page_num}: status {resp.status_code}")
                break

            found = _extract_products(resp.text, category_name, min_discount)
            unique = [p for p in found if p.url not in seen_ids]
            for p in unique:
                seen_ids.add(p.url)
            all_products.extend(unique)

            if debug:
                print(f"    [santa_isabel] {category_name} p{page_num}: {len(found)} productos, >={min_discount:.0f}%: {len(unique)}")

            if len(found) < 39:
                break

            time.sleep(1)

        except Exception as e:
            if debug:
                print(f"    [santa_isabel] Error en {category_name} p{page_num}: {e}")
            break

    return all_products
