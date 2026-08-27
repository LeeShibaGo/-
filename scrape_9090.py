# -*- coding: utf-8 -*-
"""
9090 / 9090 girl(日本選物店 yz-store.com 上的兩個品牌)全站商品爬蟲
------------------------------------------------------------
用途:
  跟 Salomon/BAPE/STUSSY/POLENE 一樣是 Shopify 官方 products.json API,
  沒有機器人偵測,一次查詢就能拿到顏色(英文)、每個顏色+尺寸的即時真實
  庫存(true/false)、每個顏色專屬圖片、售價。

  2026-08-27 老闆確認:yz-store.com 其實是代理很多小品牌的選物店(共
  27 個 vendor),只抓「9090」「9090 girl」這兩個(共 1,148 件),不是
  整間店都抓。

  網站頁面上顯示的是「$」開頭的價格,一度讓人誤以為是台幣/美金——實測
  確認過網站本身的價格篩選欄位寫著「Price (¥)」,而且瀏覽器抓到的
  window.Shopify.currency 顯示 active:"TWD"、rate 幾乎等於即時匯率,
  代表頁面上看到的「$」是網站自動把日圓即時換算成台幣顯示給訪客看的
  結果,不是原始幣別。products.json 這個 API 端點回傳的才是原始日圓
  金額,不會有這層自動換算,拿這裡的數字存進資料庫是正確的。

  顏色是英文(White、Blue Stripe、Pink 這種),直接借用 scrape_stussy.py
  已經做好的 EN->中文顏色對照表(translate_color),不重寫一份、避免
  兩邊翻譯結果不一致。

  product_type 只有 4 種(トップス/ボトムス/アウター/小物),比 BAPE 精簡
  很多,但「小物」這個大雜燴分類(帽子/包款/珠寶飾品/鑰匙圈/皮帶/襪類/
  皮夾都混在一起)一樣需要用商品名稱關鍵字細分,規則抄 add_bape_missing.py
  GOODS_SUBTYPE_RULES 的做法(關鍵字判斷優先於分類欄位本身,理由同樣是
  分類欄位不夠準)。

執行方式:
  pip install -r requirements.txt
  python scrape_9090.py

會輸出 9090_all_products.json,可以直接餵給一次性匯入腳本。
"""

import json
import re
import sys
import time

import requests

from scrape_on_full import fix_size_key
from scrape_stussy import translate_color

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

BASE = "https://yz-store.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}
TARGET_VENDORS = {"9090", "9090 girl"}

TYPE_TO_SUBTYPE = {
    "トップス": "短袖上衣",  # 預設短袖,LONGSLEEVE_RE 命中的話覆蓋成長袖
    "ボトムス": "長褲",       # 預設長褲,SHORTS_RE 命中的話覆蓋成短褲
    "アウター": "外套",
}
DEFAULT_SUBTYPE = "服飾配件"

LONGSLEEVE_RE = re.compile(r"LONG\s*SLEEVE|L/S\b|\bLS\b", re.I)
SHORTS_RE = re.compile(r"\bSHORTS?\b", re.I)

# 「小物」分類底下的關鍵字細分規則,對照 add_bape_missing.py 的
# GOODS_SUBTYPE_RULES,同樣排除「BELT BAG(腰包)」誤判成皮帶的狀況。
GOODS_SUBTYPE_RULES = [
    (r"KEY\s*(CHAIN|RING|HOLDER)", "鑰匙圈吊飾"),
    (r"\bWALLET\b", "皮夾"),
    (r"\bBELT\b(?!\s*BAG)", "皮帶"),
    (r"\bCAP\b|\bHAT\b|BEANIE", "帽子"),
    (r"STICKER|PATCH|BADGE", "徽章貼紙"),
    (r"\bBAG\b", "包款"),
    (r"NECKLACE|\bRING\b|EARRING|BRACELET|PENDANT", "珠寶飾品"),
    (r"\bSOCKS?\b", "襪類"),
    (r"CARD|LIGHTER|DECK", "服飾配件"),
]

WEIGHT_BY_SUBTYPE = {
    "短袖上衣": 0.25, "長袖上衣": 0.35, "長褲": 0.45, "短褲": 0.3, "外套": 0.6,
    "帽子": 0.15, "包款": 0.4, "皮夾": 0.15, "皮帶": 0.15, "珠寶飾品": 0.03,
    "鑰匙圈吊飾": 0.03, "徽章貼紙": 0.02, "襪類": 0.08, "服飾配件": 0.1,
}
DEFAULT_WEIGHT = 0.2


def guess_subtype(product_type, title):
    for pattern, subtype in GOODS_SUBTYPE_RULES:
        if re.search(pattern, title, re.IGNORECASE):
            return subtype
    if product_type == "トップス":
        return "長袖上衣" if LONGSLEEVE_RE.search(title) else "短袖上衣"
    if product_type == "ボトムス":
        return "短褲" if SHORTS_RE.search(title) else "長褲"
    return TYPE_TO_SUBTYPE.get(product_type, DEFAULT_SUBTYPE)


def guess_weight(subtype):
    return WEIGHT_BY_SUBTYPE.get(subtype, DEFAULT_WEIGHT)


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
    title = (raw.get("title") or "").strip()
    vendor = raw.get("vendor")
    subtype = guess_subtype(raw.get("product_type"), title)

    by_color = {}
    for v in raw.get("variants", []):
        color_en = (v.get("option1") or "").strip()
        if not color_en:
            continue
        size = fix_size_key((v.get("option2") or "").strip()) or "F"
        entry = by_color.setdefault(color_en, {
            "name": translate_color(color_en), "sizes": [], "stock": {}, "image": None,
        })
        if size not in entry["stock"]:
            entry["sizes"].append(size)
        entry["stock"][size] = 5 if v.get("available") else 0
        if not entry["image"]:
            img = v.get("featured_image") or {}
            if img.get("src"):
                entry["image"] = img["src"]

    main_image = None
    imgs = raw.get("images") or []
    if imgs:
        main_image = imgs[0].get("src")
    colors = []
    for c in by_color.values():
        if not c["image"]:
            c["image"] = main_image
        colors.append(c)

    if not colors:
        return None

    try:
        jpy = int(float(raw["variants"][0]["price"]))
    except (KeyError, ValueError, TypeError, IndexError):
        return None

    return {
        "name": title,
        "jpy": jpy,
        "weight": guess_weight(subtype),
        "brand": vendor,
        "subtype": subtype,
        "country": "JP",
        "saleType": "instock",
        "link": f"{BASE}/products/{raw.get('handle')}",
        "colors": colors,
    }


def main():
    print("抓取商品清單(全站,之後篩選 vendor)...")
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
        time.sleep(0.5)

    target_raw = [p for p in all_raw if p.get("vendor") in TARGET_VENDORS]
    print(f"篩出 9090 + 9090 girl 共 {len(target_raw)} 件(全站 {len(all_raw)} 件)")

    final_list = []
    for raw in target_raw:
        entry = build_product(raw)
        if entry:
            final_list.append(entry)

    with open("9090_all_products.json", "w", encoding="utf-8") as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)
    print(f"完成!共 {len(final_list)} 件商品,已輸出 9090_all_products.json")


if __name__ == "__main__":
    main()
