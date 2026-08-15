# -*- coding: utf-8 -*-
"""一次性:從現有 daigou-products-v1 補建 daigou-products-index-v1
------------------------------------------------------------
用途:
  2026-08-14 前端改成首頁一開先抓精簡版索引(daigou-products-index-v1),
  不再整包抓 daigou-products-v1(17,897 件、12.5MB,實測光這個請求就要
  1.4 秒以上)。sync_stock.py 的 merge_and_save() 之後每天同步完會自動
  重建這份索引,但索引節點在那之前完全不存在——上線前要先手動跑這支,
  把索引從「現在資料庫裡已經有的全部商品」補建起來一次,不然前端切過去
  的當下索引是空的,首頁會直接看起來像沒有任何商品。

  重跑這支是安全的:只是重新算一次索引整包覆寫,不會動到
  daigou-products-v1 本身。

執行方式(透過 GitHub Actions 手動觸發):
  GitHub 網頁 -> 這個 repo -> Actions 分頁 -> 左邊選
  "One-off: rebuild products index" -> 右邊 "Run workflow" 按鈕
"""

import sys

from sync_stock import firebase_app, load_products, save_products_index

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")


def main():
    firebase_app()
    products = load_products()
    print(f"現有商品共 {len(products)} 件,開始重建索引...")
    save_products_index(products)
    print("完成!")


if __name__ == "__main__":
    main()
