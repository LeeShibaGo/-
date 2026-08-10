# -*- coding: utf-8 -*-
"""一次性:把 N9PNM7 這筆訂單從今天的備份還原
------------------------------------------------------------
2026-08-09 測試「匿名寫入會不會被規則擋下來」時,不小心真的用沒有登入的
PUT 把這筆真實訂單蓋成垃圾資料({"malicious":"overwrite attempt"})。
從 db_backup/daigou-orders-v1_2026-08-09.json(今天稍早的每日備份,蓋掉
之前抓的)把正確內容還原回去。
"""
import json
import sys

import firebase_admin
from firebase_admin import credentials, db

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

FIREBASE_DB_URL = "https://shibago-4dd3c-default-rtdb.asia-southeast1.firebasedatabase.app"


def main():
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DB_URL})

    with open("n9pnm7_restore.json", encoding="utf-8") as f:
        correct_order = json.load(f)

    ref = db.reference("daigou-orders-v1/N9PNM7")
    before = ref.get()
    print(f"還原前(壞掉的內容):{before!r}")
    ref.set(correct_order)
    after = ref.get()
    print(f"還原後:{after.get('name')!r}, status={after.get('status')!r}, items={len(after.get('items', []))}")


if __name__ == "__main__":
    main()
