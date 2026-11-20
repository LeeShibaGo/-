# -*- coding: utf-8 -*-
"""
一次性/可重跑:UNIQLO 感謝祭(2026-11)限期特價結束後下架或還原
------------------------------------------------------------
用途:
  import_uniqlo_kanshasai.py 匯入時,每件感謝祭商品都標了 campaign=
  "uniqlo-kanshasai-2026"、saleEnd="2026-11-26"。特價結束後,用這支一次
  處理整批,不用在後台一件一件改:

    - 這次「新增」的商品卡(id 以 p_uniqlokss_ 開頭):
        mode=end    設成 hidden(客人看不到,資料保留,隨時可以改回來)
        mode=delete 整張卡刪除(也是匯入的回滾方式)
    - 這次「只更新價格」的既有商品:兩種 mode 都是還原:jpy 還原成
      campaignOrigJpy(匯入前的價格)、拿掉 twdOverride/campaign/saleEnd。
      (官網每日同步本來就會把 jpy 改回官網現價,但 twdOverride 不會被
      同步清掉,不處理的話這些商品會一直用特價台幣價賣,所以一定要跑。)

  dry-run(預設)只印出會改什麼,不寫入;確認後再用 apply 真的執行。

執行方式(透過 GitHub Actions 手動觸發):
  GitHub -> Actions -> "One-off: expire UNIQLO kanshasai" -> Run workflow
  mode 選 end 或 delete;apply 勾選才會真的寫入。
"""

import sys

from sync_stock import load_products_by_brand, merge_and_save, firebase_app, db, PRODUCTS_PATH, save_products_index, load_products

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

CAMPAIGN = "uniqlo-kanshasai-2026"


def main():
    mode = (sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
    apply = (sys.argv[2] if len(sys.argv) > 2 else "dry-run").strip().lower() == "apply"
    if mode not in ("end", "delete"):
        print("用法:python expire_uniqlo_kanshasai.py end|delete [apply]")
        sys.exit(1)

    firebase_app()
    uniqlo = load_products_by_brand("UNIQLO")
    campaign_items = [p for p in uniqlo if p.get("campaign") == CAMPAIGN]
    new_cards = [p for p in campaign_items if str(p.get("id", "")).startswith("p_uniqlokss_")]
    repriced = [p for p in campaign_items if not str(p.get("id", "")).startswith("p_uniqlokss_")]
    print(f"感謝祭商品:新增卡 {len(new_cards)} 張、只更新價格的既有商品 {len(repriced)} 件")
    print(f"模式:{mode}({'實際寫入' if apply else 'dry-run,不寫入'})")

    for p in repriced:
        orig = p.get("campaignOrigJpy")
        print(f"  還原價格:{p['name']} ¥{p.get('jpy')} -> ¥{orig}(拿掉手動定價 NT${p.get('twdOverride')})")
    for p in new_cards[:10]:
        print(f"  {'刪除' if mode == 'delete' else '隱藏'}:{p['name']}")
    if len(new_cards) > 10:
        print(f"  ...其餘 {len(new_cards) - 10} 張")

    if not apply:
        print("dry-run 結束,沒有寫入任何東西。")
        return

    changed = []
    for p in repriced:
        if p.get("campaignOrigJpy") is not None:
            p["jpy"] = p["campaignOrigJpy"]
        for k in ("twdOverride", "campaign", "saleEnd", "campaignOrigJpy"):
            p.pop(k, None)
        changed.append(p)

    if mode == "end":
        for p in new_cards:
            p["hidden"] = True
            changed.append(p)
        if changed:
            merge_and_save(changed)
    else:  # delete:merge_and_save 只會更新/新增,刪除要自己整包處理
        if changed:
            merge_and_save(changed)
        drop_ids = {p["id"] for p in new_cards}
        fresh = load_products()
        kept = [p for p in fresh if p.get("id") not in drop_ids]
        print(f"刪除 {len(fresh) - len(kept)} 張新增卡")
        db.reference(PRODUCTS_PATH).set(kept)
        save_products_index(kept)
    print("完成!")


if __name__ == "__main__":
    main()
