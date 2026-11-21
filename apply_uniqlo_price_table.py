# -*- coding: utf-8 -*-
"""
一次性:UNIQLO 感謝祭商品改用老闆指定的「日幣感謝價 -> 台幣售價」價目表(2026-11-20)
------------------------------------------------------------
取代之前的「改成去年價 / 成本×1.2」規則:每張感謝祭商品卡,依匯入檔裡的日幣感謝價
(uniqlo_kanshasai_import.json,不用資料庫的 jpy,因為每日同步偶爾會把少數卡改回官網原價)
查下面的價目表,直接寫進 twdOverride。價目表以外的日幣價不處理並印出警告。

舊價格:Excel 建議售價另存在 campaignTwdExcel(沒有才補,不會蓋掉已存的),要還原時
把 twdOverride 改回它即可。寫入走 merge_and_save(整包合併,不會蓋掉別的同步)。

用法:
  python apply_uniqlo_price_table.py report   # 只看報告,不寫入
  python apply_uniqlo_price_table.py apply    # 寫入(走 GitHub Actions)
"""

import json
import sys
import urllib.request

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

CAMPAIGN = "uniqlo-kanshasai-2026"
DB = "https://shibago-4dd3c-default-rtdb.asia-southeast1.firebasedatabase.app"

PRICE_TABLE = {
    390: 100,
    790: 220,
    990: 299,
    1290: 350,
    1990: 499,
    2990: 745,  # 2026-11-21 老闆指示:¥2,990 全部改賣 745(原 725)
    3990: 1050,
    5990: 1600,
    7990: 2100,
    9990: 2650,
    11900: 3150,
    12900: 3300,
    13900: 3750,
    15900: 4200,
}


def main():
    mode = (sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
    if mode not in ("report", "apply"):
        print("用法:python apply_uniqlo_price_table.py report|apply")
        sys.exit(1)

    with open("uniqlo_kanshasai_import.json", encoding="utf-8") as f:
        imp = json.load(f)
    sale_jpy_by_id = {u["id"]: u["jpy"] for u in imp["updates"]}
    sale_jpy_by_id.update({p["id"]: p["jpy"] for p in imp["new"]})

    if mode == "apply":
        from sync_stock import load_products_by_brand, merge_and_save, firebase_app
        firebase_app()
        uniqlo = load_products_by_brand("UNIQLO")
    else:
        raw = json.load(urllib.request.urlopen(DB + '/daigou-products-v1.json?orderBy="brand"&equalTo="UNIQLO"'))
        uniqlo = list(raw.values()) if isinstance(raw, dict) else raw
    # 不屬於感謝祭、但老闆指定也照價目表賣的商品(id -> 日幣價):2026-11 新上架的 HEATTECH 高領/亨利領
    extra_jpy = {"p_uniqlo3_1795181728265_0": 3990, "p_uniqlo3_1795248263245_1": 2990}
    cards = [p for p in uniqlo if p.get("campaign") == CAMPAIGN or p.get("id") in extra_jpy]
    sale_jpy_by_id.update(extra_jpy)
    print(f"感謝祭商品卡 {len(cards)} 張")

    to_save, unchanged, unknown = [], 0, []
    up = down = 0
    for p in cards:
        jpy = sale_jpy_by_id.get(p["id"])
        if jpy not in PRICE_TABLE:
            unknown.append((p["name"], jpy))
            continue
        target = PRICE_TABLE[jpy]
        cur = p.get("twdOverride")
        if cur == target:
            unchanged += 1
            continue
        if p.get("campaign") == CAMPAIGN:
            p.setdefault("campaignTwdExcel", cur)
        p["twdOverride"] = target
        to_save.append(p)
        if target > cur:
            up += 1
        else:
            down += 1
    for n, j in unknown:
        print(f"  警告:價目表沒有 ¥{j}:{n}(不動)")
    print(f"統計:要改 {len(to_save)} 張(變貴 {up}、變便宜 {down}),原本就一樣 {unchanged} 張,價目表沒有 {len(unknown)} 張")

    if mode == "report":
        print("(report 模式:沒有寫入)")
        return
    if not to_save:
        print("沒有需要寫入的東西。")
        return
    merge_and_save(to_save)
    print(f"完成!已寫入 {len(to_save)} 張卡。")


if __name__ == "__main__":
    main()
