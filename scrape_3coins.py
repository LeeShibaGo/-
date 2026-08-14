# -*- coding: utf-8 -*-
"""
3COINS(スリーコインズ,PAL集團旗下生活雜貨/時尚配件品牌)商品爬蟲
------------------------------------------------------------
用途:
  抓 3COINS 在 PAL CLOSET 商城(palcloset.jp)上架的商品,輸出
  3coins_full_products.json,格式跟 daigou-products-v1 裡其他多顏色
  品牌(On、Salomon、GU)完全一樣,可以直接合併進 Firebase。

範圍(2026-08-13 老闆確認):只抓「時尚配件類」——包包、髮飾、飾品、
帽子、錢包小物這五大類(CATEGORY_IDS),大約 1,900 件商品。3COINS
官網其實是生活雜貨百貨,還有廚房用品/收納/家電小物/寢具等 20+ 大分類、
全站粗估 5,000+ 件,那些不在這次的範圍內,故意不抓。

技術細節(這個商城平台不需要瀏覽器渲染,純 requests 就能拿到完整資料,
跟 HONMA/DESCENTE 那種一定要 Playwright 的情況不一樣):
  1) 分類商品列表(找出這個分類底下有哪些商品):
       GET /display/display/?mode=zSearch&b=3coins&c={category_id}&sex=&cpvcd=&p={page}&type=01
     一般不加 mode=zSearch 直接開分類頁,商品是網頁載入後才用 JS 灌進去的
     (ZETA/RetailSearch 搜尋外掛),原始 HTML 是空的;但只要在網址加上
     mode=zSearch,伺服器端就會直接把商品清單渲染進 HTML 回傳,不需要
     JS。分頁參數是 p(從 1 開始)+ type=01,固定每頁 120 件——這組參數
     不是文件寫的,是實際在瀏覽器點分頁按鈕、看 network 請求反查出來的
     (直接猜 page=2/pageNo=2 都是錯的,url 送出去但被忽略,回傳還是
     第一頁)。
  2) 商品詳細頁(每個商品的顏色/尺寸/庫存):
       GET /display/item/{item_slug}/?cl=01&b=3coins&ss=
     item_slug 是列表頁 <a href="/display/item/{slug}/..."> 裡的網址
     代碼,例如 "1909-B25-CP-000"。詳細頁裡每個 <div class="cbk_sku_wrapper">
     區塊是一個顏色款式,class 多帶 "contain_out_of_stock" 代表這個顏色
     缺貨;裡面的 <dt>{尺寸}/<span>在庫あり/在庫なし</span></dt> 才是
     真正的庫存有無(3COINS 大多數商品沒有真正的「尺寸」選項,只有單一
     FREE 尺寸,但寫成迴圈通用處理,遇到少數真的有多尺寸的款式也能抓)。
  3) 價格是稅込(含稅)顯示價,直接讀 <span id="price_standard_from_id">
     旁邊的數字,不用像 DHC 那樣另外處理稅前/稅後轉換。

分類(subtype)對照:
  盡量對到 index.html SUBTYPE_GROUP 已經有的 key,這樣不用改前端就能
  自動歸進正確的大分類(包包/配件)。髮飾類原本沒有對應的 key,新增
  「髮飾」這個 subtype,同時要在 index.html SUBTYPE_GROUP 補一行
  '髮飾': '配件'。

執行方式:
  pip install -r requirements.txt
  python scrape_3coins.py

會輸出 3coins_full_products.json。
"""

import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import requests
from bs4 import BeautifulSoup

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

BASE = "https://www.palcloset.jp"
LIST_URL = f"{BASE}/display/display/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}
BRAND = "3COINS"
PAGE_SIZE = 120
WORKERS = 8

# category id -> (日文分類名稱,中文 subtype)。subtype 盡量對到 index.html
# SUBTYPE_GROUP 既有的 key(包款/後背包/波士頓包/斜背小包/其他包款/皮夾/
# 小型皮件/圍巾配件/服飾配件/鑰匙圈吊飾/鑰匙包/護照套/配件/帽子/珠寶飾品),
# 只有「髮飾」是新的,需要另外在 index.html 補一行 SUBTYPE_GROUP 對照。
CATEGORY_IDS = {
    # BAG バッグ
    1701: ("ショルダーバッグ", "肩背包"),
    1702: ("トート/ミニトートバッグ", "包款"),
    1703: ("バックパック/リュック", "後背包"),
    1704: ("ボストン/ミニボストンバッグ", "波士頓包"),
    1706: ("ハンドバッグ", "包款"),
    1712: ("エコバッグ", "包款"),
    1713: ("かごバッグ", "包款"),
    1715: ("スマホショルダーバッグ/ポーチ", "斜背小包"),
    1716: ("ビジネスバッグ", "包款"),
    1799: ("その他バッグ", "其他包款"),
    # WALLET＆GOODS 財布/小物
    2015: ("財布", "皮夾"),
    2002: ("コインケース/札入れ", "小型皮件"),
    2004: ("ポーチ", "小型皮件"),
    2005: ("手鏡/コンパクト", "配件"),
    2006: ("ハンカチ/ハンドタオル", "服飾配件"),
    2007: ("バンダナ/スカーフ", "圍巾配件"),
    2008: ("キーホルダー", "鑰匙圈吊飾"),
    2009: ("キーケース/キーアクセサリー", "鑰匙包"),
    2011: ("パスケース", "護照套"),
    2099: ("その他財布/小物", "小型皮件"),
    # HAIR ACCESSORIES ヘアアクセサリー(全部歸進新 subtype「髮飾」)
    2201: ("ヘアゴム/ポニー", "髮飾"),
    2202: ("ヘアバンド/ターバン", "髮飾"),
    2203: ("カチューシャ", "髮飾"),
    2204: ("バレッタ/ヘアクリップ", "髮飾"),
    2205: ("シュシュ", "髮飾"),
    2206: ("バナナ/バンス", "髮飾"),
    2207: ("ヘアピン", "髮飾"),
    2208: ("ヘアカフ", "髮飾"),
    2299: ("その他ヘアアクセサリー", "髮飾"),
    # ACCESSORIES アクセサリー(全部歸進既有的「珠寶飾品」)
    2301: ("ネックレス", "珠寶飾品"),
    2302: ("リング", "珠寶飾品"),
    2303: ("ピアス", "珠寶飾品"),
    2305: ("イヤリング", "珠寶飾品"),
    2311: ("イヤーカフ", "珠寶飾品"),
    2306: ("ブレスレット", "珠寶飾品"),
    2309: ("ブローチ/コサージュ", "珠寶飾品"),
    2310: ("ネックレスチャーム", "珠寶飾品"),
    # CAPS 帽子
    2601: ("キャップ", "帽子"),
    2602: ("ハット", "帽子"),
}

WEIGHT_BY_SUBTYPE = {
    "肩背包": 0.35, "包款": 0.3, "後背包": 0.45, "波士頓包": 0.5, "斜背小包": 0.2,
    "其他包款": 0.3, "皮夾": 0.15, "小型皮件": 0.1, "配件": 0.08, "服飾配件": 0.08,
    "圍巾配件": 0.1, "鑰匙圈吊飾": 0.03, "鑰匙包": 0.08, "護照套": 0.05,
    "髮飾": 0.03, "珠寶飾品": 0.03, "帽子": 0.15,
}
DEFAULT_WEIGHT = 0.1


def http_get(url, params=None, retries=3):
    for attempt in range(retries):
        try:
            res = requests.get(url, params=params, headers=HEADERS, timeout=20)
            if res.status_code != 200:
                return None
            return res.text
        except Exception as e:
            if attempt == retries - 1:
                print(f"  [錯誤] {url} {params} -> {e}")
                return None
            time.sleep(1)
    return None


def upgrade_image(src):
    """列表頁圖是縮圖(/static/images/item/120/xxx.jpg 或 /360/),
    拿掉尺寸資料夾拿原圖網址。"""
    if not src:
        return src
    return re.sub(r"/static/images/item/(120|360)/", "/static/images/item/", src)


def fetch_category_items(cat_id, ja_name, subtype):
    """回傳這個分類底下所有商品的 (slug, name, jpy, image, subtype) list,自動翻頁。

    2026-08-13 抓到:列表頁一張卡是「一個顏色」不是「一個商品」,同一件
    商品有幾個顏色就會在同一頁裡出現幾次(slug 相同,只有網址上的
    cl= 顏色參數不同)。判斷「這一頁是不是最後一頁」不能用「去重後這頁
    新增了幾件商品」(可能整頁 120 張卡都是同一批商品的不同顏色,去重完
    只剩幾十件,卻不代表後面沒有下一頁了),要用「這一頁原始卡片總數」
    來判斷,原始卡片數 < PAGE_SIZE 才代表真的翻完了。
    """
    items = []
    seen_slugs = set()
    page = 1
    while True:
        html = http_get(LIST_URL, {
            "mode": "zSearch", "b": "3coins", "c": cat_id, "sex": "", "cpvcd": "",
            "p": page, "type": "01",
        })
        if not html:
            break
        soup = BeautifulSoup(html, "html.parser")
        item_list = soup.select_one("#item_list")
        cards = item_list.select("li") if item_list else []
        raw_card_count = 0
        for li in cards:
            a = li.find("a", href=re.compile(r"^/display/item/"))
            if not a:
                continue
            raw_card_count += 1
            m = re.search(r"/display/item/([^/]+)/", a["href"])
            if not m:
                continue
            slug = m.group(1)
            if slug in seen_slugs:
                continue
            seen_slugs.add(slug)
            name_el = a.select_one(".textOverflow p")
            price_el = a.select_one(".price .tt01")
            img_el = a.find("img")
            name = name_el.get_text(strip=True) if name_el else ""
            price_text = price_el.get_text(strip=True) if price_el else ""
            jpy = int(re.sub(r"[^\d]", "", price_text)) if price_text else 0
            image = None
            if img_el:
                image = img_el.get("data-src") or img_el.get("src")
                image = upgrade_image(image)
            if not name:
                continue
            items.append({
                "slug": slug, "name": name, "jpy": jpy, "image": image,
                "subtype": subtype,
            })
        if raw_card_count == 0:
            break
        page += 1
        if page > 60:  # 安全上限(120*60=7200 張卡),避免分頁邏輯出錯時無限迴圈
            print(f"  [警告] 分類 {cat_id} {ja_name} 已翻到第 60 頁,強制停止")
            break
        if raw_card_count < PAGE_SIZE:
            break
    return items


def fetch_product_detail(slug):
    """回傳 (name, jpy, colors)。colors 是 [{name, sizes, stock, image}]。"""
    html = http_get(f"{BASE}/display/item/{slug}/", {"cl": "01", "b": "3coins", "ss": ""})
    if not html:
        return None, None, []
    soup = BeautifulSoup(html, "html.parser")
    name_el = soup.select_one("#di_name_id")
    price_el = soup.select_one("#price_standard_from_id")
    name = name_el.get_text(strip=True) if name_el else ""
    jpy = int(re.sub(r"[^\d]", "", price_el.get_text())) if price_el else 0

    colors = []
    for wrap in soup.select(".cbk_sku_wrapper"):
        # id="cbk_sku_wrapper_base" 是頁面裡藏起來(style="display:none")的
        # jQuery clone 樣板,JS 用它複製出每個真正的顏色區塊,樣板本身不是
        # 真實資料,一定要排除,不然會多出一組空白的假顏色。
        if wrap.get("id") == "cbk_sku_wrapper_base":
            continue
        color_el = wrap.select_one(".cart_pic__desc__color")
        color_name = color_el.get_text(strip=True).replace("カラー：", "") if color_el else "其他"
        img_el = wrap.select_one(".cart_pic img")
        image = upgrade_image(img_el.get("src")) if img_el else None
        sizes, stock = [], {}
        for dl in wrap.select("dl.cart_inbox"):
            dt = dl.select_one("dt")
            if not dt:
                continue
            dt_text = dt.get_text(" ", strip=True)
            # 格式是「{尺寸}/{在庫あり or 在庫なし}」,尺寸本身可能包含
            # 除了 / 以外的任何字元(例如 "FREE"),用 [^/]+ 而不是 \S+,
            # 不然 \S+ 會把後面那個 / 也吃進尺寸名稱裡。
            m = re.match(r"([^/]+)/\s*(在庫あり|在庫なし)", dt_text)
            if not m:
                # 沒有明確尺寸/庫存文字的話,退而求其次用整塊 class 判斷
                size_key = "FREE"
                has_stock = "contain_out_of_stock" not in (wrap.get("class") or [])
            else:
                size_key = m.group(1).strip()
                has_stock = m.group(2) == "在庫あり"
            if size_key not in stock:
                sizes.append(size_key)
            stock[size_key] = max(stock.get(size_key, 0), 1 if has_stock else 0)
        if not sizes:
            sizes = ["FREE"]
            stock = {"FREE": 0 if "contain_out_of_stock" in (wrap.get("class") or []) else 1}
        colors.append({"name": color_name, "sizes": sizes, "stock": stock, "image": image})
    return name, jpy, colors


def guess_weight(subtype):
    return WEIGHT_BY_SUBTYPE.get(subtype, DEFAULT_WEIGHT)


def main():
    print(f"[1/2] 列出 {len(CATEGORY_IDS)} 個分類底下的商品...")
    all_items = {}  # slug -> item dict(取第一次看到的資料)
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {
            ex.submit(fetch_category_items, cid, ja, st): (cid, ja)
            for cid, (ja, st) in CATEGORY_IDS.items()
        }
        done = 0
        for fut in futures:
            cid, ja = futures[fut]
            done += 1
            try:
                items = fut.result()
            except Exception as e:
                print(f"  [錯誤] 分類 {cid} {ja}: {e}")
                items = []
            for it in items:
                all_items.setdefault(it["slug"], it)
            print(f"  ({done}/{len(CATEGORY_IDS)}) {ja}: {len(items)} 件,目前累積 {len(all_items)} 件不重複商品")

    print(f"共 {len(all_items)} 件不重複商品,開始抓每件的顏色/庫存...")

    final_list = []
    slugs = list(all_items.keys())

    def process(slug):
        base = all_items[slug]
        name, jpy, colors = fetch_product_detail(slug)
        if not colors:
            return None
        if not name:
            name = base["name"]
        if not jpy:
            jpy = base["jpy"]
        if base.get("image") and colors and not colors[0].get("image"):
            colors[0]["image"] = base["image"]
        return {
            "name": name,
            "jpy": jpy,
            "weight": guess_weight(base["subtype"]),
            "brand": BRAND,
            "subtype": base["subtype"],
            "country": "JP",
            "saleType": "instock",
            "image": base.get("image"),
            "link": f"{BASE}/display/item/{slug}/?cl=01&b=3coins&ss=",
            "colors": colors,
        }

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        done = 0
        for entry in ex.map(process, slugs):
            done += 1
            if entry:
                final_list.append(entry)
            if done % 200 == 0:
                print(f"  ({done}/{len(slugs)},已取得 {len(final_list)} 件)")
                with open("3coins_full_products.json", "w", encoding="utf-8") as f:
                    json.dump(final_list, f, ensure_ascii=False, indent=2)

    with open("3coins_full_products.json", "w", encoding="utf-8") as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)

    print(f"完成!已輸出 3coins_full_products.json,共 {len(final_list)} 件商品。")


if __name__ == "__main__":
    main()
