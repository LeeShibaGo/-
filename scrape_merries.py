# -*- coding: utf-8 -*-
"""
メリーズ(Merries,花王嬰兒紙尿布/濕紙巾/乳液品牌)商品爬蟲
------------------------------------------------------------
用途:
  抓花王官方商城 My Kao Mall(kao-kirei.com)上架的メリーズ商品,輸出
  merries_full_products.json,格式跟 daigou-products-v1 裡其他品牌
  一樣,可以直接合併進 Firebase。

範圍(2026-08-20 老闆確認要不要抓這個品牌):
  My Kao Mall 底下這個品牌總共有 58 筆列表項目,但裡面很多是「ケース
  販売(整箱)」「定期便(訂閱制,需要辦會員、每期自動出貨扣款)」這種
  不適合代購一次性下單模式的組合商品,同一個組合甚至會拆成好幾筆重複
  列出。這裡故意只抓「單品購入、JAN 條碼式網址」的 27 件商品(尿布、
  夜用褲、濕紙巾、嬰兒乳液四類),不抓整箱/訂閱制那些,判斷方式是
  pageUrl 網址結尾是純數字(JAN 碼)還是 PAC_ 開頭的組合代碼。

技術細節:
  1) 商品清單:My Kao Mall 有一份「全站商品」的公開 JSON(不是官方文件、
     是實測瀏覽器 devtools 找到的),一次回傳全站 5,664 件商品(含其他
     品牌),用 brand.brandId == "merries" 篩出這個品牌的部份:
       GET /content/wcm_kao/sites/kao/www-kao-kirei-com/jp/ja/mkm/
           json-common/product-list/_jcr_content/root/responsivegrid/
           kirei_product_model.model.json
     這份清單裡的 name/image 可靠,但 price 幾乎全部是 "0.00" 或
     null,不能拿來當售價,只能拿來building 清單、不能拿來定價。

  2) 個別商品頁的價格/庫存是頁面載入後才用 JS 打 API 填進去的(實測用
     plain requests 抓下來的原始 HTML,加入購物車按鈕是 disabled 的
     loading 骨架,庫存文字是 data-in-stock-text="あり" 這種樣板字串,
     不是真正的庫存狀態),跟 HONMA/DESCENTE 一樣一定要用瀏覽器把 JS
     跑完,所以價格/庫存不是在這支腳本抓、是共用 sync_stock.py 裡
     HONMA/DESCENTE 那套 Playwright 機制(見 sync_stock.py 的
     sync_merries())。這支只負責建立商品清單清單(名稱/圖片/分類),
     真正的價格/庫存由 sync_merries() 用 Playwright 補上。

  3) extract_price_stock(page):給一個「已經 goto 商品頁」的 Playwright
     page,讀頁面裡 <script type="application/ld+json"> 這個 schema.org
     Product 結構化資料,裡面的 offers.price / offers.availability 是
     JS 執行完、對這個 SKU 唯一且乾淨的來源(比自己刮 class/文字穩定,
     不用擔心 class 名稱以後改版跑掉)。

執行方式:
  單獨執行這支只會產生「名稱/圖片/分類」清單(沒有價格,jpy 是 0)——
  正常應該透過 sync_stock.py 走完整流程(見 import_merries.py 開頭的
  說明),不需要單獨執行 main()。
"""

import re
import sys

import requests

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

BASE = "https://www.kao-kirei.com"
CATALOG_URL = (
    f"{BASE}/content/wcm_kao/sites/kao/www-kao-kirei-com/jp/ja/mkm/"
    "json-common/product-list/_jcr_content/root/responsivegrid/"
    "kirei_product_model.model.json"
)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}
BRAND = "Merries"

# category.categoryId -> (中文 subtype,估計重量kg)。重量是憑包裝規格
# 粗抓的估計值(尿布大包裝比較重、濕紙巾補充包/乳液瓶身較輕),不是
# 官網有寫的實際重量,老闆之後發現運費算起來不準可以到後台個別調整。
CATEGORY_MAP = {
    "babydiaper": ("紙尿布", 1.0),
    "nightpants": ("夜用褲", 0.6),
    "bottomwipes": ("濕紙巾", 0.5),
    "bodylotion": ("嬰兒乳液", 0.4),
}
DEFAULT_WEIGHT = 0.5

# 只抓 JAN 條碼式網址(單品購入),PAC_ 開頭是整箱/訂閱制組合,故意不抓
# (見檔案開頭說明)。
JAN_URL_RE = re.compile(r"/merries/(\d+)/?$")


def fetch_catalog():
    """回傳 27 件「單品購入」メリーズ商品的基本資料(還沒有價格,
    jpy 先填 0,真正售價/庫存由 sync_stock.py 的 sync_merries() 用
    Playwright 補上)。"""
    res = requests.get(CATALOG_URL, headers=HEADERS, timeout=30)
    res.raise_for_status()
    product_list = res.json().get("productList", [])

    items = []
    for p in product_list:
        brand = p.get("brand") or {}
        if brand.get("brandId") != "merries":
            continue
        page_url = p.get("pageUrl") or ""
        if not JAN_URL_RE.search(page_url):
            continue  # PAC_ 開頭的整箱/訂閱制組合,跳過

        category = p.get("category") or {}
        subtype, weight = CATEGORY_MAP.get(
            category.get("categoryId"), ("嬰兒用品", DEFAULT_WEIGHT)
        )
        name = p.get("groupName") or p.get("dispName") or ""
        if not name:
            continue

        image = (p.get("images") or {}).get("src")
        if image and image.startswith("//"):
            image = "https:" + image
        # 2026-08-21 老闆回報上架商品沒圖片,查出來是這裡:清單 JSON 裡
        # images.src 本身帶著 "?hide=1&fmt=png8-alpha" 這種花王網站自己
        # 前端專用的 Scene7 動態圖片參數,單獨拿掉 query string 直接連
        # 這個 Adobe 圖片伺服器,回傳的是一張空白圖(實測確認:帶參數
        # 空白、拿掉參數是正常的尿布包裝照片)。這組參數顯然是設計給
        # 官網自己某個特定版位用的,不是通用的縮圖網址,直接切掉
        # query string,只留乾淨的圖片路徑最保險。
        if image and "?" in image:
            image = image.split("?", 1)[0]

        items.append({
            "name": name.strip(),
            "jpy": 0,  # sync_merries() 用 Playwright 補上真實售價
            "weight": weight,
            "brand": BRAND,
            "subtype": subtype,
            "country": "JP",
            "saleType": "instock",  # sync_merries() 會依實際庫存立刻校正
            "image": image,
            "link": page_url,
        })
    return items


def extract_price_stock(page):
    """給一個已經 page.goto() 到商品頁的 Playwright page,回傳
    (jpy, in_stock)。讀頁面裡 schema.org 的 ld+json 結構化資料,是
    JS 執行完、對這個 SKU 唯一乾淨的價格/庫存來源。抓不到就回傳
    (None, None),呼叫端沿用舊資料、不要誤判成缺貨。"""
    try:
        # state="attached":<script> 標籤本來就不會是「visible」(不是拿來
        # 顯示的元素),wait_for_selector 預設等 visible 永遠等不到、一定
        # 逾時——這裡只需要確認它已經被 JS 塞進 DOM,用 attached 就夠。
        page.wait_for_selector('script[type="application/ld+json"]', state="attached", timeout=15000)
    except Exception:
        return None, None
    scripts = page.locator('script[type="application/ld+json"]')
    for i in range(scripts.count()):
        text = scripts.nth(i).text_content(timeout=5000) or ""
        m = re.search(r'"price"\s*:\s*(\d+)', text)
        if not m:
            continue
        jpy = int(m.group(1))
        avail_m = re.search(r'"availability"\s*:\s*"([^"]+)"', text)
        in_stock = bool(avail_m) and avail_m.group(1).endswith("InStock")
        return jpy, in_stock
    return None, None


def main():
    print("抓取メリーズ商品清單(名稱/圖片/分類,不含價格)...")
    items = fetch_catalog()
    print(f"共 {len(items)} 件單品購入商品(已排除整箱/訂閱制組合)")
    import json
    with open("merries_full_products.json", "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    print("已輸出 merries_full_products.json——注意這份還沒有真實價格,"
          "要接著透過 import_merries.py(內部會用 Playwright 補上價格/庫存)匯入。")


if __name__ == "__main__":
    main()
