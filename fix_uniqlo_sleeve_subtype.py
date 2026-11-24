# -*- coding: utf-8 -*-
"""一次性:修正 UNIQLO 長袖/背心/發熱衣被分到「短袖上衣」的商品
------------------------------------------------------------
老闆回報「ソフトタッチクルーネックTシャツ/長袖」分類成短袖上衣。原因是
prepare_uniqlo_kanshasai.py 的 guess_subtype() 只要名稱有 Tシャツ/クルーネックT
就當短袖,沒看名稱裡的「長袖」。已修好規則(之後新匯入不會再錯),這支把
已經在資料庫裡、逐張確認過(官網圖看袖長)的幾件改正。
只動下面清單裡 brand == UNIQLO 且目前 subtype == 短袖上衣 的商品;重跑安全。
"""
import sys

from sync_stock import load_products, merge_and_save

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

FIX = {
    "E450179": "長袖上衣",  # ソフトタッチクルーネックTシャツ/長袖
    "E474832": "長袖上衣",  # AIRism棉質圓領T恤(長袖)
    "E465751": "長袖上衣",  # ソフトリブクルーネックT(看圖:長袖)
    "E470143": "長袖上衣",  # ソフトニットフリースクルーネックT(女款)
    "E479791": "長袖上衣",  # ソフトニットフリースクルーネックT
    "E442063": "內著",      # ヒートテックフリースタートルネックT(發熱衣,跟其他 HEATTECH 同類)
    "E465189": "背心",      # ドライカラーリブタンクトップ
}


def main():
    cards = load_products()
    changed = []
    for p in cards:
        if p.get("brand") != "UNIQLO" or p.get("subtype") != "短袖上衣":
            continue
        code = (p.get("link") or "").split("/products/")[-1][:7]
        new = FIX.get(code)
        if new:
            print(f"  {p.get('name')}: 短袖上衣 -> {new}")
            p["subtype"] = new
            changed.append(p)
    print(f"共修正 {len(changed)} 件")
    if changed:
        merge_and_save(changed)
        print("已寫回 Firebase 並更新索引")


if __name__ == "__main__":
    main()
