# -*- coding: utf-8 -*-
"""產生每件商品的靜態 SEO/分享頁面(product/{id}/index.html)
------------------------------------------------------------
用途:
  跟 generate_brand_pages.py 是同一個原因(見該檔開頭說明):主站
  index.html 整頁都是 JS 動態產生,搜尋引擎/LINE、FB 分享預覽的爬蟲
  抓不到內容。brand 頁面解決了「品牌」這一層,但客人把單一商品的
  ?p=商品id 連結貼到 LINE 群組時,預覽小卡顯示的還是整個網站的通用
  縮圖,不是那件商品自己的照片/名稱/價格——這支把這一層也補上。

  2026-08-21 老闆確認要做,主要目的兩個都要:
    1) 分享單一商品連結時,LINE/FB 預覽小卡要顯示那件商品自己的照片、
       名稱、價格(不是網站通用縮圖)
    2) 讓 Google 有機會直接索引「品牌+商品名稱」的搜尋結果

  範圍:只產生「沒有被老闆隱藏、而且不是全面缺貨」的商品頁面
  (isFullySoldOut() 邏輯直接複用 sync_stock.py 的 _is_fully_sold_out,
  兩邊要保持一致,不要另外寫一份)。已下架/賣完的商品沒有頁面對客人
  沒有意義,也不該被 Google 索引到,徒增網站規模又指去一個「缺貨」的
  死頁面。實測 2026-08-21:20,303 件商品裡符合條件的約 1.9 萬件。

  每頁內容:
    - 商品專屬的 <title>/OG 標籤(圖片用該商品實際的照片)
    - schema.org Product 結構化資料(JSON-LD),讓 Google 有機會顯示
      加值搜尋結果(價格/現貨狀態)
    - 靜態顯示商品名稱/價格/顏色清單(純文字,不做互動選色/加購物車
      ——那些邏輯只在主站 index.html 維護一份,這裡故意不重做,避免
      兩邊分開維護、公式跑不同步)
    - 「前往網站查看/加入購物車」按鈕連回主站 ?p=商品id 深連結

  跟 generate_brand_pages.py 的分工:
    這支負責寫 product/{id}/index.html,並把自己產生的網址列表存到
    PRODUCT_SITEMAP_TMP(暫存檔,不進 git),讓 generate_brand_pages.py
    收尾寫 sitemap.xml 的時候一併讀進來合併,只維護一份 sitemap.xml,
    不要兩支各自寫、互相覆蓋掉對方的網址。GitHub Actions 裡這支要排在
    generate_brand_pages.py 之前執行。

執行方式:
  python generate_product_pages.py
  建議跟 generate_brand_pages.py 一樣排進每天的 GitHub Actions,緊接在
  它之前執行。
"""
import json
import os
import sys

from generate_brand_pages import (
    BRAND_SLUGS, SITE_BASE, esc, fetch_dict, fetch_list, product_brand,
)
from sync_stock import _is_fully_sold_out

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

OUTPUT_DIR = "product"
PRODUCT_SITEMAP_TMP = "_product_sitemap_urls.txt"


def brand_slug(brand):
    return BRAND_SLUGS.get(brand)


def render_page(p, brand, slug, shop_name):
    pid = p["id"]
    name = p.get("name", "")
    jpy = p.get("jpy", 0)
    image = p.get("image") or (p.get("colors") or [{}])[0].get("image")
    subtype = p.get("subtype", "")
    desc_text = p.get("desc", "")
    color_names = [c.get("name") for c in (p.get("colors") or []) if c.get("name")]

    page_url = f"{SITE_BASE}/product/{esc(pid)}/"
    shop_link = f"{SITE_BASE}/?p={esc(pid)}"

    badge_parts = [b for b in [brand, subtype] if b]
    description = f"{' · '.join(badge_parts)},¥{jpy:,}。{shop_name}日本/韓國代購,正版保證,即時更新現貨與價格。"[:150]

    colors_html = ""
    if color_names:
        chips = "".join(f'<span class="chip">{esc(c)}</span>' for c in color_names)
        colors_html = f'<div class="colors">{chips}</div>'

    brand_link_html = ""
    if slug:
        brand_link_html = f'<a class="home-link" href="{SITE_BASE}/brand/{esc(slug)}/">← {esc(brand)} 所有商品</a>'
    else:
        brand_link_html = f'<a class="home-link" href="{SITE_BASE}/">← 回 {esc(shop_name)} 首頁</a>'

    # 用 json.dumps() 而不是自己手動拼字串轉義——商品名稱偶爾會帶引號
    # (例如 "Men's"),手動拼容易漏轉義、把 JSON-LD 弄壞,json.dumps 對
    # 特殊字元的處理才是可靠的。
    ld_data = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": name,
        "brand": {"@type": "Brand", "name": brand},
        "offers": {
            "@type": "Offer",
            "priceCurrency": "JPY",
            "price": jpy,
            "availability": "https://schema.org/InStock",
            "url": page_url,
        },
    }
    if image:
        ld_data["image"] = image
    # 商品名稱萬一剛好包含 "</script>" 這種子字串(理論上可能,雖然這批
    # 資料是自己爬來的、不是使用者輸入),會提早關掉這個 <script> 標籤、
    # 把後面的 HTML 弄壞,轉義掉 "</" 保險一點。
    ld_json = json.dumps(ld_data, ensure_ascii=False).replace("</", "<\\/")

    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(name)} - {esc(brand)}代購 - {esc(shop_name)}</title>
<meta name="description" content="{esc(description)}">
<meta property="og:title" content="{esc(name)}">
<meta property="og:description" content="{esc(description)}">
{f'<meta property="og:image" content="{esc(image)}">' if image else ""}
<meta property="og:type" content="product">
<link rel="canonical" href="{page_url}">
<script type="application/ld+json">{ld_json}</script>
<style>
  body{{font-family:'Noto Sans TC',sans-serif; max-width:640px; margin:0 auto; padding:24px 20px 80px; color:#141F2B; background:#F4EFE2;}}
  a{{color:inherit;}}
  .home-link{{font-size:13px; color:#6B7686; text-decoration:none;}}
  .photo{{width:100%; aspect-ratio:1; object-fit:cover; border-radius:12px; margin:16px 0; background:#eee;}}
  .badges{{font-size:12px; color:#6B7686; margin-bottom:6px;}}
  h1{{font-family:'Noto Serif TC',serif; font-size:22px; margin:0 0 10px; line-height:1.4;}}
  .price{{font-family:monospace; font-size:20px; font-weight:700; color:#A6392C; margin-bottom:14px;}}
  .colors{{display:flex; flex-wrap:wrap; gap:6px; margin-bottom:18px;}}
  .chip{{background:#fff; border-radius:999px; padding:5px 12px; font-size:12px;}}
  .desc{{line-height:1.8; color:#233648; margin-bottom:20px; white-space:pre-line;}}
  .cta{{display:block; text-align:center; background:#C9973F; color:#141F2B; padding:14px 22px; border-radius:10px; font-weight:700; text-decoration:none;}}
</style>
</head>
<body>
  {brand_link_html}
  {f'<img class="photo" src="{esc(image)}" alt="{esc(name)}">' if image else ""}
  <div class="badges">{esc(" · ".join(badge_parts))}</div>
  <h1>{esc(name)}</h1>
  <div class="price">¥{jpy:,}</div>
  {colors_html}
  {f'<div class="desc">{esc(desc_text)}</div>' if desc_text else ""}
  <a class="cta" href="{shop_link}">前往網站查看規格、加入購物車 →</a>
</body>
</html>
"""


def main():
    print("抓取商品/設定資料...")
    products = [p for p in fetch_list("daigou-products-v1") if p]
    settings = fetch_dict("daigou-settings-v1")
    shop_name = settings.get("shopName") or "柴代購 ShibaGo"

    eligible = [
        p for p in products
        if p.get("id") and p.get("name") and not p.get("hidden") and not _is_fully_sold_out(p)
    ]
    print(f"商品共 {len(products)} 件,可產生頁面的(未隱藏、未全面缺貨)有 {len(eligible)} 件")

    urls = []
    generated = 0
    for p in eligible:
        brand = product_brand(p)
        slug = brand_slug(brand)
        html = render_page(p, brand, slug, shop_name)
        out_dir = os.path.join(OUTPUT_DIR, p["id"])
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
            f.write(html)
        urls.append(f"{SITE_BASE}/product/{p['id']}/")
        generated += 1
        if generated % 2000 == 0:
            print(f"  已產生 {generated}/{len(eligible)}")

    with open(PRODUCT_SITEMAP_TMP, "w", encoding="utf-8") as f:
        f.write("\n".join(urls))

    print(f"共產生 {generated} 個商品頁面,網址清單已寫到 {PRODUCT_SITEMAP_TMP}"
          f"(給 generate_brand_pages.py 合併進 sitemap.xml 用)")


if __name__ == "__main__":
    main()
