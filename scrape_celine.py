# -*- coding: utf-8 -*-
"""
CELINE 日本官網(celine.com/ja-jp)全站商品爬蟲
------------------------------------------------------------
用途:
  跟 Dior/LV 不一樣,CELINE(同屬 LVMH)沒有擋非瀏覽器的請求,商品頁是
  Salesforce Commerce Cloud(demandware)輸出的完整靜態 HTML:
  1) 商品名稱/價格/圖片/分類:標準 schema.org JSON-LD(<script
     type="application/ld+json">),直接讀。
  2) 尺寸庫存:每個尺寸是一個 <li data-mselector-listitem
     data-gtm-interactiontype="Size Selector - {尺寸}">,缺貨的尺寸
     <input> 會多一個 class="s-disabled",用這個判斷有貨/缺貨,不用
     額外呼叫 AJAX,親測跟畫面上顯示的一致。
  3) 顏色:CELINE 每個顏色是「獨立網址」(不像 GU 一頁涵蓋所有顏色),
     同一頁裡目前選中的顏色可以從 data-gtm-interactiontype=
     "Color swatch - {顏色}" 那個 li(帶 aria-current=page)讀到。
  4) 商品編號(sku)格式是「{款式代碼}.{顏色代碼}」(例如
     368285500C.09EC),用「.」前面的款式代碼把同一款不同顏色的頁面
     合併成一張商品卡(colors 陣列),邏輯跟 Lacoste 的
     scrape_lacoste_detail.py 类似。

  商品清單來源是官網自己的 sitemap(/ja-jp/sitemap_0-product.xml),
  3,039 個網址(每個網址是一個顏色,不是一個款式,合併後款式數會更少)。

  商品數量大、每頁都要真的抓一次(沒有像 Shopify 那種一次拿全部的
  API),抓完整站容易跑 30 分鐘以上,建議背景執行。

執行方式:
  pip install -r requirements.txt
  python scrape_celine.py [--limit N]   # --limit 只抓前 N 個網址,測試用

會輸出 celine_all_products.json。
"""

import argparse
import json
import re
import sys
import time
from urllib.parse import urljoin

import requests

from scrape_aape import COLOR_JA_TO_ZH as _BASE_COLOR_JA_TO_ZH
from scrape_on_full import fix_size_key

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

BASE = "https://www.celine.com"
SITEMAP_URL = f"{BASE}/ja-jp/sitemap_0-product.xml"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}
BRAND = "CELINE"

LDJSON_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.DOTALL)
LISTITEM_RE = re.compile(r'<li\s+data-mselector-listitem.*?</li>', re.DOTALL)

CATEGORY_TO_SUBTYPE = {
    "シューズ": "鞋類", "スニーカー": "鞋類", "サンダル": "鞋類", "ブーツ": "鞋類", "パンプス": "鞋類",
    "バッグ": "包款", "ハンドバッグ": "包款", "ショルダーバッグ": "包款", "トートバッグ": "包款",
    "クラッチバッグ": "包款", "バックパック": "包款",
    "アクセサリー": "配件", "ジュエリー": "配件", "チャーム": "配件", "ベルト": "皮帶",
    "スカーフ": "圍巾配件", "ストール": "圍巾配件",
    "サングラス": "配件", "アイウェア": "配件",
    "財布": "皮夾", "小物": "皮夾",
    "レディ・トゥ・ウェア": "上衣", "ニット": "針織衫", "コート": "外套", "ジャケット": "外套",
    "パンツ": "長褲", "スカート": "裙裝", "ドレス": "洋裝", "Tシャツ": "T恤", "シャツ": "襯衫",
    "帽子": "帽子", "キャップ": "帽子",
}
DEFAULT_SUBTYPE = "配件"

WEIGHT_BY_SUBTYPE = {
    "鞋類": 0.9, "包款": 0.6, "配件": 0.2, "皮帶": 0.25, "圍巾配件": 0.15,
    "皮夾": 0.25, "上衣": 0.35, "針織衫": 0.4, "外套": 0.7, "長褲": 0.45,
    "裙裝": 0.35, "洋裝": 0.4, "T恤": 0.25, "襯衫": 0.3, "帽子": 0.15,
}


# category 麵包屑對不到的時候(CELINE 的分類詞很雜,麵包屑本身常常也只是
# 「アクセサリー」這種大分類,對不到細項),退而求其次用商品名稱裡的關鍵字
# 猜——2026-08-08 第一次整站匯入時發現光靠 category 有 58% 的商品全部
# 掉進預設的「配件」,包括長褲、T恤、皮夾這種明顯分類錯誤的,才加這段。
NAME_KEYWORD_TO_SUBTYPE = [
    ("カードホルダー", "皮夾"), ("ウォレット", "皮夾"), ("パスポートカバー", "皮夾"),
    ("タンクトップ", "背心"),
    ("Tシャツ", "T恤"),
    ("スウェットシャツ", "上衣"), ("スウェット", "上衣"), ("パーカ", "連帽外套"), ("フーディ", "連帽外套"),
    ("シャツ", "襯衫"),
    ("ジーンズ", "長褲"), ("パンツ", "長褲"),
    ("スカーフ", "圍巾配件"), ("ストール", "圍巾配件"), ("マフラー", "圍巾配件"),
    ("キャップ", "帽子"), ("ハット", "帽子"),
    ("ワンピース", "洋裝"), ("ドレス", "洋裝"),
    ("セーター", "針織衫"), ("ニット", "針織衫"), ("カーディガン", "針織衫"),
    ("スカート", "裙裝"),
]


def guess_subtype(category, name=""):
    for part in (category or "").split(">"):
        part = part.strip()
        if part in CATEGORY_TO_SUBTYPE:
            return CATEGORY_TO_SUBTYPE[part]
    for kw, subtype in NAME_KEYWORD_TO_SUBTYPE:
        if kw in (name or ""):
            return subtype
    return DEFAULT_SUBTYPE


def guess_weight(subtype):
    return WEIGHT_BY_SUBTYPE.get(subtype, 0.3)


# CELINE 的顏色名稱一直是原始日文,2026-08-09 實測發現陌生客人看到
# 「マルチカラー」「ブラック / ゴールド」這種完全看不懂,決定補上翻譯。
# CELINE 自己的命名習慣是「形容詞+色名」黏在一起、中間不分隔的複合詞
# (例如「イエローゴールド」=黃色調金色、「ダークブラウン」=深棕色),直接
# 沿用 AAPE 那份基礎色表(scrape_aape.COLOR_JA_TO_ZH)靠子字串比對也抓得到
# (因為抓得到裡面的「ゴールド」「ブラウン」詞根),但會少了「深/淺/亮」這種
# 修飾語,語意還是對的顏色只是不夠精準。這裡先收錄幾組 CELINE 常見、值得
# 精準翻譯的複合詞,順序放在基礎表「前面」——translate_celine_color() 是
# 「先試完全比對、比對不到才退回子字串比對」,只有子字串那一段才需要在意
# 順序(比對到就傳回,不會再往下比),完全比對那一段不用擔心順序。
CELINE_COLOR_OVERRIDES = [
    ("イエローゴールド", "黃金色"),
    ("ホワイトゴールド", "白金色"),
    ("ダークブラウン", "深棕色"),
    ("ライトカーキ", "淺卡其"),
    ("ウルトラレッド", "亮紅色"),
    ("ウルトラブルー", "亮藍色"),
    ("ブライトレッド", "鮮紅色"),
    ("ソフトタン", "淺駝棕色"),
    ("ゴールデンタン", "金駝棕色"),
    ("ティールブルー", "藍綠色"),
    ("オプティックホワイト", "純白色"),
    ("ソフトライム", "淺萊姆綠"),
    ("ソフトクリーム", "淺奶油色"),
    ("タン", "駝棕色"),
    ("ナチュラル", "原色"),
    ("チェスナッツ", "栗棕色"),
    ("ライスカラー", "米色"),
    ("ライス", "米色"),
    ("バニラ", "香草色"),
    ("バーガンディ", "酒紅色"),
    ("デニム", "丹寧藍"),
    ("クリーム", "奶油色"),
]
CELINE_COLOR_JA_TO_ZH = CELINE_COLOR_OVERRIDES + _BASE_COLOR_JA_TO_ZH
# 「タン」這種只有兩個字的詞,拿去做子字串比對風險很高——實測發現「07
# コンスタンス」(其實是某個包款系列名稱,不是顏色,應該是官網那頁色票資料
# 本身標錯)裡面剛好包得住「タン」兩個字,子字串比對會誤翻成「07 駝棕色」。
# 兩個字的詞只做「完全比對」,三個字以上的詞才允許子字串比對,兩者風險差很多。
_EXACT_ONLY_MIN_LEN = 3


def translate_celine_color(name):
    name = (name or "").strip()
    if not name:
        return name
    # CELINE 顏色欄位常見「黑 / 金」這種用「/」隔開的雙色/撞色款,
    # 兩邊分開翻譯再組回去,跟 scrape_aape.translate_color() 處理
    # 「黑×紫」的邏輯是同一個道理。
    if "/" in name:
        return " / ".join(translate_celine_color(part.strip()) for part in name.split("/") if part.strip())
    for ja, zh in CELINE_COLOR_JA_TO_ZH:
        if ja == name:
            return zh
    for ja, zh in CELINE_COLOR_JA_TO_ZH:
        if len(ja) >= _EXACT_ONLY_MIN_LEN and ja in name:
            return zh
    return name  # 沒對到的通常是皮革專用色號(37TT)或法式色名,照原文顯示,不亂猜


def fetch_text(url, retries=3, timeout=25):
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
            time.sleep(3 * (attempt + 1))
    return None


def fetch_product_urls():
    xml = fetch_text(SITEMAP_URL, timeout=30)
    return sorted(set(re.findall(r"<loc>([^<]+)</loc>", xml or "")))


def parse_page(url, html):
    m = LDJSON_RE.search(html)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except Exception:
        return None
    node = next((n for n in data.get("@graph", []) if n.get("@type") == "Product"), None)
    if not node:
        return None

    sku = node.get("sku", "")
    if "." not in sku:
        return None
    style_code, color_code = sku.split(".", 1)

    offers = node.get("offers", {})
    try:
        jpy = int(float(offers.get("price")))
    except (TypeError, ValueError):
        return None
    availability = offers.get("availability", "")

    images = node.get("image") or []
    image = images[0].get("contentUrl") if images and isinstance(images[0], dict) else None

    # 顏色名稱:目前這頁選中的顏色 swatch(aria-current=page)
    color_name = color_code
    cm = re.search(
        r'data-gtm-interactiontype="Color swatch - ([^"]+)"(?:(?!</li>).)*?aria-current=page',
        html, re.S,
    )
    if cm:
        color_name = translate_celine_color(cm.group(1).strip())

    # 尺寸庫存:s-disabled = 缺貨。有些商品(單一尺寸的配件類)完全沒有
    # 尺寸選單,這種就當作「無尺寸選項」的單一庫存商品處理。
    sizes, stock = [], {}
    for li in LISTITEM_RE.findall(html):
        if "Size Selector" not in li:
            continue
        vm = re.search(r'data-value="([^"]+)"', li)
        if not vm:
            continue
        size = fix_size_key(vm.group(1).strip())
        if not size or size in stock:
            continue
        is_out = "s-disabled" in li
        sizes.append(size)
        stock[size] = 0 if is_out else 5
    if not sizes:
        # 沒有尺寸選項的商品,用 offers.availability 當唯一的庫存狀態
        sizes = ["F"]
        stock = {"F": 0 if "OutOfStock" in availability else 5}

    return {
        "style_code": style_code,
        "name": node.get("name", "").strip(),
        "jpy": jpy,
        "category": node.get("category", ""),
        "link": url,
        "color": {"name": color_name, "sizes": sizes, "stock": stock, "image": image},
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    print("抓取商品清單(sitemap)...")
    urls = fetch_product_urls()
    if args.limit:
        urls = urls[: args.limit]
    print(f"共 {len(urls)} 個顏色頁面")

    by_style = {}
    errors = 0
    for idx, url in enumerate(urls):
        html = fetch_text(url)
        if html:
            parsed = parse_page(url, html)
            if parsed:
                entry = by_style.setdefault(parsed["style_code"], {
                    "name": parsed["name"],
                    "jpy": parsed["jpy"],
                    "subtype": guess_subtype(parsed["category"], parsed["name"]),
                    "link": parsed["link"],
                    "colors": [],
                })
                entry["colors"].append(parsed["color"])
            else:
                errors += 1
        else:
            errors += 1
        time.sleep(0.4)
        if (idx + 1) % 100 == 0:
            print(f"  ({idx+1}/{len(urls)},已解析 {len(by_style)} 款,錯誤 {errors})")
            final_list = []
            for style_code, entry in by_style.items():
                subtype = entry["subtype"]
                final_list.append({
                    "name": entry["name"],
                    "jpy": entry["jpy"],
                    "weight": guess_weight(subtype),
                    "brand": BRAND,
                    "subtype": subtype,
                    "country": "JP",
                    "saleType": "instock",
                    "link": entry["link"],
                    "colors": entry["colors"],
                })
            with open("celine_all_products.json", "w", encoding="utf-8") as f:
                json.dump(final_list, f, ensure_ascii=False, indent=2)

    final_list = []
    for style_code, entry in by_style.items():
        subtype = entry["subtype"]
        final_list.append({
            "name": entry["name"],
            "jpy": entry["jpy"],
            "weight": guess_weight(subtype),
            "brand": BRAND,
            "subtype": subtype,
            "country": "JP",
            "saleType": "instock",
            "link": entry["link"],
            "colors": entry["colors"],
        })
    with open("celine_all_products.json", "w", encoding="utf-8") as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)
    print(f"完成!共 {len(final_list)} 款商品(合併顏色後),已輸出 celine_all_products.json")


if __name__ == "__main__":
    main()
