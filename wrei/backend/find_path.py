import json

def find_items(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "items" and isinstance(v, list) and len(v) > 0:
                print(f"Found non-empty 'items' at: {path}.{k} (len: {len(v)})")
            find_items(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            find_items(item, f"{path}[{i}]")

with open("backend/sample_otodom.json", "r") as f:
    data = json.load(f)
    find_items(data)
