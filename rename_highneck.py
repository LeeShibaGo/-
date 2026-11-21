# -*- coding: utf-8 -*-
"""一次性:把 E493521 高領 T 的中文名稱改成「花花高領T」(2026-11-21 老闆指示),日文原名不動。"""
import sys

from sync_stock import firebase_app, load_products_by_brand, merge_and_save

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

PID = "p_uniqlo3_1795248263245_1"
NEW_NAME = "極暖ヒートテックカシミヤブレンドリブハイネックT 花花高領T"

firebase_app()
for p in load_products_by_brand("UNIQLO"):
    if p.get("id") == PID:
        print(f"舊名稱:{p['name']}")
        p["name"] = NEW_NAME
        merge_and_save([p])
        print(f"完成!新名稱:{NEW_NAME}")
        break
else:
    print("找不到商品")
