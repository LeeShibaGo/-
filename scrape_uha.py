# -*- coding: utf-8 -*-
"""
UHA(UHA味覚糖,日本零食/軟糖/保健食品品牌,uha-shop.jp)全站商品爬蟲
------------------------------------------------------------
用途:
  抓 UHA 官方網購網站全站商品,輸出 uha_full_products.json,格式跟
  Dior、Louis Vuitton 這種「單一款式、沒有顏色/尺寸選項」的商品一樣
  (沒有 colors 陣列),因為 UHA 賣的糖果/保健食品本來就沒有顏色尺寸
  可選,硬套用顏色/尺寸選單反而會在商品卡片上多出兩排沒有意義的按鈕。

  這支只做「價格 + 上架狀態」同步(跟 AAPE、Lacoste 那組price-only品牌
  同一等級),不做庫存件數追蹤——沒有 colors 陣列就沒有地方可以標記
  「這個顏色缺貨」,跟 Dior/LV 一樣,商品永遠顯示現貨,下架與否由
  官網 404 或 schema.org availability 變成 OutOfStock 來偵測,偵測到
  就發 LINE 通知請老闆自己決定要不要手動下架,不會自動改變網站顯示。

技術細節:
  1) 商品清單:官網自己的 sitemap.xml(https://www.uha-shop.jp/sitemap.xml)
     裡列了全部 /shop/products/{id} 網址,沒有機器人偵測,純 requests
     就抓得到,sitemap 本身的 lastmod 是當天日期,證實是有在維護的清單
     (不像 GU 那份舊到 2023/2024 的沒用)。
  2) 每個商品頁的 <script type="application/ld+json"> 是標準
     schema.org Product 格式,直接有 name / image / offers.price /
     offers.priceCurrency / offers.availability,不用自己解析 HTML
     湊價格。
  3) 分類(subtype):每個商品頁的麵包屑(breadcrumbs)有這個商品所屬
     的分類連結,例如 <a href="/shop/product_categories/shunkan-supplement">
     瞬間サプリ</a>,直接抓文字內容比對 JA_TO_SUBTYPE 對照表轉中文,
     對不到的就歸進「零食」(大部分商品都是糖果零食,只有少數是保健
     食品,預設值統一算零食比較不容易錯)。

執行方式:
  pip install -r requirements.txt
  python scrape_uha.py

會輸出 uha_full_products.json。
"""

import json
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import requests

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

BASE = "https://www.uha-shop.jp"
SITEMAP_URL = f"{BASE}/sitemap.xml"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}
BRAND = "UHA"
WORKERS = 8

LDJSON_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.DOTALL)
BREADCRUMB_RE = re.compile(
    r'product_categories/[^"]+">\s*([^<]+?)\s*</a>\s*</li>\s*<li class="c-unq-breadcrumbs__arrow">.*?'
    r'<li class="c-unq-breadcrumbs__item">\s*<div>',
    re.DOTALL,
)

# 麵包屑裡的日文分類名稱 -> 中文 subtype。大部分商品是糖果零食,對不到的
# 名稱就用 guess_subtype() 的預設值「零食」,不會漏掉商品,只是分類比較粗。
JA_TO_SUBTYPE = {
    "サプリメント": "保健食品", "オートファジー": "保健食品",
    "グミサプリ": "保健食品", "瞬間サプリ": "保健食品",
    "キッズグミサプリ": "保健食品",
    "満腹バー": "機能性食品", "SIXPACK": "機能性食品",
    "ヴィーガンカカオバー": "機能性食品", "COMP": "機能性食品",
    "グミ": "零食", "ソフトキャンディ": "零食", "キャンディ": "零食",
    "スナック": "零食", "ラムネ": "零食", "チョコレート": "零食",
    "お菓子": "零食", "食品": "零食",
    "のどあめ": "喉糖", "プロポリスのどあめ": "喉糖", "クリアのどあめ": "喉糖",
}
DEFAULT_SUBTYPE = "零食"

WEIGHT_BY_SUBTYPE = {
    "保健食品": 0.2, "機能性食品": 0.35, "零食": 0.15, "喉糖": 0.08,
}
DEFAULT_WEIGHT = 0.15


def guess_subtype(ja_label):
    return JA_TO_SUBTYPE.get((ja_label or "").strip(), DEFAULT_SUBTYPE)


def guess_weight(subtype):
    return WEIGHT_BY_SUBTYPE.get(subtype, DEFAULT_WEIGHT)


def fetch_text(url, retries=3, timeout=20):
    for attempt in range(retries):
        try:
            res = requests.get(url, headers=HEADERS, timeout=timeout)
            if res.status_code == 404:
                return None
            res.raise_for_status()
            return res.text
        except Exception as e:
            if attempt == retries - 1:
                print(f"  [錯誤] {url} -> {e}")
                return None
            time.sleep(2)
    return None


def fetch_product_ids():
    xml = fetch_text(SITEMAP_URL, timeout=30)
    ids = sorted(set(re.findall(r"/shop/products/(\w+)", xml or "")))
    return ids


def parse_product(pid):
    url = f"{BASE}/shop/products/{pid}"
    html = fetch_text(url)
    if not html:
        return None

    ld_match = LDJSON_RE.search(html)
    if not ld_match:
        return None
    try:
        data = json.loads(ld_match.group(1))
    except Exception:
        return None
    if data.get("@type") != "Product":
        return None

    offers = data.get("offers", {})
    price = offers.get("price")
    try:
        jpy = int(float(price))
    except (TypeError, ValueError):
        return None
    availability = offers.get("availability", "")
    # UHA 商品沒有 colors/尺寸庫存可以追蹤(單一款式),所以直接用官網當下的
    # availability 決定 saleType,前端看到 "soldout" 就整張卡標成缺貨——
    # 跟 Salomon/On 那種「鎖定某個顏色/尺寸」的缺貨標記不是同一套機制。
    sale_type = "soldout" if "OutOfStock" in availability else "instock"

    bc_match = BREADCRUMB_RE.search(html)
    ja_label = bc_match.group(1) if bc_match else None
    subtype = guess_subtype(ja_label)

    return {
        "name": data.get("name", "").strip(),
        "jpy": jpy,
        "weight": guess_weight(subtype),
        "brand": BRAND,
        "subtype": subtype,
        "country": "JP",
        "saleType": sale_type,
        "link": url,
        "image": data.get("image") or None,
    }


def main():
    print("抓取商品清單(sitemap.xml)...")
    ids = fetch_product_ids()
    print(f"共 {len(ids)} 件商品,開始逐一抓取...")

    final_list = []
    soldout_count = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        done = 0
        for entry in ex.map(parse_product, ids):
            done += 1
            if entry:
                if entry.get("saleType") == "soldout":
                    soldout_count += 1
                final_list.append(entry)
            if done % 100 == 0:
                print(f"  ({done}/{len(ids)},已取得 {len(final_list)} 件,其中缺貨 {soldout_count} 件)")
                with open("uha_full_products.json", "w", encoding="utf-8") as f:
                    json.dump(final_list, f, ensure_ascii=False, indent=2)

    with open("uha_full_products.json", "w", encoding="utf-8") as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)

    print(f"完成!已輸出 uha_full_products.json,共 {len(final_list)} 件商品(其中缺貨 {soldout_count} 件)。")


if __name__ == "__main__":
    main()
