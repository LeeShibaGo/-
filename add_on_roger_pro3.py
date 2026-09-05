# -*- coding: utf-8 -*-
"""
一次性:上架 On THE ROGER Pro 3(男款,3MG10365204)
------------------------------------------------------------
用途:
  老闆貼了 on.com 這雙網球鞋的網址要求上架。On 這個品牌/「THE ROGER」
  這個系列在資料庫裡已經有很多件了,不是新品牌,單一件商品一樣不值得
  寫爬蟲,直接核對官網資料手動寫這支一次性匯入腳本。

  官網資料核對重點:
    - on.com 預設用訪客地區顯示當地價格(跟 HUMAN MADE 那次踩到的
      Global-e 動態定價是類似的坑),我這次直接改用 /ja-jp/ 這個網址
      路徑(不是靠語言選單、是網址本身的地區路徑),拿到的是「On 日本」
      這個分站,價格用日幣顯示——這才是真正的日本原價,不是我猜的。
      ¥26,400 這個數字也用頁面裡 schema.org 的 ld+json 結構化資料
      (price:26400, priceCurrency:JPY)交叉確認過,而且資料庫裡同系列
      的「男款 THE ROGER Pro Ace」「男款 THE ROGER Pro Fire」剛好也是
      同一個價位 ¥26,400,價位對得起來,不是孤立的怪數字。
    - 官網這雙鞋共有 3 個配色(Black|Ash、White|Pink、Brook|Neem),
      但只有 Black|Ash 現在還有現貨(6 個尺寸都能選),另外兩個配色
      官網直接顯示「沒有可選尺寸」+ 跳出其他熱賣品推薦(等於全部尺寸
      都缺貨),所以只上架這個現貨的配色,不擺兩個完全買不到的配色
      進去徒增混亂,以後如果補貨了再另外加。
    - 尺寸是官網當下可選的 6 個:25.5/26/26.5/27/27.5/28(JP cm 尺碼),
      格式比照這個資料庫既有 On 鞋類商品的寫法(小數點用連字號,
      例如 25.5 -> "25-5")。
    - 顏色中文名「黑 | 灰」比照資料庫既有 On 商品的顏色命名慣例
      (例如「白 | 靛藍」「亞麻色 | 萊姆綠」這種「顏色1 | 顏色2」格式)。
    - subtype 用「網球鞋」(THE ROGER 系列都是網球鞋,跟資料庫裡同系列
      商品一致),weight 用 0.8kg(資料庫裡所有網球鞋商品統一都是這個
      估計重量,不是用官網寫的鞋子本體 390g,那個沒算包裝/運送估重)。
    - saleType 用「現貨」,因為 6 個尺寸確實都能選、不是預購。

  圖片一樣直接連到官網原始圖檔網址,不重新上傳,跟這個資料庫的既有
  做法一致。

執行方式(透過 GitHub Actions 手動觸發):
  GitHub 網頁 -> 這個 repo -> Actions 分頁 -> 左邊選
  "One-off: add On THE ROGER Pro 3" -> 右邊 "Run workflow" 按鈕

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

NEW_PRODUCT = {
    "name": "男款 THE ROGER Pro 3",
    "jpy": 26400,
    "weight": 0.8,
    "brand": "On",
    "subtype": "網球鞋",
    "country": "JP",
    "saleType": "instock",
    "link": "https://www.on.com/ja-jp/products/the-roger-pro-3-m-3mg1036/mens/black-ash-shoes-3MG10365204",
    "colors": [
        {
            "name": "黑 | 灰",
            "sizes": ["25-5", "26", "26-5", "27", "27-5", "28"],
            "image": (
                "https://images.ctfassets.net/hnk2vsx53n6l/4MEWFwNv2BA1anQlfOiBRi/"
                "5989992871cd0233e5bab28e39c3c8dc/a7ca383b7521fe2115f1a040d73d9aae5cfcc172.png?fm=webp"
            ),
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
    item["id"] = f"p_on_{int(time.time() * 1000)}_0"
    item["addedAt"] = int(time.time() * 1000)
    products.append(item)

    db.reference(PRODUCTS_PATH).set(products)
    print(f"已新增:{item['name']}(id={item['id']})")

    db.reference(PRODUCTS_INDEX_PATH).set(build_products_index(products))
    print("索引已更新,完成!")


if __name__ == "__main__":
    main()
