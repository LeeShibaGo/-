# -*- coding: utf-8 -*-
"""
一次性:上線前測試收尾(2026-11-20)
  1. 刪掉測試下單時留下的測試訂單(只刪「訂購人 = 測試單請忽略」的那一筆)
  2. 刪掉測試時寫進轉換分析的假節點 zz_test_probe
  3. 把兩個售價是 0 元、客人會以 NT$0 買到的商品暫時下架(hidden=true,
     不是刪除,補上日幣價後把 hidden 拿掉就會重新上架):
       UHA ウハウハBOX、Callaway QUANTUM MAX D 發球木桿
"""

import sys

from firebase_admin import db

from sync_stock import firebase_app, load_products_by_brand, merge_and_save

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

TEST_ORDER_CODE = "2845XC"
ZERO_PRICE_IDS = {
    "UHA": "p_uha_1785652096815_408",
    "Callaway": "p_callaway_1786794603757_0",
}


def main():
    firebase_app()

    ref = db.reference(f"/daigou-orders-v1/{TEST_ORDER_CODE}")
    order = ref.get()
    if order and order.get("name") == "測試單請忽略":
        ref.delete()
        print(f"已刪除測試訂單 {TEST_ORDER_CODE}")
    else:
        print(f"測試訂單 {TEST_ORDER_CODE}:不存在或不是測試單,沒有刪除({(order or {}).get('name')})")

    for day, steps in (db.reference("/daigou-funnel-v1").get() or {}).items():
        if isinstance(steps, dict) and "zz_test_probe" in steps:
            db.reference(f"/daigou-funnel-v1/{day}/zz_test_probe").delete()
            print(f"已刪除 funnel 測試節點 {day}/zz_test_probe")

    to_save = []
    for brand, pid in ZERO_PRICE_IDS.items():
        for p in load_products_by_brand(brand):
            if p.get("id") == pid and not p.get("hidden") and not (p.get("jpy") or 0) > 0:
                p["hidden"] = True
                to_save.append(p)
                print(f"暫時下架(售價 0 元):{p.get('name')}")
    if to_save:
        merge_and_save(to_save)
    print("完成")


if __name__ == "__main__":
    main()
