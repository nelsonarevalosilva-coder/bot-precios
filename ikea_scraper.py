"""
Scraper para IKEA Chile — página de ofertas HTML con JSON embebido en scripts.
Los productos en oferta tienen tag=TIME_RESTRICTED_OFFER y salesPrice.previous con el precio anterior.
"""
import json
import re
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "es-CL,es;q=0.9",
}


@dataclass
class Product:
    name: str
    url: str
    normal_price: int
    sale_price: int
    discount_pct: float
    category: str
    store: str = "IKEA"


def _parse_formatted_price(whole_number: str) -> int:
    return int(re.sub(r"[^\d]", "", whole_number)) if whole_number else 0


def _extract_from_script(script_text: str, category_name: str, min_discount: float) -> list[Product]:
    try:
        data = json.loads(script_text)
    except Exception:
        return []

    state = data.get("storeState", {})
    results = []

    # Carousel and listing sections both store items in nested dict
    for section_key in ["carousel", "listing", "productIdCarousel"]:
        section = state.get(section_key, {})
        items_container = section.get("items", {})
        if isinstance(items_container, dict):
            items = items_container.get("items", [])
        elif isinstance(items_container, list):
            items = items_container
        else:
            continue

        for item in items:
            p = item.get("product", {})
            sp = p.get("salesPrice", {})
            previous = sp.get("previous")
            if not previous:
                continue

            sale_price = int(sp.get("numeral", 0))
            normal_price = _parse_formatted_price(previous.get("wholeNumber", ""))

            if not sale_price or not normal_price or normal_price <= sale_price:
                continue

            discount_pct = (normal_price - sale_price) / normal_price * 100
            if discount_pct < min_discount:
                continue

            name = f"{p.get('name', '')} {p.get('typeName', '')}".strip()
            url = p.get("pipUrl", "")
            if not name or not url:
                continue

            results.append(Product(
                name=name,
                url=url,
                normal_price=normal_price,
                sale_price=sale_price,
                discount_pct=discount_pct,
                category=category_name,
                store="IKEA",
            ))

    return results


def scrape_category(
    url: str,
    category_name: str,
    min_discount: float = 40.0,
    max_pages: int = 1,
    debug: bool = False,
) -> list[Product]:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        if debug:
            print(f"  [ikea] Error al obtener {url}: {e}")
        return []

    scripts = re.findall(r"<script[^>]*>(.*?)</script>", resp.text, re.DOTALL)

    results = []
    for script in scripts:
        if "storeState" not in script:
            continue
        found = _extract_from_script(script, category_name, min_discount)
        results.extend(found)

    seen = set()
    deduped = []
    for p in results:
        if p.url not in seen:
            seen.add(p.url)
            deduped.append(p)

    if debug:
        print(f"  [ikea] {url}: {len(deduped)} producto(s) con >= {min_discount:.0f}% off")

    return deduped
