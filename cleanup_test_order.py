# -*- coding: utf-8 -*-
"""一次性:刪除 daigou-orders-v1 裡殘留的測試訂單 test_rule_check_delete_me。
------------------------------------------------------------
2026-08-09 抓到:這筆是先前測試 Firebase 安全規則時建立的假訂單,忘記清掉,
整個物件是空的(items 是 null),後台一讀到這筆就整頁 crash(見
debug_find_order.py 的稽核輸出)。程式碼那邊已經另外修好防呆
((o.items||[]).map(...)),這支單純負責把這筆垃圾測試資料本身刪掉。
"""
import sys

import firebase_admin
from firebase_admin import credentials, db

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

FIREBASE_DB_URL = "https://shibago-4dd3c-default-rtdb.asia-southeast1.firebasedatabase.app"
ORDERS_PATH = "daigou-orders-v1"
BAD_KEY = "QATEST1"


def main():
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DB_URL})

    ref = db.reference(f"{ORDERS_PATH}/{BAD_KEY}")
    before = ref.get()
    print(f"刪除前的值:{before!r}")
    ref.delete()
    after = ref.get()
    print(f"刪除後的值:{after!r}(應該是 None)")

    remaining = db.reference(ORDERS_PATH).get() or {}
    print(f"目前訂單總數:{len(remaining)}")
    for code in remaining:
        print(f"  - {code}")


if __name__ == "__main__":
    main()
