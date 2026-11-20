# -*- coding: utf-8 -*-
"""
一次性:上架 UNIQLO「極暖 HEATTECH 喀什米爾混紡羅紋亨利領 T 恤(女款)」(E491270-000)
------------------------------------------------------------
客人傳來影片截圖問有沒有這件發熱衣(2026-11-20),老闆指示馬上上架。
  - 顏色/尺寸/圖片/庫存全部讀官網(詳細頁 + /stock 真實庫存),LIGHT GRAY 放第一個
    (客人要的色,也是商品卡預設顯示的顏色)
  - 日幣價 ¥3,990,台幣賣價照老闆的價目表(¥3,990 = 1,050)固定寫在 twdOverride
  - 不是感謝祭商品,沒有 campaign 欄位;之後由每日同步(sync_uniqlo)接手更新庫存
重跑安全:已經上架過(link 裡有同樣商品代碼)就不會重複新增。
"""

import re
import sys
import time

import requests

from sync_stock import firebase_app, load_products_by_brand, merge_and_save

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

PID = "E491270-000"
API = "https://www.uniqlo.com/jp/api/commerce/v5/ja/products"
HEADERS = {"x-fr-clientid": "uq.jp.web-spa", "User-Agent": "Mozilla/5.0"}
TWD = 1050
FIRST_COLOR = "02"  # LIGHT GRAY


def fix_size_key(s):
    return str(s).replace(".", "-").replace("/", "／")


def main():
    firebase_app()
    for p in load_products_by_brand("UNIQLO"):
        if re.search(r"/products/" + re.escape(PID) + r"/", p.get("link") or ""):
            print(f"已經上架過了:{p.get('name')},不重複新增。")
            return

    d = requests.get(f"{API}/{PID}", params={"withPrices": "true", "withStocks": "true", "httpFailure": "true"},
                     headers=HEADERS, timeout=25).json()
    s = requests.get(f"{API}/{PID}/stock", headers=HEADERS, timeout=25).json()
    assert d.get("status") == "ok" and s.get("status") == "ok", "官網資料抓取失敗"
    res, st = d["result"], s["result"]
    jpy = res["l2s"][0]["prices"]["base"]["value"]
    assert jpy == 3990, f"官網價格變了:{jpy}"

    colors = {}
    for l2 in res["l2s"]:
        c = l2["color"]
        e = colors.setdefault(c["displayCode"], {"name": c["name"], "sizes": [], "stock": {}})
        sz = fix_size_key(l2["size"]["name"])
        if sz not in e["stock"]:
            e["sizes"].append(sz)
        info = st.get(l2["l2Id"]) or {}
        ok = bool(l2.get("sales")) and info.get("statusCode") in ("IN_STOCK", "LOW_STOCK") and (info.get("quantity") or 0) > 0
        e["stock"][sz] = max(e["stock"].get(sz, 0), 1 if ok else 0)
    images = res["images"]["main"]
    ordered = []
    for code in sorted(colors, key=lambda k: (k != FIRST_COLOR, k)):
        e = colors[code]
        img = (images.get(code) or {}).get("image")
        if img:
            e["image"] = img
        ordered.append(e)

    now = int(time.time() * 1000)
    prod = {
        "id": f"p_uniqlo3_{now}_0",
        "addedAt": now,
        "name": "極暖ヒートテックカシミヤブレンドリブヘンリーネックT HEATTECH 極暖 喀什米爾混紡羅紋亨利領T恤(女款)",
        "nameJa": "極暖ヒートテックカシミヤブレンドリブヘンリーネックT",
        "brand": "UNIQLO",
        "country": "JP",
        "subtype": "內著",
        "jpy": jpy,
        "twdOverride": TWD,
        "weight": 0.2,
        "saleType": "instock",
        "hidden": False,
        "desc": "女款・HEATTECH 極暖 喀什米爾混紡・羅紋亨利領(胸前釦子)",
        "link": f"https://www.uniqlo.com/jp/ja/products/{PID}/00",
        "image": ordered[0].get("image") or next((c["image"] for c in ordered if c.get("image")), None),
        "colors": ordered,
    }
    if not prod["image"]:
        prod.pop("image")
    for c in ordered:
        print(f"  {c['name']}: 有貨尺寸 {[k for k, v in c['stock'].items() if v]}")
    merge_and_save([prod])
    print(f"完成!已上架 {prod['name']}(¥{jpy} / NT${TWD}),id = {prod['id']}")


if __name__ == "__main__":
    main()
