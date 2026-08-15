# -*- coding: utf-8 -*-
"""一次性:把 Callaway QUANTUM MAX D 那張商品卡的空白顏色名稱補上文字
------------------------------------------------------------
add_callaway_driver.py 加入時顏色名稱留空字串(這支球桿本來就沒有顏色
選項,只有規格選項),但前端顏色選擇按鈕會照樣印出一個看起來像壞掉的
空白按鈕——補一個「標準款」頂著,不影響庫存/尺寸判斷。
"""

import sys

from sync_stock import firebase_app, load_products, save_products, save_products_index

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

LINK = "https://callaway.com.tw/products/quantum-max-d-dr"


def main():
    firebase_app()
    products = load_products()
    fixed = 0
    for p in products:
        if p.get("link") == LINK:
            for c in p.get("colors", []):
                if not c.get("name"):
                    c["name"] = "標準款"
                    fixed += 1
    if fixed:
        save_products(products)
        save_products_index(products)
        print(f"已修正 {fixed} 個顏色名稱,完成!")
    else:
        print("沒有找到要修正的商品(可能已經修過了)。")


if __name__ == "__main__":
    main()
