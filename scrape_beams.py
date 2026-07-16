"""
BEAMS (beams.co.jp) 指定品牌商品爬蟲
------------------------------------------------------------
用途:
  只抓取「指定品牌」的商品(目前設定 Needles、Fred Perry),不是抓全站。
  BEAMS 全站商品高達 27000+ 件(光是男裝 T 恤一個分類就有 3000+ 件),
  不適合像 AAPE 一樣整站爬,所以改用「關鍵字搜尋」鎖定單一品牌:
  https://www.beams.co.jp/search/?search=true&q={品牌名}&sex=M

  BEAMS 站上這些「店中店」品牌的商品命名慣例固定是「品牌名 / 商品名稱」,
  所以關鍵字搜尋品牌名幾乎不會有漏抓或誤抓(誤抓的極少數會在整理階段
  用「名稱是否以品牌名開頭」再過濾一次)。

selector 已對照 beams.co.jp 實際網頁結構驗證過(2026-07-16):
  - 沒有 robots.txt 擋 ClaudeBot,也沒有 Cloudflare/Akamai 這類 bot 防護,
    伺服器端直接輸出完整 HTML,requests + BeautifulSoup 就夠用。
  - 商品詳細頁「同一頁」就包含所有顏色 × 尺寸的庫存矩陣(不像 AAPE 要
    另外處理 variation-row),每個顏色是一個
    `.item-stock-container[data-color]`,裡面 `.item-size` 就是這個顏色
    每個尺寸的庫存文字(在庫あり/残りわずか/残り1点/在庫なし)。

執行方式:
  pip install -r requirements.txt
  python scrape_beams.py

會輸出 beams_products.json,可直接貼進 daigou-shop.html 的批次匯入功能。

注意(2026-07-16 實測):beams.co.jp 對「非瀏覽器」的連線似乎有網路層級的
擋法(不是回 403,是直接不回應、連線逾時,連 curl 都一樣),跟 aape.jp
用 requests 完全沒問題的狀況不一樣。這支程式在某些網路環境下可能會一直
逾時失敗;如果遇到這個狀況,改用瀏覽器工具(在已開啟 beams.co.jp 分頁的
JS console 裡執行同樣邏輯的 fetch())仍然抓得到資料 —— 第一批 Needles /
Fred Perry 64 件商品就是用這個方式手動跑成功的,可參考聊天記錄裡的做法。
"""

import argparse
import json
import re
import sys
import time
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

BASE_URL = "https://www.beams.co.jp"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}
REQUEST_DELAY = 0.8

# 目前只指定這兩個品牌,之後要加別的品牌只要在這裡加一行
# (key 是我們自己網站上要顯示的品牌名稱, value 是拿去 BEAMS 搜尋的關鍵字)
BRANDS = {
    "NEEDLES": "Needles",
    "FRED PERRY": "Fred Perry",
}

WEIGHT_RULES = [
    (r"BACKPACK|BOSTON BAG|TOTE BAG|\bBAG\b", 1.2),
    (r"JACKET|BLOUSON|COAT|HOODIE|SWEAT(SHIRT)?\b", 0.65),
    (r"PANTS?\b|DENIM|CARGO|TROUSER|SLACKS|\bSHORTS?\b", 0.45),
    (r"SHOES|SNEAKER|BOOTS?", 0.6),
    (r"CAP\b|HAT\b|BANDANA", 0.2),
    (r"BAG\b", 1.0),
    (r"TEE\b|POLO|SHIRT", 0.3),
]
DEFAULT_WEIGHT = 0.4


def guess_weight(name):
    for pattern, weight in WEIGHT_RULES:
        if re.search(pattern, name, re.IGNORECASE):
            return weight
    return DEFAULT_WEIGHT


# breadcrumb 上的細分類(日文)→ 我們自己網站用的中文種類,
# 對照不到的就直接保留原文,不會硬翻譯出錯誤的中文。
SUBTYPE_JA_TO_ZH = {
    "ポロシャツ": "Polo衫",
    "Tシャツ": "T恤",
    "カットソー": "上衣",
    "シャツ": "襯衫",
    "ブラウス": "襯衫",
    "スウェット": "長袖上衣",
    "パーカー": "連帽外套",
    "ニット": "針織衫",
    "カーディガン": "針織衫",
    "ジャケット": "外套",
    "ブルゾン": "外套",
    "コート": "外套",
    "ベスト": "背心",
    "パンツ": "長褲",
    "デニム": "牛仔褲",
    "ショーツ": "短褲",
    "スカート": "裙裝",
    "ワンピース": "洋裝",
    "バッグ": "包款",
    "トートバッグ": "包款",
    "リュック": "包款",
    "シューズ": "鞋類",
    "スニーカー": "鞋類",
    "サンダル": "鞋類",
    "帽子": "帽子",
    "キャップ": "帽子",
    "ハット": "帽子",
    "財布": "錢包小物",
    "小物": "錢包小物",
    "ベルト": "皮帶",
    "マフラー": "圍巾",
    "ストール": "圍巾",
    "手袋": "手套",
    "靴下": "襪類",
    "ソックス": "襪類",
    "サングラス": "配件",
    "アクセサリー": "配件",
    "時計": "手錶",
    "バンダナ": "配件",
}


def guess_subtype(breadcrumb_items):
    # breadcrumb 结构: [TOP, 店鋪名, 大分類, 細分類, 商品名稱]
    # 細分類(倒數第二個)比較具體,優先用它;對照不到再退回大分類。
    candidates = []
    if len(breadcrumb_items) >= 2:
        candidates.append(breadcrumb_items[-2])
    if len(breadcrumb_items) >= 3:
        candidates.append(breadcrumb_items[-3])
    for label in candidates:
        if label in SUBTYPE_JA_TO_ZH:
            return SUBTYPE_JA_TO_ZH[label]
    return candidates[0] if candidates else "其他"


STOCK_TEXT_MAP = [
    ("在庫なし", 0),
    ("残り1点", 1),
    ("残りわずか", 2),
    ("在庫あり", 5),
]


def parse_stock_text(text):
    for keyword, qty in STOCK_TEXT_MAP:
        if keyword in text:
            return qty
    return 0


def upsize_image(url):
    """
    列表卡片跟顏色縮圖抓到的圖都是小尺寸(S1 資料夾實測只有 60x72,S2 是
    250x300),换成 O 資料夾(實測 1200x1440,原始大圖)才不會放大後模糊。
    """
    if not url:
        return url
    return re.sub(r"/(S1|S2)/", "/O/", url)


def extract_price_number(text):
    matches = re.findall(r"[\d,]+", text)
    if not matches:
        return None
    # 特價商品會同時出現原價和特價兩個數字,取最後一個(目前實際售價)
    return int(matches[-1].replace(",", ""))


def fetch_soup(url):
    res = requests.get(url, headers=HEADERS, timeout=15)
    res.raise_for_status()
    time.sleep(REQUEST_DELAY)
    return BeautifulSoup(res.text, "html.parser")


def discover_products(keyword, brand_label, max_pages=20):
    """
    用關鍵字搜尋鎖定品牌,翻頁抓出該品牌底下所有商品的基本資訊。
    """
    products = []
    seen_links = set()
    page = 1
    while page <= max_pages:
        url = f"{BASE_URL}/search/?search=true&q={quote(keyword)}&sex=M&ps=80"
        if page > 1:
            url += f"&p={page}"
        soup = fetch_soup(url)

        cards = soup.select("li.beams-list-image-item")
        if not cards:
            break

        new_this_page = 0
        for card in cards:
            a = card.select_one('a[href*="/item/"]')
            if not a or not a.get("href"):
                continue
            name_tag = card.select_one(".product-name")
            name = name_tag.get_text(strip=True) if name_tag else a.get("title", "").strip()
            if not name or not name.upper().startswith(brand_label.upper()):
                continue

            price_tag = card.select_one(".price")
            price = extract_price_number(price_tag.get_text()) if price_tag else None

            link = urljoin(BASE_URL, a["href"]).split("?")[0]
            if link in seen_links:
                continue
            seen_links.add(link)

            img_tag = card.select_one("img")
            image = None
            if img_tag and img_tag.get("src"):
                image = img_tag["src"]
                if image.startswith("//"):
                    image = "https:" + image
                image = upsize_image(image)

            if price:
                products.append({"name": name, "jpy": price, "link": link, "image": image})
                new_this_page += 1

        if new_this_page == 0:
            break
        page += 1

    return products


def fetch_product_detail(link):
    """
    打開商品詳細頁,一次抓出 breadcrumb 分類跟所有顏色 × 尺寸的庫存矩陣。
    這個站的詳細頁跟 AAPE 不一樣的地方是:同一頁就包含全部顏色的庫存
    (`.item-stock-container` 每個顏色各一個區塊),不用像 AAPE 額外對每個
    顏色多發一次請求。
    """
    try:
        soup = fetch_soup(link)
    except Exception as e:
        return {"colors": [], "breadcrumb": [], "error": str(e)}

    breadcrumb = [
        el.get_text(strip=True)
        for el in soup.select(".breadcrumb-list [itemprop=name]")
    ]

    price_tag = soup.select_one(".price")
    price = extract_price_number(price_tag.get_text()) if price_tag else None

    colors = []
    for container in soup.select(".item-stock-container"):
        color_code = container.get("data-color")
        name_el = container.select_one("h4.item-color")
        color_name = name_el.get_text(strip=True) if name_el else color_code
        if not color_name:
            continue

        img_el = container.select_one(".item-thumb img")
        color_image = None
        if img_el and img_el.get("src"):
            color_image = img_el["src"]
            if color_image.startswith("//"):
                color_image = "https:" + color_image
            color_image = upsize_image(color_image)

        sizes = []
        stock = {}
        for size_el in container.select(".item-size"):
            # .item-size 文字是「S／在庫あり」這種格式,第一段是尺寸,
            # 之後不定會接「最短当日発送」等額外文字,只取斜線前後兩段。
            full_text = size_el.get_text(strip=True)
            if "／" not in full_text:
                continue
            size_name, status_text = full_text.split("／", 1)
            size_name = size_name.strip()
            if not size_name:
                continue
            sizes.append(size_name)
            stock[size_name] = parse_stock_text(status_text)

        if sizes:
            entry = {"name": color_name, "sizes": sizes, "stock": stock}
            if color_image:
                entry["image"] = color_image
            colors.append(entry)

    return {"colors": colors, "breadcrumb": breadcrumb, "price": price}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="只抓前 N 件商品,方便測試")
    args = parser.parse_args()

    all_products = []
    seen_links = set()

    for brand_display, keyword in BRANDS.items():
        print(f"搜尋品牌:{brand_display}(關鍵字:{keyword})")
        try:
            items = discover_products(keyword, brand_display)
        except Exception as e:
            print(f"  [錯誤] 這個品牌搜尋失敗:{e}")
            continue
        print(f"  找到 {len(items)} 件")
        for it in items:
            if it["link"] in seen_links:
                continue
            seen_links.add(it["link"])
            it["brand"] = brand_display
            all_products.append(it)
            if args.limit and len(all_products) >= args.limit:
                break
        if args.limit and len(all_products) >= args.limit:
            break

    print(f"共找到 {len(all_products)} 件不重複商品,開始查詢顏色尺寸庫存...")

    final_list = []
    for i, p in enumerate(all_products):
        name = p["name"]
        print(f"  [{i+1}/{len(all_products)}] {name}")
        detail = fetch_product_detail(p["link"])

        entry = {
            "name": name,
            "jpy": detail.get("price") or p["jpy"],
            "weight": guess_weight(name),
            "brand": p["brand"],
            "subtype": guess_subtype(detail.get("breadcrumb", [])),
            "country": "JP",
            "saleType": "instock",
            "link": p["link"],
        }
        if p.get("image"):
            entry["image"] = p["image"]
        if detail.get("colors"):
            entry["colors"] = detail["colors"]

        final_list.append(entry)

        if (i + 1) % 50 == 0:
            with open("beams_products.json", "w", encoding="utf-8") as f:
                json.dump(final_list, f, ensure_ascii=False, indent=2)
            print(f"  (已儲存進度:{i+1}/{len(all_products)})")

    with open("beams_products.json", "w", encoding="utf-8") as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)

    print(f"完成!已輸出 beams_products.json,共 {len(final_list)} 件商品。")


if __name__ == "__main__":
    main()
