# -*- coding: utf-8 -*-
"""每日庫存 + 價格同步(Salomon + On + Onitsuka Tiger)
------------------------------------------------------------
用途:
  網站上這幾個品牌商品的尺寸庫存,原本只是上架當下抓的快照,
  官網賣掉或補貨都不會反映。這支程式每天由 GitHub Actions 排程執行,
  重新到官網抓一次「每個顏色每個尺寸的庫存」和「目前售價」,
  直接更新 Firebase 上的商品資料,客人看到的缺貨狀態最多只落後一天。

比對方式:
  商品顏色名稱在網站上已翻成中文,沒辦法拿名字對照官網,
  所以用「顏色圖片的網址」當對照鍵:
  - Salomon:Shopify 圖片檔名(去掉 ?v= 版本參數)
  - On:Contentful 圖片網址裡的 asset id(路徑第二段)
  - Onitsuka Tiger:asics.scene7.com 圖片網址裡的貨號(SKU)
  圖片對不到的顏色(官網下架該配色)一律把庫存歸零,不刪資料。

執行方式:
  python sync_stock.py            # Salomon + On + Onitsuka Tiger 都跑
  python sync_stock.py salomon    # 只跑 Salomon(快,測試用)
  python sync_stock.py onitsuka   # 只跑 Onitsuka Tiger
"""

import json
import os
import re
import sys
import time

import requests

from scrape_on_full import extract_ldjson, extract_size_stock, fix_size_key
from scrape_onitsuka import ENDPOINT as ONITSUKA_ENDPOINT, HEADERS as ONITSUKA_HEADERS, QUERY as ONITSUKA_QUERY

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
price_change_lines = []  # 這次同步中所有官網價格變動,結束後彙整成一則 LINE 通知


def send_line(message):
    if not LINE_CHANNEL_ACCESS_TOKEN:
        print("[提示] 未設定 LINE_CHANNEL_ACCESS_TOKEN,價格變動摘要只印出不發送")
        return
    res = requests.post(
        "https://api.line.me/v2/bot/message/broadcast",
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"},
        json={"messages": [{"type": "text", "text": message[:4900]}]},
        timeout=15,
    )
    if res.status_code != 200:
        print(f"[錯誤] LINE 發送失敗:{res.status_code} {res.text}")

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

FIREBASE = "https://shibago-4dd3c-default-rtdb.asia-southeast1.firebasedatabase.app/daigou-products-v1.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
ON_BASE = "https://www.on.com"


def fetch(url, retries=4, timeout=30):
    for attempt in range(retries):
        try:
            res = requests.get(url, headers=HEADERS, timeout=timeout)
            res.raise_for_status()
            return res
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(4 * (attempt + 1))


def load_products():
    data = fetch(FIREBASE, timeout=60).json()
    items = data if isinstance(data, list) else list(data.values())
    return [p for p in items if p]


def save_products(items):
    res = requests.put(FIREBASE, data=json.dumps(items, ensure_ascii=False).encode("utf-8"),
                       headers={"Content-Type": "application/json"}, timeout=300)
    res.raise_for_status()
    print(f"Firebase 已更新(HTTP {res.status_code})")


# ---------- Salomon ----------

def salomon_image_key(url):
    # Shopify 圖片網址的 ?v= 版本參數會變,拿掉之後用檔名當對照鍵
    return (url or "").split("?")[0].rsplit("/", 1)[-1]


def sync_salomon(items):
    print("=== Salomon 同步開始 ===")
    shop_products = []
    page = 1
    while page <= 30:
        ps = fetch(f"https://salomon.jp/products.json?limit=250&page={page}").json().get("products", [])
        shop_products.extend(ps)
        if len(ps) < 250:
            break
        page += 1
        time.sleep(1.5)
    print(f"官網商品共 {len(shop_products)} 件")

    by_image = {}
    for sp in shop_products:
        for img in sp.get("images", []):
            by_image[salomon_image_key(img.get("src"))] = sp

    cards = [p for p in items if p.get("brand") == "Salomon"]
    stock_changed = price_changed = colors_gone = 0
    for card in cards:
        new_jpy = None
        for ci, color in enumerate(card.get("colors", [])):
            sp = by_image.get(salomon_image_key(color.get("image")))
            if not sp or not sp.get("variants"):
                if any(v > 0 for v in (color.get("stock") or {}).values()):
                    colors_gone += 1
                color["stock"] = {s: 0 for s in color.get("sizes", [])}
                continue
            sizes, stock = [], {}
            for v in sp["variants"]:
                s = fix_size_key((v.get("option2") or v.get("option1") or "").strip())
                if not s or s in stock:
                    continue
                sizes.append(s)
                stock[s] = 5 if v.get("available") else 0
            if stock != (color.get("stock") or {}):
                stock_changed += 1
            color["sizes"], color["stock"] = sizes, stock
            if ci == 0:
                try:
                    new_jpy = int(float(sp["variants"][0]["price"]))
                except (KeyError, ValueError, TypeError):
                    new_jpy = None
        if new_jpy and new_jpy != card.get("jpy"):
            print(f"  價格變動:{card.get('name')} ¥{card.get('jpy')} → ¥{new_jpy}")
            price_change_lines.append(f"[Salomon] {card.get('name')}:¥{card.get('jpy'):,} → ¥{new_jpy:,}")
            card["jpy"] = new_jpy
            price_changed += 1
    print(f"Salomon 完成:{len(cards)} 張卡,庫存有變 {stock_changed} 個顏色,"
          f"價格變動 {price_changed} 件,配色已下架 {colors_gone} 個")


# ---------- On ----------

def on_image_key(url):
    # Contentful 圖片網址:images.ctfassets.net/<space>/<assetId>/<hash>/<檔名>
    m = re.search(r"ctfassets\.net/[^/]+/([^/]+)/", url or "")
    return m.group(1) if m else (url or "")


def sync_on(items):
    print("=== On 同步開始 ===")
    cards = [p for p in items if p.get("brand") == "On"]
    stock_changed = price_changed = errors = 0
    for idx, card in enumerate(cards):
        link = card.get("link")
        if not link:
            continue
        try:
            html = fetch(link, timeout=25).text
            time.sleep(0.4)
        except Exception as e:
            print(f"  [{idx+1}/{len(cards)}] 抓取失敗:{card.get('name')} ({e})")
            errors += 1
            continue
        group, _ = extract_ldjson(html)
        if not group:
            errors += 1
            continue
        variants = group.get("hasVariant", [])
        by_asset = {}
        for v in variants:
            img = v.get("image")
            img = img[0] if isinstance(img, list) else img
            by_asset[on_image_key(img)] = v

        new_jpy = None
        for v in variants:
            offer = v.get("offers", {})
            if offer.get("price"):
                try:
                    new_jpy = int(float(offer["price"]))
                except (ValueError, TypeError):
                    pass
                break
        if new_jpy and new_jpy != card.get("jpy"):
            print(f"  價格變動:{card.get('name')} ¥{card.get('jpy')} → ¥{new_jpy}")
            price_change_lines.append(f"[On] {card.get('name')}:¥{card.get('jpy'):,} → ¥{new_jpy:,}")
            card["jpy"] = new_jpy
            price_changed += 1

        for color in card.get("colors", []):
            v = by_asset.get(on_image_key(color.get("image")))
            if not v:
                color["stock"] = {s: 0 for s in color.get("sizes", [])}
                continue
            offer = v.get("offers", {})
            color_url = offer.get("url", "")
            full_url = color_url if color_url.startswith("http") else ON_BASE + color_url
            try:
                sizes_stock = extract_size_stock(fetch(full_url, timeout=25).text)
                time.sleep(0.4)
            except Exception:
                continue  # 單一顏色抓失敗就先保留舊資料,下次再更新
            if not sizes_stock:
                continue
            if sizes_stock != (color.get("stock") or {}):
                stock_changed += 1
            color["sizes"] = list(sizes_stock.keys())
            color["stock"] = sizes_stock
        if (idx + 1) % 50 == 0:
            print(f"  進度 {idx+1}/{len(cards)}(庫存有變 {stock_changed},錯誤 {errors})")
    print(f"On 完成:{len(cards)} 張卡,庫存有變 {stock_changed} 個顏色,"
          f"價格變動 {price_changed} 件,錯誤 {errors} 件")


# ---------- Onitsuka Tiger ----------

def onitsuka_sku_from_image(url):
    # 圖片網址範例:https://asics.scene7.com/is/image/asics/1183C102_200_SR_RT_GLB?...
    # 檔名開頭的貨號(SKU)跟官網 API 回傳的 sku 欄位是同一組,拿來對照最準。
    m = re.search(r"/asics/([A-Za-z0-9]+_[A-Za-z0-9]+)_", url or "")
    return m.group(1) if m else (url or "")


def onitsuka_fetch_all():
    all_items = []
    page = 1
    while True:
        res = requests.post(
            ONITSUKA_ENDPOINT, headers=ONITSUKA_HEADERS,
            json={"query": ONITSUKA_QUERY, "variables": {"page": page}}, timeout=30,
        )
        res.raise_for_status()
        data = res.json()["data"]["productSearch"]
        all_items.extend(data["items"])
        if page * 100 >= data["total_count"]:
            break
        page += 1
        time.sleep(0.3)
    return [x["productView"] for x in all_items]


def sync_onitsuka(items):
    print("=== Onitsuka Tiger 同步開始 ===")
    fresh = onitsuka_fetch_all()
    print(f"官網商品共 {len(fresh)} 件(每色一筆)")
    by_sku = {p["sku"]: p for p in fresh}

    cards = [p for p in items if p.get("brand") == "Onitsuka Tiger"]
    stock_changed = price_changed = colors_gone = 0
    for card in cards:
        new_jpy = None
        for ci, color in enumerate(card.get("colors", [])):
            sku = onitsuka_sku_from_image(color.get("image"))
            fp = by_sku.get(sku)
            if not fp:
                if any(v > 0 for v in (color.get("stock") or {}).values()):
                    colors_gone += 1
                color["stock"] = {s: 0 for s in color.get("sizes", [])}
                continue
            size_opt = next((o for o in (fp.get("options") or []) if o["id"] == "size"), None)
            sizes, stock = [], {}
            if size_opt:
                for v in size_opt["values"]:
                    label = fix_size_key(v["title"])
                    if label in stock:
                        continue
                    sizes.append(label)
                    stock[label] = 5 if v.get("inStock") else 0
            if sizes and stock != (color.get("stock") or {}):
                stock_changed += 1
            if sizes:
                color["sizes"], color["stock"] = sizes, stock
            if ci == 0:
                pr = (fp.get("priceRange") or {}).get("minimum", {}).get("final", {}).get("amount", {}).get("value")
                if pr:
                    new_jpy = int(pr)
        if new_jpy and new_jpy != card.get("jpy"):
            print(f"  價格變動:{card.get('name')} ¥{card.get('jpy')} → ¥{new_jpy}")
            price_change_lines.append(f"[Onitsuka Tiger] {card.get('name')}:¥{card.get('jpy'):,} → ¥{new_jpy:,}")
            card["jpy"] = new_jpy
            price_changed += 1
    print(f"Onitsuka Tiger 完成:{len(cards)} 張卡,庫存有變 {stock_changed} 個顏色,"
          f"價格變動 {price_changed} 件,配色已下架 {colors_gone} 個")


def main():
    only = sys.argv[1].lower() if len(sys.argv) > 1 else None
    items = load_products()
    if only in (None, "salomon"):
        sync_salomon(items)
    if only in (None, "on"):
        sync_on(items)
    if only in (None, "onitsuka"):
        sync_onitsuka(items)
    save_products(items)
    if price_change_lines:
        # 官網改價後網站售價已自動跟著更新,這則通知讓老闆知道動了哪些
        head = f"📋 今日價格同步:共 {len(price_change_lines)} 件官網改價,網站售價已自動更新\n\n"
        send_line(head + "\n".join(price_change_lines[:60]))


if __name__ == "__main__":
    main()
