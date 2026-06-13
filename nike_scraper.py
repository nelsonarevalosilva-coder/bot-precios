"""
Scraper para Nike Chile — VTEX Catalog API pública.
Intenta 3 endpoints en orden hasta obtener datos.
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
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "cors",
}
BASE_URL = "https://www.nike.cl"
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
    session = requests.Session()
    session.headers.update(HEADERS)
    try:
        # Cargar home para obtener cookies Cloudflare (__cf_bm, etc.)
        r = session.get(BASE_URL + "/", timeout=12, allow_redirects=True)
        _ = r.status_code
    except Exception:
        pass
    return session


def _parse_vtex_products(products: list, category_name: str, min_discount: float, seen_ids: set) -> list[Product]:
    results = []
    for p in products:
        try:
            pid = str(p.get("productId") or p.get("productReference") or "")
            if not pid or pid in seen_ids:
                continue
            seen_ids.add(pid)

            name = p.get("productName", "").strip()
            link = p.get("link", "")
            product_url = link if link.startswith("http") else f"{BASE_URL}{link}"
            if not name or not product_url:
                continue

            price_range = p.get("priceRange", {})
            normal = int(price_range.get("listPrice", {}).get("highPrice") or 0)
            sale = int(price_range.get("sellingPrice", {}).get("lowPrice") or 0)

            if not normal or not sale:
                offer = p.get("items", [{}])[0].get("sellers", [{}])[0].get("commertialOffer", {})
                normal = int(offer.get("ListPrice") or 0)
                sale = int(offer.get("Price") or 0)

            if not normal or not sale or normal <= sale:
                continue

            discount_pct = (normal - sale) / normal * 100
            if discount_pct < min_discount:
                continue

            results.append(Product(
                name=name[:120],
                url=product_url,
                normal_price=normal,
                sale_price=sale,
                discount_pct=round(discount_pct, 1),
                category=category_name,
                store="Nike",
            ))
        except Exception:
            continue
    return results


def _scrape_catalog_api(session: requests.Session, category_name: str, min_discount: float,
                         max_pages: int, debug: bool) -> list[Product]:
    """Endpoint primario: VTEX catalog_system."""
    results = []
    seen_ids: set = set()
    api_url = f"{BASE_URL}/api/catalog_system/pub/products/search"

    for page_num in range(max_pages):
        start = page_num * PAGE_SIZE
        try:
            resp = session.get(api_url, params={
                "_from": start, "_to": start + PAGE_SIZE - 1,
                "fq": "C:/nike/oferta/", "O": "OrderByBestDiscountDESC",
            }, timeout=15)
            resp.raise_for_status()
            products = resp.json()
            if not isinstance(products, list) or not products:
                break
        except Exception as e:
            if debug:
                print(f"  [nike/catalog] Error start={start}: {e}")
            return []  # señal de fallo total para intentar el siguiente endpoint

        found = _parse_vtex_products(products, category_name, min_discount, seen_ids)
        results.extend(found)

        resources = resp.headers.get("resources", "")
        try:
            total = int(resources.split("/")[1]) if "/" in resources else 9999
        except Exception:
            total = 9999

        if debug:
            print(f"  [nike/catalog] start={start}: {len(products)} productos | con desc: {len(found)} | total: {total}")

        if start + PAGE_SIZE >= total:
            break
        time.sleep(0.4)

    return results


def _scrape_intelligent_search(session: requests.Session, category_name: str, min_discount: float,
                                max_pages: int, debug: bool) -> list[Product]:
    """Endpoint alternativo: intelligent-search."""
    results = []
    seen_ids: set = set()
    api_url = f"{BASE_URL}/api/intelligent-search/product_search"

    for page_num in range(1, max_pages + 1):
        try:
            resp = session.get(api_url, params={
                "query": "oferta sale descuento",
                "page": page_num,
                "count": PAGE_SIZE,
                "sort": "discount:desc",
                "locale": "es-CL",
                "selectedFacets": "category-2/oferta",
            }, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            products = data.get("products", [])
            if not products:
                break
        except Exception as e:
            if debug:
                print(f"  [nike/search] Error p{page_num}: {e}")
            return []

        for p in products:
            try:
                pid = str(p.get("productId") or "")
                if not pid or pid in seen_ids:
                    continue
                seen_ids.add(pid)

                name = p.get("productName", "").strip()
                link = p.get("link", "")
                product_url = link if link.startswith("http") else f"{BASE_URL}{link}"

                price_range = p.get("priceRange", {})
                normal = int(price_range.get("listPrice", {}).get("highPrice") or 0)
                sale = int(price_range.get("sellingPrice", {}).get("lowPrice") or 0)

                if not normal or not sale or normal <= sale:
                    continue
                discount_pct = (normal - sale) / normal * 100
                if discount_pct < min_discount:
                    continue

                results.append(Product(
                    name=name[:120], url=product_url,
                    normal_price=normal, sale_price=sale,
                    discount_pct=round(discount_pct, 1),
                    category=category_name, store="Nike",
                ))
            except Exception:
                continue

        if debug:
            print(f"  [nike/search] p{page_num}: {len(products)} productos")

        total_pages = data.get("pagination", {}).get("last", page_num)
        if page_num >= total_pages:
            break
        time.sleep(0.4)

    return results


def scrape_category(
    url: str,
    category_name: str,
    min_discount: float = 40.0,
    max_pages: int = 10,
    debug: bool = False,
) -> list[Product]:
    session = _make_session()

    # Intento 1: VTEX catalog_system (más completo)
    results = _scrape_catalog_api(session, category_name, min_discount, max_pages, debug)
    if results or results == []:
        # Si devolvió lista (aunque vacía), el endpoint respondió OK
        # Solo si hubo error total (retorna []) probamos el siguiente
        pass

    # Intento 2: intelligent-search como fallback
    if not results:
        if debug:
            print("  [nike] Fallback a intelligent-search")
        results = _scrape_intelligent_search(session, category_name, min_discount, max_pages, debug)

    return results
