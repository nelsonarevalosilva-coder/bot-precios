"""
Scraper para SuperZoo Chile — Salesforce Commerce Cloud (SFCC), HTML renderizado.
Usa precios del atributo content en .strike-through.list y .sales para calcular descuento.
"""
import time
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "es-CL,es;q=0.9",
}
BASE_URL = "https://www.superzoo.cl"
PAGE_SIZE = 48


@dataclass
class Product:
    name: str
    url: str
    normal_price: int
    sale_price: int
    discount_pct: float
    category: str
    store: str = "SuperZoo"
    image_url: str = ""


def _parse_content(el) -> int:
    if el is None:
        return 0
    content = el.get("content", "")
    return int(content) if content.isdigit() else 0


def _extract_products(soup: BeautifulSoup, category_name: str, min_discount: float) -> list[Product]:
    results = []
    for tile in soup.select(".product-tile"):
        strike_el = tile.select_one(".strike-through.list .value")
        normal_price = _parse_content(strike_el)
        if not normal_price:
            continue

        sale_el = tile.select_one(".sales .value")
        sale_price = _parse_content(sale_el)
        if not sale_price or sale_price >= normal_price:
            continue

        discount_pct = (normal_price - sale_price) / normal_price * 100
        if discount_pct < min_discount:
            continue

        name_el = tile.select_one("h2.text-base") or tile.select_one(".pdp-link a")
        name = name_el.get_text(strip=True) if name_el else ""
        if not name:
            continue

        link_el = tile.select_one(".pdp-link a")
        href = link_el.get("href", "") if link_el else ""
        url = (BASE_URL + href) if href.startswith("/") else href

        img_el = tile.select_one("img.tile-image")
        img_src = img_el.get("src", "") if img_el else ""
        image_url = (BASE_URL + img_src) if img_src.startswith("/") else img_src

        results.append(Product(
            name=name[:120],
            url=url,
            normal_price=normal_price,
            sale_price=sale_price,
            discount_pct=round(discount_pct, 1),
            category=category_name,
            store="SuperZoo",
            image_url=image_url,
        ))
    return results


def scrape_category(
    url: str,
    category_name: str,
    min_discount: float = 25.0,
    max_pages: int = 5,
    debug: bool = False,
) -> list[Product]:
    results: list[Product] = []
    base_url = url.split("?")[0]

    for page in range(max_pages):
        start = page * PAGE_SIZE
        paged_url = f"{base_url}?start={start}&sz={PAGE_SIZE}"
        try:
            resp = requests.get(paged_url, headers=HEADERS, timeout=20)
            resp.raise_for_status()
        except Exception as e:
            if debug:
                print(f"  [superzoo] Error {paged_url}: {e}")
            break

        soup = BeautifulSoup(resp.text, "html.parser")
        tiles = soup.select(".product-tile")
        if not tiles:
            break

        products = _extract_products(soup, category_name, min_discount)
        results.extend(products)

        if debug:
            print(f"  [superzoo] {category_name} start={start}: {len(tiles)} tiles, {len(products)} con >= {min_discount:.0f}%")

        if len(tiles) < PAGE_SIZE:
            break

        time.sleep(0.5)

    return results
