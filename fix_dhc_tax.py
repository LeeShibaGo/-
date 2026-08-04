# -*- coding: utf-8 -*-
"""一次性:修正 DHC 商品價格漏算消費稅(x1.08),並補上一件新商品
------------------------------------------------------------
用途:
  scrape_dhc.py / sync_stock.py 的 sync_dhc() 原本直接拿 DHC 商品頁
  JSON-LD 的 offers.price 當作日幣售價,但那個欄位其實是「未稅價」,
  官網實際顯示、客人實際要付的是「稅込(含稅)價」,差 8%(食品類消費稅)。
  用「濃縮プエラリアミリフィカ」(官網稅込4,104,JSON-LD寫3800)跟
  「カルシウム＋CBP」(官網特價稅込432,JSON-LD寫400)兩件商品交叉驗證過,
  兩者都剛好差 1.08 倍,確認是全站一致的規則,不是單一商品的巧合。

  兩支程式的抓取邏輯已經改成抓到價格後乘上 1.08。這支不直接對現有資料
  「盲目乘 1.08」(如果每天的自動排程已經先跑過一次修好的 sync_dhc(),
  現有資料可能已經是對的,再乘一次會變成重複課稅、稅上加稅),而是直接
  呼叫 sync_stock.py 已經修好的 sync_dhc(),用官網當下的即時資料重新算一次
  ——不管現有資料是舊的未稅價還是已經被排程修好過,結果都會是正確的。

  順便把使用者傳來的這件新商品加進資料庫(官網 https://www.dhc.co.jp/goods/77038.html
  ,特價活動 2,430 円 -> 1,215 円(税込)50%off,已經用 origJpy 存好原價,
  商品卡片會顯示劃線原價 + 特價,這個顯示邏輯本來就有,只是之前沒有任何
  商品資料帶 origJpy 欄位)。

  用服務帳號(Admin SDK)寫入,因為資料庫規則已經鎖起來。

執行方式(透過 GitHub Actions 手動觸發):
  GitHub 網頁 -> 這個 repo -> Actions 分頁 -> 左邊選
  "One-off: fix DHC tax-excluded prices" -> 右邊 "Run workflow" 按鈕
"""

import sys
import time

import firebase_admin
from firebase_admin import credentials, db

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

FIREBASE_DB_URL = "https://shibago-4dd3c-default-rtdb.asia-southeast1.firebasedatabase.app"
PRODUCTS_PATH = "daigou-products-v1"

NEW_PRODUCT = {
    "id": f"p_dhc_{int(time.time() * 1000)}_manual",
    "name": "【WEB限定】はじめて購入 持続型各3個セット（持続型ビタミンC・持続型ビタミンBミックス）",
    "jpy": 1215,
    "origJpy": 2430,
    "weight": 0.2,
    "brand": "DHC",
    "subtype": "保健食品",
    "country": "JP",
    "saleType": "instock",
    "link": "https://www.dhc.co.jp/goods/77038.html",
    "image": (
        "https://www.dhc.co.jp/dw/image/v2/BLLL_PRD/on/demandware.static/-/"
        "Sites-dhc_catalog-ms/default/dwe0ea77a6/large/77038/77038_G.png?sw=256&sh=256&sm=cut"
    ),
}


def main():
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DB_URL})

    import sync_stock
    sync_stock._firebase_app = firebase_admin.get_app()
    items = sync_stock.load_products()
    sync_stock.sync_dhc(items)  # 內部會自己重新抓最新清單、合併、寫回

    products = db.reference(PRODUCTS_PATH).get()
    if isinstance(products, dict):
        products = list(products.values())
    products = [p for p in products if p]

    if any(p.get("link") == NEW_PRODUCT["link"] for p in products):
        print("這件商品已經上架過了,不重複新增")
        return

    products.append(NEW_PRODUCT)
    db.reference(PRODUCTS_PATH).set(products)
    print(f"已新增商品:{NEW_PRODUCT['name']}")


if __name__ == "__main__":
    main()
