# -*- coding: utf-8 -*-
"""一次性:抓 Merries(メリーズ)商品清單,補上真實價格/庫存,匯入資料庫
------------------------------------------------------------
用途:
  scrape_merries.py 的 fetch_catalog() 只能拿到商品名稱/圖片/分類,
  價格/庫存要用瀏覽器把 JS 跑完才抓得到(見 scrape_merries.py 開頭
  說明),所以跟 3COINS/POLENE 那種「先跑 scrape_xxx.py 產生完整 JSON
  檔、這支只負責匯入」的兩階段做法不一樣——這支自己內部就會用
  Playwright 逐一補齊 27 件商品的價格/庫存,一次做完「抓資料+匯入」。

  重跑這支是安全的:用 link 當比對鍵,已經存在的商品會被跳過,不會
  重複匯入或洗掉手動改過的欄位(例如已售件數)。

執行方式(透過 GitHub Actions 手動觸發):
  GitHub 網頁 -> 這個 repo -> Actions 分頁 -> 左邊選
  "One-off: import Merries catalog" -> 右邊 "Run workflow" 按鈕
"""

import sys
import time

import firebase_admin
from firebase_admin import credentials, db

from scrape_merries import HEADERS, extract_price_stock, fetch_catalog
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
    existing_links = {p.get("link") for p in products if p.get("brand") == "Merries"}
    print(f"資料庫裡已經有 {len(existing_links)} 件 Merries 商品")

    print("抓取メリーズ商品清單...")
    fresh_items = [it for it in fetch_catalog() if it["link"] not in existing_links]
    print(f"待匯入商品共 {len(fresh_items)} 件,開始用瀏覽器逐一補上價格/庫存...")

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(user_agent=HEADERS["User-Agent"])
        for idx, item in enumerate(fresh_items):
            try:
                # networkidle 在這個站會一直逾時(背景持續打分析追蹤請求,
                # 見 sync_stock.py sync_merries() 裡的說明),改用
                # domcontentloaded + extract_price_stock() 自己精準等 ld+json。
                page.goto(item["link"], timeout=30000, wait_until="domcontentloaded")
                jpy, in_stock = extract_price_stock(page)
            except Exception as e:
                print(f"  [{idx+1}/{len(fresh_items)}] 抓取失敗:{item['name']} ({e})")
                jpy, in_stock = None, None
            if jpy:
                item["jpy"] = jpy
            item["saleType"] = "instock" if in_stock else "soldout"
            print(f"  [{idx+1}/{len(fresh_items)}] {item['name']}: ¥{item['jpy']} "
                  f"({'現貨' if in_stock else '缺貨/抓取失敗'})")
            time.sleep(0.5)
        browser.close()

    fresh_items = [it for it in fresh_items if it["jpy"] > 0]
    print(f"成功抓到價格的有 {len(fresh_items)} 件(抓不到價格的略過,不匯入沒有售價的商品)")

    ts = int(time.time() * 1000)
    for idx, item in enumerate(fresh_items):
        item["id"] = f"p_merries_{ts}_{idx}"
        item["addedAt"] = ts
        products.append(item)

    print(f"新增 {len(fresh_items)} 件")
    db.reference(PRODUCTS_PATH).set(products)
    print("已寫回 Firebase,完成!")

    db.reference(PRODUCTS_INDEX_PATH).set(build_products_index(products))
    print("索引已更新,完成!")


if __name__ == "__main__":
    main()
