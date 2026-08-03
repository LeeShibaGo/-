# -*- coding: utf-8 -*-
"""一次性:修正 DHC 商品價格漏算消費稅(x1.08)的問題
------------------------------------------------------------
用途:
  scrape_dhc.py / sync_stock.py 的 sync_dhc() 原本直接拿 DHC 商品頁
  JSON-LD 的 offers.price 當作日幣售價,但那個欄位其實是「未稅價」,
  官網實際顯示、客人實際要付的是「稅込(含稅)價」,差 8%(食品類消費稅)。
  用「濃縮プエラリアミリフィカ」(官網稅込4,104,JSON-LD寫3800)跟
  「カルシウム＋CBP」(官網特價稅込432,JSON-LD寫400)兩件商品交叉驗證過,
  兩者都剛好差 1.08 倍,確認是全站一致的規則,不是單一商品的巧合。

  兩支程式的抓取邏輯已經改成抓到價格後乘上 1.08,這支負責把「已經匯入、
  現在還停留在未稅價」的既有 252 件 DHC 商品資料一次性修正過來。

  用服務帳號(Admin SDK)寫入,因為資料庫規則已經鎖起來。

執行方式(透過 GitHub Actions 手動觸發):
  GitHub 網頁 -> 這個 repo -> Actions 分頁 -> 左邊選
  "One-off: fix DHC tax-excluded prices" -> 右邊 "Run workflow" 按鈕
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
        if p.get("brand") != "DHC":
            continue
        jpy = p.get("jpy")
        if not jpy:
            continue
        new_jpy = round(jpy * 1.08)
        if new_jpy != jpy:
            print(f"{p.get('name')}: ¥{jpy} -> ¥{new_jpy}")
            p["jpy"] = new_jpy
            updated += 1

    print(f"共修正 {updated} 件 DHC 商品的價格")
    db.reference(PRODUCTS_PATH).set(products)
    print("已寫回 Firebase,完成!")


if __name__ == "__main__":
    main()
