import json
import logging
import re
from dataclasses import dataclass

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

try:
    from playwright_stealth import stealth_sync
    _HAS_STEALTH = True
except ImportError:
    _HAS_STEALTH = False

BASE_URL = "https://www.tricot.cl"


@dataclass
class Product:
    name: str
    url: str
    normal_price: int
    sale_price: int
    discount_pct: float
    category: str
    store: str = "Tricot"
    image_url: str = ""


def _clean_price(text: str) -> int | None:
    digits = re.sub(r"[^\d]", "", str(text))
    return int(digits) if digits and 3 < len(digits) < 10 else None


def _extract_next_data(next_json: str, category_name: str, min_discount: float) -> list[Product]:
    try:
        data = json.loads(next_json)
        results = data.get("props", {}).get("pageProps", {}).get("results", [])
    except Exception:
        return []

    products = []
    for item in results:
        try:
            name = item.get("displayName", "")
            if not name:
                continue

            prices = item.get("prices", {})
            if isinstance(prices, dict):
                normal = _clean_price(prices.get("price-list-cl") or prices.get("normalPrice", ""))
                sale = _clean_price(prices.get("price-sale-cl", ""))
            else:
                continue

            if not sale:
                continue
            if not normal:
                normal = sale

            url = item.get("url", "")
            if url.startswith("/"):
                url = BASE_URL + url
            if not url:
                continue

            disc = (normal - sale) / normal * 100 if normal > sale else 0.0
            if disc < min_discount:
                continue

            media = item.get("mediaUrls") or []
            img = media[0] if media else ""
            if not img:
                img = (item.get("primaryImage") or {}).get("url", "")

            products.append(Product(
                name=name[:120], url=url,
                normal_price=normal, sale_price=sale,
                discount_pct=round(disc, 1),
                category=category_name, store="Tricot",
                image_url=img,
            ))
        except Exception:
            continue

    return products


_TRICOT_JS = """() => {
    const results = [];
    const tiles = document.querySelectorAll(
        '.product-tile, [class*="product-tile"], [class*="productTile"]'
    );
    for (const tile of tiles) {
        const linkEl = tile.querySelector(
            '.name-link, .product-name a, .pdp-link a, a[href$=".html"]'
        );
        const listEl = tile.querySelector(
            '.price-standard, [class*="price-standard"], .original-price, del, s'
        );
        const saleEl = tile.querySelector(
            '.price-sales, .sales, [class*="price-sales"], [class*="price-internet"], .price-reduced'
        );
        const imgEl = tile.querySelector('img.primary-image, img[class*="primary"], img');
        if (!linkEl) continue;
        results.push({
            name: (linkEl.getAttribute('title') || linkEl.textContent).trim(),
            url: linkEl.href,
            list: listEl ? listEl.textContent.trim() : '',
            sale: saleEl ? saleEl.textContent.trim() : '',
            img: imgEl ? (imgEl.src || imgEl.getAttribute('data-src') || '') : '',
        });
    }
    return results;
}"""


def _parse_html(raw: list, category_name: str, min_discount: float, seen: set) -> list[Product]:
    products = []
    for item in raw:
        name = item.get("name", "").strip()
        url = item.get("url", "").strip()
        if not name or not url or url in seen:
            continue
        if not url.startswith("http"):
            url = BASE_URL + url if url.startswith("/") else url

        normal = _clean_price(item.get("list", ""))
        sale = _clean_price(item.get("sale", ""))

        if not sale:
            continue
        if not normal or normal <= sale:
            normal = sale
            disc = 0.0
        else:
            disc = (normal - sale) / normal * 100

        if disc < min_discount:
            continue

        products.append(Product(
            name=name[:120], url=url,
            normal_price=normal, sale_price=sale,
            discount_pct=round(disc, 1),
            category=category_name, store="Tricot",
            image_url=item.get("img", ""),
        ))
    return products


def scrape_category(
    url: str,
    category_name: str,
    min_discount: float = 20.0,
    max_pages: int = 10,
    debug: bool = False,
) -> list[Product]:
    all_products: list[Product] = []
    seen: set = set()

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled", "--disable-dev-shm-usage"],
            )
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="es-CL",
                viewport={"width": 1920, "height": 1080},
                extra_http_headers={"Accept-Language": "es-CL,es;q=0.9"},
            )
            page = context.new_page()
            if _HAS_STEALTH:
                stealth_sync(page)

            for page_num in range(max_pages):
                sep = "&" if "?" in url else "?"
                page_url = url if page_num == 0 else f"{url}{sep}page={page_num + 1}"

                try:
                    page.goto(page_url, wait_until="networkidle", timeout=45000)
                    page.wait_for_timeout(3000)
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.6)")
                    page.wait_for_timeout(2000)

                    if debug:
                        print(f"  [tricot] {category_name} p{page_num+1}: {page.title()[:50]}")

                    # Try __NEXT_DATA__ first (headless SFCC + Next.js)
                    batch = []
                    try:
                        next_json = page.eval_on_selector(
                            "script#__NEXT_DATA__", "el => el.textContent"
                        )
                        if next_json:
                            batch = _extract_next_data(next_json, category_name, min_discount)
                            batch = [p for p in batch if p.url not in seen]
                    except Exception:
                        pass

                    # Fall back to Demandware HTML extraction
                    if not batch:
                        raw = page.evaluate(_TRICOT_JS)
                        batch = _parse_html(raw, category_name, min_discount, seen)

                    seen.update(p.url for p in batch)
                    all_products.extend(batch)

                    if debug:
                        print(f"  [tricot] {len(batch)} nuevos (total {len(all_products)})")

                    if not batch and page_num > 0:
                        break

                except PlaywrightTimeout:
                    logging.warning("[tricot] Timeout en %s", page_url)
                    break
                except Exception as e:
                    logging.error("[tricot] Error: %s", e)
                    break

            browser.close()

    except Exception as e:
        logging.error("[tricot] Error general: %s", e)

    return all_products
