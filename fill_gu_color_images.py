# -*- coding: utf-8 -*-
"""一次性:補 GU 感謝祭商品卡「沒有圖片的顏色」(2026-11-21)。
GU 舊商品卡只有第一個顏色有圖,客人選其他顏色看到的還是同一張。這裡依顏色名稱對官網詳細頁的
顏色色碼,把該色的官網圖補上(圖片網址先確認真的載得到才寫);對不到的顏色不動。只動 image 欄位。
用法: python fill_gu_color_images.py report|apply"""
import json
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import requests

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

API = "https://www.gu-global.com/jp/api/commerce/v5/ja/products"
HEADERS = {"x-fr-clientid": "gu.jp.web-spa", "User-Agent": "Mozilla/5.0"}
DB = "https://shibago-4dd3c-default-rtdb.asia-southeast1.firebasedatabase.app"
CAMPAIGN = "gu-kanshasai-2026"


def works(u):
    try:
        r = requests.get(u, headers=HEADERS, timeout=20, stream=True)
        ok = r.status_code == 200 and "image" in (r.headers.get("content-type") or "")
        r.close()
        return ok
    except Exception:
        return False


def main():
    mode = (sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
    if mode not in ("report", "apply"):
        sys.exit("用法:python fill_gu_color_images.py report|apply")
    if mode == "apply":
        from sync_stock import load_products_by_brand, merge_and_save, firebase_app
        firebase_app()
        cards = load_products_by_brand("GU")
    else:
        raw = json.load(urllib.request.urlopen(DB + '/daigou-products-v1.json?orderBy="brand"&equalTo="GU"'))
        cards = list(raw.values())
    cards = [p for p in cards if p.get("campaign") == CAMPAIGN]

    import re

    def detail(p):
        m = re.search(r"/products/([^/]+)/", p.get("link") or "")
        time.sleep(0.1)
        try:
            d = requests.get(f"{API}/{m.group(1)}", params={"withPrices": "true", "httpFailure": "true"},
                             headers=HEADERS, timeout=25).json()
            return p["id"], d["result"] if d.get("status") == "ok" else None
        except Exception:
            return p["id"], None

    with ThreadPoolExecutor(4) as ex:
        det = dict(ex.map(detail, cards))
    filled = missed = 0
    changed = []
    for p in cards:
        res = det.get(p["id"])
        if not res or p.get("mergedProductIds"):
            continue
        by_name = {}
        for l2 in res["l2s"]:
            by_name.setdefault(l2["color"]["name"], l2["color"]["displayCode"])
        touched = False
        for c in p.get("colors") or []:
            if c.get("image"):
                continue
            code = by_name.get(c.get("name"))
            url = (res["images"]["main"].get(code) or {}).get("image") if code else None
            if url and works(url):
                c["image"] = url
                filled += 1
                touched = True
            else:
                missed += 1
        if touched:
            changed.append(p)
    print(f"補上 {filled} 個顏色圖;補不到 {missed} 個;要寫入 {len(changed)} 張卡")
    if mode == "apply" and changed:
        merge_and_save(changed)
        print("完成!")


if __name__ == "__main__":
    main()
