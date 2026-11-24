# -*- coding: utf-8 -*-
"""一次性:星巴克 x BEAMS 的 T 恤/大學 T/皮外套加上 XS 尺寸(老闆要接 XS 預購)
官網說 XS 只在 BEAMS 實體店販售,所以要去實體店買;重跑安全。"""
import sys

from sync_stock import load_products, merge_and_save

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

LINKS = {
    "https://menu.starbucks.co.jp/4524785660083",  # 短袖 T 恤
    "https://menu.starbucks.co.jp/4524785660120",  # 圓領大學 T
    "https://menu.starbucks.co.jp/4524785660038",  # 皮外套
}
NOTE = "XS 僅 BEAMS 實體店販售"


def main():
    changed = []
    for p in load_products():
        if p.get("brand") != "STARBUCKS x BEAMS" or p.get("link") not in LINKS:
            continue
        for c in p.get("colors") or []:
            if "XS" not in c["sizes"]:
                c["sizes"] = ["XS"] + c["sizes"]
        if NOTE not in (p.get("desc") or ""):
            p["desc"] = (p.get("desc") or "") + "・" + NOTE
        print(f"  {p['name']}: {p['colors'][0]['sizes']}")
        changed.append(p)
    if changed:
        merge_and_save(changed)
    print(f"完成,更新 {len(changed)} 件")


if __name__ == "__main__":
    main()
