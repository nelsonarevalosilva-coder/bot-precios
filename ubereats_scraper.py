"""
Uber Eats Chile restaurant promotions scraper.
Uses Playwright headless=False to establish session, then curl_cffi for subsequent calls.
Session is cached in ubereats_session.json and auto-refreshed when expired.
"""

import asyncio
import json
import logging
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
SESSION_FILE = BASE_DIR / "ubereats_session.json"
UBEREATS_BASE = "https://www.ubereats.com"
FEED_URL = f"{UBEREATS_BASE}/_p/api/getFeedV1?localeCode=cl"

SANTIAGO_ADDR = "Alameda 340, Santiago, Chile"

PCT_RE = re.compile(r'(\d+)%\s*de\s*descuento', re.IGNORECASE)
CLP_RE = re.compile(r'\$([0-9.,]+)\s*de\s*descuento', re.IGNORECASE)
FREE_DELIVERY_RE = re.compile(r'env[íi]o\s+gratis|despacho\s+gratis|env[íi]o\s+sin\s+costo|\$0\s*env[íi]o', re.IGNORECASE)
FREE_ITEM_RE = re.compile(r'art[íi]culo\s+sin\s+costo|gratis\s+en\s+la\s+compra', re.IGNORECASE)


@dataclass
class UEPromo:
    name: str
    promo_text: str
    url: str
    eta: str
    rating: Optional[float]
    discount_pct: int = 0       # % off (e.g. 40)
    discount_clp: int = 0       # CLP fixed discount (e.g. 2780)
    is_free_delivery: bool = False
    is_free_item: bool = False
    uuid: str = ""


def _parse_clp(s: str) -> int:
    """'$2.780' → 2780"""
    cleaned = s.replace(".", "").replace(",", "").replace("$", "").strip()
    try:
        return int(cleaned)
    except ValueError:
        return 0


def _parse_store(s: dict) -> Optional[UEPromo]:
    if not isinstance(s, dict):
        return None
    name = s.get("title", {}).get("text", "?") if isinstance(s.get("title"), dict) else "?"
    action_url = s.get("actionUrl", "")
    url = f"{UBEREATS_BASE}{action_url}" if action_url else UBEREATS_BASE

    meta = s.get("meta") or []
    eta = "?"
    for m_item in meta:
        if isinstance(m_item, dict) and m_item.get("badgeType") == "ETD":
            eta = m_item.get("text", "?")
            break
    if eta == "?" and meta and isinstance(meta[0], dict):
        eta = meta[0].get("text", "?")

    rating_data = s.get("rating") or {}
    try:
        rating = float(rating_data.get("text", "")) if isinstance(rating_data, dict) else None
    except (ValueError, TypeError):
        rating = None

    signposts = s.get("signposts") or []
    all_texts = [sp.get("text", "") for sp in signposts if isinstance(sp, dict)]
    promo_text = " | ".join(t for t in all_texts if t)

    discount_pct = 0
    discount_clp = 0
    is_free_delivery = False
    is_free_item = False

    for text in all_texts:
        m = PCT_RE.search(text)
        if m:
            discount_pct = max(discount_pct, int(m.group(1)))
        m2 = CLP_RE.search(text)
        if m2:
            discount_clp = max(discount_clp, _parse_clp(m2.group(1)))
        if FREE_DELIVERY_RE.search(text):
            is_free_delivery = True
        if FREE_ITEM_RE.search(text):
            is_free_item = True

    return UEPromo(
        name=name,
        promo_text=promo_text,
        url=url,
        eta=eta,
        rating=rating,
        discount_pct=discount_pct,
        discount_clp=discount_clp,
        is_free_delivery=is_free_delivery,
        is_free_item=is_free_item,
        uuid=s.get("storeUuid", ""),
    )


def _load_session() -> Optional[dict]:
    if not SESSION_FILE.exists():
        return None
    try:
        with open(SESSION_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save_session(data: dict):
    with open(SESSION_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def _call_feed(session: dict) -> Optional[dict]:
    """Call getFeedV1 with saved cookies + request body via curl_cffi."""
    try:
        from curl_cffi import requests as cf
    except ImportError:
        logger.error("curl_cffi not installed")
        return None

    cookies = session.get("cookies", [])
    request_body = session.get("request_body")
    if not request_body:
        return None

    sess = cf.Session(impersonate="chrome124")
    for c in cookies:
        sess.cookies.set(c["name"], c["value"], domain=c.get("domain", ".ubereats.com"))

    headers = {
        "x-csrf-token": "x",
        "content-type": "application/json",
        "accept-language": "es-CL",
        "referer": "https://www.ubereats.com/cl/feed",
    }

    try:
        if isinstance(request_body, str):
            body_bytes = request_body.encode()
        else:
            body_bytes = json.dumps(request_body).encode()

        r = sess.post(FEED_URL, data=body_bytes, headers=headers, timeout=20)
        if r.status_code != 200:
            logger.warning(f"getFeedV1 returned {r.status_code}")
            return None
        data = r.json()
        fd = data.get("data", {})
        items = fd.get("feedItems", [])
        if not items:
            logger.warning("getFeedV1 returned 0 feedItems — session likely expired")
            return None
        logger.info(f"getFeedV1: {len(items)} feedItems, currency={fd.get('currencyCode')}")
        return fd
    except Exception as e:
        logger.warning(f"getFeedV1 error: {e}")
        return None


async def _refresh_session_async() -> Optional[dict]:
    """Use Playwright headless=False to get fresh cookies and request body."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.error("playwright not installed")
        return None

    logger.info("Refreshing Uber Eats session via Playwright (browser will open)...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        ctx = await browser.new_context(locale="es-CL", viewport={"width": 1280, "height": 900})
        await ctx.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
        """)
        page = await ctx.new_page()

        captured_body = None
        captured_resp = None

        async def on_req(req):
            nonlocal captured_body
            if "_p/api/getFeedV1" in req.url:
                captured_body = req.post_data

        async def on_resp(resp):
            nonlocal captured_resp
            if "_p/api/getFeedV1" in resp.url and resp.status == 200:
                try:
                    captured_resp = await resp.body()
                except Exception:
                    pass

        page.on("request", on_req)
        page.on("response", on_resp)

        await page.goto(f"{UBEREATS_BASE}/cl", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)

        inp = await page.query_selector("input[placeholder*='irección']")
        if inp:
            await inp.click()
            await asyncio.sleep(0.5)
            await inp.type(SANTIAGO_ADDR, delay=40)
            await asyncio.sleep(3)
            try:
                await page.wait_for_selector("li[role='option']", timeout=6000)
                sugs = await page.query_selector_all("li[role='option']")
                if sugs:
                    await sugs[0].click()
                    logger.info("Address set, waiting for feed...")
                    await asyncio.sleep(10)
            except Exception as e:
                logger.warning(f"Address suggestion not found: {e}")
        else:
            logger.warning("Address input not found")
            await asyncio.sleep(5)

        cookies = await ctx.cookies()
        await browser.close()

        if not cookies:
            logger.error("No cookies captured")
            return None

        session = {
            "cookies": cookies,
            "request_body": captured_body,
        }
        _save_session(session)
        logger.info(f"Session saved ({len(cookies)} cookies)")
        return session


def _refresh_session() -> Optional[dict]:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    return asyncio.run(_refresh_session_async())


def _extract_stores(feed_data: dict) -> list[dict]:
    stores = []
    seen = set()
    for item in feed_data.get("feedItems", []):
        t = item.get("type", "")
        if t == "REGULAR_STORE":
            s = item.get("store", {})
            uid = s.get("storeUuid", "")
            if uid not in seen:
                seen.add(uid)
                stores.append(s)
        elif t == "REGULAR_CAROUSEL":
            for s in item.get("carousel", {}).get("stores", []) or []:
                uid = s.get("storeUuid", "")
                if uid not in seen:
                    seen.add(uid)
                    stores.append(s)
        elif t == "FEATURED_STORES":
            for s in item.get("payload", {}).get("stores", []) or []:
                uid = s.get("storeUuid", "")
                if uid not in seen:
                    seen.add(uid)
                    stores.append(s)
    return stores


def scrape_restaurants(
    min_discount: int = 20,
    min_clp: int = 2000,
    include_free_delivery: bool = True,
    include_free_item: bool = True,
    force_refresh: bool = False,
    debug: bool = False,
) -> list[UEPromo]:
    """
    Scrape Uber Eats Chile restaurant promotions.
    Returns promos matching: discount_pct >= min_discount OR discount_clp >= min_clp
    OR is_free_delivery OR is_free_item.
    """
    session = None if force_refresh else _load_session()
    feed_data = None

    if session:
        feed_data = _call_feed(session)

    if feed_data is None:
        session = _refresh_session()
        if session:
            feed_data = _call_feed(session)

    if feed_data is None:
        logger.error("Could not fetch Uber Eats feed")
        return []

    raw_stores = _extract_stores(feed_data)
    logger.info(f"UberEats: {len(raw_stores)} stores in feed")

    results = []
    for s in raw_stores:
        promo = _parse_store(s)
        if promo is None:
            continue
        if debug and promo.promo_text:
            logger.debug(f"  {promo.name:<35} | {promo.promo_text}")

        qualifies = (
            promo.discount_pct >= min_discount
            or promo.discount_clp >= min_clp
            or (include_free_delivery and promo.is_free_delivery)
            or (include_free_item and promo.is_free_item)
        )
        if qualifies:
            results.append(promo)

    logger.info(f"UberEats: {len(results)} qualifying promos")
    return results


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.DEBUG, format="%(message)s")
    promos = scrape_restaurants(min_discount=20, min_clp=2000, debug=True)
    print(f"\n{'='*60}")
    print(f"PROMOS ACTIVAS EN UBER EATS ({len(promos)} restaurantes)")
    print("="*60)
    for p in sorted(promos, key=lambda x: -x.discount_pct):
        if p.discount_pct:
            tag = f"{p.discount_pct}% Off"
        elif p.discount_clp:
            tag = f"${p.discount_clp:,} Off"
        elif p.is_free_delivery:
            tag = "Envio Gratis"
        else:
            tag = "Promo"
        print(f"  {tag:<15} | {p.name:<35} | {p.eta:<8} | {p.promo_text}")
