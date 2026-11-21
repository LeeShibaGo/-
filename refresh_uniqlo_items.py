# -*- coding: utf-8 -*-
"""
一次性:立刻更新指定 UNIQLO 商品卡的官網真實庫存(跟每日同步 sync_uniqlo 同一套邏輯,
只是只跑指定的幾張卡,不用等整個 UNIQLO 品牌同步跑完)。

用法:python refresh_uniqlo_items.py <商品卡id> [<商品卡id> ...]
(GitHub Actions 手動觸發:One-off: refresh UNIQLO items,id 用空格分開)
"""

import sys

import sync_stock
from sync_stock import firebase_app, load_products_by_brand, sync_uniqlo

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")


def snapshot(card):
    return {c["name"]: dict(c.get("stock") or {}) for c in card.get("colors", [])}


def main():
    ids = sys.argv[1:]
    if not ids:
        print("用法:python refresh_uniqlo_items.py <商品卡id> ...")
        sys.exit(1)
    firebase_app()
    by_id = {p["id"]: p for p in load_products_by_brand("UNIQLO")}
    cards = []
    for i in ids:
        if i not in by_id:
            print(f"找不到商品卡:{i}")
            continue
        cards.append(by_id[i])
    if not cards:
        sys.exit(1)
    before = {c["id"]: snapshot(c) for c in cards}
    sync_uniqlo(cards)  # 內含 merge_and_save
    for c in cards:
        print(f"\n== {c['name']} ¥{c.get('jpy')} ==")
        for color in c.get("colors", []):
            old = before[c["id"]].get(color["name"], {})
            line = []
            for size in color.get("sizes", []):
                n, o = (color.get("stock") or {}).get(size, 0), old.get(size, 0)
                line.append(f"{size}:{'有' if n else '無'}" + ("" if n == o else f"(原{'有' if o else '無'})"))
            print(f"  {color['name']}: " + " ".join(line))


if __name__ == "__main__":
    main()
