# -*- coding: utf-8 -*-
"""
一次性:把 GU 感謝祭(2026-11,App 會員特別價,至 11/26)商品匯入官網
------------------------------------------------------------
讀 prepare_gu_kanshasai.py 產生的 gu_kanshasai_import.json:
  - updates:站上已經有的 GU 商品 -> 價格改感謝價(jpy / twdOverride),舊日幣價記在 campaignOrigJpy
    (活動結束可還原),加 campaign / saleEnd 活動標記,名稱換成「日文原名 中文(性別)」
  - new:站上還沒有的 -> 新增商品卡(中文名稱見 gu_zh_names.py)
寫入走 sync_stock.merge_and_save()(整包合併,不會蓋掉別的同步)。重跑安全:已經匯入過的會略過。

用法(GitHub Actions 手動觸發):One-off: import GU kanshasai
"""

import json
import sys

from gu_zh_names import display_name
from sync_stock import load_products_by_brand, merge_and_save, firebase_app

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

DATA_FILE = "gu_kanshasai_import.json"


def main():
    with open(DATA_FILE, encoding="utf-8") as f:
        data = json.load(f)
    campaign, sale_end = data["campaign"], data["saleEnd"]

    firebase_app()
    gu = load_products_by_brand("GU")
    by_id = {p["id"]: p for p in gu}
    existing_links = {p.get("link") for p in gu}

    to_save = []
    added = skipped_new = 0
    for p in data["new"]:
        if p["id"] in by_id or p.get("link") in existing_links:
            skipped_new += 1
            continue
        name = display_name(p["nameJa"], p["_gender"])
        assert name, f"缺中文名稱:{p['nameJa']}"
        p["name"] = name
        p.pop("_gender", None)
        p.pop("_pid", None)
        to_save.append(p)
        added += 1
    print(f"新增:{added} 張(已存在而跳過 {skipped_new} 張)")

    updated = skipped_upd = missing = 0
    for u in data["updates"]:
        p = by_id.get(u["id"])
        if not p:
            print(f"  警告:找不到既有商品 {u['id']}({u['name']}),略過")
            missing += 1
            continue
        if p.get("campaign") == campaign:
            skipped_upd += 1
            continue
        name = display_name(u["nameJa"], u["gender"])
        assert name, f"缺中文名稱:{u['nameJa']}"
        p.setdefault("campaignOrigJpy", p.get("jpy"))
        p["jpy"] = u["jpy"]
        p["twdOverride"] = u["twdOverride"]
        p["campaign"] = campaign
        p["saleEnd"] = sale_end
        p["nameJa"] = u["nameJa"]
        p["name"] = name
        to_save.append(p)
        updated += 1
    print(f"更新價格:{updated} 件(已更新過 {skipped_upd}、找不到 {missing})")

    if not to_save:
        print("沒有需要寫入的東西。")
        return
    merge_and_save(to_save)
    print(f"完成!共寫入 {len(to_save)} 件。")


if __name__ == "__main__":
    main()
