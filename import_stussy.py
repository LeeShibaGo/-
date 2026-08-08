# -*- coding: utf-8 -*-
"""一次性:把 scrape_stussy.py 抓好的 stussy_all_products.json 匯入資料庫
------------------------------------------------------------
用途:
  scrape_stussy.py 只負責抓資料、輸出 JSON 檔,不會寫入 Firebase(資料庫
  規則鎖起來之後,寫入需要登入身分,一般 requests 沒辦法直接寫)。這支
  用服務帳號(Admin SDK)把那份 JSON 加上商品 id 之後,合併進現有的
  daigou-products-v1(不影響其他品牌的資料)。

  重跑這支是安全的:用 link 當比對鍵,已經存在的商品會被跳過,不會
  重複匯入或洗掉手動改過的欄位(例如已售件數)。

執行方式(透過 GitHub Actions 手動觸發):
  GitHub 網頁 -> 這個 repo -> Actions 分頁 -> 左邊選
  "One-off: import STUSSY catalog" -> 右邊 "Run workflow" 按鈕
"""

import json
import sys
import time

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

    with open("stussy_all_products.json", encoding="utf-8") as f:
        fresh_items = json.load(f)
    print(f"待匯入商品共 {len(fresh_items)} 件")

    products = db.reference(PRODUCTS_PATH).get()
    if isinstance(products, dict):
        products = list(products.values())
    products = [p for p in products if p]
    existing_links = {p.get("link") for p in products if p.get("brand") == "STUSSY"}
    print(f"資料庫裡已經有 {len(existing_links)} 件 STUSSY 商品")

    ts = int(time.time() * 1000)
    added = 0
    for idx, item in enumerate(fresh_items):
        if item.get("link") in existing_links:
            continue
        item["id"] = f"p_stussy_{ts}_{idx}"
        item["addedAt"] = ts
        products.append(item)
        added += 1

    print(f"新增 {added} 件(其餘已存在,略過)")
    db.reference(PRODUCTS_PATH).set(products)
    print("已寫回 Firebase,完成!")


if __name__ == "__main__":
    main()
