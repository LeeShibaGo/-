# -*- coding: utf-8 -*-
"""
一次性:修正感謝祭商品卡裡「同名顏色」(官網同一款有好幾個不同色號,顏色名稱都叫
PINK/BLUE...)。顏色選單是用名稱當 key,重名會選不到後面那幾個。
做法:同一張卡裡名稱(去掉舊的「 (E123456)」後綴)重複的顏色,全部改成
「名稱 色號」,色號從該顏色圖片檔名(jpgoods_11_...)取。
"""
import re
import sys
import collections

from sync_stock import load_products_by_brand, merge_and_save, firebase_app

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

CODE = re.compile(r"jpgoods_(\d+)_")
OLD_SUFFIX = re.compile(r"\s*\(E\d+\)$")


def main():
    firebase_app()
    items = [p for p in load_products_by_brand("UNIQLO") if p.get("campaign") == "uniqlo-kanshasai-2026"]
    changed = []
    for p in items:
        cols = p.get("colors") or []
        base = [OLD_SUFFIX.sub("", c.get("name") or "") for c in cols]
        counts = collections.Counter(base)
        if all(v == 1 for v in counts.values()) and not any(OLD_SUFFIX.search(c.get("name") or "") for c in cols):
            continue
        seq = collections.Counter()
        for c, b in zip(cols, base):
            if counts[b] > 1:
                seq[b] += 1
                m = CODE.search(c.get("image") or "")
                # 沒有圖片(抓不到色號)的顏色用流水號區分
                c["name"] = f"{b} {m.group(1)}" if m else f"{b} {seq[b]}"
            else:
                c["name"] = b
        names = [c["name"] for c in cols]
        if len(set(names)) != len(names):  # 極少數:色號跟流水號撞名,全部改用流水號
            seq = collections.Counter()
            for c, b in zip(cols, base):
                if counts[b] > 1:
                    seq[b] += 1
                    c["name"] = f"{b} {seq[b]}"
            names = [c["name"] for c in cols]
        assert len(set(names)) == len(names), (p["name"], names)
        print(f"  {p['name']}: {names}")
        changed.append(p)
    print(f"修正 {len(changed)} 張卡")
    if changed:
        merge_and_save(changed)


if __name__ == "__main__":
    main()
