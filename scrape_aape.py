"""
AAPE.JP 全站商品爬蟲
------------------------------------------------------------
用途:
  1. 找出網站上所有商品分類頁
  2. 每個分類自動翻頁,抓出該分類底下所有商品的名稱/價格/連結/圖片
  3. 點進每一件商品的詳細頁,抓出可選的顏色、尺寸、實際庫存件數
  4. 整理成一份 JSON,格式對應 daigou-shop.html 後台「批次匯入商品」功能

selector 已對照 aape.jp 實際網頁結構驗證過(2026-07-15),網站是伺服器端
直接輸出 HTML(EBISUMART 平台),不需要等 JavaScript 執行就抓得到資料,
requests + BeautifulSoup 就夠用,不需要 Selenium。

執行方式:
  pip install -r requirements.txt
  python scrape_aape.py

會輸出 aape_all_products.json,可直接貼進 daigou-shop.html 的批次匯入功能,
或用 --limit 參數先抓少量測試。
"""

import argparse
import json
import re
import sys
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# Windows 的終端機預設編碼(cp950/cp936 等)印不出某些日文/特殊字元,
# 商品名稱裡只要出現一個這種字元,print() 就會直接讓整支程式當掉。
# 改成 UTF-8 並把印不出來的字元用問號取代,才不會因為印字失敗而前功盡棄。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

BASE_URL = "https://aape.jp"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}
# 兩次請求之間的間隔秒數,避免對官網造成負擔、也降低被擋的機率
REQUEST_DELAY = 0.8

# 依商品名稱關鍵字概略估重量(公斤),已包含約 45% 的安全緩衝
# TODO: 這是概略估計,不是官方數據,建議上架前抽件確認
WEIGHT_RULES = [
    (r"SUITCASE", 3.6),
    (r"BACKPACK|BOSTON BAG|TOTE BAG|BAG\b", 1.2),
    (r"JACKET|HOODIE|SWEAT(SHIRT)?\b", 0.65),
    # \b 是必要的:沒有的話 "SHORTS" 會連帶匹配到 "ShortSleeve"(短袖),
    # 把一件 T 恤估成褲子的重量
    (r"PANTS|DENIM|CARGO|\bSHORTS\b", 0.45),
    (r"SLIDER|SHOES|SNEAKER", 0.5),
    (r"CAP|HAT|BUCKET", 0.2),
    (r"CUSHION", 0.55),
    (r"TEE|POLO|SHIRT", 0.3),
]
DEFAULT_WEIGHT = 0.4

# 日文顏色名稱 → 中文,依「特殊/複合詞優先」的順序比對(用 in 判斷子字串,
# 例如「グレー系その他」只要含有「グレー」就會對到「灰色」)。
# 對照不到的顏色會保留日文原文,不會硬翻譯出錯誤的中文。
COLOR_JA_TO_ZH = [
    ("ライトグレー", "淺灰"),
    ("チャコール", "炭灰色"),
    ("オフホワイト", "米白"),
    ("アイボリー", "象牙白"),
    ("ベージュ", "米色"),
    ("キャメル", "駝色"),
    ("カーキ", "卡其"),
    ("モカ", "摩卡棕"),
    ("ブラウン", "棕色"),
    ("ネイビー", "深藍"),
    ("サックス", "淺藍"),
    ("ターコイズ", "土耳其藍"),
    ("ブルー", "藍色"),
    ("ミント", "薄荷綠"),
    ("オリーブ", "橄欖綠"),
    ("グリーン", "綠色"),
    ("マスタード", "芥末黃"),
    ("イエロー", "黃色"),
    ("オレンジ", "橘色"),
    ("ボルドー", "酒紅色"),
    ("ワイン", "酒紅色"),
    ("レッド", "紅色"),
    ("ピンク", "粉紅色"),
    ("ラベンダー", "薰衣草紫"),
    ("パープル", "紫色"),
    ("ゴールド", "金色"),
    ("シルバー", "銀色"),
    ("グレー", "灰色"),
    ("ホワイト", "白色"),
    ("ブラック", "黑色"),
    ("カモフラージュ", "迷彩"),
    ("カモ", "迷彩"),
    ("マルチ", "多彩花色"),
]


def translate_color(name):
    for ja, zh in COLOR_JA_TO_ZH:
        if ja in name:
            return zh
    return name


# 網站尺寸標示是英文全稱(SMALL/MEDIUM/...),換成代購網頁慣用的縮寫格式
SIZE_STANDARDIZE = {
    "XXS": "XXS", "XS": "XS", "SMALL": "S", "MEDIUM": "M", "LARGE": "L",
    "X-LARGE": "XL", "XX-LARGE": "XXL", "XXX-LARGE": "XXXL",
    "FREE": "F", "FREE SIZE": "F", "ONE SIZE": "F",
}


def standardize_size(name):
    return SIZE_STANDARDIZE.get(name.strip().upper(), name.strip())


def guess_weight(name):
    for pattern, weight in WEIGHT_RULES:
        if re.search(pattern, name, re.IGNORECASE):
            return weight
    return DEFAULT_WEIGHT


BRAND = "AAPE"

# 三層分類的第三層(種類)。原本整個靠猜商品名稱關鍵字分類,結果「Shortsleeve
# Tee(短袖上衣)」的名字裡剛好包含 "SHORTS" 這個子字串,被誤判成短褲 ——
# 這種以偏概全的規則問題,不如直接信任 aape.jp 自己的分類頁面(每個分類頁的
# 日文名稱,見 discover_categories() 抓到的 label_ja)。
# 網站本身沒有再把「トップス(上衣)」細分成長袖/短袖,「パンツ(褲裝)」也
# 沒有再細分長褲/短褲 —— 這兩個是我們自己加的更細分類,所以只在這兩個分類底下
# 才需要額外用商品名稱關鍵字判斷,其他分類就直接照官網的分類名稱走,不用再猜。
CATEGORY_ZH = {
    "ジャケット/アウター": "外套",
    "オールインワン・サロペット": "連身褲",
    "スカート": "裙裝",
    "ワンピース/ドレス": "洋裝",
    "バッグ": "包款",
    "シューズ": "鞋類",
    "ファッション雑貨": "時尚配件",
    "財布/小物": "錢包小物",
    "腕時計": "手錶",
    "ヘアアクセサリー": "髮飾",
    "アクセサリー": "配件",
    "アンダーウェア": "內著",
    "レッグウェア": "襪類",
    "帽子": "帽子",
    "インテリア": "居家雜貨",
    "食器/キッチン": "餐廚用品",
    "雑貨/ホビー": "雜貨嗜好",
    "水着/着物・浴衣": "泳裝和服",
    "その他": "其他",
}

# 只有「トップス(上衣)」底下才需要再細分長袖/短袖/背心/針織/連帽,
# 依序比對、第一個命中的規則就決定分類。
TOPS_SUBTYPE_RULES = [
    (r"TANKTOP|TANK\s*TOP", "背心"),
    (r"HOODIE", "連帽外套"),
    (r"CARDIGAN|KNIT", "針織衫"),
    (r"LONG\s*SLEEVE|LONG\s*SLLEVE", "長袖上衣"),  # 官網商品名偶爾把 SLEEVE 拼成 SLLEVE
    (r"CREW\s*NECK\s*SWEAT|RAGLAN.*SWEAT|SWEAT\b", "長袖上衣"),
    (r"SHORT\s*SLEEVE|SHORTSLEEVE|TEE|POLO|SHIRT", "短袖上衣"),  # AAPE 的上衣預設多半是短袖
]

# 只有「パンツ(褲裝)」底下才需要再細分長褲/短褲
PANTS_SUBTYPE_RULES = [
    (r"SHORTS", "短褲"),
]


def guess_subtype(name, category_ja):
    if category_ja == "トップス":
        for pattern, subtype in TOPS_SUBTYPE_RULES:
            if re.search(pattern, name, re.IGNORECASE):
                return subtype
        return "上衣"
    if category_ja == "パンツ":
        for pattern, subtype in PANTS_SUBTYPE_RULES:
            if re.search(pattern, name, re.IGNORECASE):
                return subtype
        return "長褲"
    return CATEGORY_ZH.get(category_ja, "其他")


def is_reversible(name):
    return bool(re.search(r"REVERSIBLE", name, re.IGNORECASE))


def fetch_soup(url):
    res = requests.get(url, headers=HEADERS, timeout=15)
    res.raise_for_status()
    time.sleep(REQUEST_DELAY)
    return BeautifulSoup(res.text, "html.parser")


# 實測發現伺服器每頁最多給 200 件(要求更高的數字也只會回 200 件),
# 用這個當每頁筆數,分類頁數就會降到最低。
PAGE_SIZE = 200

# 分類連結長這樣:https://aape.jp/category/GT101/?condition=GENDER:G1&...
# 同一個分類代碼(如 GT101)在男/女導覽列各出現一次,但拿掉 condition=GENDER 這個
# 篩選條件後,分類頁本身就會回傳該分類「不分性別」的完整商品清單(實測 708 件
# vs 加了 GENDER:G1 篩選只有 576 件),所以只需要依代碼去重,不用管性別參數。
CATEGORY_CODE_RE = re.compile(r"/category/([A-Za-z0-9_]+)/")
TOTAL_COUNT_RE = re.compile(r"全\s*([\d,]+)\s*件")


def discover_categories():
    """
    從首頁導覽列找出所有分類頁連結跟它的日文分類名稱(連結文字),依分類代碼去重,
    組成不帶性別篩選的乾淨網址。分類名稱之後會拿來決定商品的「種類」(三層分類的
    第三層),比自己用商品名稱關鍵字用猜的準確,也是這次改版的原因。
    "GOODS_TYPE" 是「顯示全部商品」的總覽分類,底下的商品其實都會出現在
    各個細分分類裡,略過它可以避免整批商品被重複抓兩次。
    """
    soup = fetch_soup(BASE_URL)
    categories = {}
    for a in soup.select("a[href*='/category/']"):
        href = a.get("href")
        if not href:
            continue
        m = CATEGORY_CODE_RE.search(href)
        if not m:
            continue
        code = m.group(1)
        if code == "GOODS_TYPE":
            continue
        label = a.get_text(strip=True)
        if code not in categories and label:
            categories[code] = label
    return sorted(
        ({"code": code, "label_ja": label, "url": f"{BASE_URL}/category/{code}/"} for code, label in categories.items()),
        key=lambda c: c["code"],
    )


def discover_products_in_category(category_url, max_pages=50):
    """
    翻遍一個分類底下所有分頁,回傳該分類所有商品的基本資訊(名稱/連結/圖片/價格)。
    每個商品卡片是 <li class="card-item">,商品名稱/連結在 .card-item-name a,
    價格(含稅、跟網站上顯示的售價一致)在 .card-item-price .price-entity。
    """
    products = []
    page = 1
    while page <= max_pages:
        if page == 1:
            url = f"{category_url}?SEARCH_MAX_ROW_LIST={PAGE_SIZE}&sort_order=1&item_list_mode=1"
        else:
            url = (
                f"{category_url}?SEARCH_MAX_ROW_LIST={PAGE_SIZE}&sort_order=1"
                f"&item_list_mode=1&request=page&next_page={page}"
            )
        soup = fetch_soup(url)

        cards = soup.select("li.card-item")
        if not cards:
            break

        for card in cards:
            name_tag = card.select_one(".card-item-name a")
            link_tag = name_tag or card.select_one(".card-item-image a")
            if not link_tag or not link_tag.get("href"):
                continue
            price_tag = card.select_one(".card-item-price .price-entity")
            img_tag = card.select_one(".card-item-image img")

            name = name_tag.get_text(strip=True) if name_tag else link_tag.get("title", "").strip()
            price_text = price_tag.get_text(strip=True) if price_tag else ""
            price = extract_price_number(price_text)
            link = urljoin(BASE_URL, link_tag.get("href"))
            image = urljoin(BASE_URL, img_tag.get("src")) if img_tag and img_tag.get("src") else None

            if name and price:
                products.append({"name": name, "jpy": price, "link": link, "image": image})

        # 用頁面上「全 N 件」的總數,判斷是不是已經抓完,比找「下一頁」按鈕更可靠
        count_tag = soup.select_one(".c-page_count")
        total = None
        if count_tag:
            m = TOTAL_COUNT_RE.search(count_tag.get_text())
            if m:
                total = int(m.group(1).replace(",", ""))
        if total is not None and page * PAGE_SIZE >= total:
            break
        if len(cards) < PAGE_SIZE:
            break
        page += 1

    return products


def extract_price_number(text):
    cleaned = re.sub(r"[^\d]", "", text)
    return int(cleaned) if cleaned else None


def fetch_product_detail(link):
    """
    打開商品詳細頁,抓出顏色與每個顏色對應的尺寸、庫存狀態。
    實測結構:每個顏色是一個 <div class="variation-row">,裡面
    .variation-row-thumbnail .color 是顏色名稱(日文,例如「グレー系その他」),
    底下 .variation-col-item 每一個是一個尺寸,.size 是尺寸文字、
    .quantity 是實際庫存件數的數字、.stock 的 class 會是 "stock in"(有貨)
    或推測缺貨時是 "stock out"(未實際遇到缺貨商品驗證,故 quantity<=0 時也視為缺貨)。
    """
    try:
        soup = fetch_soup(link)
    except Exception as e:
        return {"colors": [], "error": str(e)}

    colors = []
    for row in soup.select(".variation-row"):
        color_el = row.select_one(".variation-row-thumbnail .color")
        color_name_ja = color_el.get_text(strip=True) if color_el else None
        if not color_name_ja:
            continue
        color_name = translate_color(color_name_ja)

        # 縮圖網址是 xxx_d_125.jpg 這種低解析度版本,換成 _d_240 跟商品列表圖片同等級
        img_el = row.select_one(".variation-row-thumbnail .image img")
        color_image = None
        if img_el and img_el.get("src"):
            color_image = urljoin(BASE_URL, img_el["src"]).replace("_d_125.jpg", "_d_240.jpg")

        sizes = []
        stock = {}
        for item_el in row.select(".variation-col-item"):
            size_el = item_el.select_one(".variation-col-size_stock .size")
            qty_el = item_el.select_one(".variation-col-size_stock .quantity")
            stock_el = item_el.select_one(".variation-col-size_stock .stock")
            if not size_el:
                continue
            size_name = standardize_size(size_el.get_text(strip=True))
            if not size_name:
                continue
            qty = extract_price_number(qty_el.get_text()) if qty_el else None
            stock_classes = (stock_el.get("class") or []) if stock_el else []
            is_out = ("out" in stock_classes) or (qty is not None and qty <= 0)
            sizes.append(size_name)
            stock[size_name] = 0 if is_out else (qty if qty is not None else 1)

        if sizes:
            color_entry = {"name": color_name, "sizes": sizes, "stock": stock}
            if color_image:
                color_entry["image"] = color_image
            colors.append(color_entry)

    return {"colors": colors}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="只抓前 N 件商品,方便測試")
    parser.add_argument("--skip-detail", action="store_true", help="先只抓列表資訊,不點進詳細頁(比較快,用來確認列表抓取邏輯是否正確)")
    args = parser.parse_args()

    print("尋找所有分類頁...")
    categories = discover_categories()
    print(f"找到 {len(categories)} 個分類")

    all_products = []
    seen_links = set()

    for cat in categories:
        print(f"抓取分類:{cat['label_ja']}({cat['url']})")
        try:
            items = discover_products_in_category(cat["url"])
        except Exception as e:
            print(f"  [錯誤] 這個分類抓取失敗:{e}")
            continue
        for it in items:
            if it["link"] in seen_links:
                continue
            seen_links.add(it["link"])
            it["category_ja"] = cat["label_ja"]
            all_products.append(it)
            if args.limit and len(all_products) >= args.limit:
                break
        if args.limit and len(all_products) >= args.limit:
            break

    print(f"共找到 {len(all_products)} 件不重複商品,開始整理欄位...")

    final_list = []
    for i, p in enumerate(all_products):
        name = p["name"]
        entry = {
            "name": name,
            "jpy": p["jpy"],
            "weight": guess_weight(name),
            "brand": BRAND,
            "subtype": guess_subtype(name, p["category_ja"]),
            "country": "JP",
            "saleType": "instock",
            "link": p["link"],
        }
        if is_reversible(name):
            entry["note"] = "雙面穿商品,實際兩面顏色請以官網介紹連結的照片為準"
        if p.get("image"):
            entry["image"] = p["image"]

        if not args.skip_detail:
            print(f"  [{i+1}/{len(all_products)}] 查詢尺寸顏色:{name}")
            detail = fetch_product_detail(p["link"])
            if detail.get("colors"):
                entry["colors"] = detail["colors"]

        final_list.append(entry)

        # 每 100 件先存一次檔:全站上千件商品要跑很久,中途萬一斷線或出錯,
        # 已經抓到的資料不會白費,重跑時也能看到目前進度。
        if (i + 1) % 100 == 0:
            with open("aape_all_products.json", "w", encoding="utf-8") as f:
                json.dump(final_list, f, ensure_ascii=False, indent=2)
            print(f"  (已儲存進度:{i+1}/{len(all_products)})")

    with open("aape_all_products.json", "w", encoding="utf-8") as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)

    print(f"完成!已輸出 aape_all_products.json,共 {len(final_list)} 件商品。")


if __name__ == "__main__":
    main()
