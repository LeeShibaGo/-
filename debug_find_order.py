# -*- coding: utf-8 -*-
"""暫時性除錯用:列出姓名符合「李哲寧」的訂單完整內容,不比對金額。"""
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
            continue
        if "李哲寧" in (o.get("name") or ""):
            print(json.dumps({"code": code, **o}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
