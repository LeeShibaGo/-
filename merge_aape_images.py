# -*- coding: utf-8 -*-
"""一次性:把 aape_all_products.json 的顏色圖片合併回正式資料庫
------------------------------------------------------------
用途:
  scrape_aape.py 重新整批爬完之後,輸出的 aape_all_products.json 裡
  每個顏色現在都有各自正確的圖片(修好了原本很多商品顏色沒有圖片、
  或多個顏色共用同一張圖的問題)。這支程式把這份新資料合併回正式的
  daigou-products-v1,只更新 colors(連帶 jpy 價格一起更新為最新),
  不動 id、addedAt、extraSoldQty、twdOverride 這些既有欄位。

  用服務帳號(Admin SDK)寫入,因為資料庫規則已經鎖起來,不接受
  沒有驗證的寫入請求——這支只需要跑這一次,不用排進每天的排程。

執行方式(透過 GitHub Actions 手動觸發,不需要在本機安裝東西):
  GitHub 網頁 → 這個 repo → Actions 分頁 → 左邊選
  "One-off: merge AAPE images" → 右邊 "Run workflow" 按鈕
"""

import json
import sys

import firebase_admin
from firebase_admin import credentials, db

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

FIREBASE_DB_URL = "https://shibago-4dd3c-default-rtdb.asia-southeast1.firebasedatabase.app"
PRODUCTS_PATH = "daigou-products-v1"


def main():
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DB_URL})

    with open("aape_all_products.json", encoding="utf-8") as f:
        fresh_items = json.load(f)
    fresh_by_link = {it["link"]: it for it in fresh_items if it.get("link")}
    print(f"新資料共 {len(fresh_by_link)} 件")

    products = db.reference(PRODUCTS_PATH).get()
    if isinstance(products, dict):
        products = list(products.values())
    products = [p for p in products if p]
    print(f"資料庫現有商品共 {len(products)} 件")

    updated = not_matched = 0
    for p in products:
        if p.get("brand") != "AAPE":
            continue
        fresh = fresh_by_link.get(p.get("link"))
        if not fresh:
            not_matched += 1
            continue
        if fresh.get("colors"):
            p["colors"] = fresh["colors"]
        if fresh.get("jpy"):
            p["jpy"] = fresh["jpy"]
        updated += 1

    print(f"更新 {updated} 件,官網對不到(保留原樣) {not_matched} 件")

    db.reference(PRODUCTS_PATH).set(products)
    print("已寫回 Firebase,完成!")


if __name__ == "__main__":
    main()
