# -*- coding: utf-8 -*-
"""產生每個品牌的靜態 SEO 頁面(brand/{slug}/index.html)
------------------------------------------------------------
用途:
  主網站(index.html)整頁都是 JavaScript 動態產生內容,Google 第一時間
  抓到的原始 HTML 裡完全沒有商品/品牌文字,搜尋引擎不容易索引、
  LINE/FB 分享連結預覽小卡也抓不到內容(社群平台的爬蟲通常不執行 JS)。

  這支程式幫每個品牌另外產生一份「純 HTML、不需要跑 JavaScript 就看得到
  內容」的靜態頁面,放在 brand/{slug}/index.html,包含:
    - 品牌獨立的 <title>/<meta description>(SEO)
    - 品牌介紹文字(從 settings.brandIntros 讀,老闆自己在後台填寫;
      沒填就跳過這段,不留「尚未填寫」這種字樣在公開頁面上)
    - 精選/熱門商品(用真實訂單算出的銷售數量排序,完全沒有銷售紀錄
      的品牌就退而求其次列出現貨商品,標題改叫「精選商品」而不是「熱門
      商品」,不假裝有熱銷數據)
    - FAQ(沿用 settings.faq 的內容)
    - 導回主站對應品牌篩選頁的連結(/-/{品牌名}),真正要下單還是要
      到主站,這裡不重做一次購物車/計價邏輯,避免兩邊公式不同步。

  執行方式:
    python generate_brand_pages.py
  建議跟 sync_stock.py 一樣排進每天的 GitHub Actions,商品/庫存/品牌
  介紹更新之後,靜態頁面才會跟著換新。
"""
import json
import os
import re
import sys

import requests

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
FIREBASE_PRODUCTS = "https://shibago-4dd3c-default-rtdb.asia-southeast1.firebasedatabase.app/daigou-products-v1.json"
FIREBASE_SETTINGS = "https://shibago-4dd3c-default-rtdb.asia-southeast1.firebasedatabase.app/daigou-settings-v1.json"
FIREBASE_ORDERS = "https://shibago-4dd3c-default-rtdb.asia-southeast1.firebasedatabase.app/daigou-orders-v1.json"

SITE_BASE = "https://leeshibago.github.io/-"
OUTPUT_DIR = "brand"

# 品牌名稱 -> 網址代稱(slug)。新增品牌時記得回來補一筆,沒補到的品牌
# 就不會產生靜態頁面(不影響主站,主站的品牌篩選跟這份清單無關)。
BRAND_SLUGS = {
    "Salomon": "salomon",
    "BAPE": "bape",
    "Carhartt WIP": "carhartt-wip",
    "DESCENTE": "descente",
    "AAPE": "aape",
    "Lacoste": "lacoste",
    "Onitsuka Tiger": "onitsuka-tiger",
    "On": "on",
    "UNIQLO": "uniqlo",
    "J.Lindeberg": "j-lindeberg",
    "HONMA": "honma",
    "Dior 日本限定": "dior-japan-exclusive",
    "Louis Vuitton": "louis-vuitton",
    "TaylorMade": "taylormade",
    "Dior": "dior",
    "GU": "gu",
}


def fetch_list(url):
    """給 products/orders 用:Firebase 存的 key 如果不是連續數字索引,
    讀出來會是物件而不是陣列,這裡一律轉成陣列。"""
    r = requests.get(url, headers=HEADERS, timeout=60)
    r.raise_for_status()
    data = r.json()
    if data is None:
        return []
    return data if isinstance(data, list) else list(data.values())


def fetch_dict(url):
    """給 settings 用:本來就是單一物件,不要被轉成陣列。"""
    r = requests.get(url, headers=HEADERS, timeout=60)
    r.raise_for_status()
    return r.json() or {}


def product_brand(p):
    return p.get("brand") or p.get("category") or "其他"


def compute_sold_qty(products, orders):
    """比照網站 JS 的 getSoldQty():訂單裡「無法完成」不算,其餘用
    productId 對應、對不到的用商品名稱對應,再加上手動加成的 extraSoldQty。"""
    by_id, by_name = {}, {}
    for o in orders:
        if not o or o.get("status") == "無法完成":
            continue
        for item in o.get("items", []):
            qty = item.get("qty", 0) or 0
            pid = item.get("productId")
            name = item.get("name")
            if pid:
                by_id[pid] = by_id.get(pid, 0) + qty
            if name:
                by_name[name] = by_name.get(name, 0) + qty

    result = {}
    for p in products:
        qty = by_id.get(p.get("id"), 0) + by_name.get(p.get("name"), 0) + (p.get("extraSoldQty") or 0)
        result[p["id"]] = qty
    return result


def parse_brand_intros(raw):
    """格式比照 FAQ:一個品牌一組用 --- 分隔,第一行是品牌名稱、其餘是介紹。"""
    intros = {}
    if not raw:
        return intros
    for block in raw.split("---"):
        block = block.strip()
        if not block:
            continue
        lines = block.split("\n")
        name = lines[0].strip()
        body = "\n".join(lines[1:]).strip()
        if name and body:
            intros[name] = body
    return intros


def parse_faq(raw):
    blocks = []
    if not raw:
        return blocks
    for block in raw.split("---"):
        block = block.strip()
        if not block:
            continue
        lines = block.split("\n")
        q = lines[0].strip()
        a = "\n".join(lines[1:]).strip()
        if q:
            blocks.append((q, a))
    return blocks


def esc(s):
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render_page(brand, slug, intro_text, items, sold_map, shop_name, faq_blocks, has_real_sales):
    section_title = "熱門商品" if has_real_sales else "精選商品"
    product_cards = []
    for p in items:
        img = esc(p.get("image", ""))
        name = esc(p.get("name", ""))
        jpy = p.get("jpy", 0)
        link = f"{SITE_BASE}/?p={esc(p['id'])}"
        sold = sold_map.get(p["id"], 0)
        sold_html = f'<div class="sold">🔥 已售 {sold} 件</div>' if sold > 0 else ""
        product_cards.append(f"""
      <a class="card" href="{link}">
        {f'<img src="{img}" alt="{name}" loading="lazy">' if img else ''}
        <div class="name">{name}</div>
        <div class="price">¥{jpy:,}</div>
        {sold_html}
      </a>""")

    intro_html = ""
    if intro_text:
        paras = "".join(f"<p>{esc(line)}</p>" for line in intro_text.split("\n") if line.strip())
        intro_html = f'<section class="intro">{paras}</section>'

    faq_html = ""
    if faq_blocks:
        items_html = "".join(
            f'<div class="faq-item"><div class="q">Q. {esc(q)}</div><div class="a">{esc(a)}</div></div>'
            for q, a in faq_blocks
        )
        faq_html = f'<section class="faq"><h2>常見問題</h2>{items_html}</section>'

    description = (intro_text.split("\n")[0] if intro_text else f"{brand} 日本/韓國代購,{shop_name}即時更新現貨與價格,{len(items)}+ 件商品線上選購。")[:150]

    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(brand)} 代購 - {esc(shop_name)}</title>
<meta name="description" content="{esc(description)}">
<meta property="og:title" content="{esc(brand)} 代購 - {esc(shop_name)}">
<meta property="og:description" content="{esc(description)}">
{f'<meta property="og:image" content="{esc(items[0]["image"])}">' if items and items[0].get("image") else ""}
<link rel="canonical" href="{SITE_BASE}/brand/{esc(slug)}/">
<style>
  body{{font-family:'Noto Sans TC',sans-serif; max-width:960px; margin:0 auto; padding:24px 20px 80px; color:#141F2B; background:#F4EFE2;}}
  a{{color:inherit;}}
  .home-link{{font-size:13px; color:#6B7686; text-decoration:none;}}
  h1{{font-family:'Noto Serif TC',serif; font-size:28px; margin:16px 0 8px;}}
  .cta{{display:inline-block; margin:12px 0 24px; background:#C9973F; color:#141F2B; padding:12px 22px; border-radius:10px; font-weight:700; text-decoration:none;}}
  .intro p{{line-height:1.9; color:#233648;}}
  h2{{font-family:'Noto Serif TC',serif; font-size:20px; margin-top:36px;}}
  .grid{{display:grid; grid-template-columns:repeat(auto-fill, minmax(160px,1fr)); gap:16px; margin-top:16px;}}
  .card{{display:block; background:#fff; border-radius:12px; padding:10px; text-decoration:none; color:#141F2B;}}
  .card img{{width:100%; aspect-ratio:1; object-fit:cover; border-radius:8px; margin-bottom:8px; background:#eee;}}
  .card .name{{font-size:13px; font-weight:700; line-height:1.4; margin-bottom:4px;}}
  .card .price{{font-size:13px; color:#6B7686; font-family:monospace;}}
  .card .sold{{font-size:11px; color:#A6392C; margin-top:4px;}}
  .faq-item{{margin-bottom:18px;}}
  .faq-item .q{{font-weight:700; margin-bottom:4px;}}
  .faq-item .a{{color:#233648; white-space:pre-line; line-height:1.7;}}
</style>
</head>
<body>
  <a class="home-link" href="{SITE_BASE}/">← 回 {esc(shop_name)} 首頁</a>
  <h1>{esc(brand)} 代購</h1>
  {intro_html}
  <a class="cta" href="{SITE_BASE}/{esc(brand)}">查看全部 {esc(brand)} 代購商品 →</a>
  <section>
    <h2>{section_title}</h2>
    <div class="grid">{"".join(product_cards)}</div>
  </section>
  {faq_html}
</body>
</html>
"""


def main():
    print("抓取商品/設定/訂單資料...")
    products = [p for p in fetch_list(FIREBASE_PRODUCTS) if p]
    settings = fetch_dict(FIREBASE_SETTINGS)
    orders = [o for o in fetch_list(FIREBASE_ORDERS) if o]

    shop_name = settings.get("shopName") or "柴代購 ShibaGo"
    intros = parse_brand_intros(settings.get("brandIntros", ""))
    faq_blocks = parse_faq(settings.get("faq", ""))
    sold_map = compute_sold_qty(products, orders)

    by_brand = {}
    for p in products:
        by_brand.setdefault(product_brand(p), []).append(p)

    generated = []
    for brand, slug in BRAND_SLUGS.items():
        items = by_brand.get(brand, [])
        if not items:
            print(f"  跳過 {brand}:目前沒有上架商品")
            continue

        has_real_sales = any(sold_map.get(p["id"], 0) > 0 for p in items)
        if has_real_sales:
            ranked = sorted(items, key=lambda p: sold_map.get(p["id"], 0), reverse=True)
        else:
            ranked = items
        top_items = ranked[:8]

        html = render_page(brand, slug, intros.get(brand, ""), top_items, sold_map, shop_name, faq_blocks, has_real_sales)
        out_dir = os.path.join(OUTPUT_DIR, slug)
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, "index.html")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)
        generated.append((brand, slug, len(items)))
        print(f"  已產生 {out_path}({brand},{len(items)} 件商品,intro={'有' if brand in intros else '未填寫'})")

    # sitemap.xml:讓 Google 知道有這些頁面存在,不用完全靠自己爬到
    urls = [f"{SITE_BASE}/"] + [f"{SITE_BASE}/brand/{slug}/" for _, slug, _ in generated]
    sitemap = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for u in urls:
        sitemap += f"  <url><loc>{esc(u)}</loc></url>\n"
    sitemap += "</urlset>\n"
    with open("sitemap.xml", "w", encoding="utf-8") as f:
        f.write(sitemap)

    print(f"\n共產生 {len(generated)} 個品牌頁面,sitemap.xml 已更新")


if __name__ == "__main__":
    main()
