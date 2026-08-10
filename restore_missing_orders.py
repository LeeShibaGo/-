# -*- coding: utf-8 -*-
"""一次性:把整批消失的訂單從 2026-08-09 的每日備份還原
------------------------------------------------------------
2026-08-10 發現 daigou-orders-v1 整包變成 null(4 筆真實訂單:9D9YS7、
EQAKMY、N9PNM7、XNKHUR 全部不見),從還有資料的每日備份
(db_backup/daigou-orders-v1_2026-08-09.json)全部還原回去。N9PNM7
稍早已經先單獨還原過一次,這裡一起處理确保四筆都對得上備份。
"""
import json
import sys

import firebase_admin
from firebase_admin import credentials, db

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

FIREBASE_DB_URL = "https://shibago-4dd3c-default-rtdb.asia-southeast1.firebasedatabase.app"
CODES = ["9D9YS7", "EQAKMY", "N9PNM7", "XNKHUR"]


def main():
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DB_URL})

    with open("db_backup/daigou-orders-v1_2026-08-09.json", encoding="utf-8") as f:
        backup = json.load(f)

    current = db.reference("daigou-orders-v1").get()
    print(f"還原前,資料庫現況:{current!r}")

    for code in CODES:
        order = backup.get(code)
        if not order:
            print(f"  [{code}] 備份裡也沒有,跳過")
            continue
        ref = db.reference(f"daigou-orders-v1/{code}")
        ref.set(order)
        after = ref.get()
        print(f"  [{code}] 還原完成:name={after.get('name')!r} status={after.get('status')!r} items={len(after.get('items', []))}")

    final = db.reference("daigou-orders-v1").get() or {}
    print(f"還原後訂單總數:{len(final)},codes={sorted(final.keys())}")


if __name__ == "__main__":
    main()
