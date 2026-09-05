# -*- coding: utf-8 -*-
"""
一次性:把 HUMAN MADE CLASSIC ZIP-UP HOODIE 的原幣價格改成 ¥30,800
------------------------------------------------------------
用途:
  add_humanmade_product.py 上架時,官網頁面顯示的價格經查證高度懷疑是
  Global-e 跨境動態定價(不是日本當地原始售價),當時先用查得到的
  ¥6,100 頂著、標記待確認。2026-09-06 老闆自行確認實際日幣售價是
  ¥30,800,這支腳本只負責把這個欄位改過去,其他欄位(顏色/圖片/尺寸/
  分類/link)完全不動。

  用 link 當比對鍵(這個品牌目前只有這一件商品,理論上只會對到一筆)。

執行方式(透過 GitHub Actions 手動觸發):
  GitHub 網頁 -> 這個 repo -> Actions 分頁 -> 左邊選
  "One-off: fix HUMAN MADE hoodie price" -> 右邊 "Run workflow" 按鈕
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

TARGET_LINK = "https://www.humanmade.jp/en/new-arrivals/HM32CS022.html"
NEW_JPY = 30800


def main():
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DB_URL})

    products = db.reference(PRODUCTS_PATH).get()
    if isinstance(products, dict):
        products = list(products.values())
    products = [p for p in products if p]

    matched = [p for p in products if p.get("link") == TARGET_LINK]
    if not matched:
        print("警告:找不到 link 相符的商品,沒有任何東西被改到。")
        return

    for p in matched:
        old_jpy = p.get("jpy")
        p["jpy"] = NEW_JPY
        print(f"{p.get('name')}:¥{old_jpy} -> ¥{NEW_JPY}")

    db.reference(PRODUCTS_PATH).set(products)
    print("已寫回 Firebase,完成!")

    db.reference(PRODUCTS_INDEX_PATH).set(build_products_index(products))
    print("索引已更新,完成!")


if __name__ == "__main__":
    main()
