# -*- coding: utf-8 -*-
"""一次性:把 DESCENTE 裡「台灣買得到」的商品隱藏,只留「日本限定」上架
------------------------------------------------------------
背景:
  DESCENTE 的定價比台灣官網貴 40~53%(2026-08-08 全品牌價格比對抓到的),
  陌生客人容易上網比價、發現我們比台灣官網貴,傷信任感。老闆決定(
  2026-08-09):先不調整定價公式,改成只上架「日本真的買不到」的品項,
  台灣官網也買得到的先隱藏,等於用「稀缺性」取代「比價劣勢」。

  日本限定的判斷方式沿用先前的品名研究(見對話紀錄):
    - 商品名稱或 series 欄位帶有「I/O」的,是這次調查裡確認台灣完全沒有
      在賣的系列(123 款)。
    - 商品名稱帶有「限定」兩個字的(公式線上限定/店舗限定等,8 款)。
  兩者聯集共 131 款,維持上架;其餘 1,109 款(SPORTS STYLE、RUNNING、
  雪靴等 —— 這些先前查過台灣官網也找得到同系列名稱,不是真的限定)設
  hidden:true,沿用 Dior 皮帶那次已經做好的「隱藏但不刪除」機制
  (index.html 的 visibleProducts() 會把 hidden:true 的商品從所有客人看得到
  的地方濾掉,後台管理清單仍看得到、可以隨時取消隱藏)。

  這支只碰 hidden 欄位,不動價格/庫存/其他資料,之後如果調整了定價策略、
  想把這批重新上架,直接把 hidden 拿掉即可(不用重新匯入)。

執行方式(透過 GitHub Actions 手動觸發):
  GitHub 網頁 -> 這個 repo -> Actions 分頁 -> 左邊選
  "One-off: hide non-exclusive DESCENTE products" -> 右邊 "Run workflow"
"""
import sys

from sync_stock import load_products, merge_and_save


def is_japan_exclusive(p):
    name = p.get("name") or ""
    series = p.get("series") or ""
    return ("I/O" in name) or ("I/O" in series) or ("限定" in name)


def main():
    for _s in (sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")

    products = load_products()
    descente = [p for p in products if p.get("brand") == "DESCENTE"]
    print(f"資料庫裡目前 DESCENTE 商品:{len(descente)} 款")

    updated_cards = []
    hidden_count = 0
    unhidden_count = 0
    for p in descente:
        exclusive = is_japan_exclusive(p)
        want_hidden = not exclusive
        current_hidden = bool(p.get("hidden"))
        if want_hidden == current_hidden:
            continue
        if want_hidden:
            p["hidden"] = True
            hidden_count += 1
        else:
            p.pop("hidden", None)
            unhidden_count += 1
        updated_cards.append(p)

    print(f"新隱藏:{hidden_count} 款,取消隱藏:{unhidden_count} 款,共更新 {len(updated_cards)} 款")
    if updated_cards:
        merge_and_save(updated_cards)
    else:
        print("沒有需要更新的商品,不寫回。")


if __name__ == "__main__":
    main()
