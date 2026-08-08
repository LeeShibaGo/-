# -*- coding: utf-8 -*-
"""一次性:補救 BAPE 已經匯入、但顏色圖片抓錯(好幾個顏色共用同一張圖)的資料
------------------------------------------------------------
用途:
  BAPE 有些商品的 Shopify variant.featured_image 是 null(不是每件都
  這樣,實測確認過),原本的 sync_bape() 沒有 fallback,這種商品的每個
  顏色就會抓不到專屬圖片、變成整張商品卡只有一張圖(通常是第一個顏色的
  圖),客人切換顏色時圖片完全不會變——已經修好 sync_bape() 本身(見
  bape_variant_image()),這支只是把「已經匯入、圖片還是錯的」既有資料
  重新跑一次修正,直接呼叫已經修好的 sync_bape(),不重複邏輯。

  用服務帳號(Admin SDK)寫入,因為資料庫規則已經鎖起來。

執行方式(透過 GitHub Actions 手動觸發):
  GitHub 網頁 -> 這個 repo -> Actions 分頁 -> 左邊選
  "One-off: fix BAPE color images" -> 右邊 "Run workflow" 按鈕
"""

import sys

import firebase_admin
from firebase_admin import credentials

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

FIREBASE_DB_URL = "https://shibago-4dd3c-default-rtdb.asia-southeast1.firebasedatabase.app"


def main():
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DB_URL})

    import sync_stock
    sync_stock._firebase_app = firebase_admin.get_app()
    items = sync_stock.load_products()
    sync_stock.sync_bape(items)  # 內部會自己重新抓最新清單、合併、寫回


if __name__ == "__main__":
    main()
