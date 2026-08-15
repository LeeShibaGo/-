# -*- coding: utf-8 -*-
"""一次性:手動加入單一件商品(Callaway QUANTUM MAX D 發球木桿)
------------------------------------------------------------
用途:
  老闆指定要上架這一支球桿(來源頁面是 callaway.com.tw 台灣官網,不是
  一般代購流程的日本官網掃描;跟 MUSINSA/Nike/零食伴手禮那幾件一樣,
  是手動加的參考商品),售價老闆說之後再更新,現在先用「私訊報價」
  (quoteOnly)頂著,不亂填一個數字,等老闆之後在後台補上正式價格。

  規格(右手/9°/10.5° 兩種桿面角度 x Stiff/S.R 兩種桿身硬度,共 4 種
  組合)當作「尺寸」選項存,不是顏色——這支球桿沒有可選顏色,只有
  規格選擇。

  重跑這支是安全的:用 link 當比對鍵,已經存在就不會重複加入。

執行方式(透過 GitHub Actions 手動觸發):
  GitHub 網頁 -> 這個 repo -> Actions 分頁 -> 左邊選
  "One-off: add Callaway QUANTUM MAX D driver" -> 右邊 "Run workflow" 按鈕
"""

import sys
import time

import firebase_admin
from firebase_admin import credentials, db

from sync_stock import build_products_index

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

FIREBASE_DB_URL = "https://shibago-4dd3c-default-rtdb.asia-southeast1.firebasedatabase.app"
PRODUCTS_PATH = "daigou-products-v1"
PRODUCTS_INDEX_PATH = "daigou-products-index-v1"

NEW_PRODUCT = {
    "name": "Callaway QUANTUM MAX D 發球木桿",
    "jpy": 0,
    "quoteOnly": True,
    "weight": 0.6,
    "brand": "Callaway",
    "subtype": "一號木桿",
    "country": "JP",
    "saleType": "instock",
    "link": "https://callaway.com.tw/products/quantum-max-d-dr",
    "colors": [
        {
            "name": "",
            "sizes": ["右手／9°／Stiff", "右手／9°／S-R", "右手／10-5°／Stiff", "右手／10-5°／S-R"],
            "stock": {
                "右手／9°／Stiff": 1,
                "右手／9°／S-R": 1,
                "右手／10-5°／Stiff": 1,
                "右手／10-5°／S-R": 1,
            },
            "image": "https://cdn.shopify.com/s/files/1/0626/8246/4470/files/2501_Quantum_DRMAXD.jpg?v=1768543290",
        }
    ],
}


def main():
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DB_URL})

    products = db.reference(PRODUCTS_PATH).get()
    if isinstance(products, dict):
        products = list(products.values())
    products = [p for p in products if p]

    if any(p.get("link") == NEW_PRODUCT["link"] for p in products):
        print("這件商品已經存在(用 link 比對到),不重複加入。")
        return

    ts = int(time.time() * 1000)
    item = dict(NEW_PRODUCT)
    item["id"] = f"p_callaway_{ts}_0"
    item["addedAt"] = ts
    products.append(item)

    db.reference(PRODUCTS_PATH).set(products)
    print("已加入商品,寫回 Firebase 完成!")

    db.reference(PRODUCTS_INDEX_PATH).set(build_products_index(products))
    print("索引已更新,完成!")


if __name__ == "__main__":
    main()
