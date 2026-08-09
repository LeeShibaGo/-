# -*- coding: utf-8 -*-
"""一次性:把資料庫裡現有 CELINE 商品的顏色名稱從日文換成中文
------------------------------------------------------------
用途:
  2026-08-09 實測發現 CELINE 商品的顏色選項(例如「マルチカラー」「ブラック
  / ゴールド」)一直是原始日文,陌生客人看不懂。scrape_celine.py 跟
  sync_stock.sync_celine() 已經改好,之後新抓/同步的顏色會自動翻譯
  (見 scrape_celine.translate_celine_color()),這支負責把資料庫裡已經
  存在的 1,774 款商品的顏色名稱一次補翻。

  同步用的比對邏輯(sync_celine 用顏色名稱去對應官網的顏色 swatch 網址)
  也已經改成拿當下抓到的日文名稱先跑過同一個翻譯函式再比對,所以這裡把
  資料庫顏色名稱換成中文之後,不會讓明天的每日同步找不到對應顏色。

  寫回用 sync_stock.merge_and_save() 同一套安全寫法,見
  update_celine_names.py 開頭的說明。

執行方式(透過 GitHub Actions 手動觸發):
  GitHub 網頁 -> 這個 repo -> Actions 分頁 -> 左邊選
  "One-off: translate CELINE color names to Chinese" -> 右邊 "Run workflow"
"""
import sys

from scrape_celine import translate_celine_color
from sync_stock import load_products, merge_and_save

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")


def main():
    products = load_products()
    celine = [p for p in products if p.get("brand") == "CELINE"]
    print(f"資料庫裡目前 CELINE 商品:{len(celine)} 款")

    updated_cards = []
    color_changed = 0
    for p in celine:
        touched = False
        for color in p.get("colors", []):
            old_name = color.get("name")
            new_name = translate_celine_color(old_name)
            if new_name != old_name:
                color["name"] = new_name
                color_changed += 1
                touched = True
        if touched:
            updated_cards.append(p)

    print(f"轉換完成:{len(updated_cards)} 款商品、共 {color_changed} 個顏色換成中文")
    if updated_cards:
        merge_and_save(updated_cards)
    else:
        print("沒有需要更新的商品,不寫回。")


if __name__ == "__main__":
    main()
