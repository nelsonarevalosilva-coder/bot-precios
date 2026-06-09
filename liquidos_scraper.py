"""
Scraper para Liquidos.cl — API REST propia.
Endpoint: https://www.liquidos.cl/api/products/category/{category}?store_id=9
URL de producto: https://www.liquidos.cl/productos/{id}/{slug}
"""
from dataclasses import dataclass
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://www.liquidos.cl/",
}
STORE_ID = 9
BASE_URL = "https://www.liquidos.cl"
API_URL = f"{BASE_URL}/api/products/category/{{category}}?store_id={STORE_ID}"


@dataclass
class Product:
    name: str
    url: str
    normal_price: int
    sale_price: int
    discount_pct: float
    category: str
    store: str = "Liquidos"


def scrape_category(
    url: str,
    category_name: str,
    min_discount: float = 30.0,
    max_pages: int = 1,
    debug: bool = False,
) -> list[Product]:
    # url contiene la categoría codificada como último segmento, p.ej. /whisky o /vino
    category_slug = url.rstrip("/").split("/")[-1]

    endpoint = API_URL.format(category=category_slug)
    try:
        resp = requests.get(endpoint, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        if debug:
            print(f"  [liquidos] Error al obtener {category_slug}: {e}")
        return []

    raw_products = resp.json().get("data", {}).get("products", [])
    if debug:
        print(f"  [liquidos] {category_slug}: {len(raw_products)} productos en API")

    results: list[Product] = []
    for p in raw_products:
        ref_price = p.get("reference_price")
        prices_list = p.get("prices", [])
        if not ref_price or not prices_list:
            continue

        normal_price = int(round(ref_price))
        sale_price = int(round(prices_list[0]["price"]))

        if normal_price <= 0 or sale_price <= 0 or sale_price >= normal_price:
            continue

        discount_pct = (normal_price - sale_price) / normal_price * 100
        if discount_pct < min_discount:
            continue

        product_id = p.get("id", "")
        slug = p.get("slug", "")
        product_url = f"{BASE_URL}/productos/{product_id}/{slug}" if product_id else BASE_URL

        name = p.get("name", "Sin nombre")
        sub_family = p.get("sub_family") or p.get("family") or category_name

        results.append(Product(
            name=name,
            url=product_url,
            normal_price=normal_price,
            sale_price=sale_price,
            discount_pct=discount_pct,
            category=sub_family,
            store="Liquidos",
        ))

    if debug:
        print(f"  [liquidos] {category_slug}: {len(results)} con >= {min_discount:.0f}% descuento")

    return results
