# -*- coding: utf-8 -*-
"""一次性:把 CELINE 全部隱藏(不刪除資料)
------------------------------------------------------------
用途:
  CELINE 官網(celine.com)最近開始用 Akamai Bot Manager 擋掉每日自動
  同步的請求(2026-08-25 查證:回應帶有 _abck/bm_s/bm_sz 這些 Akamai
  專屬的識別 cookie,不是單純網路問題),導致 1,774 件商品每一次同步
  都要耗盡重試次數才放棄,單一品牌就跑到快 20 小時,遠超過 GitHub
  Actions 單一工作 6 小時的硬性上限。這種商用等級的機器人防護不打算
  硬解(跟 sync_stock.py 開頭列出的 TaylorMade/Dior/LV/Gentle Monster
  同一種情況、同一種決定:不用繞過偵測的方式硬做)。老闆決定先整個
  下架,之後庫存/價格不會再更新,不確定要不要重新開放。

  比照 unlist_dior_belts.py 的做法,只加 hidden: true,不刪除商品資料
  ——index.html 客人看得到的畫面(商品列表、本週新品、熱銷商品、分類
  選單、分享連結、靜態 SEO 頁面)都已經是用 hidden 欄位過濾,後台商品
  管理列表刻意不過濾,老闆自己隨時可以在後台把 hidden 改回 false 重新
  上架。跟 unlist_dior_belts.py 不同的地方:那支是 2026-08-14「精簡版
  商品索引」daigou-products-index-v1 上線之前寫的,沒有同步更新索引;
  這支額外呼叫 build_products_index() 把索引也一起更新,不然首頁
  瀏覽用的索引還是會顯示 hidden:false,商品照樣會出現在品牌導覽/分類
  裡,跟後台看到的「已隱藏」狀態對不起來。

  用服務帳號(Admin SDK)寫入,因為資料庫規則已經鎖起來。

執行方式(透過 GitHub Actions 手動觸發):
  GitHub 網頁 -> 這個 repo -> Actions 分頁 -> 左邊選
  "One-off: hide CELINE (Akamai blocking sync)" -> 右邊 "Run workflow" 按鈕
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

    updated = 0
    for p in products:
        if p.get("brand") == "CELINE" and not p.get("hidden"):
            p["hidden"] = True
            updated += 1

    print(f"共隱藏 {updated} 件 CELINE 商品")
    if updated == 0:
        print("沒有需要隱藏的商品,結束。")
        return

    db.reference(PRODUCTS_PATH).set(products)
    print("已寫回 Firebase,完成!")

    db.reference(PRODUCTS_INDEX_PATH).set(build_products_index(products))
    print("索引已更新,完成!")


if __name__ == "__main__":
    main()
