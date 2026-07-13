import requests, json

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.easy.cl/",
    "Accept": "application/json",
}

r = requests.get(
    "https://ac.cnstrc.com/search/muebles",
    params={"key": "key_AimxrTjorsjiKQPy", "page": 1, "num_results_per_page": 3, "section": "Products"},
    headers=HEADERS, timeout=15
)
data = r.json()
results = data.get("response", {}).get("results", [])
if results:
    print("Campos disponibles en data:")
    print(json.dumps(results[0].get("data", {}), indent=2, ensure_ascii=False))
