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
    _HAS_UC = True
except Exception:
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
            model_id = (item.get("modelId") or item.get("id") or
                        item.get("productId") or item.get("sku") or "")
            name = (item.get("displayName") or item.get("name") or
                    item.get("title") or "").strip()
            if not name or not model_id or model_id in seen:
                continue
            product_url = f"{BASE_URL}/{model_id}.html"
            pricing = item.get("pricing") or item.get("price") or {}
            sale = _clean_price(
                pricing.get("currentPrice") or pricing.get("sale") or
                pricing.get("salePrice") or item.get("salePrice") or
                item.get("currentPrice")
            )
            normal = _clean_price(
                pricing.get("standardPrice") or pricing.get("original") or
                pricing.get("originalPrice") or item.get("originalPrice") or
                item.get("standardPrice")
            )
            imgs = item.get("image") or item.get("images") or {}
            if isinstance(imgs, dict):
                image_url = imgs.get("src") or imgs.get("url") or ""
            elif isinstance(imgs, list) and imgs:
                image_url = imgs[0].get("src", "") if isinstance(imgs[0], dict) else ""
            else:
                image_url = ""
            if not sale or not normal or normal <= sale:
                continue
            disc = (normal - sale) / normal * 100
            if disc < min_discount:
                continue
            seen.add(model_id)
            results.append(Product(
                name=name[:120], url=product_url, normal_price=normal,
                sale_price=sale, discount_pct=round(disc, 1),
                category=category_name, store="Adidas", image_url=image_url,
            ))
        except Exception:
            continue
    return results


def _deep_extract(data, category_name, min_discount, seen):
    if not isinstance(data, dict):
        return []
    items = (
        data.get("raw", {}).get("itemList", {}).get("items") or
        data.get("itemList", {}).get("items") or
        data.get("products") or data.get("items") or []
    )
    if items:
        return _parse_items(items, category_name, min_discount, seen)
    for v in data.values():
        if isinstance(v, dict):
            r = _deep_extract(v, category_name, min_discount, seen)
            if r:
                return r
    return []


def _make_options():
    """Siempre crear un objeto ChromeOptions nuevo — no reutilizar."""
    opts = uc.ChromeOptions()
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--disable-software-rasterizer")
    opts.add_argument("--lang=es-CL")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--no-first-run")
    opts.add_argument("--no-default-browser-check")
    return opts


def scrape_category(url, category_name, min_discount=25.0, max_pages=3, debug=False):
    logging.info("[adidas] Iniciando: %s | uc=%s", category_name, _HAS_UC)

    if not _HAS_UC:
        logging.error("[adidas] undetected-chromedriver no disponible")
        return []

    all_products, seen = [], set()

    try:
        driver = uc.Chrome(options=_make_options(), headless=True, version_main=149)
        try:
            driver.get(BASE_URL)
            time.sleep(3)

            driver.get(url)
            time.sleep(5)

            title = driver.title
            body = driver.find_element("tag name", "body").text[:300]
            blocked = any(w in body for w in [
                "UNABLE TO GIVE YOU ACCESS", "security issue", "Reference #",
            ])

            if debug:
                print(f"  [adidas] title={title[:50]} | blocked={blocked}")

            if blocked:
                logging.warning("[adidas] Akamai bloqueó %s", category_name)
                return []

            driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.5)")
            time.sleep(2)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(3)

            # 1. __NEXT_DATA__
            try:
                nxt = driver.execute_script("return JSON.stringify(window.__NEXT_DATA__ || null)")
                if nxt and nxt != "null":
                    found = _deep_extract(json.loads(nxt), category_name, min_discount, seen)
                    if debug:
                        print(f"  [adidas] __NEXT_DATA__: {len(found)} productos")
                    all_products.extend(found)
            except Exception:
                pass

            # 2. In-browser fetch usando execute_async_script
            if not all_products:
                path = url.replace(BASE_URL, "").strip("/")
                ep = f"/api/plp/content-engine?query={path}&start=0&count=48&sort=discount-desc"
                try:
                    driver.set_script_timeout(20)
                    result = driver.execute_async_script(f"""
                        var done = arguments[arguments.length - 1];
                        fetch('{ep}', {{
                            credentials: 'include',
                            headers: {{'Accept': 'application/json'}}
                        }})
                        .then(function(r) {{ return r.ok ? r.text() : JSON.stringify({{error:r.status}}); }})
                        .then(function(t) {{ done(t); }})
                        .catch(function(e) {{ done(JSON.stringify({{error:e.message}})); }});
                    """)
                    if result and '"error"' not in str(result)[:20]:
                        found = _deep_extract(json.loads(result), category_name, min_discount, seen)
                        if debug:
                            print(f"  [adidas] fetch: {len(found)} productos")
                        all_products.extend(found)
                except Exception as fe:
                    if debug:
                        print(f"  [adidas] fetch error: {fe}")

        finally:
            try:
                driver.quit()
            except Exception:
                pass
            time.sleep(2)

    except Exception as e:
        logging.error("[adidas] Error general: %s", e)

    logging.info("[adidas] %s: %d productos >= %.0f%%", category_name, len(all_products), min_discount)
    if debug:
        print(f"  [adidas] Total: {len(all_products)} productos >= {min_discount:.0f}%")
    return all_products
