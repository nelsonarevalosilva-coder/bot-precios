import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "es-CL,es;q=0.9",
}

tests = [
    # Rappi
    ("https://services.rappi.com/api/web-gateway/v1/chile/stores/?lat=-33.4489&lng=-70.6693&is_prime=false", "Rappi stores"),
    ("https://services.rappi.com/api/prime-offers/v2/banners?country_code=cl", "Rappi banners"),
    # Pedidos Ya
    ("https://www.pedidosya.cl/api/restaurants?city=1&cuisines=&order=RELEVANCE", "PedidosYa restaurants"),
    # Uber Eats
    ("https://www.ubereats.com/api/getFeedV1?localeCode=es-CL", "UberEats feed"),
]

for url, name in tests:
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        print(f"{name}: {r.status_code} | {len(r.text)} chars | {r.text[:100]}")
    except Exception as e:
        print(f"{name}: ERROR — {e}")
