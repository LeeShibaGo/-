# -*- coding: utf-8 -*-
"""
一次性:把感謝祭商品卡上「被每日同步改回官網原價」的日幣價,改回感謝價
------------------------------------------------------------
問題:少數卡(例如彈性羊毛修身褲)官網的 prices.base 是原價(¥7,990),感謝價(¥2,990)
是限期促銷價,每日同步(sync_uniqlo)會把卡片的 jpy 改回 base,結果商品卡上顯示
「¥7,990 / NT$725」,看起來像標錯價。台幣價是固定價(twdOverride),不受影響。

做法:依匯入檔(uniqlo_kanshasai_import.json)的日幣感謝價,把 jpy 不一致的感謝祭卡改回去;
舊的 jpy 沒有 campaignOrigJpy 的話順便存起來(還原用)。同時 sync_stock.sync_uniqlo 已改成
感謝祭卡不再被同步改價,所以不會再被改回去。

用法:python fix_kanshasai_jpy.py   (走 GitHub Actions)
"""

import json
import sys

from sync_stock import load_products_by_brand, merge_and_save, firebase_app

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

CAMPAIGN = "uniqlo-kanshasai-2026"


def main():
    with open("uniqlo_kanshasai_import.json", encoding="utf-8") as f:
        imp = json.load(f)
    sale = {u["id"]: u["jpy"] for u in imp["updates"]}
    sale.update({p["id"]: p["jpy"] for p in imp["new"]})

    firebase_app()
    cards = [p for p in load_products_by_brand("UNIQLO") if p.get("campaign") == CAMPAIGN]
    fix = []
    for p in cards:
        want = sale.get(p["id"])
        if want and p.get("jpy") != want:
            print(f"  {p['name'][:36]}  ¥{p.get('jpy')} -> ¥{want}")
            p.setdefault("campaignOrigJpy", p.get("jpy"))
            p["jpy"] = want
            fix.append(p)
    print(f"需要修正 {len(fix)} 張(共 {len(cards)} 張感謝祭卡)")
    if fix:
        merge_and_save(fix)
        print(f"完成!已寫入 {len(fix)} 張卡。")


if __name__ == "__main__":
    main()
