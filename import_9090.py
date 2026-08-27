# -*- coding: utf-8 -*-
"""一次性:把 scrape_9090.py 抓好的 9090_all_products.json 匯入資料庫
------------------------------------------------------------
用途:
  scrape_9090.py 只負責抓資料、輸出 JSON 檔,不會寫入 Firebase(資料庫
  規則鎖起來之後,寫入需要登入身分)。這支用服務帳號(Admin SDK)把那份
  JSON 加上商品 id 之後,合併進現有的 daigou-products-v1。

  這份 JSON 裡混著兩個品牌(brand 欄位是 "9090" 或 "9090 girl"),用
  link 當比對鍵、按各自的 brand 分開去重——不能只看「這個 link 有沒有
  出現過」,萬一兩個品牌未來剛好有相同 handle(理論上不會,但保險起見
  照抄 import_3coins.py 的慣例:key 是 (brand, link) 一組)。

  重跑是安全的:已經存在的商品會被跳過,不會重複匯入。

執行方式(透過 GitHub Actions 手動觸發):
  GitHub 網頁 -> 這個 repo -> Actions 分頁 -> 左邊選
  "One-off: import 9090 / 9090 girl catalog" -> 右邊 "Run workflow" 按鈕
"""

import json
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


def main():
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DB_URL})

    with open("9090_all_products.json", encoding="utf-8") as f:
        fresh_items = json.load(f)
    print(f"待匯入商品共 {len(fresh_items)} 件")

    products = db.reference(PRODUCTS_PATH).get()
    if isinstance(products, dict):
        products = list(products.values())
    products = [p for p in products if p]
    existing_keys = {
        (p.get("brand"), p.get("link")) for p in products
        if p.get("brand") in ("9090", "9090 girl")
    }
    print(f"資料庫裡已經有 {len(existing_keys)} 件 9090/9090 girl 商品")

    ts = int(time.time() * 1000)
    added = 0
    for idx, item in enumerate(fresh_items):
        key = (item.get("brand"), item.get("link"))
        if key in existing_keys:
            continue
        item["id"] = f"p_9090_{ts}_{idx}"
        item["addedAt"] = ts
        products.append(item)
        added += 1

    print(f"新增 {added} 件(其餘已存在,略過)")
    db.reference(PRODUCTS_PATH).set(products)
    print("已寫回 Firebase,完成!")

    db.reference(PRODUCTS_INDEX_PATH).set(build_products_index(products))
    print("索引已更新,完成!")


if __name__ == "__main__":
    main()
