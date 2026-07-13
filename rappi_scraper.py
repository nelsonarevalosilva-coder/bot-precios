"""
Rappi Chile restaurant promotions scraper.
Extracts active promotions (% discount, free delivery) from rappi.cl/restaurantes
via server-side rendered __NEXT_DATA__ — no auth required.
"""

import json
import re
import time
import logging
from dataclasses import dataclass, field
from typing import Optional

from curl_cffi import requests as cf

logger = logging.getLogger(__name__)

RAPPI_RESTAURANTS_URL = "https://www.rappi.cl/restaurantes"
RAPPI_MARKET_URL = "https://www.rappi.cl/tiendas/tipo/market"
RAPPI_BASE = "https://www.rappi.cl"

DISCOUNT_RE = re.compile(r'(\d+)\s*%', re.IGNORECASE)
FREE_SHIPPING_RE = re.compile(r'envío?\s+gratis|despacho\s+gratis|free\s+shipping', re.IGNORECASE)


@dataclass
class RappiPromo:
    name: str
    promo_text: str
    url: str
    delivery_cost: Optional[int]
    has_free_shipping: bool
    eta: str
    rating: Optional[float]
    discount_pct: int = 0       # 0 if not a % discount
    is_free_delivery: bool = False
    store_type: str = "restaurant"   # "restaurant" | "market"

    @classmethod
    def from_restaurant(cls, r: dict) -> "RappiPromo":
        promo_text = r.get("promotionText", "")
        name = r.get("name", "?")
        store_id = r.get("id", "")
        slug = name.lower().replace(" ", "-").replace("'", "")
        url = f"{RAPPI_BASE}/restaurantes/{store_id}-{slug}"

        disc_match = DISCOUNT_RE.search(promo_text)
        discount_pct = int(disc_match.group(1)) if disc_match else 0
        is_free = FREE_SHIPPING_RE.search(promo_text) is not None or r.get("hasFreeShipping", False)

        return cls(
            name=name,
            promo_text=promo_text,
            url=url,
            delivery_cost=r.get("deliveryCost"),
            has_free_shipping=r.get("hasFreeShipping", False),
            eta=r.get("etaString", "?"),
            rating=r.get("rating"),
            discount_pct=discount_pct,
            is_free_delivery=is_free,
            store_type="restaurant",
        )


def _make_session() -> cf.Session:
    sess = cf.Session(impersonate="chrome124")
    sess.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "es-CL,es;q=0.9",
    })
    return sess


def _extract_nextdata_restaurants(html: str) -> list[dict]:
    """Extract restaurant list from __NEXT_DATA__ embedded JSON."""
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
        pp = data.get("props", {}).get("pageProps", {})
        return pp.get("catalog", {}).get("restaurants", [])
    except (json.JSONDecodeError, KeyError):
        logger.warning("Failed to parse __NEXT_DATA__")
        return []


def scrape_restaurants(
    min_discount: int = 20,
    include_free_delivery: bool = True,
    debug: bool = False,
) -> list[RappiPromo]:
    """
    Scrape Rappi Chile restaurant promotions.

    Returns promos that meet criteria:
    - discount_pct >= min_discount (e.g. "Hasta 40% Off")
    - OR is_free_delivery == True and include_free_delivery
    """
    sess = _make_session()
    try:
        r = sess.get(RAPPI_RESTAURANTS_URL, timeout=25)
        r.raise_for_status()
    except Exception as e:
        logger.error(f"Failed to fetch Rappi restaurants: {e}")
        return []

    raw_restaurants = _extract_nextdata_restaurants(r.text)
    if not raw_restaurants:
        logger.warning("No restaurants found in Rappi NEXT_DATA")
        return []

    results = []
    seen_ids = set()

    for raw in raw_restaurants:
        store_id = raw.get("id")
        if store_id in seen_ids:
            continue
        seen_ids.add(store_id)

        promo_text = raw.get("promotionText", "")
        if not promo_text:
            continue

        promo = RappiPromo.from_restaurant(raw)

        if debug:
            logger.debug(f"  {promo.name:<35} | {promo.promo_text}")

        if promo.discount_pct >= min_discount:
            results.append(promo)
        elif include_free_delivery and promo.is_free_delivery:
            results.append(promo)

    logger.info(f"Rappi: {len(raw_restaurants)} restaurants scraped, {len(results)} with qualifying promos")
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(message)s")
    promos = scrape_restaurants(min_discount=20, include_free_delivery=True, debug=True)
    print(f"\n{'='*60}")
    print(f"PROMOS ACTIVAS EN RAPPI ({len(promos)} restaurantes)")
    print("="*60)
    for p in sorted(promos, key=lambda x: -x.discount_pct):
        tag = f"🔥 {p.discount_pct}% Off" if p.discount_pct else "🚚 Envío Gratis"
        cost_str = "GRATIS" if p.has_free_shipping else f"${p.delivery_cost:,}" if p.delivery_cost else "?"
        print(f"  {tag:<18} | {p.name:<35} | {p.eta:<8} | {p.promo_text}")
