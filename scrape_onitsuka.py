# -*- coding: utf-8 -*-
"""
Onitsuka Tiger 日本官網(onitsukatiger.com)全站商品爬蟲
------------------------------------------------------------
用途:
  這個網站的分類頁本身是用 JavaScript 動態載入商品(純程式抓不到),但
  背後其實是呼叫 Adobe Commerce 的公開「Catalog Service」GraphQL API
  (adobe 官方文件稱為 Live Search),這個 API 本身不擋一般程式呼叫,而且
  一次查詢就能拿到:型號名、顏色(含色碼/清爽的英文顏色名)、性別、分類、
  多角度圖片、售價、每個尺寸的即時真實庫存(true/false)。

  API 端點跟金鑰是從分類頁的原始碼裡找到的(公開金鑰,瀏覽器本來就會用
  這組資訊直接呼叫,不是我方破解或繞過任何權限管制):
    endpoint: https://catalog-service.adobe.io/graphql
    Magento-Environment-Id / Magento-Website-Code / Magento-Store-Code /
    Magento-Store-View-Code / x-api-key 這幾個 header

  productSearch(phrase:"") 用空字串查詢,等於「查全站」,total_count 1870
  (每個顏色算一筆),分頁用 page_size + current_page。

執行方式:
  python scrape_onitsuka.py
  輸出 onitsuka_raw.json,供 _onitsuka_import.py 進一步合併/翻譯/上架。
"""
import json
import time

import requests

ENDPOINT = "https://catalog-service.adobe.io/graphql"
HEADERS = {
    "Content-Type": "application/json",
    "Magento-Environment-Id": "f8da41c4-ebd1-40be-aa62-a171aca70072",
    "Magento-Website-Code": "base",
    "Magento-Store-Code": "main_website_store",
    "Magento-Store-View-Code": "default",
    "x-api-key": "e1adbaf4ef3142c6b4381a6eb0216723",
}

QUERY = """
query($page: Int) {
  productSearch(phrase: "", page_size: 100, current_page: $page, filter: []) {
    total_count
    items {
      productView {
        __typename
        sku
        name
        url
        inStock
        images { url roles }
        attributes { name value }
        ... on ComplexProductView {
          priceRange { minimum { final { amount { value currency } } } }
          options {
            id
            title
            values {
              __typename
              id
              title
              inStock
              ... on ProductViewOptionValueSwatch { type value }
            }
          }
        }
      }
    }
  }
}
"""


def fetch_page(page, retries=4):
    for attempt in range(retries):
        try:
            res = requests.post(
                ENDPOINT, headers=HEADERS,
                json={"query": QUERY, "variables": {"page": page}}, timeout=30,
            )
            res.raise_for_status()
            data = res.json()
            if "errors" in data:
                raise RuntimeError(str(data["errors"])[:300])
            return data["data"]["productSearch"]
        except Exception as e:
            if attempt == retries - 1:
                raise
            print(f"  page {page} attempt {attempt+1} failed ({e}), retrying", flush=True)
            time.sleep(3 * (attempt + 1))


def main():
    first = fetch_page(1)
    total = first["total_count"]
    page_size = 100
    total_pages = (total + page_size - 1) // page_size
    print(f"total items: {total}, pages: {total_pages}", flush=True)

    all_items = list(first["items"])
    for page in range(2, total_pages + 1):
        data = fetch_page(page)
        all_items.extend(data["items"])
        print(f"page {page}/{total_pages}: +{len(data['items'])} (累計 {len(all_items)})", flush=True)
        time.sleep(0.3)

    with open("onitsuka_raw.json", "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False)
    print(f"完成!共 {len(all_items)} 筆,已存成 onitsuka_raw.json")


if __name__ == "__main__":
    main()
