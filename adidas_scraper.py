"""
Scraper para Adidas Chile — undetected-chromedriver bypasea Akamai.
"""
import json
import logging
import re
import time
from dataclasses import dataclass

try:
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    _HAS_UC = True
except ImportError:
    _HAS_UC = False

BASE_URL = "https://www.adidas.cl"


@dataclass
class Product:
    name: str
    url: str
    normal_price: int
    sale_price: int
    discount_pct: float
    category: str
    store: str = "Adidas"
    image_url: str = ""


def _clean_price(val) -> int | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return int(val)
    digits = re.sub(r"[^\d]", "", str(val))
    return int(digits) if digits and 3 <= len(digits) <= 8 else None


def _parse_items(items, category_name, min_discount, seen):
    results = []
    for item in (items or []):
        try:
            model_id = item.get("modelId") or item.get("id") or item.get("productId") or ""
            name = (item.get("displayName") or item.get("name") or item.get("title") or "").strip()
            if not name or not model_id or model_id in seen:
                continue
            product_url = f"{BASE_URL}/{model_id}.html"
            pricing = item.get("pricing") or item.get("price") or {}
            sale = _clean_price(pricing.get("currentPrice") or pricing.get("sale") or pricing.get("salePrice") or item.get("salePrice"))
            normal = _clean_price(pricing.get("standardPrice") or pricing.get("original") or pricing.get("originalPrice") or item.get("originalPrice"))
            imgs = item.get("image") or item.get("images") or {}
            image_url = (imgs.get("src") or imgs.get("url") or "") if isinstance(imgs, dict) else (imgs[0].get("src", "") if imgs else "")
            if not sale or not normal or normal <= sale:
                continue
            disc = (normal - sale) / normal * 100
            if disc < min_discount:
                continue
            seen.add(model_id)
            results.append(Product(name=name[:120], url=product_url, normal_price=normal,
                                   sale_price=sale, discount_pct=round(disc, 1),
                                   category=category_name, store="Adidas", image_url=image_url))
        except Exception:
            continue
    return results


def _extract_from_data(data, category_name, min_discount, seen):
    if not isinstance(data, dict):
        return []
    items = (data.get("raw", {}).get("itemList", {}).get("items") or
             data.get("itemList", {}).get("items") or
             data.get("products") or data.get("items") or [])
    if items:
        return _parse_items(items, category_name, min_discount, seen)
    for v in data.values():
        if isinstance(v, dict):
            result = _extract_from_data(v, category_name, min_discount, seen)
            if result:
                return result
    return []


def scrape_category(url, category_name, min_discount=25.0, max_pages=3, debug=False):
    logging.info("[adidas] Iniciando scrape: %s | uc=%s", category_name, _HAS_UC)
    if debug:
        print(f"  [adidas] scrape_category llamado: {category_name} | uc={_HAS_UC}")

    if not _HAS_UC:
        logging.error("[adidas] undetected-chromedriver no instalado. Corre: pip install undetected-chromedriver")
        return []

    all_products, seen = [], set()

    try:
        options = uc.ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--lang=es-CL")
        options.add_argument("--window-size=1920,1080")

        driver = uc.Chrome(options=options, version_main=None)
        try:
            # Warmup en home
            driver.get(BASE_URL)
            time.sleep(3)

            driver.get(url)
            time.sleep(5)

            # Scroll para cargar productos
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.5)")
            time.sleep(2)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(3)

            title = driver.title
            if debug:
                print(f"  [adidas] title={title[:60]}")

            # 1. Intentar __NEXT_DATA__
            try:
                next_json = driver.execute_script("return JSON.stringify(window.__NEXT_DATA__ || null)")
                if next_json and next_json != "null":
                    next_data = json.loads(next_json)
                    found = _extract_from_data(next_data, category_name, min_discount, seen)
                    if debug:
                        print(f"  [adidas] __NEXT_DATA__: {len(found)} productos")
                    all_products.extend(found)
            except Exception as e:
                if debug:
                    print(f"  [adidas] __NEXT_DATA__ error: {e}")

            # 2. Fetch in-browser al content-engine
            if not all_products:
                path = url.replace(BASE_URL, "").strip("/")
                ep = f"/api/plp/content-engine?query={path}&start=0&count=48&sort=discount-desc"
                try:
                    api_json = driver.execute_script(f"""
                        const r = await fetch('{ep}', {{credentials:'include', headers:{{'Accept':'application/json'}}}});
                        return r.ok ? await r.text() : JSON.stringify({{error: r.status}});
                    """)
                    if debug:
                        print(f"  [adidas] fetch: {str(api_json)[:80]}")
                    if api_json and '"error"' not in str(api_json)[:20]:
                        data = json.loads(api_json)
                        found = _extract_from_data(data, category_name, min_discount, seen)
                        all_products.extend(found)
                except Exception as e:
                    if debug:
                        print(f"  [adidas] fetch error: {e}")

        finally:
            driver.quit()

    except Exception as e:
        logging.error("[adidas] Error: %s", e)

    if debug:
        print(f"  [adidas] Total: {len(all_products)} productos >= {min_discount:.0f}%")
    return all_products
