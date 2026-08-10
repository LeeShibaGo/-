# -*- coding: utf-8 -*-
"""一次性:把「Dior 日本限定」併進「Dior」,不再分成兩個品牌
------------------------------------------------------------
老闆決定 Dior 日本限定系列不用另外獨立成一個品牌,商品直接併到 Dior
底下,品牌展示圖示也只留一個。這支把 brand 欄位是 "Dior 日本限定" 的
商品全部改成 "Dior",其他欄位不動。

寫回用 sync_stock.merge_and_save() 同一套安全寫法。

執行方式(透過 GitHub Actions 手動觸發):
  GitHub 網頁 -> 這個 repo -> Actions 分頁 -> 左邊選
  "One-off: merge Dior Japan-exclusive into Dior" -> 右邊 "Run workflow"
"""
import sys

from sync_stock import load_products, merge_and_save

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

OLD_BRAND = "Dior 日本限定"
NEW_BRAND = "Dior"


def main():
    products = load_products()
    targets = [p for p in products if p.get("brand") == OLD_BRAND]
    print(f"資料庫裡目前 brand=\"{OLD_BRAND}\" 的商品:{len(targets)} 款")

    for p in targets:
        p["brand"] = NEW_BRAND

    print(f"改成 brand=\"{NEW_BRAND}\":{len(targets)} 款")
    if targets:
        merge_and_save(targets)
    else:
        print("沒有需要更新的商品,不寫回。")


if __name__ == "__main__":
    main()
