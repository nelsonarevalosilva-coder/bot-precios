"""
Scraper para Nike Chile — VTEX Catalog API pública.
Filtra directamente con fq=C:/nike/oferta/ para obtener solo productos en oferta.
Normal price: priceRange.listPrice | Sale price: priceRange.sellingPrice
"""
import time
from dataclasses import dataclass

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://www.nike.cl/",
    "Accept-Language": "es-CL,es;q=0.9",
}
BASE_URL = "https://www.nike.cl"
API_URL = f"{BASE_URL}/api/catalog_system/pub/products/search"
PAGE_SIZE = 50


@dataclass
class Product:
    name: str
    url: str
    normal_price: int
    sale_price: int
    discount_pct: float
    category: str
    store: str = "Nike"


def _make_session() -> requests.Session:
    """Crea sesión cargando el home para obtener cookies Cloudflare."""
    session = requests.Session()
    session.headers.update(HEADERS)
    try:
        session.get(BASE_URL + "/", timeout=10)
    except Exception:
        pass
    return session


def scrape_category(
    url: str,
    category_name: str,
    min_discount: float = 40.0,
    max_pages: int = 10,
    debug: bool = False,
) -> list[Product]:
    results: list[Product] = []
    seen_ids: set = set()
    start = 0
    session = _make_session()

    for _ in range(max_pages):
        try:
            resp = session.get(
                API_URL,
                params={
                    "_from": start,
                    "_to": start + PAGE_SIZE - 1,
                    "fq": "C:/nike/oferta/",
                    "O": "OrderByBestDiscountDESC",
                },
                headers=HEADERS,
                timeout=15,
            )
            resp.raise_for_status()
            products = resp.json()
        except Exception as e:
            if debug:
                print(f"  [nike] Error start={start}: {e}")
            break

        if not isinstance(products, list):
            break

        if not products:
            break

        # Total disponible desde el header resources (ej: "0-49/2397")
        resources = resp.headers.get("resources", "")
        try:
            total = int(resources.split("/")[1]) if "/" in resources else 9999
        except Exception:
            total = 9999

        for p in products:
            pid = p.get("productId") or p.get("productReference", "")
            if not pid or pid in seen_ids:
                continue
            seen_ids.add(pid)

            name = p.get("productName", "").strip()
            link = p.get("link", "")
            product_url = link if link.startswith("http") else f"{BASE_URL}{link}"
            if not name or not product_url:
                continue

            # Precios desde priceRange (nivel producto)
            price_range = p.get("priceRange", {})
            normal = int(price_range.get("listPrice", {}).get("highPrice") or 0)
            sale = int(price_range.get("sellingPrice", {}).get("lowPrice") or 0)

            # Fallback a items[0].sellers[0].commertialOffer
            if not normal or not sale:
                try:
                    offer = p["items"][0]["sellers"][0]["commertialOffer"]
                    normal = int(offer.get("ListPrice") or 0)
                    sale = int(offer.get("Price") or 0)
                except Exception:
                    continue

            if not normal or not sale or normal <= sale:
                continue

            discount_pct = (normal - sale) / normal * 100
            if discount_pct < min_discount:
                continue

            if debug:
                print(f"  [nike] {name[:55]} — ${sale:,} (normal ${normal:,}) {discount_pct:.1f}%")

            results.append(Product(
                name=name[:120],
                url=product_url,
                normal_price=normal,
                sale_price=sale,
                discount_pct=round(discount_pct, 1),
                category=category_name,
                store="Nike",
            ))

        if debug:
            print(f"  [nike] start={start}: {len(products)} productos, total={total}")

        start += PAGE_SIZE
        if start >= total:
            break
        time.sleep(0.4)

    return results
