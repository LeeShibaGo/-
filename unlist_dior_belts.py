# -*- coding: utf-8 -*-
"""一次性:把 Dior 皮帶全部隱藏(不刪除資料)
------------------------------------------------------------
用途:
  老闆一開始要求把 Dior 皮帶下架,先做成標記缺貨(saleType: soldout)——
  後來澄清是要「整個藏起來,不要顯示在主頁」,不只是顯示缺貨徽章。改成
  額外加上 hidden: true,index.html 這邊客人瀏覽會用到的畫面(商品列表、
  本週新品、熱銷商品、分類選單、分享連結)都已經改成用 visibleProducts()
  (products.filter(p => !p.hidden))過濾掉這些商品,後台商品管理列表則
  故意不套用這個過濾,老闆自己在後台還是看得到、可以隨時把 hidden 改回
  false 重新上架。

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
            changed = False
            if p.get("saleType") != "soldout":
                p["saleType"] = "soldout"
                changed = True
            if not p.get("hidden"):
                p["hidden"] = True
                changed = True
            if changed:
                updated += 1

    print(f"共隱藏 {updated} 件 Dior 皮帶")
    db.reference(PRODUCTS_PATH).set(products)
    print("已寫回 Firebase,完成!")


if __name__ == "__main__":
    main()
