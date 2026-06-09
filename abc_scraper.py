"""
Scraper de abc.cl (ex La Polar + AbcDin) — Salesforce Commerce Cloud.
Usa requests + BeautifulSoup, sin Playwright.
"""
import json
import time
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.abc.cl"
SEARCH_API = (
    "https://www.abc.cl/on/demandware.store/Sites-Abc-Site/es_CL/Search-UpdateGrid"
)
PAGE_SIZE = 36

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "es-CL,es;q=0.9",
    "Referer": "https://www.abc.cl/",
}


@dataclass
class Product:
    name: str
    url: str
    normal_price: int
    sale_price: int
    discount_pct: float
    category: str
    store: str = "abc"


def _parse_price(val: str) -> int:
    try:
        return int(float(val))
    except Exception:
        return 0


def _extract_products(html: str, category_name: str, min_discount: float) -> list[Product]:
    soup = BeautifulSoup(html, "html.parser")
    products = []

    tiles = soup.select("div[data-pid]")

    for tile in tiles:
        try:
            # Precio oferta
            sale_el = tile.select_one(".js-internet-price .price-value")
            if not sale_el:
                sale_el = tile.select_one(".price-value")
            if not sale_el:
                continue

            sale_price = _parse_price(sale_el.get("data-value", "0"))
            if not sale_price:
                continue

            # Precio normal
            normal_el = tile.select_one(".js-normal-price .price-value")
            normal_price = _parse_price(normal_el.get("data-value", "0")) if normal_el else 0
            if not normal_price or normal_price <= sale_price:
                normal_price = sale_price

            # Nombre del producto — desde GTM data o texto
            name = ""
            gtm_raw = tile.get("data-gtm-click", "")
            if gtm_raw:
                try:
                    gtm = json.loads(gtm_raw)
                    prods = gtm.get("ecommerce", {}).get("click", {}).get("products", [])
                    if prods:
                        name = prods[0].get("name", "")
                except Exception:
                    pass

            if not name:
                for sel in [".b-product-tile__name", ".product-tile__name", "h2", "h3"]:
                    el = tile.select_one(sel)
                    if el:
                        name = el.get_text(strip=True)
                        break

            if not name:
                continue

            # URL del producto
            link = tile.select_one("a[href]")
            if not link:
                continue
            href = link.get("href", "")
            if not href.startswith("http"):
                href = BASE_URL + href

            # Descuento
            discount_pct = 0.0
            if normal_price > sale_price:
                discount_pct = (normal_price - sale_price) / normal_price * 100

            is_price_error = sale_price < 1000 and normal_price > 5000

            if discount_pct < min_discount and not is_price_error:
                continue

            products.append(Product(
                name=name[:120],
                url=href,
                normal_price=normal_price,
                sale_price=sale_price,
                discount_pct=round(discount_pct, 1),
                category=category_name,
                store="abc",
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
    query = url.split("q=")[-1].split("&")[0] if "q=" in url else category_name
    all_products: list[Product] = []
    seen_urls: set = set()

    for page_num in range(max_pages):
        start = page_num * PAGE_SIZE
        try:
            params = {
                "q": query,
                "srule": "ascoring",
                "start": start,
                "sz": PAGE_SIZE,
            }
            resp = requests.get(SEARCH_API, params=params, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                if debug:
                    print(f"    [abc] {category_name} p{page_num+1}: status {resp.status_code}")
                break

            found = _extract_products(resp.text, category_name, min_discount)
            unique = [p for p in found if p.url not in seen_urls]
            for p in unique:
                seen_urls.add(p.url)
            all_products.extend(unique)

            if debug:
                print(f"    [abc] {category_name} p{page_num+1}: {len(found)} tiles, {len(unique)} nuevos")

            if len(found) < PAGE_SIZE:
                break

            time.sleep(1)

        except Exception as e:
            if debug:
                print(f"    [abc] Error: {e}")
            break

    return all_products
