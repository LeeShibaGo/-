# -*- coding: utf-8 -*-
"""
一次性:上架 HUMAN MADE CLASSIC ZIP-UP HOODIE(HM32CS022)
------------------------------------------------------------
用途:
  老闆貼了 https://www.humanmade.jp/en/new-arrivals/HM32CS022.html 這個
  網址要求上架——HUMAN MADE 這個品牌目前完全不在資料庫裡(第一次上架),
  單一件商品不值得寫一整支爬蟲,直接手動核對官網資料寫成這支一次性
  匯入腳本。

  官網資料核對重點:
    - 官網頁面顯示的是「NT$6,100」,但這其實是網站的顯示 bug(price 前面
      的貨幣符號寫死沒有跟著 locale 換,不是真的換算成台幣)——實際去讀
      頁面裡 schema.org 的 ld+json 結構化資料,priceCurrency 明確寫
      "JPY"、price 是 "6100",確認原幣價格就是 ¥6,100,不是我憑感覺換算的。
    - 4 個顏色的名稱/圖片都對照官網頁面的顏色色塊逐一核對過(不是憑
      英文色名直接翻,是真的下載每張色塊圖確認過顏色):BLACK、BEIGE、
      GRAY、NAVY,分別對到官網用的圖檔。中文顏色名稱套用這個資料庫
      既有的 EN->中文對照(跟 scrape_stussy.py 的 translate_color 一致):
      Black->黑色、Beige->米色、Gray->灰色、Navy->海軍藍。
    - 尺寸 XS/S/M/L/XL/2XL 每個顏色都有、官網頁面沒有任何尺寸/顏色組合
      被標示售完,今天(2026-09-05)剛好是這件商品的發售日(官網寫
      SALE DATE: Sat, Sep 05, 2026 11:00am JST),所以先全部視為有貨,
      不特別標示售完。
    - subtype 用「連帽外套」,對照這個資料庫裡 AAPE/BAPE 同類型連帽拉鍊
      帽T的慣例(weight 也比照這些商品统一用 0.65kg)。
    - saleType 用「預購」——這件商品剛發售,老闆走的是先接單、之後再去
      日本現場採購的代購模式,不是老闆自己已經持有現貨,比照這個資料庫
      對「剛發售的新品」的慣例做法。如果老闆其實已經有現貨,之後可以
      在後台商品管理改成「現貨」。
    - 圖片直接連到官網原始圖檔網址(不是另外下載重新上傳),跟這個資料庫
      其他品牌的做法一致(scrape_9090.py/scrape_stussy.py 等都是直接存
      原始圖片網址,不重新上傳)。

  商品品牌 HUMAN MADE 第一次出現,順便:
    - 在 TIER_BY_BRAND(index.html/404.html)裡補上 HUMAN MADE ->
      潮流品牌(NIGO 創立,跟 AAPE/BAPE/STUSSY 同一個街頭潮流品牌調性,
      信心很高,沒有另外去問老闆)。
    - 在 images/brand-logos/ 補上 humanmade.png(官網 favicon 那個紅心
      +HUMAN MADE 字樣的版本,官網導覽列那個 logo.svg 是白字設計給深色
      底用的,套用在這個網站白底的品牌方塊上文字會看不到,所以改用
      favicon 版本),並在 BRAND_SHOWCASE 清單裡補上這個品牌。
    這兩個改動是直接改 index.html/404.html 的程式碼,不是這支腳本的
    工作,這支腳本只負責把商品資料寫進 Firebase。

執行方式(透過 GitHub Actions 手動觸發):
  GitHub 網頁 -> 這個 repo -> Actions 分頁 -> 左邊選
  "One-off: add HUMAN MADE zip-up hoodie" -> 右邊 "Run workflow" 按鈕

重跑是安全的:用 link 當比對鍵,如果這個商品已經存在就跳過,不會重複新增。
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

IMG_BASE = (
    "https://www.humanmade.jp/on/demandware.static/-/"
    "Sites-catalog_master_sfcc_humanmade/default/{path}"
)

NEW_PRODUCT = {
    "name": "HUMAN MADE CLASSIC ZIP-UP HOODIE",
    "jpy": 6100,
    "weight": 0.65,
    "brand": "HUMAN MADE",
    "subtype": "連帽外套",
    "country": "JP",
    "saleType": "preorder",
    "link": "https://www.humanmade.jp/en/new-arrivals/HM32CS022.html",
    "colors": [
        {
            "name": "黑色",
            "sizes": ["XS", "S", "M", "L", "XL", "2XL"],
            "image": IMG_BASE.format(path="dw805f42b9/images/large/HM_1788062854850_6jgbns.jpg"),
        },
        {
            "name": "米色",
            "sizes": ["XS", "S", "M", "L", "XL", "2XL"],
            "image": IMG_BASE.format(path="dwb9d42563/images/large/HM_1788062854840_kioh0b.jpg"),
        },
        {
            "name": "灰色",
            "sizes": ["XS", "S", "M", "L", "XL", "2XL"],
            "image": IMG_BASE.format(path="dwa71565a3/images/large/HM_1788062854854_sfdjnr.jpg"),
        },
        {
            "name": "海軍藍",
            "sizes": ["XS", "S", "M", "L", "XL", "2XL"],
            "image": IMG_BASE.format(path="dwa3539e27/images/large/HM_1788062854866_8qm0g0.jpg"),
        },
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
        print("這個商品(同一個 link)已經存在,略過,不重複新增。")
        return

    item = dict(NEW_PRODUCT)
    item["id"] = f"p_humanmade_{int(time.time() * 1000)}_0"
    item["addedAt"] = int(time.time() * 1000)
    products.append(item)

    db.reference(PRODUCTS_PATH).set(products)
    print(f"已新增:{item['name']}(id={item['id']})")

    db.reference(PRODUCTS_INDEX_PATH).set(build_products_index(products))
    print("索引已更新,完成!")


if __name__ == "__main__":
    main()
