# -*- coding: utf-8 -*-
"""一次性:把 CELINE 商品名稱從日文換成台灣官網對到的中文名稱
------------------------------------------------------------
用途:
  celine_name_crossref.json(先前用款式代碼比對 celine.com/zht-tw 產生的
  對照表)裡,1,431 款(共 1,774 款)有對到台灣官網的名稱——但那邊抓下來的
  原始文字其實是簡體字(zht-tw 這個 locale 名稱雖然叫「繁中」,實測內容是
  簡體,2026-08-09 發現),所以這裡用 OpenCC 的 s2twp 設定(簡體 -> 台灣繁體,
  含常用詞彙轉換,不是只轉字形)做轉換,再寫回商品名稱。

  沒對到台灣官網款式代碼的 343 款維持原本的日文名稱不動(這些是台灣沒有賣
  的品項,可能是日本限定或台灣官網下架了)。

  用 link 網址裡的款式代碼(SKU 前半段)重新比對現有資料庫商品,跟
  celine_name_crossref.json 產生時用的是同一個規則,見 scrape_celine.py。

  寫回用 sync_stock.merge_and_save() 同一套「寫回前重新抓最新快照、
  只換這次真的處理過的 id」的安全寫法,避免跟同時間可能在跑的每日同步
  互相覆蓋(daigou-products-v1 的整包覆寫風險,sync_stock.py 開頭有寫)。

執行方式(透過 GitHub Actions 手動觸發):
  GitHub 網頁 -> 這個 repo -> Actions 分頁 -> 左邊選
  "One-off: convert CELINE names to Traditional Chinese" -> 右邊 "Run workflow"
"""
import json
import re
import sys
import urllib.parse

import opencc

from sync_stock import load_products, merge_and_save

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

STYLE_PAT = re.compile(r"-([A-Z0-9]{6,12})\.([A-Z0-9]{2,6})\.html$")


def main():
    converter = opencc.OpenCC("s2twp")

    with open("celine_name_crossref.json", encoding="utf-8") as f:
        crossref = json.load(f)
    tw_name_by_style = {r["style"]: r["tw_name"] for r in crossref if r.get("tw_name") and r.get("style")}
    print(f"對照表裡有台灣官網名稱的款式代碼:{len(tw_name_by_style)} 筆")

    products = load_products()
    celine = [p for p in products if p.get("brand") == "CELINE"]
    print(f"資料庫裡目前 CELINE 商品:{len(celine)} 款")

    updated_cards = []
    skipped_no_match = 0
    for p in celine:
        link = p.get("link") or ""
        m = STYLE_PAT.search(urllib.parse.unquote(link))
        style = m.group(1) if m else None
        tw_name = tw_name_by_style.get(style) if style else None
        if not tw_name:
            skipped_no_match += 1
            continue
        traditional = converter.convert(tw_name)
        if p.get("name") == traditional:
            continue
        p["nameJa"] = p.get("name")  # 保留原始日文名稱,方便之後對照/還原
        p["name"] = traditional
        updated_cards.append(p)

    print(f"轉換完成:{len(updated_cards)} 款換成台灣官網名稱(繁體),{skipped_no_match} 款維持日文")
    if updated_cards:
        merge_and_save(updated_cards)
    else:
        print("沒有需要更新的商品,不寫回。")


if __name__ == "__main__":
    main()
