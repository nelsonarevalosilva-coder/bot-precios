"""
Scraper para Farmacia Ahumada — Salesforce Commerce Cloud (SFCC).
Monitorea la página de promociones y filtra items con precio tachado (Antes/Ahora).
"""
import re
import time
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "es-CL,es;q=0.9",
}
BASE_URL = "https://www.farmaciasahumada.cl"
PAGE_SIZE = 24


@dataclass
class Product:
    name: str
    url: str
    normal_price: int
    sale_price: int
    discount_pct: float
    category: str
    store: str = "Farmacia Ahumada"
    image_url: str = ""


def _parse_price(text: str) -> int:
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else 0


def _extract_products(soup: BeautifulSoup, category_name: str, min_discount: float) -> list[Product]:
    results = []
    for tile in soup.select(".product-tile"):
        normal_price = 0
        sale_price = 0

        # Formato nuevo: "Price reduced from$18.079" en .strike-through.list
        strike_list = tile.select_one(".strike-through.list")
        if strike_list:
            matches = re.findall(r'\$([\d.]+)', strike_list.get_text())
            if matches:
                normal_price = int(matches[0].replace(".", ""))
            sale_el = tile.select_one(".promotion-badge-container.flex-row")
            if sale_el:
                sale_matches = re.findall(r'\$([\d.]+)', sale_el.get_text())
                if sale_matches:
                    sale_price = int(sale_matches[0].replace(".", ""))

        # Formato viejo: .strike-through .value con atributo content + "Antes"
        if not normal_price:
            orig_el = tile.select_one(".strike-through .value")
            if orig_el:
                orig_content = orig_el.get("content", "")
                normal_price = int(orig_content) if orig_content.isdigit() else 0
        if not sale_price and normal_price:
            default_el = tile.select_one(".default-price")
            if default_el:
                nums = [int(x.replace(".", "")) for x in re.findall(r"[\d.]+", default_el.get_text())
                        if x.replace(".", "").isdigit() and int(x.replace(".", "")) > 100]
                if nums:
                    sale_price = nums[0]

        if not normal_price or not sale_price or sale_price >= normal_price:
            continue

        discount_pct = (normal_price - sale_price) / normal_price * 100
        if discount_pct < min_discount:
            continue

        name_el = tile.select_one(".pdp-link a") or tile.select_one("a[href]")
        if not name_el:
            continue
        name = name_el.get_text(strip=True)
        href = name_el.get("href", "")
        url = href if href.startswith("http") else f"{BASE_URL}{href}"
        if not name or not url:
            continue

        img = tile.select_one("img.tile-image") or tile.select_one("img")
        image_url = img.get("src", "") if img else ""

        results.append(Product(
            name=name[:120],
            url=url,
            normal_price=normal_price,
            sale_price=sale_price,
            discount_pct=round(discount_pct, 1),
            category=category_name,
            store="Farmacia Ahumada",
            image_url=image_url,
        ))

    seen = set()
    deduped = []
    for p in results:
        if p.url not in seen:
            seen.add(p.url)
            deduped.append(p)
    return deduped


def scrape_category(
    url: str,
    category_name: str,
    min_discount: float = 40.0,
    max_pages: int = 5,
    debug: bool = False,
) -> list[Product]:
    results = []
    for page in range(max_pages):
        start = page * PAGE_SIZE
        page_url = url if page == 0 else f"{url}?start={start}&sz={PAGE_SIZE}"
        try:
            resp = requests.get(page_url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            if debug:
                print(f"  [ahumada] Error {page_url}: {e}")
            break

        soup = BeautifulSoup(resp.text, "html.parser")
        tiles = soup.select(".product-tile")
        page_results = _extract_products(soup, category_name, min_discount)

        if debug:
            sale = len([t for t in tiles if "Antes" in t.get_text() or t.select_one(".strike-through.list")])
            print(f"  [ahumada] pág {page+1}: {len(tiles)} total, {sale} con descuento, {len(page_results)} >= {min_discount:.0f}%")

        results.extend(page_results)

        if len(tiles) < PAGE_SIZE:
            break

        time.sleep(0.5)

    seen = set()
    deduped = []
    for p in results:
        if p.url not in seen:
            seen.add(p.url)
            deduped.append(p)
    return deduped
