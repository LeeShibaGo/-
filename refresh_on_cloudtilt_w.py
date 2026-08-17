# -*- coding: utf-8 -*-
"""一次性:把「女款 Cloudtilt」的顏色整組重新跟官網核對
------------------------------------------------------------
用途:
  老闆發現這款鞋少了一個官網現在真的有賣的顏色(Biscuit | Ivory),一查
  才發現資料庫存的 6 個顏色(Ether|象牙白、墨灰|黑、淡紫色|櫻花粉、
  白|象牙白、珍珠白|冰色、淺灰藍|Heather)跟官網現在實際在賣的 5 個顏色
  (Black|Ivory、Eclipse|Black、Ether|Ivory、White|Ivory、
  Biscuit|Ivory)對不太起來——每天的 sync_on() 只會更新「已經存在的
  顏色」庫存/價格,不會主動發現官網後來新增的顏色,也不會把官網已經
  下架的舊顏色從清單拿掉,久了就會跟官網實際顏色兜不起來。

  這支直接把這一款鞋的顏色整組換成「現在重新抓到的官網真實顏色」,
  不是只加一個顏色——比較徹底,舊的顏色如果官網已經下架就會跟著消失,
  新的顏色(包含這次要補的 Biscuit | Ivory)會出現。跟
  scrape_on_full.py/add_on_cloud_x5.py 用同一套抓法(extract_ldjson +
  逐色 extract_size_stock),資料品質一致。

  只動這一款鞋(用 link 比對),不影響資料庫裡其他 On 商品。

執行方式(透過 GitHub Actions 手動觸發):
  GitHub 網頁 -> 這個 repo -> Actions 分頁 -> 左邊選
  "One-off: refresh On Cloudtilt women's colors" -> 右邊 "Run workflow" 按鈕
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
PRODUCT_URL = "https://www.on.com/ja-jp/products/cloudtilt-w-3we1005/womens"


def build_colors():
    html = fetch_html(PRODUCT_URL)
    group, breadcrumb = extract_ldjson(html)
    if not group:
        raise RuntimeError("抓不到 ProductGroup,官網頁面結構可能變了")

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
            print("    [警告] 這個顏色查不到尺寸庫存,略過")
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

    return colors, price, group, breadcrumb


def main():
    print("抓取官網現在真實的顏色清單...")
    colors, price, group, breadcrumb = build_colors()
    print(f"抓到 {len(colors)} 個顏色:{[c['name'] for c in colors]}")

    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DB_URL})

    products = db.reference(PRODUCTS_PATH).get()
    if isinstance(products, dict):
        products = list(products.values())
    products = [p for p in products if p]

    target = next((p for p in products if p.get("link") == PRODUCT_URL), None)
    if not target:
        print(f"[錯誤] 資料庫裡找不到 link == {PRODUCT_URL} 的商品,沒有東西可以更新。")
        return

    old_color_names = [c.get("name") for c in target.get("colors", [])]
    target["colors"] = colors
    if colors[0].get("image"):
        target["image"] = colors[0]["image"]
    if price and price != target.get("jpy"):
        print(f"順便更新價格:¥{target.get('jpy')} → ¥{price}")
        target["jpy"] = price

    print(f"舊顏色:{old_color_names}")
    print(f"新顏色:{[c['name'] for c in colors]}")

    db.reference(PRODUCTS_PATH).set(products)
    print("已寫回 Firebase,完成!")

    db.reference(PRODUCTS_INDEX_PATH).set(build_products_index(products))
    print("索引已更新,完成!")


if __name__ == "__main__":
    main()
