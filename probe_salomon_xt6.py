# -*- coding: utf-8 -*-
"""臨時探查(只讀):Salomon 壞掉的多色卡片,對照官網商品結構,評估重建方式"""
import json, re, sys, time, urllib.request
from collections import Counter, defaultdict

from sync_stock import load_products

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


allp = []
for page in range(1, 12):
    ps = (get(f"https://salomon.jp/products.json?limit=250&page={page}") or {}).get("products", [])
    allp += ps
    if len(ps) < 250: break
    time.sleep(1.5)
print("official products", len(allp))
by_handle = {p["handle"]: p for p in allp}
sample = by_handle.get("xt-6-l491433")
print("SAMPLE keys", list(sample.keys()))
print("SAMPLE tags", sample.get("tags"), "type", sample.get("product_type"), "vendor", sample.get("vendor"))

cards = [p for p in load_products() if p.get("brand") == "Salomon"]
link_handles = {(c.get("link") or "").rsplit("/", 1)[-1]: c for c in cards}
bad = [c for c in cards if len(c.get("colors", [])) > 1 and
       len({(x.get("image") or "").split("?")[0] for x in c["colors"]}) == 1]
print("cards", len(cards), "bad", len(bad))


def norm(t):
    return re.sub(r"^(男款|女款)\s*", "", t or "").strip().upper()


by_title = defaultdict(list)
for p in allp:
    by_title[norm(re.sub(r"^【NEW】", "", p["title"]))].append(p)

for c in bad[:6] + [x for x in bad if x["id"].endswith("_18")]:
    t = norm(c["name"])
    cand = by_title.get(t, [])
    standalone = sum(1 for p in cand if p["handle"] in link_handles and link_handles[p["handle"]] is not c)
    print(f"\nCARD {c['id']} {c['name']} colours={len(c['colors'])} link={c['link'].rsplit('/',1)[-1]}")
    print("  official same-title products:", len(cand), "already standalone cards:", standalone)
    for p in cand[:60]:
        col = p["options"][0]["values"][0] if p["options"] else "?"
        print("   ", p["handle"], "|", col, "|", p.get("tags")[:4] if p.get("tags") else "", "| standalone" if p["handle"] in link_handles and link_handles[p["handle"]] is not c else "")
    print("  card colour names:", [x["name"] for x in c["colors"]][:60])
