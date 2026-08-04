# -*- coding: utf-8 -*-
"""
DHC(日本保養品/保健食品大廠,dhc.co.jp)保健食品分類爬蟲
------------------------------------------------------------
用途:
  DHC 官網賣的東西很雜(保養品、保健食品、服飾雜貨都有),這支只抓「健康
  食品」分類(官網網址 /health/ 開頭)底下的商品,不是全站商品都要。

  跟 UHA 同一套做法(見 scrape_uha.py 開頭的說明,這裡不重複):
  1) 商品清單先從官網自己的 sitemap(custom_sitemap,每天更新)撈出全部
     /goods/{編號}.html 網址,總共約 1500 多個,橫跨保養品/保健食品/服飾。
  2) 每個商品頁的麵包屑(breadcrumb)第一層分類連結,可以看出這件商品
     屬於哪個大分類——只保留第一層連結是 /health/ 開頭的商品,其餘(保養品
     /服飾雜貨等)略過不匯入。
  3) 商品頁的 <script type="application/ld+json"> 是標準 schema.org
     Product 格式,直接有 name / image / offers.price / offers.availability,
     沒有機器人偵測,純 requests 就抓得到。
  4) 商品沒有顏色/尺寸選項(保健食品本來就沒有),用跟 UHA 一樣的簡單
     schema(沒有 colors 陣列),saleType 用 "instock"/"soldout" 直接反映
     官網當下的 availability。

執行方式:
  pip install -r requirements.txt
  python scrape_dhc.py

會輸出 dhc_health_products.json。
"""

import json
import re
import sys
import time

import requests
from concurrent.futures import ThreadPoolExecutor

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

BASE = "https://www.dhc.co.jp"
SITEMAP_URL = f"{BASE}/sitemap-custom_sitemap.xml"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}
BRAND = "DHC"
WORKERS = 8
HEALTH_CATEGORY_PREFIX = "/health/"

LDJSON_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.DOTALL)
# 特價商品官網會多顯示一個劃線的原價(例如「WEB限定」組合包),這個
# class 抓到的已經是稅込價(用「2,430 / 1,215(50%off)」這組交叉驗證過,
# 兩邊都是稅込數字才會剛好差整數倍,不像 offers.price 未稅價那樣要再乘 1.08)。
ORIG_PRICE_RE = re.compile(r'class="c-price-delete">\s*<span class="d-inline-block">\s*([\d,]+)')
# 麵包屑第一層(HOME 之後的第一個 breadcrumb-item)的連結網址跟分類名稱
FIRST_CRUMB_RE = re.compile(
    r'HOME\s*</a>\s*</li>.*?<li class="breadcrumb-item">\s*<a href="([^"]+)">\s*([^<]+?)\s*</a>',
    re.DOTALL,
)
# 第二層(細分類),用來當 subtype
SECOND_CRUMB_RE = re.compile(
    r'HOME\s*</a>\s*</li>.*?breadcrumb-item">\s*<a[^>]*>[^<]*</a>\s*</li>\s*'
    r'<li class="breadcrumb-item">\s*<a href="[^"]+">\s*([^<]+?)\s*</a>',
    re.DOTALL,
)

# 細分類名稱 -> 中文 subtype,對不到的就用 DEFAULT_SUBTYPE。
JA_TO_SUBTYPE = {
    "サプリメント": "保健食品", "健康食品": "保健食品",
    "青汁・グリーンスムージー": "保健食品", "ドリンク": "保健食品",
    "ゼリー・粉末": "保健食品", "食品": "保健食品",
}
DEFAULT_SUBTYPE = "保健食品"  # 這支腳本本來就已經篩過「健康食品」大分類,細項對不到就統一算保健食品
DEFAULT_WEIGHT = 0.15


def guess_weight():
    return DEFAULT_WEIGHT


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
    ids = sorted(set(re.findall(r"/goods/(\w+)\.html", xml or "")))
    return ids


def parse_product(pid):
    url = f"{BASE}/goods/{pid}.html"
    html = fetch_text(url)
    if not html:
        return None

    first_match = FIRST_CRUMB_RE.search(html)
    if not first_match or not first_match.group(1).startswith(HEALTH_CATEGORY_PREFIX):
        return None  # 不是健康食品分類,略過

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
        # JSON-LD 的 price 是未稅價,官網實際顯示、客人實際要付的是稅込(含稅)價,
        # 差 8%(食品類消費稅率)——用「濃縮プエラリアミリフィカ」交叉比對過官網
        # 顯示的稅込價格,3800(未稅) x 1.08 = 4104(稅込)完全對上。
        jpy = round(float(price) * 1.08)
    except (TypeError, ValueError):
        return None
    availability = offers.get("availability", "")
    sale_type = "soldout" if "OutOfStock" in availability else "instock"

    second_match = SECOND_CRUMB_RE.search(html)
    subtype = JA_TO_SUBTYPE.get(second_match.group(1).strip(), DEFAULT_SUBTYPE) if second_match else DEFAULT_SUBTYPE

    images = data.get("image") or []
    image = images[0] if isinstance(images, list) and images else (images or None)

    result = {
        "name": data.get("name", "").strip(),
        "jpy": jpy,
        "weight": guess_weight(),
        "brand": BRAND,
        "subtype": subtype,
        "country": "JP",
        "saleType": sale_type,
        "link": url,
        "image": image,
    }
    orig_match = ORIG_PRICE_RE.search(html)
    if orig_match:
        orig_jpy = int(orig_match.group(1).replace(",", ""))
        if orig_jpy > jpy:
            result["origJpy"] = orig_jpy
    return result


def main():
    print("抓取商品清單(sitemap)...")
    ids = fetch_product_ids()
    print(f"共 {len(ids)} 件商品(全站,含保養品/服飾),開始逐一檢查是否為健康食品分類...")

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
            if done % 200 == 0:
                print(f"  ({done}/{len(ids)},健康食品分類目前累積 {len(final_list)} 件,其中缺貨 {soldout_count} 件)")
                with open("dhc_health_products.json", "w", encoding="utf-8") as f:
                    json.dump(final_list, f, ensure_ascii=False, indent=2)

    with open("dhc_health_products.json", "w", encoding="utf-8") as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)

    print(f"完成!已輸出 dhc_health_products.json,健康食品分類共 {len(final_list)} 件商品(其中缺貨 {soldout_count} 件)。")


if __name__ == "__main__":
    main()
