"""
Scraper para Cruz Verde — Salesforce Commerce Cloud (SFCC) API pública.
Usa la API beta.cruzverde.cl con client_id público para buscar productos con descuento.
El precio club (price-sale-cl) vs precio lista (price-list-cl) = descuento real.
"""
import re
import time
from dataclasses import dataclass

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}
API_BASE = "https://beta.cruzverde.cl/s/Chile/dw/shop/v19_1/product_search"
CLIENT_ID = "c19ce24d-1677-4754-b9f7-c193997c5a92"
BASE_URL = "https://www.cruzverde.cl"


def _make_slug(name: str) -> str:
    name = name.lower()
    for a, b in [("á","a"),("é","e"),("í","i"),("ó","o"),("ú","u"),("ñ","n"),("ü","u")]:
        name = name.replace(a, b)
    name = name.replace(".", "")  # "0.5 mg" → "05-mg" como hace el sitio
    return re.sub(r"[^a-z0-9]+", "-", name).strip("-")

PAGE_SIZE = 50

# Términos de búsqueda para cubrir el catálogo
SEARCH_TERMS = [
    "vitamina", "medicamento", "higiene", "crema", "shampoo",
    "antiinflamatorio", "analgesico", "antihistaminico", "bebe",
    "dermocosmetica", "protector solar", "suplemento",
]


@dataclass
class Product:
    name: str
    url: str
    normal_price: int
    sale_price: int
    discount_pct: float
    category: str
    store: str = "Cruz Verde"
    image_url: str = ""


def scrape_category(
    url: str,
    category_name: str,
    min_discount: float = 30.0,
    max_pages: int = 5,
    debug: bool = False,
) -> list[Product]:
    seen_ids: set = set()
    results: list[Product] = []

    for term in SEARCH_TERMS:
        start = 0
        for _ in range(max_pages):
            try:
                resp = requests.get(
                    API_BASE,
                    params={
                        "q": term,
                        "expand": "prices,images",
                        "client_id": CLIENT_ID,
                        "count": PAGE_SIZE,
                        "start": start,
                    },
                    headers=HEADERS,
                    timeout=15,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                if debug:
                    print(f"  [cruzverde] Error q={term} start={start}: {e}")
                break

            hits = data.get("hits", [])
            total = data.get("total", 0)

            for hit in hits:
                pid = hit.get("product_id", "")
                if not pid or pid in seen_ids:
                    continue
                seen_ids.add(pid)

                prices = hit.get("prices", {})
                normal = int(prices.get("price-list-cl") or 0)
                sale = int(prices.get("price-sale-cl") or 0)

                if not normal or not sale or normal <= sale:
                    continue

                discount_pct = (normal - sale) / normal * 100
                if discount_pct < min_discount:
                    continue

                name = hit.get("product_name", "").strip()
                if not name:
                    continue

                image_data = hit.get("image", {}) or {}
                image_url = image_data.get("dis_base_link") or image_data.get("link") or ""

                slug = _make_slug(name[:80])
                product_url = f"{BASE_URL}/{slug}/{pid}.html"
                results.append(Product(
                    name=name[:120],
                    url=product_url,
                    normal_price=normal,
                    sale_price=sale,
                    discount_pct=round(discount_pct, 1),
                    category=category_name,
                    store="Cruz Verde",
                    image_url=image_url,
                ))

            if debug:
                found = sum(1 for h in hits if int((h.get("prices") or {}).get("price-list-cl") or 0) > int((h.get("prices") or {}).get("price-sale-cl") or 0))
                print(f"  [cruzverde] q={term} start={start}: {len(hits)}/{total} hits, {found} con descuento")

            start += PAGE_SIZE
            if start >= total or not data.get("next"):
                break

            time.sleep(0.3)

    return results
