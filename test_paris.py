import requests
import json
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

resp = requests.get(
    "https://ac.cnstrc.com/search/outlet",
    params={
        "key": "key_8pjkPsSkEsJHKgxR",
        "page": 1,
        "num_results_per_page": 5,
        "section": "Products",
    },
    headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.paris.cl/"},
    timeout=15,
)

data = resp.json()
results = data.get("response", {}).get("results", [])
print(f"Total resultados: {len(results)}")

for i, item in enumerate(results[:3]):
    d = item.get("data", {})
    print(f"\n--- Producto {i+1}: {item.get('value', '')[:60]} ---")
    print(f"  TODOS los campos en data:")
    for k, v in sorted(d.items()):
        val_str = str(v)[:120] if not isinstance(v, (list, dict)) else json.dumps(v)[:120]
        print(f"    {k}: {val_str}")
