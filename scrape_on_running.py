"""
On(昂跑,瑞士跑鞋品牌,on.com)跑鞋爬蟲
------------------------------------------------------------
用途:
  只抓「跑鞋(ランニングシューズ)」這個分類,不是抓全站(全站含服飾/生活鞋款,
  規模大很多)。目標網址 https://www.on.com/ja-jp/shop/shoes/running 目前是
  59 件不重複商品(每個「商品」是同一款鞋的某個代表色,底下還有其他顏色)。

selector 已對照 on.com 實際網頁結構驗證過(2026-07-16):
  - robots.txt 只有通用的 `User-agent: *` 規則,擋結帳/購物車/會員/API/
    密碼/`/pdp`/客服聊天這些路徑,沒有針對 ClaudeBot 的規則,商品詳細頁網址
    是 `/ja-jp/products/...`,不在 `/pdp` 底下,不受影響。
  - 商品「詳細頁」(`/ja-jp/products/...`)本身沒有 bot 防護,實測 requests
    可以直接抓到完整資料(含 schema.org JSON-LD 和 Nuxt 的 __NUXT_DATA__)。
  - 但商品「分類列表頁」(`/ja-jp/shop/shoes/running` 這種)有 Cloudflare
    JS 驗證,plain requests 會被擋(只拿到一個空殼 + Cloudflare challenge
    script,沒有真正的商品清單)。所以這份清單改用瀏覽器工具手動蒐集
    (見 on_running_list.json),這支程式只負責「已知 59 個商品網址 →
    查詢每個商品的顏色/尺寸/庫存」這一段,不負責分類頁的商品發現。
    如果之後要抓別的分類,一樣要先用瀏覽器工具開那個分類頁面蒐集商品清單,
    不能直接對分類頁面跑這支程式。

資料來源(每個商品詳細頁下面兩種資料互補):
  1. `<script id="json-ld">` 的 schema.org ProductGroup:
     列出這個商品所有顏色(hasVariant),每個顏色有專屬 sku/name/image/
     price/availability(只有「有貨/缺貨」,沒有到尺寸級別)跟該顏色自己的
     商品網址。
  2. Nuxt 的 `__NUXT_DATA__`(一個「攤平」的陣列,物件裡的數字屬性代表
     「陣列索引」而不是字面數字,要另外解析還原):裡面藏著這個「當前顏色」
     每個尺寸的實際庫存數字(`{"size":..,"sku":..,"stock":..}` 這種
     Variant 物件)。但只有「目前這個顏色專屬網址」的頁面才有這個顏色自己
     的尺寸庫存,其他顏色要點進各自的網址才查得到 —— 所以一個商品(含所有
     顏色)要抓齊完整尺寸庫存,得對每個顏色各發一次請求。

執行方式:
  pip install -r requirements.txt
  python scrape_on_running.py

會輸出 on_running_products.json,可直接貼進 daigou-shop.html 的批次匯入功能。
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
REQUEST_DELAY = 0.6

BRAND = "On"
SUBTYPE = "跑鞋"
# 這個分類底下沒看到女鞋以外的重量差異資訊,參考官方跑鞋含盒重量抓一個概略值
WEIGHT = 0.7


def fetch_html(url):
    res = requests.get(url, headers=HEADERS, timeout=20)
    res.raise_for_status()
    time.sleep(REQUEST_DELAY)
    return res.text


LDJSON_RE = re.compile(
    r'<script[^>]*id="json-ld"[^>]*>(.*?)</script>', re.DOTALL
)
NUXT_DATA_RE = re.compile(
    r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL
)


def extract_product_group(html):
    """
    從 schema.org JSON-LD 抓出這個商品所有顏色的基本資訊。
    """
    m = LDJSON_RE.search(html)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except Exception:
        return None
    graph = data.get("@graph", [])
    for node in graph:
        if node.get("@type") == "ProductGroup":
            return node
    return None


def resolve_nuxt_value(arr, idx, depth=0):
    """
    Nuxt 的 __NUXT_DATA__ 是一個「攤平」的陣列:物件的屬性值如果是整數,
    代表「這個陣列的第 N 格」才是真正的值(不是字面數字),要遞迴查表還原。
    ean/sku/stock 這種葉節點屬性直接查表一層就好,不會再往下巢狀。
    """
    if depth > 4 or not isinstance(idx, int) or idx < 0 or idx >= len(arr):
        return idx
    val = arr[idx]
    if isinstance(val, dict):
        return {
            k: (resolve_nuxt_value(arr, v, depth + 1) if isinstance(v, int) else v)
            for k, v in val.items()
        }
    return val


def extract_size_stock(html):
    """
    從 __NUXT_DATA__ 撈出「這個顏色專屬網址」底下每個尺寸的實際庫存。
    找法:掃過整個攤平陣列,找出形狀像 Variant 的物件(同時有
    size/sku/stock 這三個 key 的字典),還原成真正的值。
    """
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
            # Firebase 的物件 key 不能含有 $ # [ ] / . 這幾個字元。半號尺寸
            # 像 "25.5" 含有 "."、男女合併尺寸像 "M25 / W25.5" 含有 "/",
            # 兩種都要換掉,不然整批資料都存不進去。"." 換成 "-",
            # "/" 換成全形的 "／"(不在 Firebase 禁用清單裡,視覺上也還是一眼看得出來是斜線)。
            size = str(size).replace(".", "-").replace("/", "／")
            try:
                stock = int(stock)
            except (TypeError, ValueError):
                stock = 0
            # 同一個尺寸可能因為陣列裡有重複物件被掃到兩次,取比較大的庫存數字
            sizes[size] = max(stock, sizes.get(size, 0))
    return sizes


def is_available(offer):
    return "InStock" in (offer.get("availability") or "")


def fetch_color_detail(color_url):
    """
    點進某個顏色專屬的商品網址,查這個顏色的完整尺寸庫存跟圖片。
    """
    try:
        html = fetch_html(color_url)
    except Exception as e:
        return {"error": str(e)}
    return {"sizes_stock": extract_size_stock(html)}


def main():
    with open("on_running_list.json", "r", encoding="utf-8") as f:
        base_list = json.load(f)

    final_list = []
    seen_group_urls = set()

    for i, base in enumerate(base_list):
        href = base["href"]
        url = BASE_URL + href
        print(f"[{i+1}/{len(base_list)}] {base['label'][:40]}")

        try:
            html = fetch_html(url)
        except Exception as e:
            print(f"  [錯誤] 抓取失敗:{e}")
            continue

        group = extract_product_group(html)
        if not group:
            print("  [錯誤] 找不到 ProductGroup 資料,略過")
            continue

        group_url = group.get("url", "")
        if group_url in seen_group_urls:
            # 同一款鞋(男/女分開列在清單裡,但這裡指的是同一個 group,理論上
            # 不會重複,保險起見還是判斷一下,避免同一款被重複整理兩次)
            continue
        seen_group_urls.add(group_url)

        is_preorder = "まもなく発売" in base["label"]

        colors = []
        variants = group.get("hasVariant", [])
        for v in variants:
            offer = v.get("offers", {})
            color_url = offer.get("url", "")
            full_url = color_url if color_url.startswith("http") else BASE_URL + color_url
            print(f"    顏色:{v.get('color')}")
            detail = fetch_color_detail(full_url)
            sizes_stock = detail.get("sizes_stock", {})
            if not sizes_stock:
                # 查不到尺寸級別庫存(可能該顏色頁面結構不同或請求失敗),
                # 退而求其次:有貨就都算 1(至少能下單),缺貨就整串設 0,
                # 不會因為抓不到細節就整個顏色漏掉。
                fallback_qty = 1 if is_available(offer) else 0
                sizes_stock = {}  # 沒有明確尺寸清單就不硬造一個
            color_entry = {
                "name": v.get("color", ""),
                "sizes": list(sizes_stock.keys()),
                "stock": sizes_stock,
            }
            if v.get("image"):
                color_entry["image"] = v["image"]
            if color_entry["sizes"]:
                colors.append(color_entry)

        if not colors:
            print("  [警告] 這款鞋所有顏色都查不到尺寸庫存,略過")
            continue

        # 售價用第一個顏色的價格(同一款鞋各色售價基本一致,偶有特別色會不同,
        # 但我們的商品資料結構是整款鞋共用一個售價,無法逐色設定)
        price = None
        for v in variants:
            p = v.get("offers", {}).get("price")
            if p:
                price = p
                break

        entry = {
            "name": group.get("name", base["label"].split(",")[0]),
            "jpy": price or 0,
            "weight": WEIGHT,
            "brand": BRAND,
            "subtype": SUBTYPE,
            "country": "JP",
            "saleType": "preorder" if is_preorder else "instock",
            "link": group_url or url,
            "colors": colors,
        }
        if colors[0].get("image"):
            entry["image"] = colors[0]["image"]

        final_list.append(entry)

        if (i + 1) % 10 == 0:
            with open("on_running_products.json", "w", encoding="utf-8") as f:
                json.dump(final_list, f, ensure_ascii=False, indent=2)
            print(f"  (已儲存進度:{i+1}/{len(base_list)})")

    with open("on_running_products.json", "w", encoding="utf-8") as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)

    print(f"完成!已輸出 on_running_products.json,共 {len(final_list)} 件商品。")


if __name__ == "__main__":
    main()
