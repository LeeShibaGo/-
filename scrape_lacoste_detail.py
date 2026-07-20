# -*- coding: utf-8 -*-
"""
Lacoste 商品詳細資料補全
------------------------------------------------------------
scrape_lacoste.py 抓到的分類列表,每個顏色只有「一筆代表性資料」,
沒有完整的尺寸庫存。但商品詳細頁(/products/{code}/{colorCode})一次
就會回傳「這個款式全部顏色 x 全部尺寸」的完整資料(貨號、庫存數量、
日本尺寸標示、顏色英文代碼),所以只需要對每個「獨立款式碼」(不是
每個顏色)抓一次詳細頁,效率比對每個顏色都抓一次高一倍以上。

輸出 lacoste_detail.json:{code: {name, description, variants:[...]}}
"""
import json
import re
import time

import requests

BASE = "https://www.lacoste.jp"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)


def fetch_detail(code, color_code, retries=3):
    url = f"{BASE}/products/{code}/{color_code}"
    for attempt in range(retries):
        try:
            res = requests.get(url, headers=HEADERS, timeout=25)
            res.raise_for_status()
            m = NEXT_DATA_RE.search(res.text)
            if not m:
                raise ValueError("no __NEXT_DATA__")
            data = json.loads(m.group(1))
            pr = data["props"]["pageProps"]["data"]["productResponse"]
            return pr["product"], pr.get("rdGroups", [])
        except Exception as e:
            if attempt == retries - 1:
                raise
            time.sleep(3 * (attempt + 1))


def main():
    raw = json.load(open("lacoste_raw.json", encoding="utf-8"))
    # 每個獨立款式碼只需要一個顏色代碼就能查到全部顏色+尺寸
    first_color = {}
    meta = {}
    for it in raw:
        code = it["code"]
        if code not in first_color:
            first_color[code] = it["variants"][0]["colorCode"]
            meta[code] = {
                "gender": it.get("properties", {}).get("gender"),
                "subCategories": it.get("properties", {}).get("subCategories", []),
                "topCategories": it.get("properties", {}).get("topCategories", []),
            }

    codes = list(first_color.keys())
    print(f"共 {len(codes)} 個獨立款式碼要抓詳細資料")

    results = {}
    errors = []
    for i, code in enumerate(codes):
        try:
            product, rd_groups = fetch_detail(code, first_color[code])
            color_zh = {}
            for g in rd_groups:
                if g.get("info", {}).get("code") == "ColorFilter":
                    for item in g["items"]:
                        color_zh[item["code"]] = item["name"]  # 日文顏色名
            results[code] = {
                "name": product.get("name", ""),
                "variants": product.get("variants", []),
                "colorNameJa": color_zh,
                "meta": meta[code],
            }
        except Exception as e:
            errors.append(f"{code}: {e}")
            print(f"  [錯誤] {code}: {e}")
        if (i + 1) % 20 == 0:
            print(f"進度 {i+1}/{len(codes)} (錯誤 {len(errors)})")
            with open("lacoste_detail.json", "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False)
        time.sleep(0.6)

    with open("lacoste_detail.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False)
    print(f"完成!{len(results)} 個款式,錯誤 {len(errors)} 個")


if __name__ == "__main__":
    main()
