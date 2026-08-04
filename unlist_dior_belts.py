# -*- coding: utf-8 -*-
"""一次性:把 Dior 皮帶全部下架(標記缺貨,不刪除資料)
------------------------------------------------------------
用途:
  老闆要求把 Dior 皮帶這個分類先下架。這些商品沒有 colors 陣列(單一款式),
  跟 UHA/DHC 同一套簡單 schema,下架方式比照:把 saleType 設成 "soldout",
  商品卡片上會顯示「缺貨」、加入清單按鈕停用,但資料還在,之後想重新上架
  只要把 saleType 改回 "instock" 就好,不用重新輸入一次商品資料。

  用服務帳號(Admin SDK)寫入,因為資料庫規則已經鎖起來。

執行方式(透過 GitHub Actions 手動觸發):
  GitHub 網頁 -> 這個 repo -> Actions 分頁 -> 左邊選
  "One-off: unlist Dior belts" -> 右邊 "Run workflow" 按鈕
"""

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

    products = db.reference(PRODUCTS_PATH).get()
    if isinstance(products, dict):
        products = list(products.values())
    products = [p for p in products if p]

    updated = 0
    for p in products:
        if p.get("brand") == "Dior" and p.get("subtype") == "皮帶":
            if p.get("saleType") != "soldout":
                p["saleType"] = "soldout"
                updated += 1

    print(f"共下架 {updated} 件 Dior 皮帶")
    db.reference(PRODUCTS_PATH).set(products)
    print("已寫回 Firebase,完成!")


if __name__ == "__main__":
    main()
