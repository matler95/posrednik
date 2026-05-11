import httpx
params = {'page': 1, 'perPage': 10, 'filterCitySlug': 'warszawa'}
try:
    resp = httpx.get('https://deweloperuch.pl/api/sale-transactions', params=params, timeout=60)
    data = resp.json()
    print(f"Total: {data.get('pagination', {}).get('total')}")
    for r in data.get('data', []):
        print(f"ID: {r.get('sale_rcn_id')} | Date: {r.get('creation_date')}")
except Exception as e:
    print(f"Error: {e}")
