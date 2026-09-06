# -*- coding: utf-8 -*-
"""
一次性:修正 POLÈNE 顏色名稱是空字串的商品
------------------------------------------------------------
用途:
  scrape_polene.py 的 guess_color_name() 原本用字面上的「 - 」
  (連字號左右都要有空格)去切商品標題取顏色名稱,官網有些標題是
  「Numéro Un -トリオ キャメル」這種連字號後面沒空格,切不出來,
  colors[0].name 就變成空字串——畫面上的顏色選單因此顯示錯位,跑去
  顯示尺寸「FREE」,而不是空白(2026-09-06 老闆截圖回報)。

  scrape_polene.py 本身已經改成用正規表示式(連字號前後空格都選填),
  之後排程重新爬一次就會抓對,但現在資料庫裡已經匯入的舊資料不會自己
  變好,這支腳本補跑一次同樣的邏輯,把現有資料裡顏色名稱是空字串的
  項目,直接從商品自己的 name 欄位重新切一次填回去。

  只改 colors[].name 是空字串、而且用同一套規則切得出非空結果的項目,
  切不出來的(理論上不會發生,防呆用)保持原樣、印出警告,不會亂填。

執行方式(透過 GitHub Actions 手動觸發):
  GitHub 網頁 -> 這個 repo -> Actions 分頁 -> 左邊選
  "One-off: fix POLENE empty color names" -> 右邊 "Run workflow" 按鈕
"""

import sys

import firebase_admin
from firebase_admin import credentials, db

from sync_stock import build_products_index
from scrape_polene import guess_color_name

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
        if p.get("brand") != "POLENE":
            continue
        for c in p.get("colors", []):
            if c.get("name"):
                continue
            new_name = guess_color_name(p.get("name") or "")
            if new_name:
                print(f"{p.get('id')}:{p.get('name')} -> 顏色補成「{new_name}」")
                c["name"] = new_name
                fixed += 1
            else:
                print(f"警告:{p.get('id')}:{p.get('name')} 一樣切不出顏色名稱,保持空白。")

    print(f"\n共修好 {fixed} 個顏色。")
    if fixed == 0:
        print("沒有東西被改到,不寫回 Firebase。")
        return

    db.reference(PRODUCTS_PATH).set(products)
    print("已寫回 Firebase,完成!")

    db.reference(PRODUCTS_INDEX_PATH).set(build_products_index(products))
    print("索引已更新,完成!")


if __name__ == "__main__":
    main()
