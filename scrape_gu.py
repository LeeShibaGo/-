# -*- coding: utf-8 -*-
"""
GU(ジーユー,Fast Retailing 集團旗下快時尚品牌,gu-global.com)全站商品爬蟲
------------------------------------------------------------
用途:
  抓 GU 日本官網全站商品(男女童裝都含),輸出 gu_full_products.json,
  格式跟 on_full_products.json / daigou-products-v1 裡其他多色多尺寸品牌
  (On、Salomon)完全一樣,可以直接合併進 Firebase。

跟其他品牌爬蟲的差異(GU 技術上比大部分品牌都好抓):
  GU 跟 UNIQLO 同屬 Fast Retailing,共用同一套公開 commerce API,
  沒有 DataDome 之類的機器人偵測,不需要瀏覽器渲染,純 requests 就能拿到
  「每個顏色+尺寸組合」的真實庫存狀態,細節如下:
  1) 列表 API(找出全站有哪些商品):
       GET /jp/api/commerce/v5/ja/products?path=,,{categoryId},&offset=&limit=
     GU 官網本身沒有公開「全部商品」或「分類樹」的單一端點,category id
     是先用十幾組常見服飾關鍵字下去搜尋、把每次搜尋結果 aggregations.tree
     裡出現的 category id 全部蒐集起來湊出 CATEGORY_ID_TO_JA(176 組)——
     這份清單是涵蓋範圍,不是官方文件,如果之後 GU 新增了完全對不到現有
     關鍵字的全新分類,不會自動出現在這裡,需要重新跑一次關鍵字蒐集。
     商品可能同時出現在好幾個分類(例如同時掛在「Tシャツ」跟行銷用的
     「GU Minimal」),所以最後用 productId 去重,不怕多抓。
  2) 詳細 API(每個商品的真實庫存):
       GET /jp/api/commerce/v5/ja/products/{productId}?withPrices=true&withStocks=true
     回傳的 l2s 陣列是「每個顏色+尺寸」的組合,每組有 sales:true/false,
     這個欄位就是即時庫存的有無(實測過:9 件商品裡有 2 件全部 sales
     都是 false,證實不是假資料)。GU 沒有公開實際庫存件數,只有這個
     布林值,所以 stock 只能存 1(有貨)或 0(缺貨),不是真實數量,
     跟其他品牌「stock 是實際件數」不完全一樣,但前端只判斷 >0,效果相同。

分類(subtype)對照:
  CATEGORY_ID_TO_JA 蒐集到的是 GU 官網自己的日文分類名稱,JA_TO_SUBTYPE
  把它對照成中文 subtype,盡量對到 index.html 裡 SUBTYPE_GROUP 已經有的
  key(T恤、長褲、牛仔褲...),這樣不用改前端就能自動歸進正確的「大分類」
  (上身/褲子/裙子/外套/鞋子/包包/配件)。對不到的(家居服、內著等 GU
  獨有但其他品牌沒有的分類)就自成一個新大分類,不勉強塞。

執行方式:
  pip install -r requirements.txt
  python scrape_gu.py

會輸出 gu_full_products.json。
"""

import json
import sys
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

import requests

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

BASE = "https://www.gu-global.com"
API = f"{BASE}/jp/api/commerce/v5/ja/products"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}
BRAND = "GU"
LIST_PAGE_SIZE = 50
WORKERS = 8

# 分類 id -> GU 官網日文分類名稱(見檔案開頭說明,用十幾組關鍵字搜尋蒐集出來的)
CATEGORY_ID_TO_JA = {
    36396: "コート", 36397: "ジャケット", 36398: "ブルゾン・パーカ",
    36400: "ウォームパデッド・中わたアウター", 36401: "ベスト", 36407: "スウェット",
    36409: "Tシャツ・カットソー", 36410: "グラフィックTシャツ", 36411: "キャミソール・タンクトップ",
    36412: "その他", 36413: "ワンピース", 36417: "ショートパンツ・スコート",
    36420: "3Dバレル・ワイドパンツ", 36422: "スウェットパンツ", 36423: "ジーンズ・デニムパンツ",
    36425: "イージーパンツ・バルーンパンツ", 36426: "スラックス", 36427: "その他",
    36428: "ミニスカート・スコート", 36429: "ミディスカート", 36430: "ロングスカート",
    36431: "その他", 36432: "パジャマ", 36433: "ルームウェア",
    36436: "ブラフィール", 36437: "ブラジャー", 36438: "ショーツ",
    36440: "スタイルドライ", 36443: "インナートップス", 36444: "レギンス・タイツ",
    36445: "ソックス・靴下", 36446: "バリューパック", 36448: "フラットシューズ",
    36449: "パンプス", 36450: "サンダル", 36451: "スニーカー", 36452: "ブーツ",
    36454: "キャップ・ハット・帽子", 36459: "バッグ", 36460: "ベルト", 36465: "その他",
    36468: "コート", 36469: "ジャケット", 36471: "ウォームパデッド・中わたアウター",
    36478: "スウェット", 36482: "Tシャツ・カットソー", 36483: "グラフィックTシャツ",
    36485: "ショートパンツ", 36486: "アンクルパンツ・クロップドパンツ", 36488: "イージーパンツ",
    36491: "スキニーパンツ・スリムパンツ", 36493: "チノパンツ", 36494: "バレルレッグ・ワイドパンツ",
    36496: "スウェットパンツ", 36497: "ジーンズ・デニムパンツ", 36499: "パジャマ",
    36500: "ルームウェア", 36502: "その他", 36503: "スタイルドライ", 36505: "スタイルヒート",
    36506: "インナートップス", 36507: "ボクサーパンツ・トランクス", 36508: "レギンス・タイツ",
    36509: "ソックス・靴下", 36510: "バリューパック", 36513: "スニーカー",
    36515: "ビジネスシューズ・ドレスシューズ", 36517: "キャップ・ハット・帽子",
    36520: "バッグ・ポーチ", 36521: "ベルト", 36526: "その他",
    36559: "キッズ スタイルヒート", 36560: "キッズ ブラフィールプチ",
    37086: "ブルゾン・パーカ", 42189: "カーゴパンツ", 42190: "スキニーパンツ",
    45587: "ポーチ・財布", 47893: "スラックス",
    52888: "キッズ アウター", 52891: "キッズ スウェット", 52892: "キッズ カーディガン",
    52893: "キッズ ニット・セーター", 52894: "キッズ シャツ・ブラウス",
    52895: "キッズ Tシャツ・カットソー", 52896: "キッズ グラフィックTシャツ",
    52912: "キッズ ワンピース・サロペット", 52915: "キッズ ロングパンツ",
    52916: "キッズ ショートパンツ・クロップドパンツ", 52924: "キッズ ルームウェア",
    52925: "キッズ パジャマ", 52928: "キッズ ショーツ・ボクサーパンツ",
    52929: "キッズ ソックス・レギンス", 52933: "キッズ インナートップス",
    52944: "TEENTシャツ・スウェット・ニット", 52946: "TEENパンツ・スカート",
    52967: "キッズ スカート", 75712: "TEENブラフィールプチ",
    86598: "ブラフィール", 94698: "シャツ・ブラウス", 94707: "ニット・セーター",
    94708: "カーディガン", 94710: "その他", 94792: "カジュアルシャツ",
    94793: "ドレスシャツ・ワイシャツ", 94794: "ポロシャツ", 94796: "ニット・セーター",
    94797: "カーディガン", 94798: "ベスト",
    101716: "TEENTシャツ・スウェット・ニット", 101718: "TEENパンツ・スカート",
    116566: "カーゴパンツ・ワークパンツ", 125257: "スウェット",
    129774: "コージーメルトン", 129776: "コージーメルトン", 131872: "アンクルパンツ",
    134031: "チュニック", 134039: "GU×UNDERCOVER", 134041: "GU×UNDERCOVER",
    134043: "GU×rokh", 134914: "ジャケット・アウター", 134920: "シャツ・ブラウス",
    134925: "Tシャツ・カットソー", 134931: "ニット・カーディガン", 134935: "パンツ",
    134940: "スカート", 134946: "グッズ・シューズ", 134952: "ジャケット・アウター",
    134957: "シャツ・ポロシャツ", 134962: "Tシャツ・カットソー", 134968: "ニット・カーディガン",
    134972: "パンツ", 134977: "グッズ・シューズ", 137720: "GU×ENGINEEREDGARMENTS",
    139979: "パーカ", 139982: "トレーナー・スウェットシャツ", 139988: "ボトムス",
    139991: "その他", 139993: "パフスウェット", 139996: "ヘビーウェイトスウェット",
    139999: "フレンチテリー", 140002: "ユニセックス", 140005: "パーカ",
    140008: "トレーナー・スウェットシャツ", 140011: "グラフィックスウェット", 140014: "ボトムス",
    140019: "パフスウェット", 140022: "ヘビーウェイトスウェット", 140025: "フレンチテリー",
    141885: "ワンピース", 143297: "ボトムス", 143298: "トップス",
    143321: "ボトムス", 143322: "トップス", 147675: "スムーススウェット",
    147678: "スムーススウェット", 147743: "チャーム・キーホルダー", 147746: "チャーム・キーホルダー",
    147750: "GUMinimal", 147767: "GUPlayful", 147784: "GUClassic",
    147803: "GUUtility", 147818: "GUSport", 147833: "GUCozy",
    147849: "GUMinimal", 147861: "ウォームインナー", 148075: "GUPlayful",
    148087: "GUClassic", 148099: "GUUtility", 148111: "GUSport",
    148123: "GUCozy", 148136: "GUPlayful", 148150: "GUUtility",
    148165: "GUSport", 148179: "GUCozy", 149500: "先行販売商品", 149515: "先行販売商品",
}

# 日文分類名稱 -> 中文 subtype,盡量對到 index.html SUBTYPE_GROUP 既有的 key。
JA_TO_SUBTYPE = {
    "コート": "外套", "ジャケット": "外套", "ブルゾン・パーカ": "連帽外套",
    "ウォームパデッド・中わたアウター": "外套", "ベスト": "外套",
    "ジャケット・アウター": "外套", "キッズ アウター": "外套",
    "スウェット": "上衣", "トレーナー・スウェットシャツ": "上衣", "グラフィックスウェット": "上衣",
    "パフスウェット": "上衣", "ヘビーウェイトスウェット": "上衣", "フレンチテリー": "上衣",
    "スムーススウェット": "上衣", "コージーメルトン": "上衣", "キッズ スウェット": "上衣",
    "トップス": "上衣",
    "パーカ": "連帽外套",
    "Tシャツ・カットソー": "T恤", "グラフィックTシャツ": "T恤",
    "キッズ Tシャツ・カットソー": "T恤", "キッズ グラフィックTシャツ": "T恤",
    "TEENTシャツ・スウェット・ニット": "T恤",
    "キャミソール・タンクトップ": "背心",
    "ワンピース": "洋裝", "キッズ ワンピース・サロペット": "洋裝", "チュニック": "洋裝",
    "ショートパンツ・スコート": "短褲", "ショートパンツ": "短褲",
    "キッズ ショートパンツ・クロップドパンツ": "短褲",
    "3Dバレル・ワイドパンツ": "長褲", "スウェットパンツ": "長褲", "イージーパンツ・バルーンパンツ": "長褲",
    "スラックス": "長褲", "アンクルパンツ・クロップドパンツ": "長褲", "イージーパンツ": "長褲",
    "スキニーパンツ・スリムパンツ": "長褲", "チノパンツ": "長褲", "バレルレッグ・ワイドパンツ": "長褲",
    "カーゴパンツ": "長褲", "スキニーパンツ": "長褲", "アンクルパンツ": "長褲",
    "カーゴパンツ・ワークパンツ": "長褲", "パンツ": "長褲", "ボトムス": "長褲",
    "キッズ ロングパンツ": "長褲", "TEENパンツ・スカート": "長褲",
    "ジーンズ・デニムパンツ": "牛仔褲",
    "ミニスカート・スコート": "裙裝", "ミディスカート": "裙裝", "ロングスカート": "裙裝",
    "キッズ スカート": "裙裝", "スカート": "裙裝",
    "パジャマ": "家居服", "ルームウェア": "家居服", "キッズ ルームウェア": "家居服",
    "キッズ パジャマ": "家居服",
    "ブラフィール": "內著", "ブラジャー": "內著", "ショーツ": "內著",
    "スタイルドライ": "內著", "インナートップス": "內著", "スタイルヒート": "內著",
    "ボクサーパンツ・トランクス": "內著", "キッズ ブラフィールプチ": "內著",
    "キッズ ショーツ・ボクサーパンツ": "內著", "キッズ インナートップス": "內著",
    "TEENブラフィールプチ": "內著", "ウォームインナー": "內著", "キッズ スタイルヒート": "內著",
    "レギンス・タイツ": "內搭褲", "キッズ ソックス・レギンス": "襪類",
    "ソックス・靴下": "襪類",
    "バリューパック": "配件", "その他": "服飾", "ユニセックス": "服飾",
    "フラットシューズ": "鞋類", "パンプス": "鞋類", "サンダル": "鞋類",
    "スニーカー": "鞋類", "ブーツ": "鞋類", "ビジネスシューズ・ドレスシューズ": "鞋類",
    "グッズ・シューズ": "鞋類",
    "キャップ・ハット・帽子": "帽子",
    "バッグ": "包包", "バッグ・ポーチ": "包包", "ポーチ・財布": "皮夾",
    "ベルト": "配件",
    "シャツ・ブラウス": "襯衫", "カジュアルシャツ": "襯衫", "ドレスシャツ・ワイシャツ": "襯衫",
    "キッズ シャツ・ブラウス": "襯衫", "シャツ・ポロシャツ": "襯衫",
    "ポロシャツ": "Polo衫",
    "ニット・セーター": "針織衫", "カーディガン": "針織衫", "ニット・カーディガン": "針織衫",
    "キッズ カーディガン": "針織衫", "キッズ ニット・セーター": "針織衫",
    "チャーム・キーホルダー": "配件",
    "GU×UNDERCOVER": "服飾", "GU×rokh": "服飾", "GU×ENGINEEREDGARMENTS": "服飾",
    "GUMinimal": "服飾", "GUPlayful": "服飾", "GUClassic": "服飾",
    "GUUtility": "服飾", "GUSport": "服飾", "GUCozy": "服飾",
    "先行販売商品": "服飾",
}

WEIGHT_BY_SUBTYPE = {
    "T恤": 0.18, "Polo衫": 0.22, "背心": 0.15, "襯衫": 0.25, "針織衫": 0.35,
    "上衣": 0.25, "外套": 0.6, "連帽外套": 0.55,
    "長褲": 0.35, "牛仔褲": 0.5, "短褲": 0.22, "內搭褲": 0.2,
    "洋裝": 0.3, "裙裝": 0.25, "家居服": 0.3,
    "內著": 0.1, "襪類": 0.05,
    "鞋類": 0.8, "帽子": 0.1, "包包": 0.4, "皮夾": 0.15, "配件": 0.15, "服飾": 0.3,
}
DEFAULT_WEIGHT = 0.3


def guess_subtype(ja_name):
    return JA_TO_SUBTYPE.get(ja_name, ja_name)


def guess_weight(subtype):
    return WEIGHT_BY_SUBTYPE.get(subtype, DEFAULT_WEIGHT)


def api_get(url, params, retries=3):
    for attempt in range(retries):
        try:
            res = requests.get(url, params=params, headers=HEADERS, timeout=20)
            if res.status_code != 200:
                return None
            return res.json()
        except Exception as e:
            if attempt == retries - 1:
                print(f"  [錯誤] {url} {params} -> {e}")
                return None
            time.sleep(1)
    return None


def fetch_category_items(category_id, ja_name):
    """回傳這個分類底下所有商品的 (productId, name, jpy, image, subtype) list。"""
    path = f",,{category_id},"
    items = []
    offset = 0
    subtype = guess_subtype(ja_name)
    while True:
        data = api_get(API, {
            "path": path, "offset": offset, "limit": LIST_PAGE_SIZE, "httpFailure": "true",
        })
        if not data or data.get("status") != "ok":
            break
        result = data.get("result", {})
        page_items = result.get("items", [])
        for it in page_items:
            pid = it.get("productId")
            if not pid:
                continue
            main_images = (it.get("images") or {}).get("main") or {}
            rep_code = it.get("representativeColorDisplayCode")
            image = None
            if rep_code and rep_code in main_images:
                image = main_images[rep_code].get("image")
            elif main_images:
                image = next(iter(main_images.values())).get("image")
            items.append({
                "productId": pid,
                "name": it.get("name") or "",
                "jpy": (it.get("prices") or {}).get("base", {}).get("value") or 0,
                "image": image,
                "subtype": subtype,
            })
        total = result.get("pagination", {}).get("total", 0)
        offset += LIST_PAGE_SIZE
        if offset >= total or not page_items:
            break
    return items


def fetch_product_detail(product_id):
    """回傳這個商品每個顏色+尺寸的庫存(sales:true/false),依顏色分組。"""
    data = api_get(f"{API}/{urllib.parse.quote(product_id)}", {
        "withPrices": "true", "withStocks": "true", "httpFailure": "true",
    })
    if not data or data.get("status") != "ok":
        return []
    l2s = data.get("result", {}).get("l2s", [])
    by_color = {}
    for l2 in l2s:
        color = l2.get("color") or {}
        color_name = color.get("name") or color.get("displayCode") or "-"
        size = (l2.get("size") or {}).get("name") or "-"
        sales = bool(l2.get("sales"))
        entry = by_color.setdefault(color_name, {"name": color_name, "sizes": [], "stock": {}})
        size_key = str(size).replace(".", "-").replace("/", "／")
        if size_key not in entry["stock"]:
            entry["sizes"].append(size_key)
        entry["stock"][size_key] = max(entry["stock"].get(size_key, 0), 1 if sales else 0)
    return list(by_color.values())


def main():
    print(f"[1/2] 列出 {len(CATEGORY_ID_TO_JA)} 個分類底下的商品...")
    all_items = {}  # productId -> item dict(取第一次看到的資料)
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {
            ex.submit(fetch_category_items, cid, ja): (cid, ja)
            for cid, ja in CATEGORY_ID_TO_JA.items()
        }
        done = 0
        for fut in futures:
            cid, ja = futures[fut]
            done += 1
            try:
                items = fut.result()
            except Exception as e:
                print(f"  [錯誤] 分類 {cid} {ja}: {e}")
                items = []
            for it in items:
                all_items.setdefault(it["productId"], it)
            if done % 20 == 0:
                print(f"  ({done}/{len(CATEGORY_ID_TO_JA)} 個分類,目前累積 {len(all_items)} 件不重複商品)")

    print(f"共 {len(all_items)} 件不重複商品,開始抓每件的顏色/尺寸庫存...")

    final_list = []
    product_ids = list(all_items.keys())

    def process(pid):
        base = all_items[pid]
        colors = fetch_product_detail(pid)
        if not colors:
            return None
        # 補上列表 API 拿到的圖片(detail API 沒有回傳圖片網址)
        if base.get("image") and colors:
            colors[0].setdefault("image", base["image"])
        return {
            "name": base["name"],
            "jpy": base["jpy"],
            "weight": guess_weight(base["subtype"]),
            "brand": BRAND,
            "subtype": base["subtype"],
            "country": "JP",
            "saleType": "instock",
            "link": f"{BASE}/jp/ja/products/{pid}/00",
            "colors": colors,
        }

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        done = 0
        for entry in ex.map(process, product_ids):
            done += 1
            if entry:
                final_list.append(entry)
            if done % 200 == 0:
                print(f"  ({done}/{len(product_ids)},已取得 {len(final_list)} 件)")
                with open("gu_full_products.json", "w", encoding="utf-8") as f:
                    json.dump(final_list, f, ensure_ascii=False, indent=2)

    with open("gu_full_products.json", "w", encoding="utf-8") as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)

    print(f"完成!已輸出 gu_full_products.json,共 {len(final_list)} 件商品。")


if __name__ == "__main__":
    main()
