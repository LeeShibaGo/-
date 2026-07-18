# -*- coding: utf-8 -*-
"""Scrape salomon.jp (Shopify) full catalog via the public products.json API."""
import json
import time
import urllib.request

BASE = "https://salomon.jp/products.json?limit=250&page={}"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def fetch_page(page, retries=5):
    url = BASE.format(page)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read()).get("products", [])
        except Exception as e:
            wait = 5 * (attempt + 1)
            print(f"page {page} attempt {attempt+1} failed ({e}), wait {wait}s", flush=True)
            time.sleep(wait)
    raise RuntimeError(f"page {page} failed after {retries} retries")


def main():
    allp = []
    page = 1
    while page <= 30:
        ps = fetch_page(page)
        allp.extend(ps)
        print(f"page {page}: {len(ps)} (total {len(allp)})", flush=True)
        if len(ps) < 250:
            break
        page += 1
        time.sleep(1.5)
    with open("_salomon_all.json", "w", encoding="utf-8") as f:
        json.dump(allp, f, ensure_ascii=False)
    print("saved", len(allp))


if __name__ == "__main__":
    main()
