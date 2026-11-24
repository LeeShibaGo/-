# -*- coding: utf-8 -*-
"""一次性:星巴克 x BEAMS 三件商品手動定價(老闆指定,寫 twdOverride)
  戒指 NT$6,500、皮革包 NT$7,000、皮外套 NT$23,999。重跑安全。"""
import sys

from sync_stock import load_products, merge_and_save

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

PRICE = {
    "https://menu.starbucks.co.jp/4524785659971": 6500,   # 純銀戒指 (p_starbucks_..._1)
    "https://menu.starbucks.co.jp/4524785660076": 7000,   # 皮革包   (p_starbucks_..._5)
    "https://menu.starbucks.co.jp/4524785660038": 23999,  # 皮外套   (p_starbucks_..._4)
}


def main():
    changed = []
    for p in load_products():
        if p.get("brand") != "STARBUCKS x BEAMS" or p.get("link") not in PRICE:
            continue
        p["twdOverride"] = PRICE[p["link"]]
        print(f"  {p['id']} {p['name']} -> NT${PRICE[p['link']]}")
        changed.append(p)
    if changed:
        merge_and_save(changed)
    print(f"完成,更新 {len(changed)} 件")


if __name__ == "__main__":
    main()
