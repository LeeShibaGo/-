# -*- coding: utf-8 -*-
"""
準備 UNIQLO 感謝祭(2026-11)商品匯入資料(只產生 JSON,不碰 Firebase)
------------------------------------------------------------
用途:
  老闆給了一份 uniqlo_kanshasai_2026.xlsx(214 列,感謝價/建議售價/截止日
  2026-11-26),但 Excel 沒有圖片、顏色、尺寸、官網連結。這支腳本:
    1. 用 UNIQLO 日本官網的公開 commerce API,用日文商品名稱搜尋,把每一列
       對回官網的商品代碼(productId,例如 E478577-000)——Excel 同名同價的
       多列,其實就是不同商品代碼(不同顏色組合)。
    2. 用官網詳細頁 API 抓每個商品代碼的顏色、尺寸、庫存、各顏色圖片,
       並用 l2s 裡的 priceFlags(limitedOffer,「11/26まで期間限定價格」)
       交叉確認這是真的期間限定價。
    3. 已經在官網資料庫裡的商品(link 裡有同一個商品代碼)→ 只更新價格;
       還沒有的 → 依「日文名稱+官網性別分類+感謝價」合併成一張卡,多個
       商品代碼的顏色合併成同一張卡的顏色選項(老闆要求)。
  輸出 uniqlo_kanshasai_import.json,由 import_uniqlo_kanshasai.py 在
  GitHub Actions 上讀取並寫進 Firebase。

執行方式:
  python prepare_uniqlo_kanshasai.py
"""

import collections
import json
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import openpyxl
import requests

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

XLSX = "uniqlo_kanshasai_2026.xlsx"
OUT = "uniqlo_kanshasai_import.json"
API = "https://www.uniqlo.com/jp/api/commerce/v5/ja/products"
DB = "https://shibago-4dd3c-default-rtdb.asia-southeast1.firebasedatabase.app"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "x-fr-clientid": "uq.jp.web-spa",
}
CAMPAIGN = "uniqlo-kanshasai-2026"
SALE_END = "2026-11-26"

GENDER_LABEL = {"MEN": "男款", "WOMEN": "女款", "KIDS": "童裝", "BABY": "嬰幼兒", "男女兼用": "男女兼用"}

# 日文名稱關鍵字 → 官網現有的 subtype(index.html SUBTYPE_GROUP 的 key)。
# 順序很重要:越前面越優先。
SUBTYPE_RULES = [
    ("ソックス", "襪類"), ("靴下", "襪類"),
    ("レギンス", "內搭褲"), ("タイツ", "內搭褲"), ("スパッツ", "內搭褲"),
    ("ジーンズ", "牛仔褲"),
    ("ショートパンツ", "短褲"), ("ショーツ", "短褲"),
    ("パンツ", "長褲"),
    ("マフラー", "配件"), ("ストール", "配件"), ("マスク", "配件"), ("アームカバー", "配件"),
    ("アームウォーマー", "配件"), ("ネックウォーマー", "配件"), ("手袋", "配件"), ("グローブ", "配件"), ("ニットキャップ", "配件"),
    ("ヒートテック", "內著"), ("エアリズム", "內著"), ("ブラトップ", "內著"),
    ("パーカ", "連帽外套"),
    ("ダウン", "外套"), ("ジャケット", "外套"), ("ブルゾン", "外套"), ("コート", "外套"),
    ("ベスト", "外套"), ("ブランケット", "配件"),
    ("セット", "服飾"), ("カバーオール", "外套"),
    ("ソフトニットフリース", "長袖上衣"),
    ("カーディガン", "毛衣"), ("セーター", "毛衣"), ("ニット", "毛衣"),
    ("スウェットシャツ", "大學T"), ("スウェット", "大學T"),
    ("シャツ", "襯衫"),
    ("Tシャツ", "短袖上衣"), ("クルーネックT", "短袖上衣"),
    ("ルームウェア", "服飾"),
]
WEIGHT_BY_SUBTYPE = {
    "短袖上衣": 0.2, "長袖上衣": 0.3, "大學T": 0.45, "襯衫": 0.3, "毛衣": 0.4, "外套": 0.6, "連帽外套": 0.55,
    "長褲": 0.4, "短褲": 0.25, "內搭褲": 0.2, "牛仔褲": 0.55, "內著": 0.12, "襪類": 0.06,
    "配件": 0.15, "服飾": 0.3,
}


def guess_subtype(name):
    # Tシャツ 要在 シャツ 之前判斷,不然 Tシャツ 會被當襯衫
    if "Tシャツ" in name or re.search(r"クルーネックT(/|$)", name) or re.search(r"[A-Za-zぁ-んァ-ヶ]T/", name):
        if not any(k in name for k in ("ヒートテック", "エアリズム")):
            return "短袖上衣"
    for kw, st in SUBTYPE_RULES:
        if kw in name:
            return st
    return "服飾"


def get_json(url, params=None, retries=4):
    for i in range(retries):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=25)
            return r.json()
        except Exception:
            time.sleep(2 * (i + 1))
    return None


def fix_size_key(s):
    return str(s).replace(".", "-").replace("/", "／")


def main():
    wb = openpyxl.load_workbook(XLSX, data_only=True)
    rows = [r for r in wb["商品"].iter_rows(min_row=2, values_only=True)]
    print(f"Excel 共 {len(rows)} 列")

    # 1. 用日文名稱搜尋,挑出名稱完全相同、價格(原價或特價)等於感謝價的候選
    names = sorted({r[1] for r in rows})

    def search(n):
        time.sleep(0.1)
        j = get_json(API, {"q": n, "queryRelaxationFlag": "true", "limit": 100, "offset": 0, "httpFailure": "true"})
        return n, (j or {}).get("result", {}).get("items", [])

    with ThreadPoolExecutor(4) as ex:
        found = dict(ex.map(search, names))

    cand = {}  # productId -> (搜尋結果 item, Excel 列)
    for r in rows:
        for it in found.get(r[1], []):
            if it["name"] != r[1]:
                continue
            p = it["prices"]
            vals = {(p.get("base") or {}).get("value"), (p.get("promo") or {}).get("value")}
            if r[4] in vals and it["productId"] not in cand:
                cand[it["productId"]] = (it, r)
    print(f"名稱+價格吻合的候選商品代碼:{len(cand)}")

    # 2. 抓詳細頁(顏色/尺寸/庫存/限期標記)
    def detail(pid):
        time.sleep(0.1)
        j = get_json(f"{API}/{pid}", {"withPrices": "true", "withStocks": "true", "httpFailure": "true"})
        return pid, (j.get("result") if j and j.get("status") == "ok" else None)

    with ThreadPoolExecutor(4) as ex:
        det = dict(ex.map(detail, list(cand)))

    def has_limited_flag(res):
        if not res:
            return False
        return any(
            f.get("code") == "limitedOffer"
            for l2 in res["l2s"] for f in (l2.get("flags") or {}).get("priceFlags", [])
        )

    flagged = {p for p, r in det.items() if has_limited_flag(r)}
    # 官網沒標「期間限定」旗標、但 Excel 有列的(名稱+價格組合沒有任何有標旗標的商品代碼),
    # 照 Excel 為準納入,但會在摘要裡列出來讓老闆知道。
    excel_counts = collections.Counter((r[1], r[4]) for r in rows)
    got = collections.Counter((cand[p][0]["name"], cand[p][1][4]) for p in flagged)
    unflagged_keys = [k for k, v in excel_counts.items() if got.get(k, 0) < v]
    extra = []
    for k in unflagged_keys:
        pool = sorted(p for p in cand if (cand[p][0]["name"], cand[p][1][4]) == k and p not in flagged)
        extra.extend(pool[: excel_counts[k] - got.get(k, 0)])
    use_ids = sorted(flagged | set(extra))
    print(f"採用商品代碼:{len(use_ids)}(官網標有 11/26 限期價 {len(flagged)} + Excel 有列但官網沒標旗標 {len(extra)})")

    # 3. 對照官網資料庫現有 UNIQLO 商品(用 link 裡的商品代碼比對)
    existing = json.load(urllib.request.urlopen(DB + '/daigou-products-v1.json?orderBy="brand"&equalTo="UNIQLO"'))
    existing = list(existing.values()) if isinstance(existing, dict) else existing
    by_pid = {}
    for p in existing:
        m = re.search(r"/products/([^/]+)/", p.get("link") or "")
        if m:
            by_pid[m.group(1)] = p

    def build_colors(pid):
        res = det.get(pid)
        item = cand[pid][0]
        colors = {}
        images = (res or item).get("images", {}).get("main", {}) or item.get("images", {}).get("main", {})
        if res:
            for l2 in res["l2s"]:
                c = l2.get("color") or {}
                code = c.get("displayCode")
                name = c.get("name") or code or "-"
                e = colors.setdefault(code, {"name": name, "sizes": [], "stock": {}, "_code": code})
                sz = fix_size_key((l2.get("size") or {}).get("name") or "-")
                if sz not in e["stock"]:
                    e["sizes"].append(sz)
                e["stock"][sz] = max(e["stock"].get(sz, 0), 1 if l2.get("sales") else 0)
        else:
            # 官網詳細頁暫時回傳伺服器錯誤:用搜尋結果補顏色/尺寸/圖片,庫存未知,
            # 先一律當作有貨(等每日同步下一次就會校正)。
            sizes = [fix_size_key(s.get("name")) for s in item.get("sizes", [])]
            for c in item["colors"]:
                colors[c["displayCode"]] = {
                    "name": c["name"], "sizes": sizes[:], "stock": {s: 1 for s in sizes}, "_code": c["displayCode"],
                }
        out = []
        for code, e in colors.items():
            img = (images.get(code) or {}).get("image")
            if img:
                e["image"] = img
            e.pop("_code")
            out.append(e)
        return out

    updates, new_groups = [], collections.OrderedDict()
    for pid in use_ids:
        item, row = cand[pid]
        sale_jpy, twd = row[4], row[6]
        orig_jpy = row[3]
        gender = (det.get(pid) or item).get("genderName")
        if pid in by_pid:
            p = by_pid[pid]
            updates.append({
                "id": p["id"], "productId": pid, "name": p["name"], "oldJpy": p.get("jpy"),
                "jpy": sale_jpy, "twdOverride": twd, "originalJpy": orig_jpy,
                "gender": GENDER_LABEL.get(gender, gender),
            })
        else:
            key = (item["name"], gender, sale_jpy)
            g = new_groups.setdefault(key, {"pids": [], "twd": twd, "orig": orig_jpy})
            g["pids"].append(pid)

    now = int(time.time() * 1000)
    new_products = []
    for n, ((name, gender, sale_jpy), g) in enumerate(new_groups.items()):
        subtype = guess_subtype(name)
        colors, seen = [], set()
        for pid in g["pids"]:
            for c in build_colors(pid):
                nm = c["name"]
                if nm in seen:  # 不同商品代碼出現同名顏色:加上顏色代碼區分,避免選項重複
                    nm = f"{nm} ({pid.split('-')[0]})"
                    c["name"] = nm
                seen.add(nm)
                colors.append(c)
        label = GENDER_LABEL.get(gender, gender)
        desc = f"{label}・感謝祭限定價 ¥{sale_jpy:,}"
        if g["orig"]:
            desc += f"(原價 ¥{g['orig']:,})"
        desc += "・至 11/26"
        first = g["pids"][0]
        # 同一個日文名稱常有男款/女款/童裝多張卡,名稱後面加上性別才分得出來
        # (男女兼用不加,官網本來就是同一件)。
        display_name = f"{name}({label})" if gender in ("MEN", "WOMEN", "KIDS", "BABY") else name
        prod = {
            "id": f"p_uniqlokss_{now}_{n}",
            "addedAt": now,
            "name": display_name,
            "brand": "UNIQLO",
            "country": "JP",
            "subtype": subtype,
            "jpy": sale_jpy,
            "twdOverride": g["twd"],
            "weight": WEIGHT_BY_SUBTYPE.get(subtype, 0.3),
            "saleType": "instock",
            "hidden": False,
            "desc": desc,
            "link": f"https://www.uniqlo.com/jp/ja/products/{first}/00",
            "image": next((c["image"] for c in colors if c.get("image")), None),
            "colors": colors,
            "campaign": CAMPAIGN,
            "saleEnd": SALE_END,
        }
        if not prod["image"]:
            prod.pop("image")
        if len(g["pids"]) > 1:
            # 多個商品代碼合併成同一張卡:每日同步(sync_uniqlo)只看得到 link 那一個
            # 商品代碼,會把其他顏色洗掉,所以合併卡要排除在同步之外。
            prod["mergedProductIds"] = g["pids"]
        new_products.append(prod)

    # 試匯入的 3 筆:一張單一商品代碼的新卡、一張合併多商品代碼(多顏色)的新卡、
    # 一件更新既有商品價格,涵蓋三種情況。其餘在「rest」階段才匯入。
    def pick(pred):
        return next(p["id"] for p in new_products if pred(p))
    trial = {
        "new": [
            pick(lambda p: p["name"] == "パフテックジャケット(男款)"),
            pick(lambda p: p["name"] == "フランネルシャツ" and len(p.get("mergedProductIds", [])) > 1),
        ],
        "updates": [u["id"] for u in updates if u["name"] == "スウェットオーバーサイズプルパーカ"][:1],
    }
    result = {
        "campaign": CAMPAIGN, "saleEnd": SALE_END, "trial": trial,
        "updates": updates, "new": new_products,
        "unflaggedProductIds": extra,
        "detailFailedProductIds": sorted(p for p in use_ids if not det.get(p)),
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)

    n_colors = sum(len(p["colors"]) for p in new_products)
    no_img = sum(1 for p in new_products if "image" not in p)
    merged = sum(1 for p in new_products if "mergedProductIds" in p)
    print(f"\n更新既有商品:{len(updates)} 件")
    print(f"新增商品卡:{len(new_products)} 張(合併多商品代碼的 {merged} 張,共 {n_colors} 個顏色選項,沒圖片的 {no_img} 張)")
    print("種類分佈:", dict(collections.Counter(p["subtype"] for p in new_products)))
    print("官網沒標限期旗標(照 Excel 納入):", extra)
    print("官網詳細頁暫時失敗:", result["detailFailedProductIds"])
    print(f"已輸出 {OUT}")


if __name__ == "__main__":
    main()
