# -*- coding: utf-8 -*-
"""
一次性(可重跑):核對 UNIQLO 感謝祭商品的「真實庫存」,把沒貨的尺寸/顏色改掉
------------------------------------------------------------
背景:
  匯入時(prepare_uniqlo_kanshasai.py)庫存只看詳細頁的 l2.sales(可販售旗標),
  那不等於「有貨」;官網另有 /products/{商品代碼}/stock 端點,每個 l2 回傳
  statusCode(IN_STOCK / LOW_STOCK / STOCK_OUT)跟 quantity,這才是真庫存。
  另外有 3 個商品代碼匯入時詳細頁回 500,庫存是「一律當有貨」。
  合併多顏色的卡(mergedProductIds)還被每日同步排除,不會自動校正。

做法:
  對每張感謝祭商品卡(campaign == uniqlo-kanshasai-2026):
    - 取出它涵蓋的所有商品代碼(mergedProductIds,或 link 裡的那一個)
    - 抓 詳細頁(l2 -> 顏色/尺寸)+ /stock(l2 -> 庫存)
    - 逐顏色逐尺寸比對:有貨 -> 1、沒貨 -> 0(跟每日同步一樣的寫法,尺寸/顏色
      保留但標成缺貨,前台會顯示缺貨;整張卡都沒貨會被前台自動隱藏)
    - 卡裡有、但官網已經沒有的尺寸 -> 標缺貨;官網有貨、卡裡沒有的尺寸 -> 補上
    - 官網已經整個下架(詳細頁 404)的顏色 -> 全部標缺貨
  不動價格、名稱、圖片。

用法:
  python check_uniqlo_kanshasai_stock.py report [all]  # 只看報告,不寫入(用公開讀取,不需要金鑰);加 all = 全部 UNIQLO 商品
  python check_uniqlo_kanshasai_stock.py apply    # 寫入(要 service account,走 GitHub Actions)
"""

import json
import sys
import time
import urllib.request
import re
from concurrent.futures import ThreadPoolExecutor

import requests

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

CAMPAIGN = "uniqlo-kanshasai-2026"
API = "https://www.uniqlo.com/jp/api/commerce/v5/ja/products"
HEADERS = {"x-fr-clientid": "uq.jp.web-spa", "User-Agent": "Mozilla/5.0"}
DB = "https://shibago-4dd3c-default-rtdb.asia-southeast1.firebasedatabase.app"
BRAND = "UNIQLO"


def fix_size_key(s):
    return str(s).replace(".", "-").replace("/", "／")


def get_json(url, params=None, retries=4):
    for i in range(retries):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=25)
            if r.status_code == 404:
                return {"status": "notfound"}
            return r.json()
        except Exception:
            time.sleep(2 * (i + 1))
    return None


def pids_of(card):
    if card.get("mergedProductIds"):
        return list(card["mergedProductIds"])
    m = re.search(r"/products/([^/]+)/", card.get("link") or "")
    return [m.group(1)] if m else []


def live_stock(pid):
    """回傳 (狀態, {色碼: {"name":..., "sizes": {尺寸: 0/1}}});狀態 ok / gone / error"""
    d = get_json(f"{API}/{pid}", {"withPrices": "true", "withStocks": "true", "httpFailure": "true"})
    s = get_json(f"{API}/{pid}/stock")
    if d is None or s is None:
        return "error", {}
    if d.get("status") == "notfound" or (d.get("status") not in ("ok", None) and s.get("status") != "ok"):
        return ("gone", {}) if d.get("status") == "notfound" else ("error", {})
    if d.get("status") != "ok" or s.get("status") != "ok":
        return "error", {}
    stocks = s.get("result") or {}
    out = {}
    for l2 in d["result"]["l2s"]:
        c = l2.get("color") or {}
        code = c.get("displayCode")
        e = out.setdefault(code, {"name": c.get("name") or code, "sizes": {}})
        sz = fix_size_key((l2.get("size") or {}).get("name") or "-")
        st = stocks.get(l2.get("l2Id")) or {}
        ok = 1 if (l2.get("sales") and st.get("statusCode") in ("IN_STOCK", "LOW_STOCK") and (st.get("quantity") or 0) > 0) else 0
        e["sizes"][sz] = max(e["sizes"].get(sz, 0), ok)
    return "ok", out


def image_code(color):
    """圖檔網址 .../jpgoods_62_491116_3x4.jpg -> (色碼 '62', 商品代碼 'E491116-000')"""
    m = re.search(r"goods_(\d+)_(\d+)_", color.get("image") or "")
    return (m.group(1), f"E{m.group(2)}") if m else (None, None)


def base_name(name):
    # 重複顏色名稱修正時會在後面加 (色碼) 或流水號,比對官網前先拿掉
    return re.sub(r"\s*[（(][^()（）]*[)）]\s*$", "", name or "").strip()


def main():
    mode = (sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
    if mode not in ("report", "apply"):
        print("用法:python check_uniqlo_kanshasai_stock.py report|apply")
        sys.exit(1)

    # 第三個參數可以指定品牌(UNIQLO 預設 / GU):GU 跟 UNIQLO 是同一套官網 API,只是網域跟 client id 不同
    global API, HEADERS, BRAND
    BRAND = (sys.argv[3].strip().upper() if len(sys.argv) > 3 else "UNIQLO")
    if BRAND == "GU":
        API = "https://www.gu-global.com/jp/api/commerce/v5/ja/products"
        HEADERS = {"x-fr-clientid": "gu.jp.web-spa", "User-Agent": "Mozilla/5.0"}

    if mode == "apply":
        from sync_stock import load_products_by_brand, merge_and_save, firebase_app
        firebase_app()
        uniqlo = load_products_by_brand(BRAND)
    else:
        raw = json.load(urllib.request.urlopen(DB + f'/daigou-products-v1.json?orderBy="brand"&equalTo="{BRAND}"'))
        uniqlo = list(raw.values()) if isinstance(raw, dict) else raw
    scope_all = len(sys.argv) > 2 and sys.argv[2].strip().lower() == "all"  # all = 全部該品牌商品卡,不只感謝祭
    cards = [p for p in uniqlo if (p.get("brand") == BRAND if scope_all else p.get("campaign") == CAMPAIGN)]
    print(f"感謝祭商品卡:{len(cards)} 張")

    all_pids = sorted({pid for c in cards for pid in pids_of(c)})
    print(f"涵蓋商品代碼:{len(all_pids)} 個,逐一抓官網庫存…")

    def fetch(pid):
        time.sleep(0.15)
        return pid, live_stock(pid)

    with ThreadPoolExecutor(4) as ex:
        live = dict(ex.map(fetch, all_pids))
    bad = [p for p, (st, _) in live.items() if st == "error"]
    gone = [p for p, (st, _) in live.items() if st == "gone"]
    print(f"官網抓取失敗(略過、不動):{len(bad)} 個 {bad}")
    print(f"官網已下架:{len(gone)} 個 {gone}")

    changed_cards = []
    n_size_off = n_size_on = n_color_off = n_unmatched = n_all_out = 0
    lines = []
    for card in cards:
        pids = pids_of(card)
        if any(live[p][0] == "error" for p in pids):
            lines.append(f"  略過(官網暫時抓不到):{card['name']} {pids}")
            continue
        # 這張卡涵蓋的所有顏色(色碼 -> 官網資料);不同商品代碼可能有同色碼,所以也要用商品代碼區分
        pool = []  # (商品代碼, 色碼, 資料)
        for p in pids:
            for code, e in live[p][1].items():
                pool.append((p, code, e))
        before = json.dumps(card.get("colors"), ensure_ascii=False, sort_keys=True)
        for color in card.get("colors", []):
            # 比對順序(2026-11-20 改):1. 顏色名稱 2. 名稱有多個同名時用圖檔色碼分辨 3. 名稱找不到再用
            # 圖檔色碼。不能把圖檔色碼放第一——GU/舊 UNIQLO 商品卡有些顏色掛的圖檔是別的顏色的
            # (例如 GRAY 掛著 NAVY 的圖),先用圖檔會把庫存對到錯的顏色。
            nm = color.get("name") or ""
            code, img_pid = image_code(color)
            cand = [x for x in pool if x[2]["name"] == nm]
            if not cand:
                bn = re.sub(r"\s+\d+$", "", base_name(nm))  # 去掉重複顏色修正時加的 (色碼)/流水號
                cand = [x for x in pool if x[2]["name"] == bn]
            if len(cand) > 1 and code:
                narrowed = [x for x in cand if x[1] == code and x[0].split("-")[0] == img_pid]
                if narrowed:
                    cand = narrowed
            gone_color = False
            if not cand:
                by_img = [x for x in pool if code and x[1] == code and x[0].split("-")[0] == img_pid]
                if by_img:
                    cand = by_img[:1]
                elif pool:
                    gone_color = True  # 官網這個商品現在已經沒有這個顏色 -> 該顏色下架,全部標缺貨
                else:
                    n_unmatched += 1
                    lines.append(f"  對不到官網顏色(不動):{card['name']} / {color.get('name')} {pids}")
                    continue
            if gone_color:
                sizes_live = {}
            elif len(cand) > 1:
                # 官網有好幾個同名顏色又分辨不出來(例如兩個 GREEN):各尺寸取「任一個有貨就算有貨」
                sizes_live = {}
                for x in cand:
                    for sz, v in x[2]["sizes"].items():
                        sizes_live[sz] = max(sizes_live.get(sz, 0), v)
            else:
                sizes_live = cand[0][2]["sizes"]
            stock = dict(color.get("stock") or {}) if isinstance(color.get("stock"), dict) else {}
            sizes = list(color.get("sizes") or [])
            had_stock = any(v > 0 for v in stock.values())
            for sz in sizes:
                new = sizes_live.get(sz, 0)
                old = 1 if (stock.get(sz) or 0) > 0 else 0
                if old and not new:
                    n_size_off += 1
                elif new and not old:
                    n_size_on += 1
                stock[sz] = new
            for sz, v in sizes_live.items():  # 官網有、卡上沒列的尺寸補上
                if sz not in stock:
                    sizes.append(sz)
                    stock[sz] = v
            if had_stock and not any(v > 0 for v in stock.values()):
                n_color_off += 1
            color["sizes"], color["stock"] = sizes, stock
        if not any(v > 0 for c in card.get("colors", []) for v in (c.get("stock") or {}).values()):
            n_all_out += 1
            lines.append(f"  整張卡都沒貨:{card['name']}")
        if json.dumps(card.get("colors"), ensure_ascii=False, sort_keys=True) != before:
            changed_cards.append(card)

    print("\n".join(lines))
    print(f"\n統計:要改的卡 {len(changed_cards)} 張;尺寸 有貨->缺貨 {n_size_off} 個、缺貨->有貨 {n_size_on} 個;"
          f"整個顏色變缺貨 {n_color_off} 個;對不到的顏色 {n_unmatched} 個;整張卡全缺貨 {n_all_out} 張")

    if mode == "report":
        print("(report 模式:沒有寫入)")
        return
    if not changed_cards:
        print("庫存都已經正確,沒有需要寫入的東西。")
        return
    merge_and_save(changed_cards)
    print(f"完成!已寫入 {len(changed_cards)} 張卡。")


if __name__ == "__main__":
    main()
