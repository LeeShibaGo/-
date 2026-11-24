# -*- coding: utf-8 -*-
"""一次性:星巴克 x BEAMS 的襪子、皮革包商品圖,換成官網專頁的穿搭照(老闆指定)
照片來源:https://www.starbucks.co.jp/starbucks-stand-by-beams/extra05/ (ph_4 襪子、ph_6_1 皮革包)
只動 brand == STARBUCKS x BEAMS 且 link 對得上的這兩件;重跑安全。"""
import sys

from sync_stock import load_products, merge_and_save

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

BASE = "https://www.starbucks.co.jp/starbucks-stand-by-beams/extra05/images/photos/"
NEW = {
    "https://menu.starbucks.co.jp/4524785660212": BASE + "ph_4.webp",    # DRINK-ID 襪子
    "https://menu.starbucks.co.jp/4524785660076": BASE + "ph_6_1.webp",  # 皮革包
}


def main():
    changed = []
    for p in load_products():
        if p.get("brand") != "STARBUCKS x BEAMS" or p.get("link") not in NEW:
            continue
        img = NEW[p["link"]]
        p["image"] = img
        for c in p.get("colors") or []:
            c["image"] = img
        print(f"  {p['name']} -> {img}")
        changed.append(p)
    if changed:
        merge_and_save(changed)
    print(f"完成,更新 {len(changed)} 件")


if __name__ == "__main__":
    main()
