# -*- coding: utf-8 -*-
"""
把 uniqlo_zh_names.py 的中文名稱套進 uniqlo_kanshasai_import.json 的新商品卡
(名稱格式:「日文原名 中文名(男款)」,日文原名另外存在 nameJa)。
只改 JSON,不碰 Firebase。可重跑(以 nameJa 為準,不會越加越長)。
"""
import json
import re

from uniqlo_zh_names import full_name

FILE = "uniqlo_kanshasai_import.json"
SUFFIX = re.compile(r"\((男款|女款|童裝|嬰幼兒)\)$")

with open(FILE, encoding="utf-8") as f:
    data = json.load(f)

changed = 0
for p in data["new"]:
    m = SUFFIX.search(p.get("nameJa") or p["name"])
    suffix = m.group(0) if m else ""
    ja = p.get("nameJa") or SUFFIX.sub("", p["name"])
    p["nameJa"] = ja
    new_name = full_name(ja) + suffix
    if new_name != p["name"]:
        p["name"] = new_name
        changed += 1

with open(FILE, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=1)
print(f"已套用中文名稱:{changed} 張新卡")
