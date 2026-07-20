# -*- coding: utf-8 -*-
"""
Lacoste 日本官網(lacoste.jp)全站商品爬蟲
------------------------------------------------------------
用途:
  抓 lacoste.jp 全站商品(男女鞋類/服飾/配件/包款),不需要繞任何防護
  (不像 On/ASICS 有 Cloudflare/Akamai 擋),每個分類列表頁本身就內建
  Next.js 的 __NEXT_DATA__,裡面已經有貨號、庫存、原價/折扣價、圖片、
  顏色代碼 —— 不需要再逐一進商品頁。

  跟 On/Salomon 一樣,同一款不同色在列表資料裡是各自一筆(variantAmount
  通常是 1),之後靠「貨號去掉最後的顏色碼」合併成同一張商品卡。

執行方式:
  python scrape_lacoste.py
  會輸出 lacoste_raw.json(每個顏色一筆的原始資料),供
  _lacoste_import.py 進一步合併、翻譯、上架。
"""
import json
import re
import time

import requests

BASE = "https://www.lacoste.jp"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    )
}
NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)

CATEGORIES = [
    ("men/shoes", "MALE", "shoes"),
    ("women/shoes", "FEMALE", "shoes"),
    ("men/clothing", "MALE", "clothing"),
    ("women/clothing", "FEMALE", "clothing"),
    ("men/accessories", "MALE", "accessories"),
    ("women/accessories", "FEMALE", "accessories"),
    ("men/bags", "MALE", "bags"),
    ("women/bags", "FEMALE", "bags"),
]


def fetch_page(path, page):
    url = f"{BASE}/{path}?page={page}"
    res = requests.get(url, headers=HEADERS, timeout=25)
    res.raise_for_status()
    m = NEXT_DATA_RE.search(res.text)
    if not m:
        raise ValueError("no __NEXT_DATA__")
    data = json.loads(m.group(1))
    return data["props"]["pageProps"]["data"]


def main():
    all_items = []
    for path, gender_fallback, top_cat in CATEGORIES:
        page = 1
        total = None
        while True:
            try:
                d = fetch_page(path, page)
            except Exception as e:
                print(f"  [錯誤] {path} page {page}: {e}")
                break
            total = int(d.get("pagination", {}).get("total", 0))
            items = d.get("list", [])
            for it in items:
                it["_sourceCategory"] = top_cat
                it["_sourcePath"] = path
                all_items.append(it)
            print(f"{path} page {page}: +{len(items)} (累計 {len(all_items)}, 這個分類共 {total})")
            per_page = int(d.get("pagination", {}).get("perPage", 48))
            if page * per_page >= total or not items:
                break
            page += 1
            time.sleep(0.8)

    with open("lacoste_raw.json", "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False)
    print(f"\n完成!共抓到 {len(all_items)} 筆(每色一筆),已存成 lacoste_raw.json")


if __name__ == "__main__":
    main()
