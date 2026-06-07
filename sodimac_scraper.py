"""
Scraper de Sodimac Chile.
Misma estructura que Falabella: pageProps.results en __NEXT_DATA__.
"""

import json
import re
import time
from dataclasses import dataclass

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from playwright_stealth import Stealth

BASE_URL = "https://www.sodimac.cl/sodimac-cl"


@dataclass
class Product:
    name: str
    url: str
    normal_price: int
    sale_price: int
    discount_pct: float
    category: str
    store: str = "Sodimac"


def _clean_price(text: str) -> int | None:
    digits = re.sub(r"[^\d]", "", str(text))
    return int(digits) if digits and 3 < len(digits) < 10 else None


def _parse_prices(prices_list: list) -> tuple[int | None, int | None]:
    normal = None
    sale = None
    for p in prices_list:
        raw = p.get("price", [""])[0] if p.get("price") else ""
        val = _clean_price(raw)
        if not val:
            continue
        if p.get("crossed"):
            normal = val
        else:
            if sale is None or val < sale:
                sale = val
    return normal, sale


def _extract_products(next_data_json: str, category_name: str, min_discount: float) -> list[Product]:
    try:
        data = json.loads(next_data_json)
        results = data.get("props", {}).get("pageProps", {}).get("results", [])
    except Exception:
        return []

    products = []
    for item in results:
        try:
            name = item.get("displayName", "")
            if not name:
                continue

            url = item.get("url", "")
            if not url:
                continue

            prices_list = item.get("prices", [])
            normal_price, sale_price = _parse_prices(prices_list)

            if not sale_price:
                continue

            if normal_price and normal_price > sale_price:
                discount = (normal_price - sale_price) / normal_price * 100
            else:
                badge = item.get("discountBadge", {}) or {}
                label = badge.get("label", "")
                m = re.search(r"(\d+)", label)
                discount = float(m.group(1)) if m else 0.0
                if not normal_price and discount > 0:
                    normal_price = int(sale_price / (1 - discount / 100))

            is_price_error = normal_price and sale_price < 1000 and normal_price > 5000

            if discount < min_discount and not is_price_error:
                continue

            if is_price_error and normal_price:
                discount = (normal_price - sale_price) / normal_price * 100

            products.append(Product(
                name=name[:120],
                url=url,
                normal_price=normal_price or sale_price,
                sale_price=sale_price,
                discount_pct=round(discount, 1),
                category=category_name,
                store="Sodimac",
            ))
        except Exception:
            continue

    return products


def scrape_category(
    url: str,
    category_name: str,
    min_discount: float = 70.0,
    max_pages: int = 3,
    debug: bool = False,
) -> list[Product]:
    all_products: list[Product] = []

    with Stealth().use_sync(sync_playwright()) as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="es-CL",
            viewport={"width": 1920, "height": 1080},
        )
        page = context.new_page()

        for page_num in range(max_pages):
            sep = "&" if "?" in url else "?"
            page_url = url if page_num == 0 else f"{url}{sep}page={page_num + 1}"

            try:
                page.goto(page_url, wait_until="load", timeout=40000)
                time.sleep(4)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.5)")
                time.sleep(1)

                if debug:
                    print(f"    [sodimac] {category_name} p{page_num+1}: {page.title()[:50]}")

                next_data = page.eval_on_selector("script#__NEXT_DATA__", "el => el.textContent")
                if not next_data:
                    break

                found = _extract_products(next_data, category_name, min_discount)
                if debug:
                    print(f"    [sodimac] Con >={min_discount:.0f}% desc: {len(found)}")

                all_products.extend(found)

                try:
                    data = json.loads(next_data)
                    pagination = data.get("props", {}).get("pageProps", {}).get("pagination", {})
                    total_pages = pagination.get("totalPages", 1)
                    if page_num + 1 >= total_pages:
                        break
                except Exception:
                    break

                time.sleep(2)

            except PlaywrightTimeout:
                print(f"    [sodimac] Timeout en {page_url}")
                break
            except Exception as e:
                print(f"    [sodimac] Error: {e}")
                break

        browser.close()

    seen = set()
    unique = []
    for p in all_products:
        if p.url not in seen:
            seen.add(p.url)
            unique.append(p)

    return unique
