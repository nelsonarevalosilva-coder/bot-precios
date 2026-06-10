"""
Comparador de precios cross-store para productos electro.
Busca el mismo producto en Falabella, Paris y Easy sin Playwright.
"""
import json
import re
import time
from dataclasses import dataclass

import requests

import paris_scraper
import easy_scraper

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}
HEADERS_HTML = {**HEADERS, "Accept": "text/html,application/xhtml+xml"}


@dataclass
class StorePrice:
    store: str
    price: int
    url: str
    best: bool = False


def _clean_query(name: str) -> str:
    """Elimina caracteres especiales y trunca el query para mejorar el match."""
    # Quitar porcentajes, unidades raras, símbolos
    name = re.sub(r"\b\d+%|\boff\b|[(){}\[\]]", "", name, flags=re.IGNORECASE)
    # Tomar las primeras 6 palabras (evita queries muy largos)
    words = name.strip().split()[:6]
    return " ".join(words)


def _search_paris(query: str) -> StorePrice | None:
    try:
        encoded = requests.utils.quote(query)
        url = f"https://ac.cnstrc.com/search/{encoded}?key={paris_scraper.CNSTRC_KEY}&num_results_per_page=5"
        r = requests.get(url, headers=HEADERS, timeout=8)
        results = r.json().get("response", {}).get("results", [])
        best_price = None
        best_url = None
        for item in results:
            data = item.get("data", {})
            price = data.get("displayedPrice")
            item_url = data.get("url", "")
            if price and price > 100 and item_url:
                if best_price is None or price < best_price:
                    best_price = price
                    best_url = item_url
        if best_price:
            return StorePrice("Paris", int(best_price), best_url)
    except Exception:
        pass
    return None


def _search_easy(query: str) -> StorePrice | None:
    try:
        encoded = requests.utils.quote(query)
        url = f"https://ac.cnstrc.com/search/{encoded}?key={easy_scraper.CNSTRC_KEY}&num_results_per_page=5"
        r = requests.get(url, headers=HEADERS, timeout=8)
        results = r.json().get("response", {}).get("results", [])
        best_price = None
        best_url = None
        for item in results:
            data = item.get("data", {})
            price = data.get("sellingPrice") or data.get("price")
            item_url = data.get("url", "")
            if price and price > 100 and item_url:
                if best_price is None or price < best_price:
                    best_price = price
                    best_url = item_url
        if best_price:
            return StorePrice("Easy", int(best_price), best_url)
    except Exception:
        pass
    return None


def _search_falabella(query: str) -> StorePrice | None:
    try:
        encoded = requests.utils.quote(query)
        r = requests.get(
            f"https://www.falabella.com/falabella-cl/search?Ntt={encoded}&pgid=1",
            headers=HEADERS_HTML, timeout=10
        )
        m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', r.text, re.DOTALL)
        if not m:
            return None
        data = json.loads(m.group(1))
        results = data.get("props", {}).get("pageProps", {}).get("results", [])
        best_price = None
        best_url = None
        for p in results:
            prices_list = p.get("prices", [])
            sale_price = None
            for entry in prices_list:
                if not entry.get("crossed"):
                    raw = entry.get("price", [""])[0]
                    digits = re.sub(r"[^\d]", "", str(raw))
                    if digits:
                        val = int(digits)
                        if val > 100:
                            if sale_price is None or val < sale_price:
                                sale_price = val
            item_url = p.get("url", "")
            if sale_price and item_url:
                if best_price is None or sale_price < best_price:
                    best_price = sale_price
                    best_url = item_url
        if best_price:
            return StorePrice("Falabella", best_price, best_url)
    except Exception:
        pass
    return None


# Categorías para las que activamos la comparación
COMPARE_CATEGORIES = {
    "electro", "tecnologia", "electrodom", "refriger", "lavadora",
    "televisor", "television", "computador", "notebook", "celular",
    "smartphone", "tablet", "audio", "monitor", "impresora",
}


def should_compare(category: str) -> bool:
    cat_lower = category.lower()
    return any(k in cat_lower for k in COMPARE_CATEGORIES)


def compare_prices(product_name: str) -> list[StorePrice]:
    """Busca el producto en Falabella, Paris y Easy. Retorna lista ordenada por precio."""
    query = _clean_query(product_name)
    results = []

    for fn in [_search_falabella, _search_paris, _search_easy]:
        result = fn(query)
        if result:
            results.append(result)
        time.sleep(0.3)

    if not results:
        return []

    results.sort(key=lambda x: x.price)
    results[0].best = True
    return results


def format_comparison(results: list[StorePrice], current_store: str, current_price: int) -> str:
    """Genera el bloque de texto para incluir en la alerta de Telegram."""
    if not results:
        return ""

    lines = ["\n\n🏪 <b>Precio en otras tiendas:</b>"]
    for r in results:
        if r.store.lower() == current_store.lower():
            continue  # no repetir la tienda de origen
        star = "⭐ " if r.best and r.price < current_price else ""
        cheaper = f" <i>({((current_price - r.price) / current_price * 100):.0f}% más barato)</i>" if r.price < current_price else ""
        lines.append(f'  {star}<a href="{r.url}">{r.store}</a>: <b>${r.price:,}</b>{cheaper}')

    if len(lines) == 1:
        return ""  # solo había la tienda de origen, nada útil
    return "\n".join(lines)
