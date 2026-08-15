# -*- coding: utf-8 -*-
"""
POLÈNE 日本官網(jp.polene-paris.com)全站商品爬蟲
------------------------------------------------------------
用途:
  跟 Salomon/BAPE/STUSSY 一樣是 Shopify 官方 products.json API,沒有
  機器人偵測,一次查詢就能拿到售價、即時庫存(available true/false)、
  圖片。

  跟 STUSSY 不一樣的地方:POLÈNE 是包包/皮件品牌,「顏色」不是同一件
  商品底下可以切換的 variant,而是**每個顏色各自獨立一個商品**——例如
  「Numéro Dix - コニャック スムース」(Numéro Dix 款、Cognac 光滑皮革色)
  跟同一顆包的其他顏色是完全不同的 Shopify 商品,不是同一個 handle 底下
  的 option。實測 424 件商品裡有 94% 只有單一個 variant(Default Title,
  代表這個商品本身就是一個固定顏色,沒有客人可以切換的選項),剩下少數
  (手鐲/戒指這類飾品配件)才是真的用 variant 做「尺寸」選項(S/M、M/L
  這種,不是顏色)。

  因為每個商品本來就對應一個固定顏色,存進 daigou-products-v1 時每件
  商品的 colors 陣列固定只放一筆(跟 GU/On 那種「一個商品好幾個顏色」
  不一樣),顏色名稱盡量從商品標題裡「款式 - 顏色描述」的慣例切出來
  (例如上面例子會切出「コニャック スムース」),切不出來就留空,不影響
  庫存/尺寸判斷。

  product_type(Handbags/Jewellery/Accessoires...)對照成中文 subtype,
  盡量對到 index.html 既有的 SUBTYPE_GROUP。

執行方式:
  pip install -r requirements.txt
  python scrape_polene.py

會輸出 polene_all_products.json,可以直接餵給一次性匯入腳本。
"""

import json
import sys
import time

import requests

from scrape_on_full import fix_size_key

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

BASE = "https://jp.polene-paris.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}
BRAND = "POLENE"

TYPE_TO_SUBTYPE = {
    "Handbags": "包款",
    "Jewellery": "珠寶飾品",
    "Accessoires": "配件",
    "Wallets & Money Clips": "皮夾",
    "Papeterie": "配件",
    "Magazine": "配件",
}
DEFAULT_SUBTYPE = "配件"

WEIGHT_BY_SUBTYPE = {
    "包款": 0.6, "珠寶飾品": 0.03, "配件": 0.15, "皮夾": 0.15,
}


def guess_subtype(product_type):
    return TYPE_TO_SUBTYPE.get(product_type, DEFAULT_SUBTYPE)


def guess_weight(subtype):
    return WEIGHT_BY_SUBTYPE.get(subtype, 0.2)


def guess_color_name(title):
    """商品標題慣例是「款式 - 顏色描述」,切出後半段當顏色名稱,
    切不出來(沒有「 - 」)就留空字串,不影響庫存/尺寸判斷,只是
    畫面上顏色標籤會是空的。"""
    if " - " in title:
        return title.split(" - ", 1)[1].strip()
    return ""


def fetch_page(page, retries=4):
    url = f"{BASE}/products.json?limit=250&page={page}"
    for attempt in range(retries):
        try:
            res = requests.get(url, headers=HEADERS, timeout=30)
            res.raise_for_status()
            return res.json().get("products", [])
        except Exception as e:
            if attempt == retries - 1:
                print(f"  [錯誤] page {page} -> {e}")
                return []
            time.sleep(3 * (attempt + 1))
    return []


def build_product(raw):
    subtype = guess_subtype(raw.get("product_type"))
    title = (raw.get("title") or "").strip()
    variants = raw.get("variants") or []
    if not variants:
        return None

    sizes, stock = [], {}
    for v in variants:
        raw_title = (v.get("title") or "").strip()
        # "Default Title" 是 Shopify 對「這個商品沒有真正的選項」的標準
        # 寫法(POLÈNE 94% 的商品都是這樣,單一顏色/單一款式,沒有客人可以
        # 選的東西),不要真的顯示這串英文給客人看,換成 FREE,跟其他沒有
        # 尺寸選項的品牌一致。
        size = "FREE" if raw_title == "Default Title" else (fix_size_key(raw_title) or "FREE")
        if size not in stock:
            sizes.append(size)
        # Shopify 沒有公開實際庫存件數,只有 available 布林值,跟 GU 一樣
        # 只能存「有貨」給一個代表數字(5)或 0,不是真實件數。
        stock[size] = max(stock.get(size, 0), 5 if v.get("available") else 0)

    imgs = raw.get("images") or []
    image = imgs[0].get("src") if imgs else None

    color = {
        "name": guess_color_name(title),
        "sizes": sizes,
        "stock": stock,
        "image": image,
    }

    try:
        jpy = int(float(variants[0]["price"]))
    except (KeyError, ValueError, TypeError, IndexError):
        return None

    return {
        "name": title,
        "jpy": jpy,
        "weight": guess_weight(subtype),
        "brand": BRAND,
        "subtype": subtype,
        "country": "JP",
        "saleType": "instock",
        "link": f"{BASE}/products/{raw.get('handle')}",
        "colors": [color],
    }


def main():
    print("抓取商品清單...")
    all_raw = []
    page = 1
    while True:
        items = fetch_page(page)
        if not items:
            break
        all_raw.extend(items)
        print(f"  page {page}: {len(items)} 件(累積 {len(all_raw)})")
        if len(items) < 250:
            break
        page += 1
        time.sleep(0.6)

    final_list = []
    for raw in all_raw:
        entry = build_product(raw)
        if entry:
            final_list.append(entry)

    with open("polene_all_products.json", "w", encoding="utf-8") as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)
    print(f"完成!共 {len(final_list)} 件商品,已輸出 polene_all_products.json")


if __name__ == "__main__":
    main()
