# -*- coding: utf-8 -*-
"""
一次性:立刻更新指定 UNIQLO / GU 商品卡的官網真實庫存與顏色(跟每日同步 sync_uniqlo / sync_gu
同一套邏輯,只是只跑指定的幾張卡,不用等整個品牌同步跑完)。

用法:
  python refresh_uniqlo_items.py <商品卡id> [<商品卡id> ...]   # 指定的卡(UNIQLO 或 GU 都可以)
  python refresh_uniqlo_items.py ALL:UNIQLO                      # 整個 UNIQLO 品牌
  python refresh_uniqlo_items.py ALL:GU                          # 整個 GU 品牌
(GitHub Actions 手動觸發:One-off: refresh UNIQLO items,id 用空格分開)
"""

import sys

from sync_stock import firebase_app, load_products_by_brand, sync_gu, sync_uniqlo

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")


def snapshot(card):
    return {c["name"]: dict(c.get("stock") or {}) for c in card.get("colors", [])}


def main():
    ids = sys.argv[1:]
    if not ids:
        print("用法:python refresh_uniqlo_items.py <商品卡id> ... 或 ALL:UNIQLO / ALL:GU")
        sys.exit(1)
    firebase_app()
    by_brand = {}
    if len(ids) == 1 and ids[0].startswith("ALL:"):
        brand = ids[0].split(":", 1)[1].upper()
        cards = load_products_by_brand(brand)
        by_brand[brand] = cards
    else:
        pool = {p["id"]: p for b in ("UNIQLO", "GU") for p in load_products_by_brand(b)}
        cards = []
        for i in ids:
            if i not in pool:
                print(f"找不到商品卡:{i}")
                continue
            cards.append(pool[i])
        for c in cards:
            by_brand.setdefault(c.get("brand"), []).append(c)
    if not cards:
        sys.exit(1)
    before = {c["id"]: snapshot(c) for c in cards}
    for brand, lst in by_brand.items():
        if brand == "UNIQLO":
            sync_uniqlo(lst)  # 內含 merge_and_save
        elif brand == "GU":
            sync_gu(lst)
        else:
            print(f"不支援的品牌:{brand}")
    changed = 0
    for c in cards:
        old = before[c["id"]]
        new = snapshot(c)
        if old == new:
            continue
        changed += 1
        print(f"\n== {c['name'][:60]} ¥{c.get('jpy')} ==")
        print("  舊顏色:", ", ".join(old.keys()))
        print("  新顏色:", ", ".join(new.keys()))
    print(f"\n共 {len(cards)} 張卡,內容有變 {changed} 張")


if __name__ == "__main__":
    main()
