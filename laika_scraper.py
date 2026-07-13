"""
Scraper para Laika Mascotas Chile — API interna Next.js.
Usa /api/proxy/v1/products/promotions/search con X-COUNTRY-ID: 1 (Chile).
Precios: price.sale = normal, price.final = oferta, price.discount = %.
"""
import time
from dataclasses import dataclass

import requests

BASE_URL = "https://laikamascotas.cl"
PROMOTIONS_API = f"{BASE_URL}/api/proxy/v1/products/promotions/search"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "X-COUNTRY-ID": "1",
}


@dataclass
class Product:
    name: str
    url: str
    normal_price: int
    sale_price: int
    discount_pct: float
    category: str
    store: str = "Laika"
    image_url: str = ""


def scrape_category(
    url: str,
    category_name: str,
    min_discount: float = 25.0,
    max_pages: int = 5,
    debug: bool = False,
) -> list[Product]:
    results: list[Product] = []
    seen_ids: set = set()

    for page in range(1, max_pages + 1):
        try:
            resp = requests.get(
                PROMOTIONS_API,
                params={"page": page, "limit": 50},
                headers=HEADERS,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            if debug:
                print(f"  [laika] Error página {page}: {e}")
            break

        products = data.get("products") or []
        if not products:
            break

        found = 0
        for p in products:
            pid = p.get("id") or p.get("referenceId")
            if not pid or pid in seen_ids:
                continue
            seen_ids.add(pid)

            price = p.get("price") or {}
            normal = int(price.get("sale") or 0)
            final = int(price.get("final") or 0)
            discount = float(price.get("discount") or 0)

            if not normal or not final or final >= normal:
                continue
            if discount < min_discount:
                continue

            name = (p.get("name") or "").strip()
            if not name:
                continue

            slug = p.get("slug") or ""
            product_url = f"{BASE_URL}/{slug}" if slug else BASE_URL

            image = p.get("image") or {}
            image_url = image.get("url") or ""

            results.append(Product(
                name=name[:120],
                url=product_url,
                normal_price=normal,
                sale_price=final,
                discount_pct=round(discount, 1),
                category=category_name,
                store="Laika",
                image_url=image_url,
            ))
            found += 1

        if debug:
            print(f"  [laika] página {page}: {len(products)} productos, {found} con >= {min_discount:.0f}%")

        if len(products) < 50:
            break

        time.sleep(0.3)

    return results
