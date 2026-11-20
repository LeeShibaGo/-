# -*- coding: utf-8 -*-
"""
一次性(可重跑):修 UNIQLO 商品卡上「載入失敗的圖片網址」(2026-11-20 上線前測試發現 23 張)
------------------------------------------------------------
UNIQLO 的圖檔有兩種網址格式,有的商品只有其中一種能載入:
  .../ST3/jp/imagesgoods/<商品>/item/jpgoods_<色碼>_<商品>_3x4.jpg      (舊格式,部分商品已失效)
  .../ST3/AsianCommon/imagesgoods/<商品>/item/goods_<色碼>_<商品>_3x4.jpg (通用格式)
做法:逐一檢查每張 UNIQLO 商品卡的主圖/各顏色圖,載入失敗的就依序試備用網址:
  1. AsianCommon ... goods_..._3x4.jpg   2. AsianCommon ... goods_....jpg   3. jp ... jpgoods_....jpg
找到能載入的就換掉;都不行的:顏色圖直接移除(商品卡會用主圖當預設),主圖壞了就改用第一張
能載入的顏色圖;完全沒有能用的圖就不動,報告裡列出來。只改圖片欄位,不動價格/庫存/名稱。

用法:
  python fix_uniqlo_broken_images.py report   # 只看報告,不寫入
  python fix_uniqlo_broken_images.py apply    # 寫入(走 GitHub Actions)
"""

import json
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import requests

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

DB = "https://shibago-4dd3c-default-rtdb.asia-southeast1.firebasedatabase.app"
HEADERS = {"User-Agent": "Mozilla/5.0"}
_cache = {}


def works(url):
    if url in _cache:
        return _cache[url]
    ok = False
    for _ in range(2):
        try:
            r = requests.get(url, headers=HEADERS, timeout=20, stream=True)
            ok = r.status_code == 200 and "image" in (r.headers.get("content-type") or "") \
                and int(r.headers.get("content-length") or 1000) > 500
            r.close()
            break
        except Exception:
            continue
    _cache[url] = ok
    return ok


def alternates(url):
    m = re.search(r"imagesgoods/(\d+)/item/(?:jp)?goods_(\w+?)_(\d+)", url or "")
    if not m:
        return []
    pid, code = m.group(1), m.group(2)
    return [
        f"https://image.uniqlo.com/UQ/ST3/AsianCommon/imagesgoods/{pid}/item/goods_{code}_{pid}_3x4.jpg",
        f"https://image.uniqlo.com/UQ/ST3/AsianCommon/imagesgoods/{pid}/item/goods_{code}_{pid}.jpg",
        f"https://image.uniqlo.com/UQ/ST3/jp/imagesgoods/{pid}/item/jpgoods_{code}_{pid}.jpg",
    ]


def main():
    mode = (sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
    if mode not in ("report", "apply"):
        print("用法:python fix_uniqlo_broken_images.py report|apply")
        sys.exit(1)

    if mode == "apply":
        from sync_stock import load_products_by_brand, merge_and_save, firebase_app
        firebase_app()
        cards = load_products_by_brand("UNIQLO")
    else:
        raw = json.load(urllib.request.urlopen(DB + '/daigou-products-v1.json?orderBy="brand"&equalTo="UNIQLO"'))
        cards = list(raw.values()) if isinstance(raw, dict) else raw
    print(f"UNIQLO 商品卡 {len(cards)} 張")

    urls = set()
    for p in cards:
        if p.get("image"):
            urls.add(p["image"])
        for c in p.get("colors") or []:
            if c.get("image"):
                urls.add(c["image"])
    print(f"檢查 {len(urls)} 個圖片網址…")
    with ThreadPoolExecutor(16) as ex:
        list(ex.map(works, urls))
    broken = [u for u in urls if not _cache[u]]
    print(f"載入失敗 {len(broken)} 個")

    fixed_alt, removed_color, main_swapped, unfixable = 0, 0, 0, []
    changed = []
    for p in cards:
        touched = False
        for c in p.get("colors") or []:
            u = c.get("image")
            if u and not _cache.get(u, True):
                new = next((a for a in alternates(u) if works(a)), None)
                if new:
                    c["image"] = new
                    fixed_alt += 1
                else:
                    del c["image"]
                    removed_color += 1
                touched = True
        u = p.get("image")
        if u and not _cache.get(u, True):
            new = next((a for a in alternates(u) if works(a)), None)
            if not new:
                new = next((c["image"] for c in p.get("colors") or [] if c.get("image")), None)
                main_swapped += 1 if new else 0
            else:
                fixed_alt += 1
            if new:
                p["image"] = new
            else:
                unfixable.append(p.get("name"))
            touched = True
        if touched:
            changed.append(p)
    print(f"改成備用網址 {fixed_alt} 個;移除失效的顏色圖 {removed_color} 個;主圖改用顏色圖 {main_swapped} 個;"
          f"完全沒圖可用 {len(unfixable)} 張 {unfixable[:5]}")
    print(f"要寫入的商品卡:{len(changed)} 張")

    if mode == "report":
        print("(report 模式:沒有寫入)")
        return
    if changed:
        merge_and_save(changed)
        print(f"完成!已寫入 {len(changed)} 張卡。")


if __name__ == "__main__":
    main()
