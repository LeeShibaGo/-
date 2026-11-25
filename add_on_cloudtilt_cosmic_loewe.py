# -*- coding: utf-8 -*-
"""一次性:上架 On x LOEWE「男款 Cloudtilt Cosmic LOEWE」(4 色,¥106,700,限量款)
老闆貼了 On 官方 App 截圖(2026-11-25)要求上架。資料直接從 on.com/ja-jp 官網頁面抓:
  - 價格:schema.org ld+json(JPY 106700)
  - 顏色:hasVariant 4 色(White / Bright Orange / Black / Dark Sand),每色自己的圖、尺寸庫存
  - 官網現貨 -> saleType instock;鞋類比照既有 On 鞋(subtype 鞋類、0.75kg、series Cloudtilt)
重跑安全:用 link 比對,已存在就跳過。寫入用 merge_and_save。
"""
import sys
import time

from scrape_on_full import extract_ldjson, extract_size_stock
from sync_stock import fetch, load_products, merge_and_save

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

LINK = "https://www.on.com/ja-jp/products/cloudtilt-cosmic-loewe-m-3mg3092/mens"
ON_BASE = "https://www.on.com"
ZH = {"White": "白", "Bright Orange": "亮橘", "Black": "黑", "Dark Sand": "深沙色"}
ORDER = ["White", "Bright Orange", "Black", "Dark Sand"]


def main():
    if any(p.get("link") == LINK for p in load_products()):
        print("已存在,略過。")
        return
    group, _ = extract_ldjson(fetch(LINK).text)
    assert group, "官網頁面解析失敗"
    variants = {v.get("color"): v for v in group.get("hasVariant", [])}
    print("官網顏色:", list(variants))
    colors, jpy = [], None
    for en in ORDER + [k for k in variants if k not in ORDER]:
        v = variants.get(en)
        if not v:
            continue
        offer = v.get("offers", {})
        if jpy is None and offer.get("price"):
            jpy = int(float(offer["price"]))
        url = offer.get("url", "")
        url = url if url.startswith("http") else ON_BASE + url
        stock = extract_size_stock(fetch(url).text)
        time.sleep(0.5)
        if not stock:
            print("  !! 沒有尺寸庫存,略過顏色", en)
            continue
        img = v.get("image")
        img = img[0] if isinstance(img, list) else img
        colors.append({"name": ZH.get(en, en), "sizes": list(stock.keys()), "stock": stock,
                       "sku": v.get("sku"), "image": img})
        print(f"  {en} -> {ZH.get(en, en)}  sizes={stock}")
    assert colors and jpy, "沒有可上架的顏色或價格"
    now = int(time.time() * 1000)
    p = {"id": f"p_on_{now}_0", "name": "男款 Cloudtilt Cosmic LOEWE", "jpy": jpy, "weight": 0.75,
         "brand": "On", "subtype": "鞋類", "series": "Cloudtilt", "country": "JP", "saleType": "instock",
         "link": LINK, "image": colors[0]["image"], "addedAt": now, "colors": colors,
         "desc": "On x LOEWE 聯名限量款"}
    merge_and_save([p])
    print("已新增:", p["name"], "¥", jpy, "顏色數", len(colors), "id", p["id"])


if __name__ == "__main__":
    main()
