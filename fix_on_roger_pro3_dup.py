# -*- coding: utf-8 -*-
"""
一次性:修正 On THE ROGER Pro 3 重複商品的問題
------------------------------------------------------------
用途:
  add_on_roger_pro3.py 上架 Black|Ash 配色時,沒發現「男款 THE ROGER
  Pro 3」其實已經存在資料庫裡(id 是 p_on2_1784220363990_440,來自
  On 品牌本來就有的例行自動同步,不是我加的)——那筆舊資料的 link 用的是
  不帶顏色後綴的網址(.../mens),跟我這次核對用的顏色專屬網址
  (.../mens/black-ash-shoes-3MG10365204)不一樣,用 link 比對鍵完全
  比不出來是同一件商品,才會被我當成新商品另外新增,變成畫面上有兩張
  一模一樣「男款 THE ROGER Pro 3」的卡片。

  這支腳本修正做法:
    1. 把 Black|Ash 這個配色,合併進原本就存在的那筆(id=
       p_on2_1784220363990_440)的 colors 陣列裡,保留它原本的
       id/link/series 等所有欄位,也保留它原本另外兩個配色(溪流藍|Neem、
       亞麻色|萊姆綠)——那是例行自動同步维护的資料,不是我該動的範圍。
       Black|Ash 的每個尺寸標 stock:5(這個資料庫裡代表「確認有貨、
       實際件數未知」的慣例寫法,跟 scrape_9090.py 的做法一致——我核對
       官網當下只確認這 6 個尺寸的按鈕沒有被 disabled,沒有像自動同步
       那樣抓到精確庫存數字)。
    2. 刪掉 add_on_roger_pro3.py 造出來的那筆重複商品(id=
       p_on_1788625904155_0)。

  改完資料庫裡只會有一筆「男款 THE ROGER Pro 3」,colors 陣列有三個
  配色(溪流藍|Neem、亞麻色|萊姆綠、黑|灰)。

執行方式(透過 GitHub Actions 手動觸發):
  GitHub 網頁 -> 這個 repo -> Actions 分頁 -> 左邊選
  "One-off: fix On THE ROGER Pro 3 duplicate" -> 右邊 "Run workflow" 按鈕
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

EXISTING_ID = "p_on2_1784220363990_440"
DUPLICATE_ID = "p_on_1788625904155_0"

BLACK_ASH_COLOR = {
    "name": "黑 | 灰",
    "sizes": ["25-5", "26", "26-5", "27", "27-5", "28"],
    "image": (
        "https://images.ctfassets.net/hnk2vsx53n6l/4MEWFwNv2BA1anQlfOiBRi/"
        "5989992871cd0233e5bab28e39c3c8dc/a7ca383b7521fe2115f1a040d73d9aae5cfcc172.png?fm=webp"
    ),
    "stock": {s: 5 for s in ["25-5", "26", "26-5", "27", "27-5", "28"]},
}


def main():
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DB_URL})

    products = db.reference(PRODUCTS_PATH).get()
    if isinstance(products, dict):
        products = list(products.values())
    products = [p for p in products if p]

    existing = next((p for p in products if p.get("id") == EXISTING_ID), None)
    if existing is None:
        print(f"警告:找不到 id={EXISTING_ID} 這筆商品,沒有做任何合併,請人工檢查。")
        return

    if any(c.get("name") == BLACK_ASH_COLOR["name"] for c in existing.get("colors", [])):
        print("黑 | 灰 這個配色已經在裡面了,不重複加。")
    else:
        existing.setdefault("colors", []).append(BLACK_ASH_COLOR)
        print(f"已把「{BLACK_ASH_COLOR['name']}」合併進 {EXISTING_ID}。")

    before_count = len(products)
    products = [p for p in products if p.get("id") != DUPLICATE_ID]
    if len(products) < before_count:
        print(f"已刪除重複商品 id={DUPLICATE_ID}。")
    else:
        print(f"警告:找不到 id={DUPLICATE_ID} 這筆重複商品,可能已經被處理過了。")

    db.reference(PRODUCTS_PATH).set(products)
    print("已寫回 Firebase,完成!")

    db.reference(PRODUCTS_INDEX_PATH).set(build_products_index(products))
    print("索引已更新,完成!")


if __name__ == "__main__":
    main()
