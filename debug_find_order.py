# -*- coding: utf-8 -*-
"""暫時性除錯用:列出所有訂單的基本結構,檢查有沒有缺少 items 欄位的異常訂單
(2026-08-09:後台一打開就整個當掉,追到是 renderOrdersAdminList 對 o.items
直接 .map(),遇到沒有 items 欄位的訂單就整頁 crash)。"""
import json
import sys

import firebase_admin
from firebase_admin import credentials, db

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

FIREBASE_DB_URL = "https://shibago-4dd3c-default-rtdb.asia-southeast1.firebasedatabase.app"
ORDERS_PATH = "daigou-orders-v1"


def main():
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DB_URL})

    orders = db.reference(ORDERS_PATH).get() or {}
    if isinstance(orders, list):
        orders = {str(i): o for i, o in enumerate(orders) if o}

    print(f"訂單總數:{len(orders)}")
    for code, o in orders.items():
        if not o:
            print(f"  [{code}] 完全是空值/None !!")
            continue
        items = o.get("items")
        print(f"  [{code}] id={o.get('id')} name={o.get('name')} status={o.get('status')} "
              f"items type={type(items).__name__} "
              f"{'len='+str(len(items)) if isinstance(items, list) else 'VALUE='+repr(items)}")


if __name__ == "__main__":
    main()
