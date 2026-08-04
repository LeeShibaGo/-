# -*- coding: utf-8 -*-
"""每日庫存 + 價格同步
------------------------------------------------------------
用途:
  網站上這幾個品牌商品的尺寸庫存,原本只是上架當下抓的快照,
  官網賣掉或補貨都不會反映。這支程式每天由 GitHub Actions 排程執行,
  重新到官網抓一次「每個顏色每個尺寸的庫存」和「目前售價」,
  直接更新 Firebase 上的商品資料,客人看到的缺貨狀態最多只落後一天。

兩種同步方式(2026-07-24 擴大範圍,2026-08-01 加入 GU,2026-08-04 加入 UNIQLO):
  A) 庫存 + 價格都同步(Salomon、On、Onitsuka Tiger、BAPE、GU、UNIQLO):
     這幾家官網的商品頁(或 API)本身就會把「每個顏色每個尺寸」的完整
     庫存用靜態資料吐出來,可以做到跟客人在網站上看到的一樣即時。
     UNIQLO 跟 GU 同屬 Fast Retailing,共用同一套 commerce API,
     邏輯直接照搬 sync_gu(見 sync_uniqlo)。手動拼出來的 UNIQLO x
     NEEDLES 聯名開襟外套(見 UNIQLO_MANUAL_SKIP_IDS)不在此列,原因是
     它的三個顏色橫跨兩個不同官網商品代碼,自動同步的話會抓不到正確
     顏色,要排除。
  B) 只同步價格(AAPE、Lacoste、J.Lindeberg、DESCENTE):
     這幾家的尺寸庫存是點了才用 AJAX 動態載入,静態頁面抓不到,沒辦法
     做庫存同步;但目前售價都能從靜態頁面(JSON-LD 或固定 CSS class)
     直接讀到,所以至少把價格這塊做到自動更新 + LINE 通知,不用像以前
     的 price_watch.py 只通知、不會自動改價。
  以下品牌目前技術上做不到自動追蹤,原因各不相同,不會用繞過偵測的
  方式硬做:
  - HONMA:售價是頁面載入後才用 JS 動態渲染,靜態抓不到數字。
  - TaylorMade:官網有 DataDome 機器人偵測,會被導到驗證頁。
  - Dior、Dior 日本限定、Louis Vuitton:官網對非瀏覽器的請求直接回
    HTTP 403。
  - MUSINSA、Nike、零食伴手禮:這些是手動加的參考商品,沒有官網連結
    可以查價。

比對方式:
  商品顏色名稱在網站上已翻成中文,沒辦法拿名字對照官網,
  所以用「顏色圖片的網址」當對照鍵(BAPE 例外,見下方 sync_bape 說明):
  - Salomon:Shopify 圖片檔名(去掉 ?v= 版本參數)
  - On:Contentful 圖片網址裡的 asset id(路徑第二段)
  - Onitsuka Tiger:asics.scene7.com 圖片網址裡的貨號(SKU)
  圖片對不到的顏色(官網下架該配色)一律把庫存歸零,不刪資料。

寫回 Firebase 的方式(2026-07-21 修正):
  每個品牌同步完自己的商品後,會呼叫 merge_and_save() 重新抓一次「當下
  最新」的完整清單當基底,只用商品 id 把這次處理過的商品換成新版本,
  不會沿用 main() 一開始那份舊快照整包覆蓋。原因是 On 單獨一次就要跑
  40 分鐘以上,加上 price_watch.py,整個排程常常跑 2 小時以上,如果全程
  共用同一份記憶體、只在最後整包寫回,執行期間只要有人從別的地方(例如
  上架新品牌)也寫入 Firebase,較晚完成的寫入就會用舊快照蓋掉那些變動
  ——DESCENTE 剛上架的 1240 件商品就這樣被蓋掉重來過一次。

執行方式:
  python sync_stock.py            # 全部品牌都跑
  python sync_stock.py salomon    # 只跑 Salomon(快,測試用)
  python sync_stock.py onitsuka   # 只跑 Onitsuka Tiger
  python sync_stock.py bape       # 只跑 BAPE
  python sync_stock.py aape       # 只跑 AAPE(只同步價格)
  python sync_stock.py lacoste    # 只跑 Lacoste(只同步價格)
  python sync_stock.py jlindeberg # 只跑 J.Lindeberg(只同步價格)
  python sync_stock.py descente   # 只跑 DESCENTE(只同步價格)
  python sync_stock.py gu         # 只跑 GU
  python sync_stock.py uniqlo     # 只跑 UNIQLO
  python sync_stock.py uha        # 只跑 UHA
  python sync_stock.py dhc        # 只跑 DHC
"""

import json
import os
import re
import sys
import time

import requests
import firebase_admin
from firebase_admin import credentials, db

from scrape_on_full import extract_ldjson, extract_size_stock, fix_size_key
from scrape_onitsuka import ENDPOINT as ONITSUKA_ENDPOINT, HEADERS as ONITSUKA_HEADERS, QUERY as ONITSUKA_QUERY

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
price_change_lines = []  # 這次同步中所有官網價格變動,結束後彙整成一則 LINE 通知
delisted_lines = []  # 這次同步中新發現官網 404(已下架)、剛標記缺貨的商品


def send_line(message):
    if not LINE_CHANNEL_ACCESS_TOKEN:
        print("[提示] 未設定 LINE_CHANNEL_ACCESS_TOKEN,價格變動摘要只印出不發送")
        return
    res = requests.post(
        "https://api.line.me/v2/bot/message/broadcast",
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"},
        json={"messages": [{"type": "text", "text": message[:4900]}]},
        timeout=15,
    )
    if res.status_code != 200:
        print(f"[錯誤] LINE 發送失敗:{res.status_code} {res.text}")

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

FIREBASE_DB_URL = "https://shibago-4dd3c-default-rtdb.asia-southeast1.firebasedatabase.app"
PRODUCTS_PATH = "daigou-products-v1"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
ON_BASE = "https://www.on.com"


def fetch(url, retries=4, timeout=30):
    for attempt in range(retries):
        try:
            res = requests.get(url, headers=HEADERS, timeout=timeout)
            res.raise_for_status()
            return res
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(4 * (attempt + 1))


# 2026-08-01 起改用 Firebase Admin SDK(服務帳號金鑰)讀寫商品資料,不再用
# 沒有驗證的 REST 端點直接 GET/PUT——資料庫規則鎖起來之後,只有這個身分
# (連同瀏覽器上真正登入的老闆)可以寫入,其他匿名請求會被拒絕。
# 金鑰路徑由 GOOGLE_APPLICATION_CREDENTIALS 環境變數指定
# (GitHub Actions 裡由 workflow 從 FIREBASE_SERVICE_ACCOUNT_KEY 這個
# secret 寫成暫存檔、再設定這個環境變數,見 .github/workflows/*.yml)。
_firebase_app = None


def firebase_app():
    global _firebase_app
    if _firebase_app is None:
        cred = credentials.ApplicationDefault()
        _firebase_app = firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DB_URL})
    return _firebase_app


def load_products():
    firebase_app()
    data = db.reference(PRODUCTS_PATH).get()
    items = data if isinstance(data, list) else list((data or {}).values())
    return [p for p in items if p]


def save_products(items):
    firebase_app()
    db.reference(PRODUCTS_PATH).set(items)
    print("Firebase 已更新(Admin SDK)")


def merge_and_save(updated_cards):
    """
    這幾個同步(尤其是 On,單一次要逐頁抓上千個顏色頁面,常常跑超過 40 分鐘)
    如果用「main() 一開始 fetch 一次、全程共用同一份記憶體、最後才整包寫回」
    的做法,執行期間只要有人從別的地方(例如手動上架新品牌)也對 Firebase
    寫入,較晚完成的寫入就會用自己開始執行當下的舊快照整包覆蓋過去,把
    中途發生的其他寫入全部抹掉——2026-07-21 就這樣把剛上架的 DESCENTE
    1240 件商品整批蓋掉過一次。

    修法:每個品牌的同步做完自己的事之後,不要沿用舊快照,而是在真正要
    寫回之前重新抓一次「當下最新」的完整清單當基底,只用 id 把這次同步
    處理過的商品換成新版本,其他商品(不管是哪個品牌、是不是這次執行期間
    才被別人加進去的)原封不動保留,寫回的時間差從「整支程式跑多久」
    縮短成「重新抓一次 Firebase 要多久」,幾乎不會再跟其他寫入互相覆蓋。
    """
    fresh = load_products()
    updated_by_id = {c["id"]: c for c in updated_cards if c.get("id")}
    seen_ids = set()
    merged = []
    for p in fresh:
        pid = p.get("id")
        seen_ids.add(pid)
        merged.append(updated_by_id.get(pid, p))
    # 這幾支同步只更新既有商品,理論上不會出現「fresh 裡找不到的 id」,
    # 但保險起見,萬一真的發生就把它補進去,不要憑空遺失資料。
    merged.extend(c for c in updated_cards if c.get("id") not in seen_ids)
    save_products(merged)


# ---------- Salomon ----------

def salomon_image_key(url):
    # Shopify 圖片網址的 ?v= 版本參數會變,拿掉之後用檔名當對照鍵
    return (url or "").split("?")[0].rsplit("/", 1)[-1]


def sync_salomon(items):
    print("=== Salomon 同步開始 ===")
    shop_products = []
    page = 1
    while page <= 30:
        ps = fetch(f"https://salomon.jp/products.json?limit=250&page={page}").json().get("products", [])
        shop_products.extend(ps)
        if len(ps) < 250:
            break
        page += 1
        time.sleep(1.5)
    print(f"官網商品共 {len(shop_products)} 件")

    by_image = {}
    for sp in shop_products:
        for img in sp.get("images", []):
            by_image[salomon_image_key(img.get("src"))] = sp

    cards = [p for p in items if p.get("brand") == "Salomon"]
    stock_changed = price_changed = colors_gone = 0
    for card in cards:
        new_jpy = None
        for ci, color in enumerate(card.get("colors", [])):
            sp = by_image.get(salomon_image_key(color.get("image")))
            if not sp or not sp.get("variants"):
                if any(v > 0 for v in (color.get("stock") or {}).values()):
                    colors_gone += 1
                color["stock"] = {s: 0 for s in color.get("sizes", [])}
                continue
            sizes, stock = [], {}
            for v in sp["variants"]:
                s = fix_size_key((v.get("option2") or v.get("option1") or "").strip())
                if not s or s in stock:
                    continue
                sizes.append(s)
                stock[s] = 5 if v.get("available") else 0
            if stock != (color.get("stock") or {}):
                stock_changed += 1
            color["sizes"], color["stock"] = sizes, stock
            if ci == 0:
                try:
                    new_jpy = int(float(sp["variants"][0]["price"]))
                except (KeyError, ValueError, TypeError):
                    new_jpy = None
        if new_jpy and new_jpy != card.get("jpy"):
            print(f"  價格變動:{card.get('name')} ¥{card.get('jpy')} → ¥{new_jpy}")
            price_change_lines.append(f"[Salomon] {card.get('name')}:¥{card.get('jpy'):,} → ¥{new_jpy:,}")
            card["jpy"] = new_jpy
            price_changed += 1
    print(f"Salomon 完成:{len(cards)} 張卡,庫存有變 {stock_changed} 個顏色,"
          f"價格變動 {price_changed} 件,配色已下架 {colors_gone} 個")
    merge_and_save(cards)


# ---------- On ----------

def on_image_key(url):
    # Contentful 圖片網址:images.ctfassets.net/<space>/<assetId>/<hash>/<檔名>
    m = re.search(r"ctfassets\.net/[^/]+/([^/]+)/", url or "")
    return m.group(1) if m else (url or "")


def sync_on(items):
    print("=== On 同步開始 ===")
    cards = [p for p in items if p.get("brand") == "On"]
    stock_changed = price_changed = errors = 0
    for idx, card in enumerate(cards):
        link = card.get("link")
        if not link:
            continue
        try:
            html = fetch(link, timeout=25).text
            time.sleep(0.4)
        except Exception as e:
            print(f"  [{idx+1}/{len(cards)}] 抓取失敗:{card.get('name')} ({e})")
            errors += 1
            continue
        group, _ = extract_ldjson(html)
        if not group:
            errors += 1
            continue
        variants = group.get("hasVariant", [])
        by_asset = {}
        for v in variants:
            img = v.get("image")
            img = img[0] if isinstance(img, list) else img
            by_asset[on_image_key(img)] = v

        new_jpy = None
        for v in variants:
            offer = v.get("offers", {})
            if offer.get("price"):
                try:
                    new_jpy = int(float(offer["price"]))
                except (ValueError, TypeError):
                    pass
                break
        if new_jpy and new_jpy != card.get("jpy"):
            print(f"  價格變動:{card.get('name')} ¥{card.get('jpy')} → ¥{new_jpy}")
            price_change_lines.append(f"[On] {card.get('name')}:¥{card.get('jpy'):,} → ¥{new_jpy:,}")
            card["jpy"] = new_jpy
            price_changed += 1

        for color in card.get("colors", []):
            v = by_asset.get(on_image_key(color.get("image")))
            if not v:
                color["stock"] = {s: 0 for s in color.get("sizes", [])}
                continue
            offer = v.get("offers", {})
            color_url = offer.get("url", "")
            full_url = color_url if color_url.startswith("http") else ON_BASE + color_url
            try:
                sizes_stock = extract_size_stock(fetch(full_url, timeout=25).text)
                time.sleep(0.4)
            except Exception:
                continue  # 單一顏色抓失敗就先保留舊資料,下次再更新
            if not sizes_stock:
                continue
            if sizes_stock != (color.get("stock") or {}):
                stock_changed += 1
            color["sizes"] = list(sizes_stock.keys())
            color["stock"] = sizes_stock
        if (idx + 1) % 50 == 0:
            print(f"  進度 {idx+1}/{len(cards)}(庫存有變 {stock_changed},錯誤 {errors})")
    print(f"On 完成:{len(cards)} 張卡,庫存有變 {stock_changed} 個顏色,"
          f"價格變動 {price_changed} 件,錯誤 {errors} 件")
    merge_and_save(cards)


# ---------- Onitsuka Tiger ----------

def onitsuka_sku_from_image(url):
    # 圖片網址範例:https://asics.scene7.com/is/image/asics/1183C102_200_SR_RT_GLB?...
    # 檔名開頭的貨號(SKU)跟官網 API 回傳的 sku 欄位是同一組,拿來對照最準。
    m = re.search(r"/asics/([A-Za-z0-9]+_[A-Za-z0-9]+)_", url or "")
    return m.group(1) if m else (url or "")


def onitsuka_fetch_all():
    all_items = []
    page = 1
    while True:
        res = requests.post(
            ONITSUKA_ENDPOINT, headers=ONITSUKA_HEADERS,
            json={"query": ONITSUKA_QUERY, "variables": {"page": page}}, timeout=30,
        )
        res.raise_for_status()
        data = res.json()["data"]["productSearch"]
        all_items.extend(data["items"])
        if page * 100 >= data["total_count"]:
            break
        page += 1
        time.sleep(0.3)
    return [x["productView"] for x in all_items]


def sync_onitsuka(items):
    print("=== Onitsuka Tiger 同步開始 ===")
    fresh = onitsuka_fetch_all()
    print(f"官網商品共 {len(fresh)} 件(每色一筆)")
    by_sku = {p["sku"]: p for p in fresh}

    cards = [p for p in items if p.get("brand") == "Onitsuka Tiger"]
    stock_changed = price_changed = colors_gone = 0
    for card in cards:
        new_jpy = None
        for ci, color in enumerate(card.get("colors", [])):
            sku = onitsuka_sku_from_image(color.get("image"))
            fp = by_sku.get(sku)
            if not fp:
                if any(v > 0 for v in (color.get("stock") or {}).values()):
                    colors_gone += 1
                color["stock"] = {s: 0 for s in color.get("sizes", [])}
                continue
            size_opt = next((o for o in (fp.get("options") or []) if o["id"] == "size"), None)
            sizes, stock = [], {}
            if size_opt:
                for v in size_opt["values"]:
                    label = fix_size_key(v["title"])
                    if label in stock:
                        continue
                    sizes.append(label)
                    stock[label] = 5 if v.get("inStock") else 0
            if sizes and stock != (color.get("stock") or {}):
                stock_changed += 1
            if sizes:
                color["sizes"], color["stock"] = sizes, stock
            if ci == 0:
                pr = (fp.get("priceRange") or {}).get("minimum", {}).get("final", {}).get("amount", {}).get("value")
                if pr:
                    new_jpy = int(pr)
        if new_jpy and new_jpy != card.get("jpy"):
            print(f"  價格變動:{card.get('name')} ¥{card.get('jpy')} → ¥{new_jpy}")
            price_change_lines.append(f"[Onitsuka Tiger] {card.get('name')}:¥{card.get('jpy'):,} → ¥{new_jpy:,}")
            card["jpy"] = new_jpy
            price_changed += 1
    print(f"Onitsuka Tiger 完成:{len(cards)} 張卡,庫存有變 {stock_changed} 個顏色,"
          f"價格變動 {price_changed} 件,配色已下架 {colors_gone} 個")
    merge_and_save(cards)


# ---------- BAPE(jp.bape.com,Shopify)----------

# 顏色代碼對照,跟原本上架用的 _bape_import.py 是同一份(該檔上架完就照慣例刪掉了,
# 這裡重新內嵌一份,同步時才能把官網顏色代碼轉成中文名稱去對照卡片上既有的顏色)。
BAPE_COLOR_SIMPLE = {
    "BLACK": "黑色", "WHITE": "白色", "GREEN": "綠色", "PINK": "粉紅色", "BLUE": "藍色", "NAVY": "深藍",
    "YELLOW": "黃色", "GRAY": "灰色", "RED": "紅色", "PURPLE": "紫色", "BROWN": "棕色", "BEIGE": "米色",
    "SILVER": "銀色", "OLIVEDRAB": "橄欖綠", "MULTI": "多色", "IVORY": "象牙白", "ORANGE": "橘色",
    "INDIGO": "靛藍", "LIGHTINDI": "淺靛藍", "CHARCOAL": "炭灰色", "GOLD": "金色", "BURGUNDY": "酒紅色",
    "CLEAR": "透明", "LIGHTGREEN": "淺綠色", "SAX": "天藍色",
}
BAPE_COLOR_CODE2 = {
    "WH": "白", "BK": "黑", "GR": "綠", "PK": "粉紅", "BL": "藍", "NY": "深藍", "YE": "黃", "PP": "紫",
    "RD": "紅", "OR": "橘", "SX": "天藍", "ML": "多色", "BW": "黑白", "OD": "橄欖綠", "BG": "米",
    "GD": "金", "SV": "銀", "GY": "灰",
}


def bape_translate_color(name):
    if name in BAPE_COLOR_SIMPLE:
        return BAPE_COLOR_SIMPLE[name]
    if len(name) == 5 and name[2] == "X":
        c1, c2 = name[:2], name[3:5]
        if c1 in BAPE_COLOR_CODE2 and c2 in BAPE_COLOR_CODE2:
            return f"{BAPE_COLOR_CODE2[c1]}x{BAPE_COLOR_CODE2[c2]}"
    return name


def bape_handle_from_link(link):
    return (link or "").rstrip("/").rsplit("/", 1)[-1]


def sync_bape(items):
    print("=== BAPE 同步開始 ===")
    shop_products = []
    page = 1
    while True:
        ps = fetch(f"https://jp.bape.com/products.json?limit=250&page={page}").json().get("products", [])
        shop_products.extend(ps)
        if len(ps) < 250:
            break
        page += 1
        time.sleep(0.8)
    print(f"官網商品共 {len(shop_products)} 件(所有 vendor)")
    by_handle = {p["handle"]: p for p in shop_products}

    cards = [p for p in items if p.get("brand") == "BAPE"]
    stock_changed = price_changed = colors_gone = 0
    for card in cards:
        sp = by_handle.get(bape_handle_from_link(card.get("link")))
        if not sp or not sp.get("variants"):
            for color in card.get("colors", []):
                if any(v > 0 for v in (color.get("stock") or {}).values()):
                    colors_gone += 1
                color["stock"] = {s: 0 for s in color.get("sizes", [])}
            continue

        by_raw_color = {}
        for v in sp["variants"]:
            raw = (v.get("option1") or "").strip()
            by_raw_color.setdefault(raw, []).append(v)
        # 同一個中文譯名如果對應到不只一種官網代碼(理論上不該發生,translate_color
        # 是固定對照表),用第一個代碼為準就好,不用太講究。
        by_translated_name = {}
        for raw in by_raw_color:
            by_translated_name.setdefault(bape_translate_color(raw), raw)

        for color in card.get("colors", []):
            raw = by_translated_name.get(color.get("name"))
            variants = by_raw_color.get(raw) if raw else None
            if not variants:
                if any(v > 0 for v in (color.get("stock") or {}).values()):
                    colors_gone += 1
                color["stock"] = {s: 0 for s in color.get("sizes", [])}
                continue
            sizes, stock = [], {}
            for v in variants:
                s = fix_size_key((v.get("option2") or "").strip())
                if not s or s in stock:
                    continue
                sizes.append(s)
                stock[s] = 5 if v.get("available") else 0
            if stock != (color.get("stock") or {}):
                stock_changed += 1
            color["sizes"], color["stock"] = sizes, stock

        try:
            new_jpy = int(float(sp["variants"][0]["price"]))
        except (KeyError, ValueError, TypeError):
            new_jpy = None
        if new_jpy and new_jpy != card.get("jpy"):
            print(f"  價格變動:{card.get('name')} ¥{card.get('jpy')} → ¥{new_jpy}")
            price_change_lines.append(f"[BAPE] {card.get('name')}:¥{card.get('jpy'):,} → ¥{new_jpy:,}")
            card["jpy"] = new_jpy
            price_changed += 1
    print(f"BAPE 完成:{len(cards)} 張卡,庫存有變 {stock_changed} 個顏色,"
          f"價格變動 {price_changed} 件,配色已下架 {colors_gone} 個")
    merge_and_save(cards)


# ---------- 只追價格的品牌(AAPE / Lacoste / J.Lindeberg / DESCENTE)----------
#
# 這幾個網站的商品頁不會像 Shopify 那樣把「每個顏色每個尺寸」的完整庫存
# 用靜態資料吐出來(尺寸庫存都是點了才用 AJAX 動態載入),沒辦法像
# Salomon/BAPE 那樣做到「每個顏色每個尺寸」的庫存同步。但商品目前的
# 售價都能從靜態頁面直接讀到,所以至少把「價格」這塊做到跟 Salomon/On/
# Onitsuka 一樣:每天自動比對、有變動就直接更新 Firebase 上的售價,
# 並且發 LINE 通知,不用像以前的 price_watch.py 只通知、不會自動改價。

_LDJSON_RE = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.DOTALL)


def extract_ldjson_price(html):
    for block in _LDJSON_RE.findall(html):
        if '"@type":"Product"' in block or '"@type": "Product"' in block:
            m = re.search(r'"price"\s*:\s*"?(\d+(?:\.\d+)?)"?', block)
            if m:
                return float(m.group(1))
    return None


def extract_aape_price(html):
    # 官網結構(ebisumart)確認過:.price-entity 這個 class 在商品頁只會出現
    # 一次、對應到當前這件商品,不會跟其他推薦商品的價格混在一起。
    m = re.search(r'class="price-entity[^"]*">\s*([\d,]+)', html)
    return float(m.group(1).replace(",", "")) if m else None


def fetch_or_none_if_404(url, retries=4, timeout=30):
    """跟 fetch() 一樣會重試暫時性錯誤,但 404 例外:代表商品在官網已經
    真的下架了,重試不會讓一個不存在的網址變回 200,直接回傳 None 讓
    呼叫端把它標記成缺貨,不要當成普通的讀取失敗浪費時間重試。"""
    for attempt in range(retries):
        try:
            res = requests.get(url, headers=HEADERS, timeout=timeout)
            if res.status_code == 404:
                return None
            res.raise_for_status()
            return res
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(4 * (attempt + 1))


def mark_all_sold_out(card):
    for color in card.get("colors", []):
        color["stock"] = {s: 0 for s in color.get("sizes", [])}


def sync_price_only(items, brand, extractor):
    print(f"=== {brand} 價格同步開始 ===")
    cards = [p for p in items if p.get("brand") == brand]
    changed = errors = delisted = 0
    for idx, card in enumerate(cards):
        link = card.get("link")
        if not link:
            continue
        try:
            res = fetch_or_none_if_404(link, timeout=25)
            time.sleep(0.4)
        except Exception as e:
            print(f"  [{idx+1}/{len(cards)}] 抓取失敗:{card.get('name')} ({e})")
            errors += 1
            continue
        if res is None:
            # 官網 404,商品已下架。之前的做法是整個略過,結果客人在網站
            # 上還是看得到、點得到「現貨」的商品,但連到官網的連結其實
            # 已經失效——這裡改成跟 Salomon/BAPE 對不到商品時一樣的做法,
            # 把所有顏色的庫存都歸零,不刪資料,網站上會自動顯示缺貨。
            if any(v > 0 for color in card.get("colors", []) for v in (color.get("stock") or {}).values()):
                mark_all_sold_out(card)
                delisted += 1
                print(f"  官網已下架(404):{card.get('name')},已標記全面缺貨")
                delisted_lines.append(f"[{brand}] {card.get('name')}")
            continue
        new_jpy = extractor(res.text)
        if new_jpy and int(new_jpy) != card.get("jpy"):
            new_jpy = int(new_jpy)
            print(f"  價格變動:{card.get('name')} ¥{card.get('jpy')} → ¥{new_jpy}")
            price_change_lines.append(f"[{brand}] {card.get('name')}:¥{card.get('jpy'):,} → ¥{new_jpy:,}")
            card["jpy"] = new_jpy
            changed += 1
        if (idx + 1) % 200 == 0:
            print(f"  進度 {idx+1}/{len(cards)}(價格變動 {changed},新標記下架 {delisted},讀取失敗 {errors})")
    print(f"{brand} 完成:{len(cards)} 張卡,價格變動 {changed} 件,新標記下架 {delisted} 件,讀取失敗 {errors} 件")
    merge_and_save(cards)


# ---------- HONMA(價格是頁面載入後才用 JS 算出來,一般 HTTP 請求抓不到,
# 要用真的瀏覽器把 JS 跑完再讀畫面上顯示的價格;跟其他品牌不同,只有這支
# 需要 playwright,所以在函式內才 import,沒有要跑 HONMA 的話不需要裝這個套件)----------

def extract_honma_price(page):
    # .item-price 這個 class 確認過同一頁只會出現「自己這件商品」的價格
    # (可能重複兩次,一次含税、一次不含,數字一樣),不會混到其他商品。
    # 顯示格式可能是單一價格,也可能是「¥ 137,500 ～ ¥ 170,500」這種
    # 依配置(桿身等)而變動的區間,抓區間裡最低的那個當作基準價。
    el = page.locator(".item-price").first
    text = el.text_content(timeout=10000)
    prices = re.findall(r"[\d,]+", text or "")
    if not prices:
        return None
    return int(prices[0].replace(",", ""))


def sync_honma(items):
    print("=== HONMA 價格同步開始(使用瀏覽器渲染 JS)===")
    from playwright.sync_api import sync_playwright

    cards = [p for p in items if p.get("brand") == "HONMA"]
    changed = errors = delisted = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(user_agent=HEADERS["User-Agent"])
        for idx, card in enumerate(cards):
            link = card.get("link")
            if not link:
                continue
            try:
                res = page.goto(link, timeout=30000, wait_until="domcontentloaded")
                if res is not None and res.status == 404:
                    if any(v > 0 for color in card.get("colors", []) for v in (color.get("stock") or {}).values()):
                        mark_all_sold_out(card)
                        delisted += 1
                        print(f"  官網已下架(404):{card.get('name')},已標記全面缺貨")
                        delisted_lines.append(f"[HONMA] {card.get('name')}")
                    continue
                new_jpy = extract_honma_price(page)
            except Exception as e:
                print(f"  [{idx+1}/{len(cards)}] 抓取失敗:{card.get('name')} ({e})")
                errors += 1
                continue
            if new_jpy and new_jpy != card.get("jpy"):
                print(f"  價格變動:{card.get('name')} ¥{card.get('jpy')} → ¥{new_jpy}")
                price_change_lines.append(f"[HONMA] {card.get('name')}:¥{card.get('jpy'):,} → ¥{new_jpy:,}")
                card["jpy"] = new_jpy
                changed += 1
            time.sleep(0.3)
            if (idx + 1) % 50 == 0:
                print(f"  進度 {idx+1}/{len(cards)}(價格變動 {changed},新標記下架 {delisted},讀取失敗 {errors})")
        browser.close()
    print(f"HONMA 完成:{len(cards)} 張卡,價格變動 {changed} 件,新標記下架 {delisted} 件,讀取失敗 {errors} 件")
    merge_and_save(cards)


# ---------- UHA(零食/保健食品,uha-shop.jp) ----------
# 商品沒有顏色/尺寸選項(colors 陣列是空的),所以不是用 Salomon/On 那種
# 「鎖定某個顏色/尺寸」的缺貨標記,而是直接把整張商品卡的 saleType 設成
# "soldout"(前端 buildCardHTML 認得這個值,會直接整張卡顯示缺貨、按鈕
# disable),跟著官網當下的 schema.org availability 自動更新,不用等老闆
# 手動處理。官網 404(整個下架)才發 LINE 通知讓老闆自己決定要不要下架。

def extract_uha_ldjson(html):
    m = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except Exception:
        return None


def sync_uha(items):
    print("=== UHA 同步開始 ===")
    cards = [p for p in items if p.get("brand") == "UHA"]
    changed = errors = delisted = now_oos = 0
    for idx, card in enumerate(cards):
        link = card.get("link")
        if not link:
            continue
        try:
            res = fetch_or_none_if_404(link, timeout=25)
            time.sleep(0.3)
        except Exception as e:
            print(f"  [{idx+1}/{len(cards)}] 抓取失敗:{card.get('name')} ({e})")
            errors += 1
            continue
        if res is None:
            delisted += 1
            print(f"  官網已下架(404):{card.get('name')}")
            delisted_lines.append(f"[UHA] {card.get('name')} 官網已下架(404),請確認是否要手動下架")
            continue

        data = extract_uha_ldjson(res.text)
        if not data:
            errors += 1
            continue
        offers = data.get("offers", {})

        # UHA 商品沒有 colors/尺寸庫存可以追蹤,saleType 直接跟著官網當下的
        # availability 走,缺貨/恢復現貨都會自動反映在網站上,不用等老闆
        # 手動處理(這點跟只發通知、不動商品顯示的 Dior/LV 不一樣)。
        new_sale_type = "soldout" if "OutOfStock" in (offers.get("availability") or "") else "instock"
        if new_sale_type != card.get("saleType"):
            if new_sale_type == "soldout":
                now_oos += 1
            card["saleType"] = new_sale_type

        try:
            new_jpy = int(float(offers.get("price")))
        except (TypeError, ValueError):
            new_jpy = None
        if new_jpy and new_jpy != card.get("jpy"):
            print(f"  價格變動:{card.get('name')} ¥{card.get('jpy')} → ¥{new_jpy}")
            price_change_lines.append(f"[UHA] {card.get('name')}:¥{card.get('jpy'):,} → ¥{new_jpy:,}")
            card["jpy"] = new_jpy
            changed += 1

        if (idx + 1) % 100 == 0:
            print(f"  進度 {idx+1}/{len(cards)}(價格變動 {changed},下架 {delisted},缺貨 {now_oos},錯誤 {errors})")
    print(f"UHA 完成:{len(cards)} 張卡,價格變動 {changed} 件,下架 {delisted} 件,"
          f"官網缺貨 {now_oos} 件,錯誤 {errors} 件")
    merge_and_save(cards)


# ---------- DHC(健康食品分類,dhc.co.jp) ----------
# 跟 UHA 同一套做法(商品沒有 colors,saleType 直接跟著官網 availability 走)。

def extract_dhc_ldjson(html):
    m = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except Exception:
        return None


# 特價商品(例如「WEB限定」組合包)官網會多顯示一個劃線原價,已經是稅込價,
# 邏輯跟 scrape_dhc.py 的 ORIG_PRICE_RE 一致。
DHC_ORIG_PRICE_RE = re.compile(r'class="c-price-delete">\s*<span class="d-inline-block">\s*([\d,]+)')


def sync_dhc(items):
    print("=== DHC 同步開始 ===")
    cards = [p for p in items if p.get("brand") == "DHC"]
    changed = errors = delisted = now_oos = 0
    for idx, card in enumerate(cards):
        link = card.get("link")
        if not link:
            continue
        try:
            res = fetch_or_none_if_404(link, timeout=25)
            time.sleep(0.3)
        except Exception as e:
            print(f"  [{idx+1}/{len(cards)}] 抓取失敗:{card.get('name')} ({e})")
            errors += 1
            continue
        if res is None:
            delisted += 1
            print(f"  官網已下架(404):{card.get('name')}")
            delisted_lines.append(f"[DHC] {card.get('name')} 官網已下架(404),請確認是否要手動下架")
            continue

        data = extract_dhc_ldjson(res.text)
        if not data:
            errors += 1
            continue
        offers = data.get("offers", {})

        new_sale_type = "soldout" if "OutOfStock" in (offers.get("availability") or "") else "instock"
        if new_sale_type != card.get("saleType"):
            if new_sale_type == "soldout":
                now_oos += 1
            card["saleType"] = new_sale_type

        try:
            # JSON-LD 的 price 是未稅價,要乘上 1.08 換算成官網實際顯示的稅込價
            # (跟 scrape_dhc.py 的換算邏輯一致,理由見該檔案的註解)
            new_jpy = round(float(offers.get("price")) * 1.08)
        except (TypeError, ValueError):
            new_jpy = None
        if new_jpy and new_jpy != card.get("jpy"):
            print(f"  價格變動:{card.get('name')} ¥{card.get('jpy')} → ¥{new_jpy}")
            price_change_lines.append(f"[DHC] {card.get('name')}:¥{card.get('jpy'):,} → ¥{new_jpy:,}")
            card["jpy"] = new_jpy
            changed += 1

        orig_match = DHC_ORIG_PRICE_RE.search(res.text)
        orig_jpy = int(orig_match.group(1).replace(",", "")) if orig_match else None
        if orig_jpy and orig_jpy > card.get("jpy", 0):
            card["origJpy"] = orig_jpy
        elif card.get("origJpy") is not None:
            # 特價活動結束、或原價現在跟現價一樣了,把劃線價拿掉
            card.pop("origJpy", None)

        if (idx + 1) % 100 == 0:
            print(f"  進度 {idx+1}/{len(cards)}(價格變動 {changed},下架 {delisted},缺貨 {now_oos},錯誤 {errors})")
    print(f"DHC 完成:{len(cards)} 張卡,價格變動 {changed} 件,下架 {delisted} 件,"
          f"官網缺貨 {now_oos} 件,錯誤 {errors} 件")
    merge_and_save(cards)


# ---------- GU ----------
# GU 跟 Salomon/On/Onitsuka 一樣做「庫存+價格都同步」,細節見 scrape_gu.py
# 開頭的說明(GU 是 Fast Retailing 集團的公開 API,沒有機器人偵測,
# 用 productId 直接打 detail API 就能拿到最新的每個顏色+尺寸庫存跟價格,
# 不像 On/Onitsuka 需要重新抓 HTML 頁面)。

GU_API = "https://www.gu-global.com/jp/api/commerce/v5/ja/products"
UNIQLO_API = "https://www.uniqlo.com/jp/api/commerce/v5/ja/products"
# 這件是手動拼出來的商品(灰色/米白色用 E483980-000,黑紫色其實是另一個
# 款式代碼 E484125-000 的條紋款,見 fix_needles_images.py 說明),link 欄位
# 只能指到其中一個商品代碼,自動同步會抓不到黑紫色、也會把顏色名稱換成
# 官網日文名稱蓋掉我們手動翻好的中文——這件要排除,不能跟其他 UNIQLO
# 商品一起自動同步。
UNIQLO_MANUAL_SKIP_IDS = {"p_uniqlo_needles_1785655033387_1"}


def gu_product_id_from_link(link):
    m = re.search(r"/products/([^/]+)/", link or "")
    return m.group(1) if m else None


def sync_gu(items):
    print("=== GU 同步開始 ===")
    cards = [p for p in items if p.get("brand") == "GU"]
    stock_changed = price_changed = errors = 0
    for idx, card in enumerate(cards):
        pid = gu_product_id_from_link(card.get("link"))
        if not pid:
            errors += 1
            continue
        try:
            data = fetch(f"{GU_API}/{pid}?withPrices=true&withStocks=true&httpFailure=true", timeout=20).json()
        except Exception as e:
            print(f"  [{idx+1}/{len(cards)}] 抓取失敗:{card.get('name')} ({e})")
            errors += 1
            continue

        if data.get("status") != "ok":
            # 商品在官網已經下架(通常是 302/404),全部標成缺貨,不刪除商品本身
            if any(v > 0 for c in card.get("colors", []) for v in (c.get("stock") or {}).values()):
                stock_changed += 1
                delisted_lines.append(f"[GU] {card.get('name')} 官網已下架,標記全面缺貨")
            for color in card.get("colors", []):
                color["stock"] = {s: 0 for s in color.get("sizes", [])}
            time.sleep(0.3)
            continue

        by_color = {}
        new_jpy = None
        for l2 in data.get("result", {}).get("l2s", []):
            color = l2.get("color") or {}
            color_name = color.get("name") or color.get("displayCode") or "-"
            size_key = fix_size_key((l2.get("size") or {}).get("name") or "-")
            entry = by_color.setdefault(color_name, {"name": color_name, "sizes": [], "stock": {}})
            if size_key not in entry["stock"]:
                entry["sizes"].append(size_key)
            entry["stock"][size_key] = max(entry["stock"].get(size_key, 0), 1 if l2.get("sales") else 0)
            if new_jpy is None:
                price_val = (l2.get("prices") or {}).get("base", {}).get("value")
                if price_val:
                    new_jpy = price_val
        if not by_color:
            errors += 1
            continue

        # detail API 不會回傳圖片網址,沿用原本每個顏色已經存好的圖片
        old_images = {c.get("name"): c.get("image") for c in card.get("colors", []) if c.get("image")}
        new_colors = list(by_color.values())
        for c in new_colors:
            if c["name"] in old_images:
                c["image"] = old_images[c["name"]]
        if new_colors != card.get("colors"):
            stock_changed += 1
        card["colors"] = new_colors

        if new_jpy and new_jpy != card.get("jpy"):
            print(f"  價格變動:{card.get('name')} ¥{card.get('jpy')} → ¥{new_jpy}")
            price_change_lines.append(f"[GU] {card.get('name')}:¥{card.get('jpy'):,} → ¥{new_jpy:,}")
            card["jpy"] = new_jpy
            price_changed += 1

        time.sleep(0.3)
        if (idx + 1) % 100 == 0:
            print(f"  進度 {idx+1}/{len(cards)}(庫存有變 {stock_changed},價格變動 {price_changed},錯誤 {errors})")
    print(f"GU 完成:{len(cards)} 張卡,庫存有變 {stock_changed} 個顏色組合,"
          f"價格變動 {price_changed} 件,錯誤 {errors} 件")
    merge_and_save(cards)


# ---------- UNIQLO(跟 GU 同屬 Fast Retailing,同一套 commerce API,
# 邏輯完全比照 sync_gu,只是換一個 API base)----------

def sync_uniqlo(items):
    print("=== UNIQLO 同步開始 ===")
    cards = [p for p in items if p.get("brand") == "UNIQLO" and p.get("id") not in UNIQLO_MANUAL_SKIP_IDS]
    stock_changed = price_changed = errors = 0
    for idx, card in enumerate(cards):
        pid = gu_product_id_from_link(card.get("link"))
        if not pid:
            errors += 1
            continue
        try:
            data = fetch(f"{UNIQLO_API}/{pid}?withPrices=true&withStocks=true&httpFailure=true", timeout=20).json()
        except Exception as e:
            print(f"  [{idx+1}/{len(cards)}] 抓取失敗:{card.get('name')} ({e})")
            errors += 1
            continue

        if data.get("status") != "ok":
            if any(v > 0 for c in card.get("colors", []) for v in (c.get("stock") or {}).values()):
                stock_changed += 1
                delisted_lines.append(f"[UNIQLO] {card.get('name')} 官網已下架,標記全面缺貨")
            for color in card.get("colors", []):
                color["stock"] = {s: 0 for s in color.get("sizes", [])}
            time.sleep(0.3)
            continue

        by_color = {}
        new_jpy = None
        for l2 in data.get("result", {}).get("l2s", []):
            color = l2.get("color") or {}
            color_name = color.get("name") or color.get("displayCode") or "-"
            size_key = fix_size_key((l2.get("size") or {}).get("name") or "-")
            entry = by_color.setdefault(color_name, {"name": color_name, "sizes": [], "stock": {}})
            if size_key not in entry["stock"]:
                entry["sizes"].append(size_key)
            entry["stock"][size_key] = max(entry["stock"].get(size_key, 0), 1 if l2.get("sales") else 0)
            if new_jpy is None:
                price_val = (l2.get("prices") or {}).get("base", {}).get("value")
                if price_val:
                    new_jpy = price_val
        if not by_color:
            errors += 1
            continue

        old_images = {c.get("name"): c.get("image") for c in card.get("colors", []) if c.get("image")}
        new_colors = list(by_color.values())
        for c in new_colors:
            if c["name"] in old_images:
                c["image"] = old_images[c["name"]]
        if new_colors != card.get("colors"):
            stock_changed += 1
        card["colors"] = new_colors

        if new_jpy and new_jpy != card.get("jpy"):
            print(f"  價格變動:{card.get('name')} ¥{card.get('jpy')} → ¥{new_jpy}")
            price_change_lines.append(f"[UNIQLO] {card.get('name')}:¥{card.get('jpy'):,} → ¥{new_jpy:,}")
            card["jpy"] = new_jpy
            price_changed += 1

        time.sleep(0.3)
        if (idx + 1) % 100 == 0:
            print(f"  進度 {idx+1}/{len(cards)}(庫存有變 {stock_changed},價格變動 {price_changed},錯誤 {errors})")
    print(f"UNIQLO 完成:{len(cards)} 張卡,庫存有變 {stock_changed} 個顏色組合,"
          f"價格變動 {price_changed} 件,錯誤 {errors} 件")
    merge_and_save(cards)


def main():
    only = sys.argv[1].lower() if len(sys.argv) > 1 else None
    items = load_products()
    # 每支 sync_xxx() 現在會在自己做完事之後,各自重新抓最新資料、合併、
    # 寫回(見 merge_and_save 的說明),不再共用這份 items 到最後才整包寫回,
    # 所以這裡不需要(也不應該)在三支都跑完後再存一次舊快照。
    if only in (None, "salomon"):
        sync_salomon(items)
    if only in (None, "on"):
        sync_on(items)
    if only in (None, "gu"):
        sync_gu(items)
    if only in (None, "uniqlo"):
        sync_uniqlo(items)
    if only in (None, "uha"):
        sync_uha(items)
    if only in (None, "dhc"):
        sync_dhc(items)
    if only in (None, "onitsuka"):
        sync_onitsuka(items)
    if only in (None, "honma"):
        sync_honma(items)
    if only in (None, "bape"):
        sync_bape(items)
    if only in (None, "aape"):
        sync_price_only(items, "AAPE", extract_aape_price)
    if only in (None, "lacoste"):
        sync_price_only(items, "Lacoste", extract_ldjson_price)
    if only in (None, "jlindeberg"):
        sync_price_only(items, "J.Lindeberg", extract_ldjson_price)
    if only in (None, "descente"):
        sync_price_only(items, "DESCENTE", extract_ldjson_price)
    if price_change_lines:
        # 官網改價後網站售價已自動跟著更新,這則通知讓老闆知道動了哪些
        head = f"📋 今日價格同步:共 {len(price_change_lines)} 件官網改價,網站售價已自動更新\n\n"
        send_line(head + "\n".join(price_change_lines[:60]))
    if delisted_lines:
        # 官網 404 的商品已經自動標記全面缺貨,這則通知讓老闆知道是哪幾件,
        # 之後可以自行決定要不要整個下架
        head = f"🚫 今日發現 {len(delisted_lines)} 件商品官網已下架,已自動標記缺貨\n\n"
        send_line(head + "\n".join(delisted_lines[:60]))


if __name__ == "__main__":
    main()
