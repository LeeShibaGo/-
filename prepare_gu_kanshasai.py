# -*- coding: utf-8 -*-
"""
準備:GU 感謝祭(2026-11,「感謝価格商品」= アプリ会員特別価格,至 11/26)商品匯入資料
------------------------------------------------------------
來源:GU 官網「期間限定価格商品」清單(feature/limited-offers)用的同一支搜尋 API:
  POST /jp/api/commerce/v5/ja/products/search
  body: flagCodes=[limitedOffer,onlineLimited,specialPrice]、withMemberPricing=true
  (2026-11-21 抓到 77 件,全部帶 appmemberLimited 價格旗標,結束時間 11/26)
  價格:prices.guest.base = 平常價、prices.member.promo(沒有就 member.base)= 感謝價。

輸出 gu_kanshasai_import.json:
  updates  官網資料庫已經有的 GU 商品(link 裡商品代碼相同)→ 只改價格/加活動標記
  new      還沒有的 → 新增商品卡(顏色/尺寸/圖片/庫存讀官網詳細頁 + /stock 真實庫存)
  台幣售價:跟 UNIQLO 同一張價目表(apply_uniqlo_price_table.PRICE_TABLE,日幣感謝價 -> 台幣),
  價目表沒有的日幣價(1,490 / 2,490 / 4,990)用前後兩個價位線性內插,尾數湊成 0 或 9。
  中文名稱另外由 gu_zh_names.py 對照(日文原名 -> 中文),沒有對照的先用日文原名。

用法:python prepare_gu_kanshasai.py
"""

import collections
import json
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import requests

from apply_uniqlo_price_table import PRICE_TABLE

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

OUT = "gu_kanshasai_import.json"
API = "https://www.gu-global.com/jp/api/commerce/v5/ja/products"
DB = "https://shibago-4dd3c-default-rtdb.asia-southeast1.firebasedatabase.app"
HEADERS = {"x-fr-clientid": "gu.jp.web-spa", "User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}
CAMPAIGN = "gu-kanshasai-2026"
SALE_END = "2026-11-26"
GENDER_LABEL = {"MEN": "男款", "WOMEN": "女款", "KIDS": "童裝", "BABY": "嬰幼兒", "ユニセックス": "男女兼用"}

# GU 商品卡原本用的分類(跟 UNIQLO 的不完全一樣,照 GU 現有商品的用法);順序越前面越優先
SUBTYPE_RULES = [
    ("ソックス", "襪類"),
    ("ブーツ", "鞋類"), ("シューズ", "鞋類"), ("サンダル", "鞋類"),
    ("ベルト", "配件"), ("マフラー", "配件"), ("ストール", "配件"), ("グローブ", "配件"), ("手袋", "配件"),
    ("バッグ", "包包"), ("リュック", "包包"), ("ポーチ", "包包"),
    ("キャップ", "帽子"), ("ハット", "帽子"), ("ニット帽", "帽子"),
    ("ワンピース", "洋裝"), ("スカート", "裙裝"),
    ("ラウンジセット", "家居服"), ("パジャマ", "家居服"), ("ルームウェア", "家居服"),
    ("レギンス", "內搭褲"), ("タイツ", "內搭褲"),
    ("ジーンズ", "牛仔褲"),
    ("ショートパンツ", "短褲"), ("ショーツ", "短褲"),
    ("パンツ", "長褲"),
    ("パーカ", "連帽外套"), ("フーディ", "連帽外套"),
    ("ベスト", "背心"),
    ("ブルゾン", "外套"), ("ジャケット", "外套"), ("コート", "外套"), ("ダウン", "外套"),
    ("カーディガン", "針織衫"), ("セーター", "針織衫"), ("ニット", "針織衫"),
    ("ブラウス", "襯衫"), ("シャツ", "襯衫"),
    ("タートルネックT", "T恤"), ("Tシャツ", "T恤"), ("T(", "T恤"), ("グラフィックT", "T恤"),
    ("スウェット", "上衣"), ("プルオーバー", "上衣"),
]
WEIGHT_BY_SUBTYPE = {
    "短褲": 0.22, "家居服": 0.3, "T恤": 0.18, "外套": 0.6, "長褲": 0.35, "連帽外套": 0.55, "服飾": 0.3,
    "襪類": 0.05, "鞋類": 0.8, "配件": 0.15, "上衣": 0.25, "裙裝": 0.25, "洋裝": 0.3, "針織衫": 0.35,
    "背心": 0.15, "帽子": 0.1, "襯衫": 0.25, "牛仔褲": 0.5, "包包": 0.4, "內搭褲": 0.2,
}


def guess_subtype(name):
    for kw, st in SUBTYPE_RULES:
        if kw in name:
            return st
    return "服飾"


def round_09(x):
    base, r = x - x % 10, x % 10
    return base if r <= 4 else base + 9


def twd_for(jpy):
    if jpy in PRICE_TABLE:
        return PRICE_TABLE[jpy]
    keys = sorted(PRICE_TABLE)
    lo = max(k for k in keys if k < jpy)
    hi = min(k for k in keys if k > jpy)
    v = PRICE_TABLE[lo] + (PRICE_TABLE[hi] - PRICE_TABLE[lo]) * (jpy - lo) / (hi - lo)
    return round_09(round(v))


def fix_size_key(s):
    return str(s).replace(".", "-").replace("/", "／")


def search_all():
    out, off = [], 0
    while True:
        body = {"flagCodes": ["limitedOffer", "onlineLimited", "specialPrice"], "offset": off, "limit": 36,
                "withMemberPricing": True}
        j = requests.post(API + "/search?httpFailure=true", headers=HEADERS, data=json.dumps(body), timeout=40).json()
        r = j["result"]
        out += r["items"]
        off += 36
        if off >= r["pagination"]["total"] or not r["items"]:
            break
    return out


def get_json(url, params=None, retries=4):
    for i in range(retries):
        try:
            return requests.get(url, params=params, headers=HEADERS, timeout=25).json()
        except Exception:
            time.sleep(2 * (i + 1))
    return None


def main():
    items = search_all()
    print(f"官網感謝價格商品:{len(items)} 件")

    def detail(it):
        pid = it["productId"]
        time.sleep(0.1)
        d = get_json(f"{API}/{pid}", {"withPrices": "true", "withStocks": "true", "httpFailure": "true"})
        s = get_json(f"{API}/{pid}/stock")
        return pid, d, s

    with ThreadPoolExecutor(4) as ex:
        det = {pid: (d, s) for pid, d, s in ex.map(detail, items)}

    raw = json.load(urllib.request.urlopen(DB + '/daigou-products-v1.json?orderBy="brand"&equalTo="GU"'))
    existing = list(raw.values()) if isinstance(raw, dict) else raw
    by_pid = {}
    for p in existing:
        m = re.search(r"/products/([^/]+)/", p.get("link") or "")
        if m:
            by_pid[m.group(1)] = p

    now = int(time.time() * 1000)
    updates, new_products, problems = [], [], []
    for n, it in enumerate(items):
        pid = it["productId"]
        pr = it["prices"]
        regular = ((pr.get("guest") or {}).get("base") or {}).get("value")
        mem = pr.get("member") or {}
        sale = ((mem.get("promo") or mem.get("base")) or {}).get("value")
        gender = it.get("genderName")
        label = GENDER_LABEL.get(gender, gender)
        twd = twd_for(sale)
        name_ja = it["name"]
        if pid in by_pid:
            p = by_pid[pid]
            updates.append({"id": p["id"], "productId": pid, "name": p["name"], "nameJa": name_ja, "oldJpy": p.get("jpy"),
                            "jpy": sale, "twdOverride": twd, "originalJpy": regular, "gender": label})
            continue
        d, s = det[pid]
        if not d or d.get("status") != "ok" or not s or s.get("status") != "ok":
            problems.append((pid, name_ja, "官網詳細頁/庫存抓取失敗"))
            continue
        res, st = d["result"], s["result"]
        colors = {}
        for l2 in res["l2s"]:
            c = l2["color"]
            e = colors.setdefault(c["displayCode"], {"name": c["name"], "sizes": [], "stock": {}, "_code": c["displayCode"]})
            sz = fix_size_key((l2.get("size") or {}).get("name") or "-")
            if sz not in e["stock"]:
                e["sizes"].append(sz)
            info = st.get(l2["l2Id"]) or {}
            ok = bool(l2.get("sales")) and info.get("statusCode") in ("IN_STOCK", "LOW_STOCK") and (info.get("quantity") or 0) > 0
            e["stock"][sz] = max(e["stock"].get(sz, 0), 1 if ok else 0)
        images = res["images"]["main"]
        rep = it.get("representativeColorDisplayCode")
        out_colors, seen = [], set()
        for code in sorted(colors, key=lambda k: (k != rep, k)):
            e = colors[code]
            img = (images.get(code) or {}).get("image")
            if img:
                e["image"] = img
            e.pop("_code")
            if e["name"] in seen:  # 同名顏色(不同色碼)加色碼區分,避免選項重複
                e["name"] = f"{e['name']} {code}"
            seen.add(e["name"])
            out_colors.append(e)
        subtype = guess_subtype(name_ja)
        prod = {
            "id": f"p_gukss_{now}_{n}",
            "addedAt": now,
            "name": name_ja,  # 之後由 gu_zh_names 換成「日文 中文(性別)」
            "nameJa": name_ja,
            "brand": "GU",
            "country": "JP",
            "subtype": subtype,
            "jpy": sale,
            "twdOverride": twd,
            "weight": WEIGHT_BY_SUBTYPE.get(subtype, 0.3),
            "saleType": "instock",
            "hidden": False,
            "desc": f"{label}・感謝祭限定價(App 會員價)¥{sale:,}" + (f"(原價 ¥{regular:,})" if regular else "") + "・至 11/26",
            "link": f"https://www.gu-global.com/jp/ja/products/{pid}/00",
            "image": next((c["image"] for c in out_colors if c.get("image")), None),
            "colors": out_colors,
            "campaign": CAMPAIGN,
            "saleEnd": SALE_END,
            "_gender": label,
            "_pid": pid,
        }
        if not prod["image"]:
            prod.pop("image")
        new_products.append(prod)

    # 同名同價同性別、不同商品代碼的新商品合併成一張卡(顏色合併),跟 UNIQLO 感謝祭一樣;
    # 合併卡帶 mergedProductIds,每日同步會跳過它們(見 sync_stock.sync_gu),庫存由
    # check_uniqlo_kanshasai_stock.py(GU)另外校正。
    groups = collections.OrderedDict()
    for p in new_products:
        groups.setdefault((p["nameJa"], p["_gender"], p["jpy"]), []).append(p)
    merged_products = []
    for plist in groups.values():
        base = plist[0]
        if len(plist) > 1:
            seen = {c["name"] for c in base["colors"]}
            for other in plist[1:]:
                for c in other["colors"]:
                    if c["name"] in seen:
                        c["name"] = f"{c['name']} ({other['_pid'].split('-')[0]})"
                    seen.add(c["name"])
                    base["colors"].append(c)
            base["mergedProductIds"] = [p["_pid"] for p in plist]
            print(f"  合併同名商品卡:{base['nameJa']}({len(plist)} 個商品代碼)")
        merged_products.append(base)
    new_products = merged_products

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"campaign": CAMPAIGN, "saleEnd": SALE_END, "updates": updates, "new": new_products}, f,
                  ensure_ascii=False, indent=1)
    print(f"更新價格(站上已有):{len(updates)} 件;新增:{len(new_products)} 件;問題:{len(problems)}")
    for p in problems:
        print("  問題:", p)
    c = collections.Counter((u["jpy"], u["twdOverride"]) for u in updates)
    c.update((p["jpy"], p["twdOverride"]) for p in new_products)
    print("日幣感謝價 -> 台幣:", sorted(c.items()))
    print("--- 日文名稱 ---")
    for p in new_products:
        print(p["_gender"], "|", p["nameJa"], "|", p["subtype"])


if __name__ == "__main__":
    main()
