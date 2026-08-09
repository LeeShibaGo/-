# -*- coding: utf-8 -*-
"""一次性:把台灣官網對照到的售價寫進 CELINE 商品的 twRefPrice 欄位
------------------------------------------------------------
用途:
  2026-08-09 老闆決定 CELINE 要「比台灣官網便宜,但還是要有margin」
  (T恤/圍巾配件/針織衫/長褲/襯衫/洋裝這幾類原本套一般分級匯率表,比台灣
  貴 10~17%)。index.html 的 sellPriceTwd() 已經改好:商品如果有
  twRefPrice(數字,台灣官網參考售價),CELINE 會改用「台灣參考價打 92 折,
  但不低於成本 1.15 倍」的算法,取代原本的分級匯率表。

  這支負責把 celine_name_crossref.json 裡對照到的台灣官網售價(1,431 款
  裡有 tw_price 的),用款式代碼比對寫進資料庫商品的 twRefPrice 欄位。
  沒對到台灣售價的商品(343 款日本限定)不會有這個欄位,sellPriceTwd()
  會自動退回原本的分級匯率表,不受影響。

  寫回用 sync_stock.merge_and_save() 同一套安全寫法。

執行方式(透過 GitHub Actions 手動觸發):
  GitHub 網頁 -> 這個 repo -> Actions 分頁 -> 左邊選
  "One-off: add CELINE Taiwan reference price" -> 右邊 "Run workflow"
"""
import re
import sys
import urllib.parse
import json

from sync_stock import load_products, merge_and_save

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

STYLE_PAT = re.compile(r"-([A-Z0-9]{6,12})\.([A-Z0-9]{2,6})\.html$")


def main():
    with open("celine_name_crossref.json", encoding="utf-8") as f:
        crossref = json.load(f)
    tw_price_by_style = {r["style"]: r["tw_price"] for r in crossref if r.get("tw_price") and r.get("style")}
    print(f"對照表裡有台灣售價的款式代碼:{len(tw_price_by_style)} 筆")

    products = load_products()
    celine = [p for p in products if p.get("brand") == "CELINE"]
    print(f"資料庫裡目前 CELINE 商品:{len(celine)} 款")

    updated_cards = []
    for p in celine:
        link = p.get("link") or ""
        m = STYLE_PAT.search(urllib.parse.unquote(link))
        style = m.group(1) if m else None
        tw_price = tw_price_by_style.get(style) if style else None
        if tw_price is None:
            continue
        if p.get("twRefPrice") == tw_price:
            continue
        p["twRefPrice"] = tw_price
        updated_cards.append(p)

    print(f"寫入 twRefPrice:{len(updated_cards)} 款")
    if updated_cards:
        merge_and_save(updated_cards)
    else:
        print("沒有需要更新的商品,不寫回。")


if __name__ == "__main__":
    main()
