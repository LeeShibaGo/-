# -*- coding: utf-8 -*-
"""一次性:修正被 product_type "バッグ" 誤蓋掉的 BAPE 錢包/皮帶分類
------------------------------------------------------------
用途:
  老闆回報「1ST CAMO MINI WALLET」這件錢包分類跑掉了(歸進「包款」,
  不是「皮夾」)。查出來是 add_bape_missing.py 的 guess_subtype() 原本
  只在官網 product_type 是「グッズ(雜貨)」的時候,才會用商品名稱關鍵字
  (WALLET/BELT/...)做細分;但官網自己把部分錢包標成 product_type
  「バッグ(包)」,不是「グッズ」,這些商品直接走「バッグ -> 包款」的
  對照,沒機會被關鍵字規則接住。add_bape_missing.py 已經修好(關鍵字
  判斷改成不管 product_type 是什麼都優先檢查),但已經匯入的商品不會
  自動套用新邏輯,這支負責把它們修正過來。

  範圍刻意縮得很小、很精準:只處理「官網 product_type 明確是バッグ、
  但商品名稱是 WALLET 或(不是 BELT BAG 的)BELT、而且資料庫裡現在
  的 subtype 剛好是包款」這幾個條件同時成立的商品——測試中發現如果
  直接對「現有分類」跟「用名稱關鍵字重新猜」兩者有沒有差異來抓錯,
  會抓到大量假警報(例如 "STA PATCH...SHORTS" 這種商品名稱裡的
  "PATCH" 只是設計元素不是真的貼紙商品,亂猜反而會把本來就分類正確
  的舊資料改錯),所以不做這種大範圍重新分類,只精準對照官網
  product_type 欄位確認過的這批。

  只動 brand == "BAPE" 且符合上述條件的商品,不影響其他資料。重跑是
  安全的:已經修正過的商品(subtype 已經不是「包款」)會被跳過。

執行方式(透過 GitHub Actions 手動觸發):
  GitHub 網頁 -> 這個 repo -> Actions 分頁 -> 左邊選
  "One-off: fix BAPE wallet/belt subtype" -> 右邊 "Run workflow" 按鈕
"""

import re
import sys

import firebase_admin
from firebase_admin import credentials, db

from sync_stock import build_products_index, fetch

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

FIREBASE_DB_URL = "https://shibago-4dd3c-default-rtdb.asia-southeast1.firebasedatabase.app"
PRODUCTS_PATH = "daigou-products-v1"
PRODUCTS_INDEX_PATH = "daigou-products-index-v1"

WALLET_RE = re.compile(r"\bWALLET\b|財布", re.IGNORECASE)
BELT_RE = re.compile(r"\bBELT\b(?!\s*BAG)", re.IGNORECASE)


def fetch_bag_type_handles():
    """回傳官網 product_type 明確是「バッグ」的商品 handle 集合。"""
    handles = set()
    page = 1
    while True:
        ps = fetch(f"https://jp.bape.com/products.json?limit=250&page={page}").json().get("products", [])
        for p in ps:
            if p.get("product_type") == "バッグ":
                handles.add(p["handle"])
        if len(ps) < 250:
            break
        page += 1
    return handles


def main():
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DB_URL})

    products = db.reference(PRODUCTS_PATH).get()
    if isinstance(products, dict):
        products = list(products.values())
    products = [p for p in products if p]

    print("抓取官網 product_type 是「バッグ」的商品清單(用來精準比對,不靠猜的)...")
    bag_handles = fetch_bag_type_handles()
    print(f"官網「バッグ」分類共 {len(bag_handles)} 件")

    fixed = 0
    for p in products:
        if p.get("brand") != "BAPE" or p.get("subtype") != "包款":
            continue
        handle = (p.get("link") or "").rstrip("/").rsplit("/", 1)[-1]
        if handle not in bag_handles:
            continue
        name = p.get("name") or ""
        if WALLET_RE.search(name):
            new_subtype = "皮夾"
        elif BELT_RE.search(name):
            new_subtype = "皮帶"
        else:
            continue
        print(f"  修正:{name}  包款 -> {new_subtype}")
        p["subtype"] = new_subtype
        fixed += 1

    print(f"共修正 {fixed} 件商品的分類")
    if fixed == 0:
        print("沒有需要修正的商品,結束。")
        return

    db.reference(PRODUCTS_PATH).set(products)
    print("已寫回 Firebase,完成!")

    db.reference(PRODUCTS_INDEX_PATH).set(build_products_index(products))
    print("索引已更新,完成!")


if __name__ == "__main__":
    main()
