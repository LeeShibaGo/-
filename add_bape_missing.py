# -*- coding: utf-8 -*-
"""一次性:把 jp.bape.com 官網有、但資料庫裡還沒上架的 BAPE 商品補上
------------------------------------------------------------
用途:
  老闆發現有些 BAPE 商品官網有賣、網站上卻找不到——查證後發現當初
  上架用的 _bape_import.py(早就照慣例刪掉了)只匯入了一部分商品,
  跟 sync_bape() 每天只同步「已經在資料庫裡」的商品、不會主動發現
  官網新商品是同一個原因(sync_bape 靠 handle 對照既有卡片,新商品
  沒有既有卡片可以對照,永遠不會被同步進來)。

  實測 2026-08-21:jp.bape.com 全站(所有 vendor)共 4,733 件商品,
  資料庫裡只有 1,848 件,缺 2,891 件。範圍太大,不是全部一次補齊——
  跟老闆確認過只上架這三塊(共 1,960 件),COLLABORATION(聯名系列,
  930 件)先不上架:
    - A BATHING APE(主線)/ MR. BATHING APE / BAPE BLACK  共 495 件
    - APEE BY A BATHING APE / BABY MILO / BABY MILO STORE  共 1,378 件
    - EYEWEAR(眼鏡)                                        共 87 件

  跟 sync_bape() 共用同一套顏色/尺寸/圖片解析邏輯(bape_translate_color/
  bape_variant_image,從 sync_stock.py import),避免同一份邏輯維護兩次、
  以後跑出不一致的結果。weight 沿用 scrape_aape.py 的 guess_weight()
  (同一個設計師品牌,服裝品項高度重疊,關鍵字規則直接適用)。

  重跑是安全的:用 handle 對照,已經存在的商品(不論是原本就有的,還是
  上次跑這支加進去的)都會被跳過,不會重複新增。

執行方式(透過 GitHub Actions 手動觸發):
  GitHub 網頁 -> 這個 repo -> Actions 分頁 -> 左邊選
  "One-off: add missing BAPE products" -> 右邊 "Run workflow" 按鈕
"""

import re
import sys
import time

import firebase_admin
from firebase_admin import credentials, db

from scrape_aape import guess_weight
from sync_stock import (
    HEADERS, bape_translate_color, bape_variant_image, build_products_index,
    fetch, fix_size_key,
)

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

FIREBASE_DB_URL = "https://shibago-4dd3c-default-rtdb.asia-southeast1.firebasedatabase.app"
PRODUCTS_PATH = "daigou-products-v1"
PRODUCTS_INDEX_PATH = "daigou-products-index-v1"

# 2026-08-21 老闆確認要上架的 vendor 範圍(見檔案開頭說明),COLLABORATION
# 聯名系列數量最多(930 件)但風格最雜,故意先不上架。
SELECTED_VENDORS = {
    "A BATHING APE", "MR. BATHING APE", "BAPE BLACK",
    "APEE", "BABY MILO", "BABY MILO STORE",
    "EYEWEAR",
}

# product_type(官網日文分類)-> 中文 subtype 基本對照,鍵值盡量沿用資料庫
# 裡既有 BAPE 商品已經在用的 subtype 字串(見本檔開頭調查記錄),不要
# 另外發明新名稱造成同一種東西被拆成兩個分類籤。
PRODUCT_TYPE_MAP = {
    "Tシャツ": "短袖上衣",
    "カットソー": "短袖上衣",
    "スウェット/パーカー": "長袖上衣",
    "アウター": "外套",
    "バッグ": "包款",
    "キャップ/ハット": "帽子",
    "シューズ": "鞋類",
    "シャツ": "襯衫",
    "アイウェア": "眼鏡",
    "ニット": "針織衫",
    "ベビー": "嬰兒服",
    "ウォッチ": "手錶",
    "ボトムス": "長褲",
}

# T恤/カットソー/パーカー底下,商品名稱帶這些關鍵字的話覆蓋成更精確的
# 分類,規則順序跟 scrape_aape.py 的 TOPS_SUBTYPE_RULES 對齊。
# BAPE 商品名稱常用「LS」當長袖縮寫(例如 "...LS TEE"),不是只有寫全稱
# "LONG SLEEVE" 才算,實測取樣就抓到這個縮寫用法,漏抓的話長袖 T 會被
# 誤分類成短袖上衣。
LONGSLEEVE_RE = re.compile(r"LONG\s*SLEEVE|L/S\b|\bLS\b", re.I)
HOODIE_RE = re.compile(r"HOODIE|PARKA|パーカー", re.I)
SHORTS_RE = re.compile(r"\bSHORTS\b", re.I)

# product_type == "グッズ"(雜貨,量最大、種類最雜的一類)底下,依商品名稱
# 關鍵字細分,對照資料庫裡既有的 subtype 字串。第一個命中的規則就採用,
# 都沒命中的話落回「服飾配件」(既有商品裡本來就有這個分類當萬用桶)。
GOODS_SUBTYPE_RULES = [
    (r"KEY\s*(CHAIN|RING|HOLDER)|キーホルダー|キーリング", "鑰匙圈吊飾"),
    (r"\bWALLET\b|財布", "皮夾"),
    # 排除「BELT BAG(腰包)」——那是包款不是皮帶,BELT 後面緊接 BAG 的話
    # 不算(2026-08-21 抓到"ABC MILO CAMO LUGGAGE BELT BAG"這種名稱,
    # 沒排除的話會被誤分類成皮帶)。
    (r"\bBELT\b(?!\s*BAG)", "皮帶"),
    (r"TOWEL|タオル", "毛巾"),
    (r"STICKER|PATCH|BADGE|ステッカー", "徽章貼紙"),
    (r"I ?PHONE|PHONE\s*CASE|スマホ", "手機周邊"),
    (r"PLUSH|DOLL|FIGURE|フィギュア|ぬいぐるみ", "公仔"),
    (r"NECKLACE|RING\b|EARRING|BRACELET|PENDANT|ネックレス|ピアス", "珠寶飾品"),
    (r"\bSWIM|TRUNKS\b|水着", "泳裝"),
    (r"UNDERWEAR|BOXER|BRIEF|ボクサー", "內著"),
    (r"\bSOCKS?\b|ソックス|靴下", "襪類"),
    (r"MUG|CUSHION|BLANKET|TRAY|PLATE|インテリア", "居家雜貨"),
]


def guess_subtype(product_type, name):
    # 2026-08-21 老闆回報有個錢包(1ST CAMO MINI WALLET)沒歸類到「皮夾」
    # ——查出來是官網自己把它的 product_type 標成「バッグ(包)」,不是
    # 預期中的「グッズ」,原本 GOODS_SUBTYPE_RULES 只在 product_type ==
    # "グッズ" 時才會套用,這件就直接落到「バッグ→包款」,沒機會被關鍵字
    # 規則接住。這些關鍵字(WALLET/BELT/KEYCHAIN...)本身辨識度已經很高,
    # 改成不管 product_type 是什麼都先檢查一次,比信任官網自己的分類欄位
    # 更準——act T恤/褲裝/外套那幾類的商品名稱不會意外命中這些關鍵字,
    # 不用擔心誤傷。
    for pattern, subtype in GOODS_SUBTYPE_RULES:
        if re.search(pattern, name, re.IGNORECASE):
            return subtype
    if product_type in ("Tシャツ", "カットソー"):
        if LONGSLEEVE_RE.search(name):
            return "長袖上衣"
        return "短袖上衣"
    if product_type == "スウェット/パーカー":
        if HOODIE_RE.search(name):
            return "連帽外套"
        return "長袖上衣"
    if product_type == "ボトムス":
        if SHORTS_RE.search(name):
            return "短褲"
        return "長褲"
    if product_type == "グッズ":
        # 走到這裡代表上面那輪 GOODS_SUBTYPE_RULES 已經沒有命中任何關鍵字,
        # 落回萬用桶,不用再檢查第二次。
        return "服飾配件"
    return PRODUCT_TYPE_MAP.get(product_type, "服飾配件")


def fetch_shop_catalog():
    """抓 jp.bape.com 全站商品(所有 vendor),跟 sync_bape() 同一支
    /products.json 端點、同一種分頁方式。"""
    shop_products = []
    page = 1
    while True:
        ps = fetch(f"https://jp.bape.com/products.json?limit=250&page={page}").json().get("products", [])
        shop_products.extend(ps)
        print(f"  第 {page} 頁,{len(ps)} 件,累積 {len(shop_products)} 件")
        if len(ps) < 250:
            break
        page += 1
        time.sleep(0.8)
    return shop_products


def build_card(sp, ts, idx):
    """把一件官網商品(Shopify 格式)轉成資料庫的卡片格式,跟
    buildCardHTML() 讀取的欄位對齊(colors[].name/sizes/stock/image)。"""
    name = sp.get("title") or ""
    product_type = sp.get("product_type") or ""
    subtype = guess_subtype(product_type, name)

    by_raw_color = {}
    for v in sp.get("variants", []):
        raw = (v.get("option1") or "").strip()
        by_raw_color.setdefault(raw, []).append(v)

    colors = []
    for raw, variants in by_raw_color.items():
        sizes, stock = [], {}
        for v in variants:
            s = fix_size_key((v.get("option2") or "").strip()) or "F"
            if s in stock:
                continue
            sizes.append(s)
            stock[s] = 5 if v.get("available") else 0
        image = bape_variant_image(sp, variants[0])
        colors.append({
            "name": bape_translate_color(raw) if raw else "預設",
            "sizes": sizes,
            "stock": stock,
            **({"image": image} if image else {}),
        })

    try:
        jpy = int(float(sp["variants"][0]["price"]))
    except (KeyError, ValueError, TypeError, IndexError):
        jpy = 0

    main_image = colors[0].get("image") if colors and colors[0].get("image") else (
        sp["images"][0]["src"] if sp.get("images") else None
    )

    return {
        "id": f"p_bape_{ts}_{idx}",
        "addedAt": ts,
        "name": name,
        "jpy": jpy,
        "weight": guess_weight(name),
        "brand": "BAPE",
        "subtype": subtype,
        "country": "JP",
        "saleType": "instock",
        "image": main_image,
        "link": f"https://jp.bape.com/products/{sp['handle']}",
        "colors": colors,
    }


def main():
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DB_URL})

    products = db.reference(PRODUCTS_PATH).get()
    if isinstance(products, dict):
        products = list(products.values())
    products = [p for p in products if p]

    existing_handles = set()
    for p in products:
        if p.get("brand") != "BAPE":
            continue
        link = p.get("link") or ""
        existing_handles.add(link.rstrip("/").rsplit("/", 1)[-1])
    print(f"資料庫裡已經有 {len(existing_handles)} 件 BAPE 商品")

    print("抓取 jp.bape.com 全站商品清單...")
    shop_products = fetch_shop_catalog()
    print(f"官網共 {len(shop_products)} 件(所有 vendor)")

    candidates = [
        sp for sp in shop_products
        if sp.get("vendor") in SELECTED_VENDORS and sp["handle"] not in existing_handles
    ]
    print(f"選定範圍({', '.join(sorted(SELECTED_VENDORS))})內,待新增 {len(candidates)} 件")

    ts = int(time.time() * 1000)
    added = 0
    skipped_no_price = 0
    for idx, sp in enumerate(candidates):
        card = build_card(sp, ts, idx)
        if card["jpy"] <= 0:
            skipped_no_price += 1
            continue
        products.append(card)
        added += 1
        if added % 200 == 0:
            print(f"  已處理 {added}/{len(candidates)}")

    print(f"新增 {added} 件,{skipped_no_price} 件因為抓不到價格略過")
    db.reference(PRODUCTS_PATH).set(products)
    print("已寫回 Firebase,完成!")

    db.reference(PRODUCTS_INDEX_PATH).set(build_products_index(products))
    print("索引已更新,完成!")


if __name__ == "__main__":
    main()
