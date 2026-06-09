"""
Scraper de Reebok Chile usando la API VTEX.
Sin Playwright — requests directo.
"""
import time
from dataclasses import dataclass

import requests

API_URL = "https://reebokcl.vtexcommercestable.com.br/api/catalog_system/pub/products/search"
PAGE_SIZE = 50

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "es-CL,es;q=0.9",
    "Referer": "https://www.reebok.cl/",
}


@dataclass
class Product:
    name: str
    url: str
    normal_price: int
    sale_price: int
    discount_pct: float
    category: str
    store: str = "Reebok"


def _extract_products(data: list, category_name: str, min_discount: float) -> list[Product]:
    products = []
    seen_ids: set = set()

    for item in data:
        try:
            product_id = item.get("productId", "")
            if product_id in seen_ids:
                continue
            seen_ids.add(product_id)

            name = item.get("productName", "")
            if not name:
                continue

            url = item.get("link", "") or item.get("linkText", "")
            if not url:
                continue
            if not url.startswith("http"):
                url = "https://www.reebok.cl/" + url.lstrip("/")

            # Precio desde el primer item del primer seller
            offer = (
                item.get("items", [{}])[0]
                .get("sellers", [{}])[0]
                .get("commertialOffer", {})
            )
            sale_price = int(offer.get("Price", 0) or 0)
            normal_price = int(offer.get("ListPrice", 0) or offer.get("PriceWithoutDiscount", 0) or 0)

            if not sale_price:
                continue
            if not normal_price or normal_price <= sale_price:
                normal_price = sale_price

            discount_pct = 0.0
            if normal_price > sale_price:
                discount_pct = (normal_price - sale_price) / normal_price * 100

            is_price_error = sale_price < 1000 and normal_price > 5000
            if discount_pct < min_discount and not is_price_error:
                continue

            products.append(Product(
                name=name[:120],
                url=url,
                normal_price=normal_price,
                sale_price=sale_price,
                discount_pct=round(discount_pct, 1),
                category=category_name,
                store="Reebok",
            ))
        except Exception:
            continue

    return products


def scrape_category(
    url: str,
    category_name: str,
    min_discount: float = 70.0,
    max_pages: int = 3,
    debug: bool = False,
) -> list[Product]:
    query = url.split("ft=")[-1].split("&")[0] if "ft=" in url else category_name
    all_products: list[Product] = []
    seen_ids: set = set()

    for page_num in range(max_pages):
        _from = page_num * PAGE_SIZE
        _to = _from + PAGE_SIZE - 1
        try:
            params = {
                "ft": query,
                "_from": _from,
                "_to": _to,
                "O": "OrderByBestDiscountDESC",
            }
            resp = requests.get(API_URL, params=params, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                if debug:
                    print(f"    [reebok] {category_name} p{page_num+1}: status {resp.status_code}")
                break

            data = resp.json()
            if not data:
                break

            found = _extract_products(data, category_name, min_discount)
            unique = [p for p in found if p.url not in seen_ids]
            for p in unique:
                seen_ids.add(p.url)
            all_products.extend(unique)

            if debug:
                print(f"    [reebok] {category_name} p{page_num+1}: {len(data)} items, {len(unique)} con descuento")

            if len(data) < PAGE_SIZE:
                break

            time.sleep(1)

        except Exception as e:
            if debug:
                print(f"    [reebok] Error: {e}")
            break

    return all_products
