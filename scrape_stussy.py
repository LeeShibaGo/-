# -*- coding: utf-8 -*-
"""
STÜSSY 日本官網(jp.stussy.com)全站商品爬蟲
------------------------------------------------------------
用途:
  跟 Salomon/BAPE 一樣是 Shopify 官方 products.json API,沒有機器人偵測,
  一次查詢就能拿到:顏色(英文)、每個顏色+尺寸的即時真實庫存(true/false)、
  每個顏色專屬圖片、售價。

  顏色是英文(White、Faded Black、Ash Heather 這種),不是 BAPE 那種需要
  代碼對照表的日文命名,所以用一份 EN->中文的關鍵字對照表:先找完全對應
  的名稱,對不到的話用「找得到的顏色關鍵字」當基底、其餘描述詞保留英文
  一起顯示(例如「Faded Black」抓不到完全對應,會變成「洗舊黑(Faded)」),
  總比整串英文看不懂好,也不會漏掉真正對不到的狀況假裝翻好了。

  product_type(HEADWEAR/FLEECE/TEES...)對照成中文 subtype,盡量對到
  index.html 既有的 SUBTYPE_GROUP。

執行方式:
  pip install -r requirements.txt
  python scrape_stussy.py

會輸出 stussy_all_products.json,可以直接餵給一次性匯入腳本。
"""

import json
import re
import sys
import time

import requests

from scrape_on_full import fix_size_key

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

BASE = "https://jp.stussy.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}
BRAND = "STUSSY"

# 顏色關鍵字 -> 中文,由長到短比對(比對時會先試長的關鍵字,例如
# "Ash Heather" 要先於 "Ash"/"Heather" 個別比對,才不會被拆散翻錯)。
COLOR_EN_TO_ZH = [
    ("Ash Heather", "灰花"), ("Grey Heather", "灰花"), ("Heather Grey", "灰花"),
    ("Off White", "米白"), ("Faded Black", "洗舊黑"), ("Washed Black", "洗舊黑"),
    ("Vintage Black", "復古黑"), ("Rinsed Indigo", "水洗靛藍"), ("Light Wash Indigo", "淺水洗靛藍"),
    ("Dark Wash Indigo", "深水洗靛藍"), ("Indigo Stone Wash", "石洗靛藍"), ("Light Wash", "淺水洗"),
    ("Dark Wash", "深水洗"), ("Woodland Camo", "林地迷彩"), ("Desert Camo", "沙漠迷彩"),
    ("Sand Camo", "沙色迷彩"), ("Real Tree Edge", "真樹迷彩"), ("Black/Black Lens", "黑/黑鏡片"),
    ("Sky Blue", "天空藍"), ("Deep Blue", "深藍"), ("Royal Blue", "寶藍"), ("Dark Brown", "深棕"),
    ("Raw Black Contrast Stitch", "生黑撞色車線"),
    ("Black", "黑色"), ("Navy", "海軍藍"), ("Blue", "藍色"), ("White", "白色"), ("Brown", "棕色"),
    ("Natural", "本色"), ("Green", "綠色"), ("Bone", "骨白"), ("Red", "紅色"), ("Olive", "橄欖綠"),
    ("Pine", "松綠"), ("Khaki", "卡其"), ("Yellow", "黃色"), ("Pink", "粉紅"), ("Stone", "石灰"),
    ("Grey", "灰色"), ("Gray", "灰色"), ("Silver", "銀色"), ("Sand", "沙色"), ("Lime", "萊姆綠"),
    ("Ivory", "象牙白"), ("Leopard", "豹紋"), ("Wine", "酒紅"), ("Slate", "板岩灰"), ("Orange", "橘色"),
    ("Tan", "淺棕"), ("Royal", "寶藍"), ("Camo", "迷彩"), ("Indigo", "靛藍"), ("Snake", "蛇紋"),
    ("Charcoal", "炭灰"), ("Army", "軍綠"), ("Lemon", "檸檬黃"), ("Grape", "葡萄紫"), ("Sherbert", "雪酪色"),
    ("Moss", "苔綠"), ("Gold", "金色"), ("Onyx", "黑瑪瑙"), ("Turquoise", "土耳其藍"), ("Sage", "鼠尾草綠"),
    ("Purple", "紫色"), ("Multi", "多彩"), ("Cream", "奶油白"), ("Beige", "米色"), ("Maroon", "栗紅"),
]


def translate_color(name):
    name = (name or "").strip()
    if not name:
        return name
    for en, zh in COLOR_EN_TO_ZH:
        if name.lower() == en.lower():
            return zh
    # 找不到完全對應,看看有沒有包含已知關鍵字,關鍵字翻中文、其餘部分保留英文附註
    for en, zh in COLOR_EN_TO_ZH:
        if en.lower() in name.lower():
            remainder = re.sub(re.escape(en), "", name, flags=re.I).strip(" /-")
            return f"{zh}({remainder})" if remainder else zh
    return name  # 真的對不到,保留原文,不亂猜


TYPE_TO_SUBTYPE = {
    "HEADWEAR": "帽子", "Headwear": "帽子",
    "FLEECE": "上衣", "TEES": "T恤", "Tees": "T恤",
    "ACCESSORIES": "配件", "All Accessories": "配件",
    "BOTTOMS": "長褲", "Bottoms": "長褲", "Shorts, Bottoms": "短褲", "Mens Short": "短褲",
    "OUTERWEAR": "外套", "SWEATERS": "針織衫", "KNIT/JERSEY": "針織衫",
    "BASIC STUSSY": "上衣", "WOVENS": "襯衫", "SWIMWEAR": "泳裝",
    "Tops": "上衣", "WORLD TOUR": "上衣", "Sweats": "上衣", "Sweatshirt": "上衣",
    "Mens Long Sleeve Sweatshirt": "上衣", "'CASUAL SHOE": "鞋類",
}
DEFAULT_SUBTYPE = "服飾"

WEIGHT_BY_SUBTYPE = {
    "T恤": 0.25, "上衣": 0.35, "針織衫": 0.4, "襯衫": 0.3,
    "外套": 0.6, "長褲": 0.45, "短褲": 0.25, "帽子": 0.15,
    "配件": 0.2, "泳裝": 0.2, "鞋類": 0.9, "服飾": 0.3,
}


def guess_subtype(product_type):
    return TYPE_TO_SUBTYPE.get(product_type, DEFAULT_SUBTYPE)


def guess_weight(subtype):
    return WEIGHT_BY_SUBTYPE.get(subtype, 0.3)


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

    by_color = {}
    for v in raw.get("variants", []):
        color_en = (v.get("option1") or "").strip()
        if not color_en:
            continue
        # Firebase key 不能帶 . $ # [ ] /,帽子尺寸「7 1/2」、聯名尺寸「S/M」
        # 這種帶斜線的寫法會直接擋掉整包寫入(2026-08-08 匯入失敗才發現)。
        # fix_size_key 跟 sync_stussy() 用的是同一支,才不會兩邊尺寸字串對不起來。
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

    # 有些顏色的 variant 完全沒有 featured_image(共用商品主圖),補上第一張商品圖
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
        "name": raw.get("title", "").strip(),
        "jpy": jpy,
        "weight": guess_weight(subtype),
        "brand": BRAND,
        "subtype": subtype,
        "country": "JP",
        "saleType": "instock",
        "link": f"{BASE}/products/{raw.get('handle')}",
        "colors": colors,
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

    with open("stussy_all_products.json", "w", encoding="utf-8") as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)
    print(f"完成!共 {len(final_list)} 件商品,已輸出 stussy_all_products.json")


if __name__ == "__main__":
    main()
