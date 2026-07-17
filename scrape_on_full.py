"""
On(昂跑,瑞士跑鞋品牌,on.com)全站商品爬蟲
------------------------------------------------------------
用途:
  抓 on.com 日本站全站商品(鞋類 + 服飾 + 配件,男女童都含),不是只抓跑鞋。
  商品「家族」(同一款式,不分顏色)總共 647 個 —— 這份清單是先從官網自己的
  sitemap(https://www.on.com/ja-jp/products.xml,不受 Cloudflare 影響,
  純 requests 就抓得到)裡拿出每個顏色的網址,再依「款式代碼 + 性別」去重,
  每個家族留一個代表網址,存成 on_all_families.json。

跟只抓跑鞋那支(scrape_on_running.py)的差異:
  1. 商品分類從單一的「跑鞋」擴大成全站,所以「種類」(subtype)要看每個
     商品自己的 breadcrumb 分類,不能整批寫死。分類對照表(CATEGORY_ZH)
     是先跑過一次全部 647 個商品的 breadcrumb 蒐集出來的(只有 21 種,
     詳見 _on_category_summary2.txt),對照不到的就保留日文原文。
  2. 重量估計也要看分類(鞋類/外套 vs. 襪子/配件 重量差很多)。
  3. 尺寸不再限定是鞋碼,服飾是 XS/S/M/L/XL/XXL 這種標籤,但底層資料結構
     一樣是 Nuxt __NUXT_DATA__ 裡的 Variant 物件,抓法完全共用。

其餘的技術細節(schema.org ProductGroup 抓顏色、Nuxt 資料還原庫存、
Firebase key 不能有 "." "/" 的處理)都跟 scrape_on_running.py 一樣,
详细原因請見那支程式的說明。

執行方式:
  pip install -r requirements.txt
  python scrape_on_full.py

會輸出 on_full_products.json,可直接貼進 daigou-shop.html 的批次匯入功能。
"""

import json
import re
import sys
import time

import requests

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

BASE_URL = "https://www.on.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}
REQUEST_DELAY = 0.5
BRAND = "On"

# 只依「最後一層 breadcrumb」(最具體的分類)對照,一共只出現 21 種,
# 對照不到的就保留日文原文,不硬翻譯出錯誤的中文。
CATEGORY_ZH = {
    "トップス＆Tシャツ": "上衣",
    "シューズ": "鞋類",
    "ジャケット": "外套",
    "ショーツ": "短褲",
    "ロードランニング": "路跑鞋",
    "フーディー＆スウェットシャツ": "連帽外套",
    "パンツ": "長褲",
    "タイツ": "內搭褲",
    "ソックス": "襪類",
    "アクセサリー": "配件",
    "アパレル": "服飾",
    "テニスシューズ": "網球鞋",
    "ロードランニング シューズ": "路跑鞋",
    "トレイルランニング": "越野跑鞋",
    "バッグ": "包款",
    "ハイキング": "健行鞋",
    "スポーツブラ": "運動內衣",
    "キッズ": "童裝童鞋",
    "ドレス": "洋裝",
    "スカート": "裙裝",
    "ショートパンツ": "短褲",
}

# 依分類決定重量估計(公斤)。On 官網商品頁沒有公開實際重量規格(檢查過
# 頁面原始碼,找不到公克數的商品規格欄位),這份數字是參考一般跑鞋/服飾
# 品項常見的實際重量抓的(鞋類含鞋盒,服飾則是常見的成衣重量),
# 不是從官網抓到的實際數據,建議實際商品到貨後抽件過磅核實。
WEIGHT_BY_CATEGORY = {
    "鞋類": 0.75,
    "路跑鞋": 0.75,
    "網球鞋": 0.8,
    "越野跑鞋": 0.85,
    "健行鞋": 0.9,
    "童裝童鞋": 0.4,
    "外套": 0.5,
    "連帽外套": 0.6,
    "上衣": 0.2,
    "短褲": 0.2,
    "長褲": 0.35,
    "內搭褲": 0.2,
    "洋裝": 0.3,
    "裙裝": 0.2,
    "運動內衣": 0.12,
    "襪類": 0.1,
    "包款": 0.5,
    "配件": 0.15,
    "服飾": 0.3,
}
DEFAULT_WEIGHT = 0.4


def guess_subtype(breadcrumb):
    if not breadcrumb:
        return "其他"
    last = breadcrumb[-1]
    return CATEGORY_ZH.get(last, last)


def guess_weight(subtype):
    return WEIGHT_BY_CATEGORY.get(subtype, DEFAULT_WEIGHT)


def fetch_html(url):
    res = requests.get(url, headers=HEADERS, timeout=20)
    res.raise_for_status()
    time.sleep(REQUEST_DELAY)
    return res.text


LDJSON_RE = re.compile(r'<script[^>]*id="json-ld"[^>]*>(.*?)</script>', re.DOTALL)
NUXT_DATA_RE = re.compile(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)


def extract_ldjson(html):
    m = LDJSON_RE.search(html)
    if not m:
        return None, None
    try:
        data = json.loads(m.group(1))
    except Exception:
        return None, None
    graph = data.get("@graph", [])
    pg = next((g for g in graph if g.get("@type") == "ProductGroup"), None)
    bc = next((g for g in graph if g.get("@type") == "BreadcrumbList"), None)
    labels = [item["name"] for item in bc["itemListElement"]] if bc else []
    return pg, labels


def resolve_nuxt_value(arr, idx, depth=0):
    if depth > 4 or not isinstance(idx, int) or idx < 0 or idx >= len(arr):
        return idx
    val = arr[idx]
    if isinstance(val, dict):
        return {
            k: (resolve_nuxt_value(arr, v, depth + 1) if isinstance(v, int) else v)
            for k, v in val.items()
        }
    return val


def fix_size_key(s):
    # Firebase 的物件 key 不能含有 $ # [ ] / . 這幾個字元。
    # 半號尺寸像 "25.5" 含有 "."、男女合併尺寸像 "M25 / W25.5" 含有 "/",
    # 兩種都要換掉,不然整批資料都存不進去。
    return str(s).replace(".", "-").replace("/", "／")


def extract_size_stock(html):
    m = NUXT_DATA_RE.search(html)
    if not m:
        return {}
    try:
        arr = json.loads(m.group(1))
    except Exception:
        return {}
    if not isinstance(arr, list):
        return {}

    sizes = {}
    for i, v in enumerate(arr):
        if isinstance(v, dict) and {"size", "sku", "stock"} <= v.keys():
            resolved = resolve_nuxt_value(arr, i)
            size = resolved.get("size")
            stock = resolved.get("stock")
            if size is None:
                continue
            size = fix_size_key(size)
            try:
                stock = int(stock)
            except (TypeError, ValueError):
                stock = 0
            sizes[size] = max(stock, sizes.get(size, 0))
    return sizes


def is_preorder(offer):
    return "PreOrder" in (offer.get("availability") or "")


def main():
    with open("on_all_families.json", "r", encoding="utf-8") as f:
        family_urls = json.load(f)

    final_list = []
    seen_group_urls = set()
    error_count = 0

    for i, url in enumerate(family_urls):
        print(f"[{i+1}/{len(family_urls)}] {url}")
        try:
            html = fetch_html(url)
        except Exception as e:
            print(f"  [錯誤] 抓取失敗:{e}")
            error_count += 1
            continue

        group, breadcrumb = extract_ldjson(html)
        if not group:
            print("  [錯誤] 找不到 ProductGroup,略過")
            error_count += 1
            continue

        group_url = group.get("url", "")
        if group_url in seen_group_urls:
            continue
        seen_group_urls.add(group_url)

        subtype = guess_subtype(breadcrumb)
        weight = guess_weight(subtype)

        colors = []
        variants = group.get("hasVariant", [])
        preorder_flag = False
        price = None
        for v in variants:
            offer = v.get("offers", {})
            if price is None and offer.get("price"):
                price = offer["price"]
            if is_preorder(offer):
                preorder_flag = True
            color_url = offer.get("url", "")
            full_url = color_url if color_url.startswith("http") else BASE_URL + color_url
            print(f"    顏色:{v.get('color')}")
            try:
                color_html = fetch_html(full_url)
                sizes_stock = extract_size_stock(color_html)
            except Exception as e:
                print(f"      [錯誤] {e}")
                sizes_stock = {}
            if not sizes_stock:
                continue
            color_entry = {
                "name": v.get("color", ""),
                "sizes": list(sizes_stock.keys()),
                "stock": sizes_stock,
            }
            if v.get("image"):
                color_entry["image"] = v["image"]
            colors.append(color_entry)

        if not colors:
            print("  [警告] 這款商品所有顏色都查不到尺寸庫存,略過")
            continue

        entry = {
            "name": group.get("name", ""),
            "jpy": price or 0,
            "weight": weight,
            "brand": BRAND,
            "subtype": subtype,
            "country": "JP",
            "saleType": "preorder" if preorder_flag else "instock",
            "link": group_url or url,
            "colors": colors,
        }
        if colors[0].get("image"):
            entry["image"] = colors[0]["image"]

        final_list.append(entry)

        if (i + 1) % 25 == 0:
            with open("on_full_products.json", "w", encoding="utf-8") as f:
                json.dump(final_list, f, ensure_ascii=False, indent=2)
            print(f"  (已儲存進度:{i+1}/{len(family_urls)},目前共 {len(final_list)} 件,錯誤 {error_count} 件)")

    with open("on_full_products.json", "w", encoding="utf-8") as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)

    print(f"完成!已輸出 on_full_products.json,共 {len(final_list)} 件商品(錯誤 {error_count} 件)。")


if __name__ == "__main__":
    main()
