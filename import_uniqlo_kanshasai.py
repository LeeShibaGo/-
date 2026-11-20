# -*- coding: utf-8 -*-
"""
一次性:把 UNIQLO 感謝祭(2026-11)限期特價商品匯入官網
------------------------------------------------------------
用途:
  讀 prepare_uniqlo_kanshasai.py 產生的 uniqlo_kanshasai_import.json:
    - "updates":官網已經有的 UNIQLO 商品(link 裡商品代碼相同)→ 只改價格:
      jpy 改成感謝價、twdOverride 改成 Excel 的「建議售價」,舊價格記在
      campaignOrigJpy,方便活動結束後還原(見 expire_uniqlo_kanshasai.py)。
    - "new":官網還沒有的商品卡(多顏色已合併)→ 新增。

  分兩個階段,避免一次全上線才發現問題:
    trial  只匯入 JSON 裡 "trial" 指定的 3 筆(2 張新卡 + 1 件更新價格)
    rest   匯入其餘全部(已經在 trial 匯入過的會自動跳過,不會重複)

  寫入走 sync_stock.merge_and_save():寫回前重新抓一次最新完整清單當基底,
  只換掉這次動到的商品,其他商品(包含別的同步同時寫進去的)原封不動,
  避免整包覆蓋(2026-07-21 發生過的事故,見 merge_and_save 說明)。

執行方式(透過 GitHub Actions 手動觸發):
  GitHub -> Actions -> "One-off: import UNIQLO kanshasai" -> Run workflow
  stage 選 trial 或 rest
"""

import json
import sys

from sync_stock import load_products_by_brand, merge_and_save, firebase_app

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

DATA_FILE = "uniqlo_kanshasai_import.json"


def main():
    stage = (sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
    if stage not in ("trial", "rest"):
        print("用法:python import_uniqlo_kanshasai.py trial|rest")
        sys.exit(1)

    with open(DATA_FILE, encoding="utf-8") as f:
        data = json.load(f)
    campaign, sale_end = data["campaign"], data["saleEnd"]
    trial_new = set(data["trial"]["new"])
    trial_upd = set(data["trial"]["updates"])

    if stage == "trial":
        want_new = [p for p in data["new"] if p["id"] in trial_new]
        want_upd = [u for u in data["updates"] if u["id"] in trial_upd]
    else:
        want_new = [p for p in data["new"] if p["id"] not in trial_new]
        want_upd = [u for u in data["updates"] if u["id"] not in trial_upd]
    print(f"[{stage}] 預計新增 {len(want_new)} 張卡、更新 {len(want_upd)} 件既有商品價格")

    firebase_app()
    uniqlo = load_products_by_brand("UNIQLO")
    by_id = {p["id"]: p for p in uniqlo}

    to_save = []
    skipped_new = 0
    for p in want_new:
        if p["id"] in by_id:  # 已經匯入過(例如重跑),不重複新增
            skipped_new += 1
            continue
        to_save.append(p)
    print(f"新增:{len(to_save)} 張(已存在而跳過 {skipped_new} 張)")

    updated = skipped_upd = missing = 0
    for u in want_upd:
        p = by_id.get(u["id"])
        if not p:
            print(f"  警告:找不到既有商品 {u['id']}({u['name']}),略過")
            missing += 1
            continue
        if p.get("campaign") == campaign:
            skipped_upd += 1
            continue
        p.setdefault("campaignOrigJpy", p.get("jpy"))
        p["jpy"] = u["jpy"]
        p["twdOverride"] = u["twdOverride"]
        p["campaign"] = campaign
        p["saleEnd"] = sale_end
        if not p.get("desc"):
            desc = f"{u['gender']}・感謝祭限定價 ¥{u['jpy']:,}"
            if u.get("originalJpy"):
                desc += f"(原價 ¥{u['originalJpy']:,})"
            p["desc"] = desc + "・至 11/26"
        print(f"  價格更新:{p['name']} ¥{p['campaignOrigJpy']} -> ¥{u['jpy']}(NT${u['twdOverride']})")
        to_save.append(p)
        updated += 1
    print(f"更新價格:{updated} 件(已更新過 {skipped_upd}、找不到 {missing})")

    if not to_save:
        print("沒有需要寫入的東西。")
        return
    merge_and_save(to_save)
    print(f"完成![{stage}] 共寫入 {len(to_save)} 件。")


if __name__ == "__main__":
    main()
