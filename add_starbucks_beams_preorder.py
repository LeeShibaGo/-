# -*- coding: utf-8 -*-
"""一次性:① 第一段加成 50% -> 40%;② 上架 STARBUCKS STAND by BEAMS「BLACK Collection」12 款預購
------------------------------------------------------------
老闆指示(2026-11-25):
  1. 價格級距第一段(日幣 1 萬以內)加成從 50% 降到 40%(其他段不動)。
     只改 daigou-settings-v1/priceTiers 這一個欄位,不動設定裡的其他東西。
  2. 星巴克 x BEAMS 11/27 發售的 12 款聯名商品做成預購商品。
資料來源:星巴克日本官方新聞稿(2026-11-24)與官網各商品頁
  https://www.starbucks.co.jp/starbucks-stand-by-beams/extra05/
  價格為官網含稅價;圖片是官網每個 SKU 的商品圖(asset.menu.starbucks.co.jp)。
  XS 只在 BEAMS 實體店販售(官網沒有),所以 T 恤/大學 T/皮外套的尺寸不放 XS。
寫入用 sync_stock.merge_and_save(重抓最新清單只加新商品,不會蓋掉別人同時寫入的資料)。
重跑安全:用 link 比對,已存在就跳過;priceTiers 已經是目標值就不再寫。
"""
import sys
import time

from firebase_admin import db

from sync_stock import firebase_app, load_products, merge_and_save

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

OLD_TIERS = "10000,50\n50000,40\n100000,30\n200000,25\n,25"
NEW_TIERS = "10000,40\n50000,40\n100000,30\n200000,25\n,25"

BRAND = "STARBUCKS x BEAMS"
IMG = "https://asset.menu.starbucks.co.jp/public/sku_images/{s}/{s}_1_s.jpg"
LINK = "https://menu.starbucks.co.jp/{s}"
CLOTH = ["S", "M", "L", "XL"]

# (SKU, 名稱, 日幣含稅, 重量kg, 分類, 尺寸, 備註)
ITEMS = [
    ("4524785656352", "【STARBUCKS x BEAMS】不鏽鋼 TOGO 保溫瓶 473ml 霧黑", 5800, 0.45, "居家雜貨", ["F"],
     "星巴克官網限定販售"),
    ("4524785659971", "【STARBUCKS x BEAMS】LOGO 純銀戒指(SILVER 925)", 29700, 0.10, "珠寶飾品",
     ["9", "11", "13", "15", "17", "19"], "附專用盒"),
    ("4524785660083", "【STARBUCKS x BEAMS】LOGO 短袖 T 恤", 9350, 0.25, "短袖上衣", CLOTH, ""),
    ("4524785660120", "【STARBUCKS x BEAMS】LOGO 圓領大學 T", 18150, 0.80, "大學T", CLOTH, ""),
    ("4524785660038", "【STARBUCKS x BEAMS】LOGO 皮外套(牛皮)", 99000, 1.50, "外套", CLOTH, ""),
    ("4524785660076", "【STARBUCKS x BEAMS】LOGO 皮革包(紙袋造型)", 29700, 0.60, "包款", ["F"], ""),
    ("4524785660168", "【STARBUCKS x BEAMS】6P LOGO 棒球帽", 7150, 0.15, "帽子", ["F"], ""),
    ("4524785660175", "【STARBUCKS x BEAMS】LOGO 工作圍裙", 7150, 0.30, "居家雜貨", ["F"], ""),
    ("4524785660182", "【STARBUCKS x BEAMS】2 件組收納包", 3300, 0.20, "包款", ["F"], "大小兩件一組"),
    ("4524785660199", "【STARBUCKS x BEAMS】帆布 LOGO 托特包", 8250, 0.40, "包款", ["F"], ""),
    ("4524785660205", "【STARBUCKS x BEAMS】方巾", 2970, 0.05, "圍巾配件", ["F"], ""),
    ("4524785660212", "【STARBUCKS x BEAMS】DRINK-ID 襪子", 3300, 0.10, "襪類", ["S", "M"], ""),
]


def build(i, now):
    sku, name, jpy, weight, subtype, sizes, note = ITEMS[i]
    img = IMG.format(s=sku)
    p = {
        "id": f"p_starbucks_{now}_{i}",
        "name": name,
        "jpy": jpy,
        "weight": weight,
        "brand": BRAND,
        "subtype": subtype,
        "country": "JP",
        "saleType": "preorder",
        "link": LINK.format(s=sku),
        "image": img,
        "addedAt": now,
        "colors": [{"name": "黑色", "sizes": sizes, "image": img}],
    }
    desc = "11/27 日本發售・預購" + (f"・{note}" if note else "")
    p["desc"] = desc
    return p


def main():
    firebase_app()

    # ① 價格級距
    ref = db.reference("daigou-settings-v1/priceTiers")
    cur = ref.get()
    if cur == NEW_TIERS:
        print("priceTiers 已經是 40/40/30/25/25,不重複寫。")
    elif cur == OLD_TIERS:
        ref.set(NEW_TIERS)
        print("priceTiers 已更新:第一段 50% -> 40%")
    else:
        print(f"!! priceTiers 目前是別的值,不動它:{cur!r}")

    # ② 預購商品
    existing = {p.get("link") for p in load_products()}
    now = int(time.time() * 1000)
    new_items = [build(i, now) for i in range(len(ITEMS))
                 if LINK.format(s=ITEMS[i][0]) not in existing]
    if not new_items:
        print("12 款都已存在,略過。")
        return
    merge_and_save(new_items)
    print(f"已新增 {len(new_items)} 款預購商品:")
    for p in new_items:
        print(f"  {p['name']}  ¥{p['jpy']}  {p['subtype']}")


if __name__ == "__main__":
    main()
