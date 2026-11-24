# -*- coding: utf-8 -*-
"""臨時探查:salomon.jp 官網 XT-6 的商品/顏色/圖片結構(只讀,不寫資料庫)"""
import json, sys, time, urllib.request

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

def get(url):
    for i in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=30) as r:
                return json.loads(r.read())
        except Exception as e:
            print("retry", url, e); time.sleep(5 * (i + 1))
    return None

d = get("https://salomon.jp/products/xt-6-l491433.js")
if d:
    print("TITLE", d["title"], "options", d["options"], "variants", len(d["variants"]), "images", len(d["images"]))
    for v in d["variants"][:12]:
        print(" V", v["id"], v["title"], v["available"], v.get("sku"), (v.get("featured_image") or {}).get("src", "")[-60:])
    print(" colours", len({v["option1"] for v in d["variants"]}))
allp = []
for page in range(1, 12):
    ps = (get(f"https://salomon.jp/products.json?limit=250&page={page}") or {}).get("products", [])
    allp += ps
    if len(ps) < 250: break
    time.sleep(1.5)
print("total", len(allp))
xt = [p for p in allp if "xt-6" in p["handle"] or "XT-6" in p["title"]]
print("xt6 products", len(xt))
for p in xt[:8]:
    print(p["handle"], p["title"], [o["name"] for o in p["options"]], len(p["variants"]), len(p["images"]))
