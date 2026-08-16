# -*- coding: utf-8 -*-
"""一次性:加入 On Cloud X 5(男款)這一款,補進現有 On 目錄
------------------------------------------------------------
用途:
  老闆指定的商品(https://www.on.com/products/cloud-x-5-m-3mg3008/mens/
  white-black-shoes-3MG30080462,給的是 global 站網址),查過日本站
  sitemap(on.com/ja-jp/products.xml)確認同一貨號(3MG3008)在日本站
  也有上架,一樣是 3 個顏色(White|Black、Frost|Alloy、Black|Black),
  所以直接照現有 On 品牌完全一樣的抓法(scrape_on_full.py 的
  extract_ldjson()/extract_size_stock() 那一套 Nuxt 資料還原邏輯)抓
  真實的顏色/尺寸/庫存/售價,不是用手動輸入的假資料,跟目前站上其他
  On 商品資料格式、品質完全一致。

  這件商品目前不在資料庫裡(649 件現有 On 商品裡沒有比對到 cloud-x-5
  這個 handle),之後 sync_on() 每天同步時會照樣自動跟著更新庫存/價格,
  不需要另外處理。

  重跑這支是安全的:用 link 當比對鍵,已經存在就不會重複加入。

執行方式(透過 GitHub Actions 手動觸發):
  GitHub 網頁 -> 這個 repo -> Actions 分頁 -> 左邊選
  "One-off: add On Cloud X 5" -> 右邊 "Run workflow" 按鈕
"""

import sys
import time

import firebase_admin
from firebase_admin import credentials, db

from scrape_on_full import (
    BASE_URL, extract_ldjson, extract_size_stock, fetch_html,
    guess_subtype, guess_weight,
)
from sync_stock import build_products_index

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

FIREBASE_DB_URL = "https://shibago-4dd3c-default-rtdb.asia-southeast1.firebasedatabase.app"
PRODUCTS_PATH = "daigou-products-v1"
PRODUCTS_INDEX_PATH = "daigou-products-index-v1"
PRODUCT_URL = "https://www.on.com/ja-jp/products/cloud-x-5-m-3mg3008/mens/white-black-shoes-3MG30080462"
BRAND = "On"


def build_entry():
    html = fetch_html(PRODUCT_URL)
    group, breadcrumb = extract_ldjson(html)
    if not group:
        raise RuntimeError("抓不到 ProductGroup,官網頁面結構可能變了")

    subtype = guess_subtype(breadcrumb)
    weight = guess_weight(subtype)

    colors = []
    price = None
    for v in group.get("hasVariant", []):
        offer = v.get("offers", {})
        if price is None and offer.get("price"):
            price = offer["price"]
        color_url = offer.get("url", "")
        full_url = color_url if color_url.startswith("http") else BASE_URL + color_url
        print(f"  顏色:{v.get('color')}")
        color_html = fetch_html(full_url)
        sizes_stock = extract_size_stock(color_html)
        if not sizes_stock:
            print(f"    [警告] 這個顏色查不到尺寸庫存,略過")
            continue
        color_entry = {
            "name": v.get("color", ""),
            "sizes": list(sizes_stock.keys()),
            "stock": sizes_stock,
        }
        if v.get("image"):
            color_entry["image"] = v["image"]
        colors.append(color_entry)

    if not colors:
        raise RuntimeError("全部顏色都查不到尺寸庫存")

    entry = {
        "name": group.get("name", ""),
        "jpy": price or 0,
        "weight": weight,
        "brand": BRAND,
        "subtype": subtype,
        "country": "JP",
        "saleType": "instock",
        "link": group.get("url") or PRODUCT_URL,
        "colors": colors,
    }
    if colors[0].get("image"):
        entry["image"] = colors[0]["image"]
    return entry


def main():
    print("抓取商品資料...")
    new_item = build_entry()
    print(f"抓到:{new_item['name']},{len(new_item['colors'])} 個顏色,¥{new_item['jpy']}")

    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DB_URL})

    products = db.reference(PRODUCTS_PATH).get()
    if isinstance(products, dict):
        products = list(products.values())
    products = [p for p in products if p]

    if any(p.get("link") == new_item["link"] for p in products):
        print("這件商品已經存在(用 link 比對到),不重複加入。")
        return

    ts = int(time.time() * 1000)
    new_item["id"] = f"p_on_{ts}_0"
    new_item["addedAt"] = ts
    products.append(new_item)

    db.reference(PRODUCTS_PATH).set(products)
    print("已寫回 Firebase,完成!")

    db.reference(PRODUCTS_INDEX_PATH).set(build_products_index(products))
    print("索引已更新,完成!")


if __name__ == "__main__":
    main()
