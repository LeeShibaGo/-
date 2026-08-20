# -*- coding: utf-8 -*-
"""一次性:修正已匯入 Merries 商品的空白圖片
------------------------------------------------------------
用途:
  import_merries.py 第一次跑的時候,圖片網址原封不動保留了官網 JSON
  清單裡的 "?hide=1&fmt=png8-alpha" 這組 query string,結果連到 Adobe
  Scene7 圖片伺服器回傳的是空白圖(老闆截圖回報「沒有商品圖片」查出來
  的原因,見 scrape_merries.py 裡 fetch_catalog() 的說明,拿掉這組
  參數圖片就正常了)。scrape_merries.py 已經修好,之後新匯入的商品
  不會再有這個問題,但這 20 件已經在資料庫裡的舊資料還帶著壞掉的
  網址,這支負責把它們一次修正過來。

  只動 brand == "Merries" 的商品,不影響其他品牌。重跑是安全的:
  已經是乾淨網址(不含 "?")的商品會被跳過,不會重複處理。

執行方式(透過 GitHub Actions 手動觸發):
  GitHub 網頁 -> 這個 repo -> Actions 分頁 -> 左邊選
  "One-off: fix Merries product images" -> 右邊 "Run workflow" 按鈕
"""

import sys

import firebase_admin
from firebase_admin import credentials, db

from sync_stock import build_products_index

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

FIREBASE_DB_URL = "https://shibago-4dd3c-default-rtdb.asia-southeast1.firebasedatabase.app"
PRODUCTS_PATH = "daigou-products-v1"
PRODUCTS_INDEX_PATH = "daigou-products-index-v1"


def main():
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DB_URL})

    products = db.reference(PRODUCTS_PATH).get()
    if isinstance(products, dict):
        products = list(products.values())
    products = [p for p in products if p]

    fixed = 0
    for p in products:
        if p.get("brand") != "Merries":
            continue
        image = p.get("image")
        if image and "?" in image:
            old = image
            p["image"] = image.split("?", 1)[0]
            print(f"  修正:{p.get('name')}\n    {old}\n    -> {p['image']}")
            fixed += 1

    print(f"共修正 {fixed} 件商品的圖片網址")
    if fixed == 0:
        print("沒有需要修正的商品,結束。")
        return

    db.reference(PRODUCTS_PATH).set(products)
    print("已寫回 Firebase,完成!")

    db.reference(PRODUCTS_INDEX_PATH).set(build_products_index(products))
    print("索引已更新,完成!")


if __name__ == "__main__":
    main()
