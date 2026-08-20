# -*- coding: utf-8 -*-
"""每日庫存 + 價格同步
------------------------------------------------------------
用途:
  網站上這幾個品牌商品的尺寸庫存,原本只是上架當下抓的快照,
  官網賣掉或補貨都不會反映。這支程式每天由 GitHub Actions 排程執行,
  重新到官網抓一次「每個顏色每個尺寸的庫存」和「目前售價」,
  直接更新 Firebase 上的商品資料,客人看到的缺貨狀態最多只落後一天。

四種同步方式(2026-07-24 擴大範圍,2026-08-01 加入 GU,2026-08-04 加入 UNIQLO,
2026-08-04 再把 AAPE/Lacoste 升級成真庫存同步、DESCENTE 升級成整體現貨同步,
2026-08-08 加入 STUSSY、CELINE):
  A) 庫存 + 價格都同步(Salomon、On、Onitsuka Tiger、BAPE、STUSSY、CELINE、GU、UNIQLO):
     STUSSY(jp.stussy.com)跟 BAPE 一樣是 Shopify 官方 API,做法直接照搬
     sync_bape(見 sync_stussy),差別只在顏色是英文(White、Faded Black
     這種),用 scrape_stussy.py 的 translate_color() 反查回中文對照。
     CELINE(celine.com/ja-jp,LVMH 集團旗下但跟 Dior/LV 不同,沒有擋
     非瀏覽器請求)是 Salesforce Commerce Cloud 靜態輸出,每個顏色是
     獨立網址,尺寸庫存直接寫在 HTML 裡(缺貨的尺寸 <input> 帶
     class="s-disabled"),見 sync_celine 的說明。
     這幾家官網的商品頁(或 API)本身就會把「每個顏色每個尺寸」的完整
     庫存用靜態資料吐出來,可以做到跟客人在網站上看到的一樣即時。
     UNIQLO 跟 GU 同屬 Fast Retailing,共用同一套 commerce API,
     邏輯直接照搬 sync_gu(見 sync_uniqlo)。手動拼出來的 UNIQLO x
     NEEDLES 聯名開襟外套(見 UNIQLO_MANUAL_SKIP_IDS)不在此列,原因是
     它的三個顏色橫跨兩個不同官網商品代碼,自動同步的話會抓不到正確
     顏色,要排除。
  A') 庫存 + 價格都同步,但顏色/尺寸比對邏輯是各自品牌獨有的(AAPE、Lacoste):
     一開始誤以為這兩家的尺寸庫存要點了才用 AJAX 載入抓不到,實測發現
     其實已經直接寫在靜態網頁裡(AAPE 的 .quantity、Lacoste 商品頁
     __NEXT_DATA__ 裡的 inventoryQuantity),純 requests 就抓得到,
     詳見 sync_aape/sync_lacoste 的說明。
  B) 只同步「整體現貨/缺貨」,不到每個尺寸(DESCENTE):
     尺寸庫存實測確認過是純前端樣板套版,要真的執行 JS 才抓得到,用
     Playwright 渲染頁面後看每個尺寸文字是不是「あり」;但這個品牌
     上架時是每個顏色各自一筆商品(沒有 colors 陣列),所以只做到跟
     UHA/DHC 一樣的整體 saleType,不到每個尺寸,詳見 sync_descente。
  C) 只同步價格(J.Lindeberg):
     尺寸庫存是點了才用 AJAX 動態載入,静態頁面抓不到,沒辦法做庫存
     同步;但目前售價能從靜態頁面(JSON-LD)直接讀到,所以至少把價格
     這塊做到自動更新 + LINE 通知,不用像以前的 price_watch.py 只通知、
     不會自動改價。
  以下品牌目前技術上做不到自動追蹤,原因各不相同,不會用繞過偵測的
  方式硬做:
  - HONMA:售價是頁面載入後才用 JS 動態渲染,靜態抓不到數字(不過這個
    可以用 Playwright 渲染後讀到,見 sync_honma——DESCENTE 也是同樣道理)。
  - TaylorMade:官網有 DataDome 機器人偵測,會被導到驗證頁。
  - Dior、Louis Vuitton:官網對非瀏覽器的請求直接回 HTTP 403(Dior 日本
    限定系列 2026-08-10 併回 Dior,不再是獨立品牌)。
  - Gentle Monster:CloudFront 會偵測「這是自動化瀏覽器」直接回 403,
    純 requests 讀得到但沒有 JS 執行不出商品資料,矛盾的組合導致
    plain requests/真瀏覽器兩種方式都不能用。
  - Rakuten(樂天)賣場:Akamai 邊緣節點直接擋下,回應內容只有一段
    "Reference #..." 代碼,連正常錯誤頁都不會顯示。
  - MUSINSA、Nike、零食伴手禮:這些是手動加的參考商品,沒有官網連結
    可以查價。
  D) 庫存 + 價格都同步,商城平台伺服器端渲染,不需要 Playwright(3COINS):
     3COINS 掛在 PAL CLOSET 商城(palcloset.jp)底下,分類頁預設是 JS
     載入後才灌商品進去,但只要網址加上 mode=zSearch 參數,伺服器就會
     直接把完整商品清單渲染進 HTML 回傳,詳細頁本身也是純伺服器渲染,
     兩邊都純 requests + BeautifulSoup 就能讀到,見 scrape_3coins.py。
     這裡只跑「已上架商品」的每日庫存/價格重新核對,新商品要另外重新
     跑一次 scrape_3coins.py(2026-08-13 老闆確認只抓時尚配件類——包包/
     髮飾/飾品/帽子/錢包小物,不含 3COINS 官網其餘的生活雜貨分類)。

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
  python sync_stock.py stussy     # 只跑 STUSSY
  python sync_stock.py celine     # 只跑 CELINE
  python sync_stock.py aape       # 只跑 AAPE
  python sync_stock.py lacoste    # 只跑 Lacoste
  python sync_stock.py jlindeberg # 只跑 J.Lindeberg(只同步價格)
  python sync_stock.py descente   # 只跑 DESCENTE(只同步整體現貨/缺貨,使用瀏覽器渲染 JS)
  python sync_stock.py gu         # 只跑 GU
  python sync_stock.py uniqlo     # 只跑 UNIQLO
  python sync_stock.py uha        # 只跑 UHA
  python sync_stock.py dhc        # 只跑 DHC
  python sync_stock.py 3coins     # 只跑 3COINS
  python sync_stock.py polene     # 只跑 POLENE
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


def load_products_by_brand(brand):
    """2026-08-16 抓到:main() 一開始的 load_products() 整包讀走全站
    daigou-products-v1(現在 13MB+),但現在 GitHub Actions 是每個品牌
    各自獨立一個 job(見 check-prices.yml 的 matrix),每次呼叫其實只
    需要那一個品牌的資料——加上 merge_and_save() 寫回之前自己還會再
    整包重讀一次(那次是必要的,見它的說明),等於每個品牌的 job 一天
    要整包讀兩次資料庫。17 個品牌 x 2 次 x 13MB,一個月加起來快 14GB,
    比免費方案 10GB 的下載額度還多,幾乎是自己同步自己就把額度用完,
    這是資料庫額度爆掉的主因之一,不是只有客人流量的問題。

    改成用 Firebase 的條件查詢(orderBy=brand&equalTo=X,Admin SDK 是
    order_by_child().equal_to(),跟前端 fetchProductsByBrand() 用的是
    同一個 .indexOn:["brand"] 索引)只抓「這個品牌自己」的資料,把
    main() 這一次讀取從整包 13MB 降到那個品牌的份量,一天的同步用量
    直接砍半。merge_and_save() 寫回前的整包重讀不動它,那個是為了避免
    平行跑的品牌互相覆蓋寫入,是必要的安全機制,不能拿掉。
    """
    firebase_app()
    data = db.reference(PRODUCTS_PATH).order_by_child("brand").equal_to(brand).get()
    items = list(data.values()) if isinstance(data, dict) else (data or [])
    return [p for p in items if p]


# CLI 參數(python sync_stock.py <這個>)對應到商品資料裡 brand 欄位的
# 精確字串,main() 用這份對照表在「只跑單一品牌」時改用
# load_products_by_brand() 只抓那個品牌,不用整包抓。
ONLY_ARG_TO_BRAND = {
    "salomon": "Salomon",
    "on": "On",
    "gu": "GU",
    "uniqlo": "UNIQLO",
    "3coins": "3COINS",
    "polene": "POLENE",
    "uha": "UHA",
    "dhc": "DHC",
    "onitsuka": "Onitsuka Tiger",
    "honma": "HONMA",
    "bape": "BAPE",
    "stussy": "STUSSY",
    "celine": "CELINE",
    "aape": "AAPE",
    "lacoste": "Lacoste",
    "jlindeberg": "J.Lindeberg",
    "descente": "DESCENTE",
    "merries": "Merries",
}


def save_products(items):
    firebase_app()
    db.reference(PRODUCTS_PATH).set(items)
    print("Firebase 已更新(Admin SDK)")


# ---------- 精簡版商品索引(daigou-products-index-v1,2026-08-14 加入)----------
# 前端首頁一開,不再整包抓 daigou-products-v1(17,897 件商品、12.5MB,實測
# 光這個請求就要 1.4 秒以上,手機用 LINE 內建瀏覽器+行動網路只會更久,
# 很可能是訪客還沒看到畫面就先關掉的原因)。改抓這份小很多的索引——
# 只留品牌導覽、篩選、分頁、排行榜用得到的欄位,拿掉最重的
# colors(顏色/尺寸/庫存明細/圖片)。真正要畫商品卡(顏色選擇、庫存、
# 圖片)的時候,前端才照品牌或 id 另外查完整資料,見 index.html 的
# fetchProductsByBrand()/fetchProductsByIds()。
#
# tier(精品/運動品牌/潮流品牌/生活選物)、subtypeGroup(上身/褲子/鞋子/
# 包包/配件...)這兩個前端本來就是用 brand/subtype 現查對照表算出來的,
# 不是存在資料庫裡的欄位,索引不用重複存。

PRODUCTS_INDEX_PATH = "daigou-products-index-v1"


def _stock_values(stock):
    """統一處理 Firebase 的怪癖:size 如果剛好是連續數字字串(常見於
    鞋類,例如 "5","7","8","9","10","11"),讀出來的 stock 會被自動轉成
    「陣列」而不是物件,不是存成 {"5":0,"7":8,...} 這種字典——直接呼叫
    .values() 會噴 AttributeError(2026-08-15 實測抓到兩次:AAPE SLIDER
    在 _is_fully_sold_out() 這裡先抓到過一次;3COINS 同步當天又在另一個
    地方——判斷「這件商品官網已下架、要不要標記缺貨通知」的邏輯——用
    同一個沒防到陣列形狀的寫法再爆一次,這支 sync_stock.py 裡原本共有
    16 處都是這個沒有防陣列形狀的寫法,一次全部改用這支函式,不要再
    一個一個抓到才修)。兩種形狀都轉成一份「數值列表」讓呼叫端可以直接
    用 any()/sum() 等,陣列裡的 null 缺口跳過不算。
    """
    if isinstance(stock, dict):
        return stock.values()
    if isinstance(stock, list):
        return [v for v in stock if v is not None]
    return []


def _is_fully_sold_out(p):
    """跟 index.html 的 isFullySoldOut() 邏輯逐行對照,兩邊要保持一致。"""
    sale_type = p.get("saleType") or "instock"
    if sale_type == "preorder":
        return False
    if sale_type == "soldout":
        return True
    colors = p.get("colors")
    if colors:
        for c in colors:
            stock = c.get("stock")
            if not stock:
                return False
            # Firebase 的怪癖:size 如果剛好是連續數字字串(常見於鞋類,
            # 例如 "5","7","8","9","10","11"),讀出來的 stock 會被自動
            # 轉成「陣列」而不是物件(index 0~該數字之間補 null),不是
            # 存成 {"5":0,"7":8,...} 這種字典——這裡兩種形狀都要能處理,
            # 不然會直接噴錯(2026-08-15 實測抓到,AAPE SLIDER 就是這樣)。
            # 前端 JS 那邊因為陣列本來就支援用字串數字當索引存取
            # (stock["5"] 等同 stock[5]),不會有這個問題,只有 Python
            # 這邊的 dict 專用寫法需要另外處理。
            if isinstance(stock, dict):
                sizes = c.get("sizes") or list(stock.keys())
                get_stock = lambda s: stock.get(s) or 0
            elif isinstance(stock, list):
                sizes = c.get("sizes") or [str(i) for i in range(len(stock))]
                def get_stock(s, _stock=stock):
                    try:
                        idx = int(s)
                    except (TypeError, ValueError):
                        return 0
                    return (_stock[idx] or 0) if 0 <= idx < len(_stock) else 0
            else:
                return False
            if not sizes:
                return False
            if any(get_stock(s) > 0 for s in sizes):
                return False
        return True
    return False


def build_products_index(items):
    index = []
    for p in items:
        if not p.get("id"):
            continue
        index.append({
            "id": p["id"],
            "name": p.get("name") or "",
            "brand": p.get("brand"),
            "category": p.get("category"),
            "subtype": p.get("subtype"),
            "series": p.get("series"),
            "jpy": p.get("jpy") or 0,
            "weight": p.get("weight"),
            "country": p.get("country") or "JP",
            "saleType": p.get("saleType") or "instock",
            "hidden": bool(p.get("hidden")),
            "addedAt": p.get("addedAt"),
            "extraSoldQty": p.get("extraSoldQty"),
            "soldOut": _is_fully_sold_out(p),
        })
    return index


def save_products_index(items):
    firebase_app()
    db.reference(PRODUCTS_INDEX_PATH).set(build_products_index(items))
    print(f"索引已更新(Admin SDK,共 {len(items)} 件商品)")


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
    # 每次同步完都用同一份剛合併好的最新清單重建精簡索引,不用再多讀一次
    # Firebase——daily sync 本來就會經過這裡,索引每天自動保持最新,不用
    # 另外寫排程。
    save_products_index(merged)


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
                if any(v > 0 for v in _stock_values(color.get("stock"))):
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
                if any(v > 0 for v in _stock_values(color.get("stock"))):
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


def bape_variant_image(product, variant):
    """variant.featured_image 在部分商品上會是 null(實測確認過,不是每件
    都這樣,原因不明,猜是 Shopify 資料本身的狀況),這種情況下原本的做法
    沒有 fallback,同一個商品的好幾個顏色就會全部抓不到圖片、變成共用
    同一張(通常是第一個顏色的圖)——這就是「BAPE 衣服顏色圖片不會動」
    的原因(2026-08-08 抓到)。修法:featured_image 是 null 的話,改用
    images[] 陣列裡「variant_ids 包含這個 variant id」的那張圖片,這個
    欄位實測兩種情況下都有正確填。"""
    img = variant.get("featured_image")
    if img and img.get("src"):
        return img["src"]
    vid = variant.get("id")
    for image in product.get("images", []):
        if vid in (image.get("variant_ids") or []):
            return image.get("src")
    return None


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
                if any(v > 0 for v in _stock_values(color.get("stock"))):
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
                if any(v > 0 for v in _stock_values(color.get("stock"))):
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
            new_image = bape_variant_image(sp, variants[0])
            if new_image:
                color["image"] = new_image

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


# ---------- STUSSY(2026-08-08 新增,jp.stussy.com,Shopify,做法跟 BAPE
# 幾乎一樣:option1 是顏色(英文),用 scrape_stussy.py 的 translate_color()
# 反查回中文名稱去對照既有 colors[],option2 是尺寸)----------

def stussy_handle_from_link(link):
    return (link or "").rstrip("/").rsplit("/", 1)[-1]


def sync_stussy(items):
    print("=== STUSSY 同步開始 ===")
    from scrape_stussy import translate_color

    shop_products = []
    page = 1
    while True:
        ps = fetch(f"https://jp.stussy.com/products.json?limit=250&page={page}").json().get("products", [])
        shop_products.extend(ps)
        if len(ps) < 250:
            break
        page += 1
        time.sleep(0.6)
    print(f"官網商品共 {len(shop_products)} 件")
    by_handle = {p["handle"]: p for p in shop_products}

    cards = [p for p in items if p.get("brand") == "STUSSY"]
    stock_changed = price_changed = colors_gone = 0
    for card in cards:
        sp = by_handle.get(stussy_handle_from_link(card.get("link")))
        if not sp or not sp.get("variants"):
            for color in card.get("colors", []):
                if any(v > 0 for v in _stock_values(color.get("stock"))):
                    colors_gone += 1
                color["stock"] = {s: 0 for s in color.get("sizes", [])}
            continue

        by_raw_color = {}
        for v in sp["variants"]:
            raw = (v.get("option1") or "").strip()
            by_raw_color.setdefault(raw, []).append(v)
        by_translated_name = {}
        for raw in by_raw_color:
            by_translated_name.setdefault(translate_color(raw), raw)

        for color in card.get("colors", []):
            raw = by_translated_name.get(color.get("name"))
            variants = by_raw_color.get(raw) if raw else None
            if not variants:
                if any(v > 0 for v in _stock_values(color.get("stock"))):
                    colors_gone += 1
                color["stock"] = {s: 0 for s in color.get("sizes", [])}
                continue
            sizes, stock = [], {}
            for v in variants:
                s = fix_size_key((v.get("option2") or "F").strip())
                if not s or s in stock:
                    continue
                sizes.append(s)
                stock[s] = 5 if v.get("available") else 0
            if stock != (color.get("stock") or {}):
                stock_changed += 1
            color["sizes"], color["stock"] = sizes, stock

        try:
            new_jpy = int(float(sp["variants"][0]["price"]))
        except (KeyError, ValueError, TypeError, IndexError):
            new_jpy = None
        if new_jpy and new_jpy != card.get("jpy"):
            print(f"  價格變動:{card.get('name')} ¥{card.get('jpy')} → ¥{new_jpy}")
            price_change_lines.append(f"[STUSSY] {card.get('name')}:¥{card.get('jpy'):,} → ¥{new_jpy:,}")
            card["jpy"] = new_jpy
            price_changed += 1
    print(f"STUSSY 完成:{len(cards)} 張卡,庫存有變 {stock_changed} 個顏色,"
          f"價格變動 {price_changed} 件,配色已下架 {colors_gone} 個")
    merge_and_save(cards)


# ---------- POLENE(jp.polene-paris.com,2026-08-15 加入,包包/皮件品牌)----------
# 跟 STUSSY 一樣是 Shopify 官方 products.json API,但顏色不是同一個商品
# 底下的 variant,而是每個顏色各自獨立一個 Shopify 商品(見
# scrape_polene.py 開頭的說明),所以這裡不用像 sync_stussy 那樣拆
# by_raw_color 再逐色比對,直接用 link 裡的 handle 對到「那一個」Shopify
# 商品、重建它唯一的那組 colors[0] 即可,邏輯簡單很多。

def sync_polene(items):
    print("=== POLENE 同步開始 ===")

    shop_products = []
    page = 1
    while True:
        ps = fetch(f"https://jp.polene-paris.com/products.json?limit=250&page={page}").json().get("products", [])
        shop_products.extend(ps)
        if len(ps) < 250:
            break
        page += 1
        time.sleep(0.6)
    print(f"官網商品共 {len(shop_products)} 件")
    by_handle = {p["handle"]: p for p in shop_products}

    cards = [p for p in items if p.get("brand") == "POLENE"]
    stock_changed = price_changed = errors = 0
    for card in cards:
        sp = by_handle.get(stussy_handle_from_link(card.get("link")))
        if not sp or not sp.get("variants"):
            if any(v > 0 for c in card.get("colors", []) for v in _stock_values(c.get("stock"))):
                stock_changed += 1
                delisted_lines.append(f"[POLENE] {card.get('name')} 官網已下架,標記全面缺貨")
            for color in card.get("colors", []):
                color["stock"] = {s: 0 for s in color.get("sizes", [])}
            continue

        sizes, stock = [], {}
        for v in sp["variants"]:
            raw_title = (v.get("title") or "").strip()
            s = "FREE" if raw_title == "Default Title" else (fix_size_key(raw_title) or "FREE")
            if s not in stock:
                sizes.append(s)
            stock[s] = max(stock.get(s, 0), 5 if v.get("available") else 0)

        if card.get("colors"):
            color = card["colors"][0]
            if stock != (color.get("stock") or {}):
                stock_changed += 1
            color["sizes"], color["stock"] = sizes, stock
        else:
            errors += 1

        try:
            new_jpy = int(float(sp["variants"][0]["price"]))
        except (KeyError, ValueError, TypeError, IndexError):
            new_jpy = None
        if new_jpy and new_jpy != card.get("jpy"):
            print(f"  價格變動:{card.get('name')} ¥{card.get('jpy')} → ¥{new_jpy}")
            price_change_lines.append(f"[POLENE] {card.get('name')}:¥{card.get('jpy'):,} → ¥{new_jpy:,}")
            card["jpy"] = new_jpy
            price_changed += 1

    print(f"POLENE 完成:{len(cards)} 張卡,庫存有變 {stock_changed} 件,"
          f"價格變動 {price_changed} 件,錯誤 {errors} 件")
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
            if any(v > 0 for color in card.get("colors", []) for v in _stock_values(color.get("stock"))):
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


# ---------- AAPE(2026-08-04 從「只同步價格」升級成「庫存+價格都同步」:
# 原本以為尺寸庫存要點了才用 AJAX 載入抓不到,實測發現其實每個顏色每個
# 尺寸的真實庫存件數本來就已經寫在靜態網頁裡(.variation-col-size_stock
# 裡的 .quantity),跟 scrape_aape.py 當初上架時用的抓法一模一樣,
# 顏色名稱翻譯/尺寸代碼標準化直接沿用 scrape_aape.py 裡的對照表,
# 確保新舊資料的顏色/尺寸字串是同一套,不會對不起來)----------

def sync_aape(items):
    print("=== AAPE 同步開始 ===")
    from bs4 import BeautifulSoup
    from urllib.parse import urljoin
    from scrape_aape import translate_color, standardize_size, extract_price_number, BASE_URL as AAPE_BASE

    cards = [p for p in items if p.get("brand") == "AAPE"]
    stock_changed = price_changed = errors = delisted = 0
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
            if any(v > 0 for color in card.get("colors", []) for v in _stock_values(color.get("stock"))):
                mark_all_sold_out(card)
                delisted += 1
                print(f"  官網已下架(404):{card.get('name')},已標記全面缺貨")
                delisted_lines.append(f"[AAPE] {card.get('name')}")
            continue

        new_jpy = extract_aape_price(res.text)
        if new_jpy and int(new_jpy) != card.get("jpy"):
            new_jpy = int(new_jpy)
            print(f"  價格變動:{card.get('name')} ¥{card.get('jpy')} → ¥{new_jpy}")
            price_change_lines.append(f"[AAPE] {card.get('name')}:¥{card.get('jpy'):,} → ¥{new_jpy:,}")
            card["jpy"] = new_jpy
            price_changed += 1

        soup = BeautifulSoup(res.text, "html.parser")
        old_images = {c.get("name"): c.get("image") for c in card.get("colors", []) if c.get("image")}
        new_colors = []
        for row in soup.select(".variation-row"):
            color_el = row.select_one(".variation-row-thumbnail .color")
            color_name_ja = color_el.get_text(strip=True) if color_el else None
            if not color_name_ja:
                continue
            color_name = translate_color(color_name_ja)

            img_el = row.select_one(".variation-row-thumbnail .image img")
            color_image = None
            if img_el and img_el.get("src"):
                color_image = urljoin(AAPE_BASE, img_el["src"]).replace("_d_125.jpg", "_d_240.jpg")

            sizes, stock = [], {}
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
                new_colors.append({
                    "name": color_name, "sizes": sizes, "stock": stock,
                    "image": color_image or old_images.get(color_name),
                })

        if new_colors:
            if new_colors != card.get("colors"):
                stock_changed += 1
            card["colors"] = new_colors

        if (idx + 1) % 100 == 0:
            print(f"  進度 {idx+1}/{len(cards)}(庫存有變 {stock_changed},價格變動 {price_changed},下架 {delisted},錯誤 {errors})")
    print(f"AAPE 完成:{len(cards)} 張卡,庫存有變 {stock_changed} 個顏色組合,"
          f"價格變動 {price_changed} 件,下架 {delisted} 件,錯誤 {errors} 件")
    merge_and_save(cards)


# ---------- Lacoste(2026-08-04 從「只同步價格」升級成「庫存+價格都同步」:
# 商品頁的 __NEXT_DATA__ 裡 variants 陣列每一筆都有 inventoryQuantity
# (真實庫存件數)跟 extraProperties 裡的 JapanSize,不需要額外的 AJAX 請求。
# 用 imageCode(例如 46SMA0008-1R5)當比對鍵,對照既有 colors[].image 網址
# 裡是否包含同一組代碼,找出這是哪個顏色。) ----------

LACOSTE_NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)


def sync_lacoste(items):
    print("=== Lacoste 同步開始 ===")
    cards = [p for p in items if p.get("brand") == "Lacoste"]
    stock_changed = price_changed = errors = delisted = 0
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
            if any(v > 0 for color in card.get("colors", []) for v in _stock_values(color.get("stock"))):
                mark_all_sold_out(card)
                delisted += 1
                print(f"  官網已下架(404):{card.get('name')},已標記全面缺貨")
                delisted_lines.append(f"[Lacoste] {card.get('name')}")
            continue

        new_jpy = extract_ldjson_price(res.text)
        if new_jpy and int(new_jpy) != card.get("jpy"):
            new_jpy = int(new_jpy)
            print(f"  價格變動:{card.get('name')} ¥{card.get('jpy')} → ¥{new_jpy}")
            price_change_lines.append(f"[Lacoste] {card.get('name')}:¥{card.get('jpy'):,} → ¥{new_jpy:,}")
            card["jpy"] = new_jpy
            price_changed += 1

        m = LACOSTE_NEXT_DATA_RE.search(res.text)
        if not m:
            errors += 1
            continue
        try:
            data = json.loads(m.group(1))
            variants = data["props"]["pageProps"]["data"]["productResponse"]["product"]["variants"]
        except Exception:
            errors += 1
            continue

        by_imagecode = {}
        for v in variants:
            code = (v.get("imageCode") or "").lower()
            if code:
                by_imagecode.setdefault(code, []).append(v)

        new_colors = []
        any_color_changed = False
        for color in card.get("colors", []):
            old_stock = dict(color.get("stock") or {})
            img = (color.get("image") or "").lower()
            matched_code = next((c for c in by_imagecode if c in img), None)
            if not matched_code:
                # 官網對不到這個顏色(可能是這款配色下架了),沿用舊尺寸清單但庫存歸零
                color["stock"] = {s: 0 for s in color.get("sizes", [])}
                if color["stock"] != old_stock:
                    any_color_changed = True
                new_colors.append(color)
                continue
            sizes, stock = [], {}
            for v in by_imagecode[matched_code]:
                raw_size = None
                for prop in (v.get("extraProperties") or []):
                    if prop.get("field") == "JapanSize":
                        vals = prop.get("values") or []
                        raw_size = vals[0] if vals else None
                        break
                if not raw_size:
                    continue
                # 沿用初次上架時的字串轉換規則(半形句點/斜線 -> 全形),尺寸字串才會跟舊資料一致
                size_name = raw_size.replace(".", "-").replace("/", "／")
                qty = int(v.get("inventoryQuantity") or 0)
                if size_name not in stock:
                    sizes.append(size_name)
                stock[size_name] = qty
            if stock != old_stock:
                any_color_changed = True
            color["sizes"], color["stock"] = sizes, stock
            new_colors.append(color)

        if any_color_changed:
            stock_changed += 1
        card["colors"] = new_colors

        if (idx + 1) % 100 == 0:
            print(f"  進度 {idx+1}/{len(cards)}(庫存有變 {stock_changed},價格變動 {price_changed},下架 {delisted},錯誤 {errors})")
    print(f"Lacoste 完成:{len(cards)} 張卡,庫存有變 {stock_changed} 個顏色組合,"
          f"價格變動 {price_changed} 件,下架 {delisted} 件,錯誤 {errors} 件")
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
                    if any(v > 0 for color in card.get("colors", []) for v in _stock_values(color.get("stock"))):
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


# ---------- DESCENTE(2026-08-04 從「只同步價格」升級成「同步整體現貨/缺貨」:
# 尺寸庫存實測確認過是純前端 Handlebars 樣板,套版資料要真的執行過 JS 才會
# 填進去,要用瀏覽器渲染,做法跟 HONMA 一樣。
# 這個品牌當初上架時每個顏色是各自一筆商品(沒有 colors 陣列),所以不像
# AAPE/Lacoste 追蹤到「每個尺寸」的庫存,只做到跟 UHA/DHC 一樣的整體
# saleType(這張卡代表的顏色,只要還有任一個尺寸買得到就算現貨,全部尺寸
# 都缺貨才標成 soldout)——尺寸表格每一列的「あり」就是客人看到的現貨文字,
# 直接拿這個文字判斷,不用去猜内部庫存等級代碼的確切命名。) ----------

def sync_descente(items):
    print("=== DESCENTE 同步開始(使用瀏覽器渲染 JS)===")
    from playwright.sync_api import sync_playwright

    cards = [p for p in items if p.get("brand") == "DESCENTE"]
    changed = stock_changed = errors = delisted = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(user_agent=HEADERS["User-Agent"])
        for idx, card in enumerate(cards):
            link = card.get("link")
            if not link:
                continue
            try:
                res = page.goto(link, timeout=30000, wait_until="networkidle")
                if res is not None and res.status == 404:
                    if card.get("saleType") != "soldout":
                        card["saleType"] = "soldout"
                        delisted += 1
                        print(f"  官網已下架(404):{card.get('name')},已標記缺貨")
                        delisted_lines.append(f"[DESCENTE] {card.get('name')}")
                    continue

                new_jpy = None
                price_locator = page.locator("#mrkSalesPrice").first
                if price_locator.count():
                    price_text = price_locator.text_content(timeout=10000) or ""
                    digits = re.sub(r"[^\d]", "", price_text)
                    if digits:
                        new_jpy = int(digits)

                stock_texts = page.eval_on_selector_all(
                    "li[data-sku] .stock", "els => els.map(e => e.textContent)"
                )
            except Exception as e:
                print(f"  [{idx+1}/{len(cards)}] 抓取失敗:{card.get('name')} ({e})")
                errors += 1
                continue

            if new_jpy and new_jpy != card.get("jpy"):
                print(f"  價格變動:{card.get('name')} ¥{card.get('jpy')} → ¥{new_jpy}")
                price_change_lines.append(f"[DESCENTE] {card.get('name')}:¥{card.get('jpy'):,} → ¥{new_jpy:,}")
                card["jpy"] = new_jpy
                changed += 1

            has_stock = any("あり" in (t or "") for t in stock_texts) if stock_texts else True
            new_sale_type = "instock" if has_stock else "soldout"
            if new_sale_type != card.get("saleType", "instock"):
                card["saleType"] = new_sale_type
                stock_changed += 1

            time.sleep(0.3)
            if (idx + 1) % 50 == 0:
                print(f"  進度 {idx+1}/{len(cards)}(價格變動 {changed},缺貨異動 {stock_changed},下架 {delisted},錯誤 {errors})")
        browser.close()
    print(f"DESCENTE 完成:{len(cards)} 張卡,價格變動 {changed} 件,缺貨異動 {stock_changed} 件,下架 {delisted} 件,錯誤 {errors} 件")
    merge_and_save(cards)


# ---------- Merries(メリーズ,2026-08-20 新增。跟 HONMA/DESCENTE 同一個
# 原因需要 Playwright:kao-kirei.com 的價格/庫存是頁面載入後才用 JS 打 API
# 填進去,plain requests 抓到的是 disabled 的 loading 骨架。這個品牌沒有
# 顏色/尺寸選項(每個包裝規格在資料庫裡各自是獨立一筆商品),所以跟
# DESCENTE 一樣只需要同步整體 saleType(instock/soldout),不用像
# AAPE/Salomon 那樣追蹤逐尺寸庫存。抓取邏輯共用 scrape_merries.py 的
# extract_price_stock(),兩邊(這裡的每日同步 + import_merries.py 的
# 一次性匯入)讀同一份 ld+json 結構化資料,不用維護兩套解析邏輯。) ----------

def sync_merries(items):
    print("=== Merries 同步開始(使用瀏覽器渲染 JS)===")
    from playwright.sync_api import sync_playwright

    from scrape_merries import HEADERS as MERRIES_HEADERS, extract_price_stock

    cards = [p for p in items if p.get("brand") == "Merries"]
    changed = stock_changed = errors = delisted = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(user_agent=MERRIES_HEADERS["User-Agent"])
        for idx, card in enumerate(cards):
            link = card.get("link")
            if not link:
                continue
            try:
                # 2026-08-20 抓到:這個站背景會一直打 /ja/ex/sprocket 這種
                # 分析/個人化追蹤請求,幾乎不會停,"networkidle" 永遠等不到
                # (本機實測 20 秒直接逾時)。改用 domcontentloaded,真正需要
                # 等 JS 灌完資料的部份,由 extract_price_stock() 自己用
                # wait_for_selector(state="attached") 精準等 ld+json 出現。
                res = page.goto(link, timeout=30000, wait_until="domcontentloaded")
                if res is not None and res.status == 404:
                    if card.get("saleType") != "soldout":
                        card["saleType"] = "soldout"
                        delisted += 1
                        print(f"  官網已下架(404):{card.get('name')},已標記缺貨")
                        delisted_lines.append(f"[Merries] {card.get('name')}")
                    continue
                new_jpy, in_stock = extract_price_stock(page)
            except Exception as e:
                print(f"  [{idx+1}/{len(cards)}] 抓取失敗:{card.get('name')} ({e})")
                errors += 1
                continue

            if new_jpy and new_jpy != card.get("jpy"):
                print(f"  價格變動:{card.get('name')} ¥{card.get('jpy')} → ¥{new_jpy}")
                price_change_lines.append(f"[Merries] {card.get('name')}:¥{card.get('jpy'):,} → ¥{new_jpy:,}")
                card["jpy"] = new_jpy
                changed += 1

            # in_stock 是 None 代表這次抓取沒拿到明確的庫存狀態(例如頁面
            # 結構暫時跑掉),沿用舊的 saleType,不要誤判成缺貨。
            if in_stock is not None:
                new_sale_type = "instock" if in_stock else "soldout"
                if new_sale_type != card.get("saleType", "instock"):
                    card["saleType"] = new_sale_type
                    stock_changed += 1

            time.sleep(0.3)
            if (idx + 1) % 20 == 0:
                print(f"  進度 {idx+1}/{len(cards)}(價格變動 {changed},缺貨異動 {stock_changed},下架 {delisted},錯誤 {errors})")
        browser.close()
    print(f"Merries 完成:{len(cards)} 張卡,價格變動 {changed} 件,缺貨異動 {stock_changed} 件,下架 {delisted} 件,錯誤 {errors} 件")
    merge_and_save(cards)


# ---------- CELINE(2026-08-08 新增,celine.com/ja-jp,Salesforce
# Commerce Cloud 靜態輸出,沒有機器人偵測。跟其他品牌不一樣的地方:
# 每個顏色是獨立網址(不是一頁涵蓋全部顏色),商品卡存的 link 只會是
# 「上架當時第一個顏色」的網址——但那頁本身就會列出所有顏色的 swatch
# 連結(<a href> + data-gtm-interactiontype="Color swatch - 顏色名"),
# 所以同步時先讀 link 這頁,「順便」發現所有顏色的網址,再一個一個顏色
# 去抓最新的尺寸庫存,不需要另外存每個顏色自己的連結。) ----------

CELINE_COLOR_SWATCH_RE = re.compile(
    r'data-gtm-interactiontype="Color swatch - ([^"]+)"(?:(?!</li>).)*?href="([^"]+)"',
    re.S,
)


def celine_extract_size_stock(html):
    sizes, stock = [], {}
    for li in re.findall(r'<li\s+data-mselector-listitem.*?</li>', html, re.S):
        if "Size Selector" not in li:
            continue
        vm = re.search(r'data-value="([^"]+)"', li)
        if not vm:
            continue
        size = fix_size_key(vm.group(1).strip())
        if not size or size in stock:
            continue
        sizes.append(size)
        stock[size] = 0 if "s-disabled" in li else 5
    if sizes:
        return sizes, stock
    # 沒有尺寸選單的商品(大部分配件類),跟 scrape_celine.py 的
    # parse_page() 一樣,退回用 JSON-LD 的 offers.availability 當唯一的
    # 庫存狀態,不能回傳空的 sizes/stock,不然呼叫端會誤判成「這頁抓失敗」
    # 而完全不更新,舊庫存(可能早就賣完了)就會一直卡著。
    availability = ""
    m = re.search(r'"availability"\s*:\s*"([^"]+)"', html)
    if m:
        availability = m.group(1)
    return ["F"], {"F": 0 if "OutOfStock" in availability else 5}


def sync_celine(items):
    print("=== CELINE 同步開始 ===")
    from scrape_celine import translate_celine_color
    cards = [p for p in items if p.get("brand") == "CELINE"]
    stock_changed = price_changed = errors = delisted = 0
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
            if any(v > 0 for color in card.get("colors", []) for v in _stock_values(color.get("stock"))):
                mark_all_sold_out(card)
                delisted += 1
                delisted_lines.append(f"[CELINE] {card.get('name')} 官網已下架(404)")
            continue

        # 這頁本身的 JSON-LD 拿現在這個顏色的最新售價
        new_jpy = extract_ldjson_price(res.text)
        if new_jpy and int(new_jpy) != card.get("jpy"):
            new_jpy = int(new_jpy)
            print(f"  價格變動:{card.get('name')} ¥{card.get('jpy')} → ¥{new_jpy}")
            price_change_lines.append(f"[CELINE] {card.get('name')}:¥{card.get('jpy'):,} → ¥{new_jpy:,}")
            card["jpy"] = new_jpy
            price_changed += 1

        # 從這頁的顏色 swatch 列表,找出全部顏色各自的網址。官網抓下來的
        # swatch 名稱一定是日文,但我們資料庫裡存的 color.name 是已經翻譯過
        # 的中文(2026-08-09 補的翻譯,見 scrape_celine.translate_celine_color)
        # ——這裡也要用同一個函式把剛抓到的日文名稱轉成中文,兩邊才是同一種
        # 語言,比對得起來,不然每次同步都會找不到對應顏色,庫存就再也不會更新。
        swatch_urls = {}
        for name, href in CELINE_COLOR_SWATCH_RE.findall(res.text):
            full_url = href if href.startswith("http") else f"https://www.celine.com{href}"
            swatch_urls.setdefault(translate_celine_color(name.strip()), full_url)

        for color in card.get("colors", []):
            color_url = swatch_urls.get(color.get("name"))
            # 目前這頁本身也是某個顏色,直接沿用剛剛抓到的 res,不用重抓
            html = res.text if color_url == link or not color_url else None
            if html is None and color_url:
                try:
                    r2 = fetch_or_none_if_404(color_url, timeout=25)
                    time.sleep(0.4)
                    html = r2.text if r2 is not None else None
                except Exception:
                    html = None
            if not html:
                if any(v > 0 for v in _stock_values(color.get("stock"))):
                    stock_changed += 1
                color["stock"] = {s: 0 for s in color.get("sizes", [])}
                continue
            sizes, stock = celine_extract_size_stock(html)
            if not sizes:
                continue
            if stock != (color.get("stock") or {}):
                stock_changed += 1
            color["sizes"], color["stock"] = sizes, stock

        if (idx + 1) % 100 == 0:
            print(f"  進度 {idx+1}/{len(cards)}(庫存有變 {stock_changed},價格變動 {price_changed},下架 {delisted},錯誤 {errors})")
    print(f"CELINE 完成:{len(cards)} 張卡,庫存有變 {stock_changed} 個顏色,"
          f"價格變動 {price_changed} 件,下架 {delisted} 件,錯誤 {errors} 件")
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
            if any(v > 0 for c in card.get("colors", []) for v in _stock_values(c.get("stock"))):
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
            if any(v > 0 for c in card.get("colors", []) for v in _stock_values(c.get("stock"))):
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


# ---------- 3COINS(PAL CLOSET 商城,palcloset.jp,只上架時尚配件類——
# 包包/髮飾/飾品/帽子/錢包小物,2026-08-13 加入)----------
# 商品頁是純 requests + BeautifulSoup 就能讀到完整顏色/庫存的伺服器端渲染
# 頁面,不需要 Playwright,詳細技術細節、分類/庫存解析邏輯都寫在
# scrape_3coins.py 開頭的說明跟 fetch_product_detail() 裡,這裡只是每天
# 重新呼叫同一支 fetch_product_detail() 去比對現有商品的最新庫存/價格,
# 不會發現新商品(新商品要另外重新跑一次 scrape_3coins.py)。

_3COINS_ITEM_RE = re.compile(r"/display/item/([^/]+)/")


def sync_3coins(items):
    print("=== 3COINS 同步開始 ===")
    from scrape_3coins import fetch_product_detail

    cards = [p for p in items if p.get("brand") == "3COINS"]
    stock_changed = price_changed = errors = 0
    for idx, card in enumerate(cards):
        m = _3COINS_ITEM_RE.search(card.get("link") or "")
        if not m:
            errors += 1
            continue
        slug = m.group(1)
        try:
            name, jpy, colors = fetch_product_detail(slug)
        except Exception as e:
            print(f"  [{idx+1}/{len(cards)}] 抓取失敗:{card.get('name')} ({e})")
            errors += 1
            continue

        if not colors:
            # 商品在官網已經下架,全部標成缺貨,不刪除商品本身
            if any(v > 0 for c in card.get("colors", []) for v in _stock_values(c.get("stock"))):
                stock_changed += 1
                delisted_lines.append(f"[3COINS] {card.get('name')} 官網已下架,標記全面缺貨")
            for color in card.get("colors", []):
                color["stock"] = {s: 0 for s in color.get("sizes", [])}
            time.sleep(0.3)
            continue

        # 詳細頁不一定每次都回傳圖片(極少數款式頁面結構跟預期不同),
        # 沿用原本每個顏色已經存好的圖片當備援。
        old_images = {c.get("name"): c.get("image") for c in card.get("colors", []) if c.get("image")}
        for c in colors:
            if not c.get("image") and c["name"] in old_images:
                c["image"] = old_images[c["name"]]
        if colors != card.get("colors"):
            stock_changed += 1
        card["colors"] = colors

        if jpy and jpy != card.get("jpy"):
            print(f"  價格變動:{card.get('name')} ¥{card.get('jpy')} → ¥{jpy}")
            price_change_lines.append(f"[3COINS] {card.get('name')}:¥{card.get('jpy'):,} → ¥{jpy:,}")
            card["jpy"] = jpy
            price_changed += 1

        time.sleep(0.3)
        if (idx + 1) % 100 == 0:
            print(f"  進度 {idx+1}/{len(cards)}(庫存有變 {stock_changed},價格變動 {price_changed},錯誤 {errors})")
    print(f"3COINS 完成:{len(cards)} 張卡,庫存有變 {stock_changed} 個顏色組合,"
          f"價格變動 {price_changed} 件,錯誤 {errors} 件")
    merge_and_save(cards)


def main():
    only = sys.argv[1].lower() if len(sys.argv) > 1 else None
    # 只跑單一品牌(GitHub Actions 現在每個品牌各自一個 job,實際上永遠是
    # 這個分支)的話,用條件查詢只抓那個品牌,不整包抓全站商品,見
    # load_products_by_brand() 的說明。只有本機手動整批跑全部品牌
    # (only 是 None)才需要真的整包讀一次。
    if only and only in ONLY_ARG_TO_BRAND:
        items = load_products_by_brand(ONLY_ARG_TO_BRAND[only])
    else:
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
    if only in (None, "3coins"):
        sync_3coins(items)
    if only in (None, "polene"):
        sync_polene(items)
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
    if only in (None, "stussy"):
        sync_stussy(items)
    if only in (None, "celine"):
        sync_celine(items)
    if only in (None, "aape"):
        sync_aape(items)
    if only in (None, "lacoste"):
        sync_lacoste(items)
    if only in (None, "jlindeberg"):
        sync_price_only(items, "J.Lindeberg", extract_ldjson_price)
    if only in (None, "descente"):
        sync_descente(items)
    if only in (None, "merries"):
        sync_merries(items)
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
