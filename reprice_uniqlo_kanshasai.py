# -*- coding: utf-8 -*-
"""
一次性:UNIQLO 感謝祭商品依「去年報價」重新定價(2026-11-20 老闆指示)
------------------------------------------------------------
規則(老闆原話):
  1. 今年價(Excel 建議售價)比去年「便宜」的 -> 一律改成去年的賣價
  2. 今年價比去年「貴」的 -> 不動,列出來讓老闆看怎麼處理
  3. 去年沒出現過的商品 -> 一律 成本價 × 1.2
       成本 = 日幣價 × 匯率 + 重量 × 每公斤運費(跟網站既有鞋類的「成本×1.2」同一套算法,
       見 index.html 的 shoeMarginPrice),含運費;算完先四捨五入到整數,再把尾數湊成
       0 或 9(個位 0-4 捨成 0、5-9 進成 9,見 round_09)。去年的賣價是固定值,不再湊尾數。
  去年等於今年的(例如襪子 100)不動。

怎麼對照:用商品名稱(日文原名,去掉顏色後面的說明文字)對去年報價單的編號,
對照表在下面 RULES,每一條都標了去年編號。不確定是不是同款的也照老闆指示套用,
報告裡會列出來。

安全:舊的台幣價(Excel 價)存在 campaignTwdExcel,要還原時把 twdOverride 改回它即可。
寫入走 merge_and_save(整包合併,不會蓋掉別的同步)。

用法:
  python reprice_uniqlo_kanshasai.py report   # 只看報告,不寫入
  python reprice_uniqlo_kanshasai.py apply    # 寫入(走 GitHub Actions)
"""

import json
import sys
import urllib.request

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

CAMPAIGN = "uniqlo-kanshasai-2026"
DB = "https://shibago-4dd3c-default-rtdb.asia-southeast1.firebasedatabase.app"


def base_of(name):
    return (name or "").split(" ")[0].strip()


def is_baby(name):
    return "嬰幼兒" in name


def is_kid(name):
    return "(童裝)" in name or "GIRLS" in name or "BOYS" in name


# (去年編號, 去年賣價, 判斷函式(名稱, 日文原名))
RULES = [
    ("1-A PUFFTECH 外套", 1580, lambda n, b: b == "パフテックジャケット"),
    ("1-B 無縫羽絨外套", 3560, lambda n, b: b == "シームレスダウンパーカ"),
    ("8-C PUFFTECH 可水洗連帽外套(童裝)", 880, lambda n, b: b == "パフテックウォッシャブルパーカ" and not is_baby(n)),
    ("8-E PUFFTECH 可水洗連帽外套(嬰幼兒)", 880, lambda n, b: b == "パフテックウォッシャブルパーカ" and is_baby(n)),
    ("2-A 喀什米爾圓領毛衣", 3000, lambda n, b: b in ("カシミヤクルーネックセーター", "カシミヤクルーネックセーター（長袖）")),
    ("3-A 柔軟針織刷毛圓領T恤", 355, lambda n, b: b == "ソフトニットフリースクルーネックT"),
    ("3-B 寬版連帽上衣、棉褲", 899, lambda n, b: b in ("スウェットオーバーサイズプルパーカ", "スウェットワイドパンツ", "スウェットワイドパンツ/丈長め")),
    ("8-B 長刷毛外套(童裝)", 370, lambda n, b: b == "ファーリーフリースフルジップジャケット" and is_kid(n)),
    ("3-C 長刷毛外套", 570, lambda n, b: b.startswith("ファーリーフリースフルジップジャケット") and not is_kid(n)),
    ("3-D 搖粒絨毛拉鍊外套", 399, lambda n, b: b.startswith("フリースジャケット")),
    ("3-E 法蘭絨格紋襯衫", 860, lambda n, b: b.startswith("フランネルシャツ")),
    ("4-A 保暖彈性長褲", 1150, lambda n, b: b in ("ウォームストレッチパンツ", "ウォームストレッチパンツ/丈長め")),
    ("4-B 繭型(桶狀)牛仔褲", 860, lambda n, b: b.startswith("バギーバレルレッグジーンズ") or b.startswith("EZYバレルジーンズ")),
    ("4-C 直筒卡其褲", 599, lambda n, b: b == "チノワイドパンツ"),
    ("4-D 打褶寬褲", 355, lambda n, b: b.startswith("タックバレルレッグパンツ")),
    ("5-A HEATTECH 輕暖(圓領/U領/內搭褲10分)", 280, lambda n, b: b in ("ヒートテッククルーネックT", "ヒートテックUネックTシャツ", "ヒートテックUネックT", "ヒートテックレギンス/10分丈")),
    ("5-B HEATTECH 輕暖(V領/九分袖/前開緊身褲)", 280, lambda n, b: b in ("ヒートテックVネックT", "ヒートテッククルーネックT/9分袖", "ヒートテックVネックT/9分袖", "ヒートテックタイツ/前開き")),
    ("6 極暖 喀什米爾混紡 高領/圓領", 560, lambda n, b: b in ("極暖ヒートテックカシミヤブレンドタートルネックT", "極暖ヒートテックカシミヤブレンドクルーネックT", "極暖ヒートテックカシミヤブレンドクルーT/9分袖", "極暖ヒートテックカシミヤブレンドタートルT/9分袖")),
    ("7-B 居家服組", 1150, lambda n, b: b == "ウルトラストレッチセット"),
    ("7-D HEATTECH 襪子", 100, lambda n, b: "ソックス" in b and b != "ヒートテックロングルームソックス"),
    ("8-A DRY 運動褲(童裝)", 355, lambda n, b: b in ("ドライスウェットワイドパンツ", "ドライスウェットパンツ")),
    ("8-D 刷毛絨內搭褲(嬰幼兒)", 220, lambda n, b: b.startswith("フリースレギンス")),
    ("8-F HEATTECH 棉質圓領T(嬰幼兒)", 220, lambda n, b: b == "ヒートテックコットンクルーネックT" and is_baby(n)),
]


def round_09(x):
    """尾數湊成 0 或 9(老闆指示:四捨到 0、五入到 9):
    個位 0-4 -> 捨去成 0(243 -> 240);個位 5-9 -> 進到 9(245 -> 249、298 -> 299)。"""
    base, r = x - x % 10, x % 10
    return base if r <= 4 else base + 9


def match_rule(name):
    b = base_of(name)
    for label, price, fn in RULES:
        if fn(name, b):
            return label, price
    return None, None


def main():
    mode = (sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
    if mode not in ("report", "apply"):
        print("用法:python reprice_uniqlo_kanshasai.py report|apply")
        sys.exit(1)

    st = json.load(urllib.request.urlopen(DB + "/daigou-settings-v1.json"))
    rate, ship = float(st["rate"]), float(st["shippingPerKg"])
    print(f"匯率 {rate}、運費 {ship}/kg")

    if mode == "apply":
        from sync_stock import load_products_by_brand, merge_and_save, firebase_app
        firebase_app()
        uniqlo = load_products_by_brand("UNIQLO")
    else:
        raw = json.load(urllib.request.urlopen(DB + '/daigou-products-v1.json?orderBy="brand"&equalTo="UNIQLO"'))
        uniqlo = list(raw.values()) if isinstance(raw, dict) else raw
    cards = [p for p in uniqlo if p.get("campaign") == CAMPAIGN]
    print(f"感謝祭商品卡 {len(cards)} 張\n")

    with open("uniqlo_kanshasai_import.json", encoding="utf-8") as f:
        imp = json.load(f)
    sale_jpy_by_id = {u["id"]: u["jpy"] for u in imp["updates"]}
    sale_jpy_by_id.update({p["id"]: p["jpy"] for p in imp["new"]})

    lower, higher, same, newp = [], [], [], []
    to_save = []
    for p in cards:
        cur = p.get("campaignTwdExcel", p.get("twdOverride"))  # 還沒動過的 Excel 價
        label, last = match_rule(p["name"])
        if label is None:
            # 感謝價用匯入檔裡的(每日同步偶爾會把少數卡的 jpy 改回官網原價,不可靠)
            sale_jpy = sale_jpy_by_id.get(p["id"], p["jpy"])
            cost = sale_jpy * rate + float(p.get("weight") or 0.3) * ship
            target = round_09(round(cost * 1.2))
            newp.append((p["name"], sale_jpy, cur, target))
            reason = "new"
        elif cur < last:  # 今年比去年便宜 -> 改成去年的賣價
            target = last
            lower.append((label, p["name"], cur, last))
            reason = "lower"
        elif cur > last:  # 今年比去年貴 -> 不動,列出來
            target = cur
            higher.append((label, p["name"], cur, last))
            reason = "higher"
        else:
            target = cur
            same.append((label, p["name"], cur, last))
            reason = "same"
        if reason in ("lower", "new") and p.get("twdOverride") != target:
            p.setdefault("campaignTwdExcel", cur)
            p["twdOverride"] = target
            to_save.append(p)

    print(f"== 今年比去年便宜 -> 改成去年賣價:{len(lower)} 張")
    for label, n, cur, last in sorted(lower):
        print(f"   [{label}] {n[:36]}  {cur} -> {last}")
    print(f"\n== 今年比去年貴 -> 不動,請老闆決定:{len(higher)} 張")
    for label, n, cur, last in sorted(higher):
        print(f"   [{label}] {n[:36]}  今年 {cur} / 去年 {last}(+{cur - last})")
    print(f"\n== 跟去年一樣 -> 不動:{len(same)} 張")
    print(f"\n== 去年沒有 -> 成本×1.2:{len(newp)} 張")
    for n, jpy, cur, target in sorted(newp, key=lambda x: x[1]):
        print(f"   {n[:36]}  ¥{jpy}  {cur} -> {target}")
    print(f"\n統計:改價 {len(to_save)} 張(便宜->去年價 {len(lower)}、去年沒有->成本×1.2 {len(newp)}),"
          f"今年較貴留待決定 {len(higher)} 張,一樣 {len(same)} 張")

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
