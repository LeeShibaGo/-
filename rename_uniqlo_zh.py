# -*- coding: utf-8 -*-
"""
一次性:把官網上所有 UNIQLO 商品的名稱加上中文翻譯(2026-11-20 老闆要求)
------------------------------------------------------------
名稱格式:「日文原名 中文名」,男款/女款/童裝/嬰幼兒的卡片後面保留原本的
「(男款)」之類標記。原本的日文名稱存在 nameJa 欄位,所以可重跑(永遠從
nameJa 重新組,不會越加越長),要還原也只要把 name 改回 nameJa。

名稱本來就沒有日文假名的(例如已經是中文的「AIRism棉質圓領T恤(短袖)」、
UNIQLO x NEEDLES 那件)不動。

已知副作用:官網「已售 N 件」對沒有 productId 的舊訂單是用商品名稱比對的
(index.html computeSoldMaps),改名後這些舊訂單不會再算進已售件數;
新訂單都有 productId,不受影響。

執行方式(GitHub Actions):Actions -> "One-off: rename UNIQLO to zh" -> Run workflow
"""
import re
import sys

from sync_stock import load_products_by_brand, merge_and_save, firebase_app
from uniqlo_zh_names import full_name

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

SUFFIX = re.compile(r"\((男款|女款|童裝|嬰幼兒)\)$")


def main():
    firebase_app()
    items = load_products_by_brand("UNIQLO")
    changed = []
    for p in items:
        cur = p.get("name") or ""
        ja = p.get("nameJa")
        suffix = ""
        if not ja:
            m = SUFFIX.search(cur)
            suffix = m.group(0) if m else ""
            ja = SUFFIX.sub("", cur)
        else:
            m = SUFFIX.search(cur)
            suffix = m.group(0) if m else ""
        new_name = full_name(ja) + suffix
        if new_name != cur or p.get("nameJa") != ja:
            if new_name != cur:
                print(f"  {cur}  ->  {new_name}")
            p["nameJa"] = ja
            p["name"] = new_name
            changed.append(p)
    print(f"UNIQLO 共 {len(items)} 件,需要更新名稱 {len(changed)} 件")
    if changed:
        merge_and_save(changed)
    print("完成!")


if __name__ == "__main__":
    main()
