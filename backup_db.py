# -*- coding: utf-8 -*-
"""每日資料庫備份(commit 進 git,當成版本歷史)
------------------------------------------------------------
用途:
  Firebase Realtime Database 本身沒有內建的「回溯到某個時間點」功能,
  萬一資料庫哪天無故被清空、被寫壞(之前訂單資料表就發生過一次,原因
  始終沒查清楚),沒有備份的話完全沒辦法回溯是哪一天、變成什麼樣子。

  這支程式每天由 GitHub Actions 執行,把 daigou-products-v1、
  daigou-settings-v1、daigou-orders-v1 三包資料整包抓下來,存成
  db_backup/ 資料夾底下的 JSON 檔,commit 進 repo——git 本身就是現成的
  版本歷史,之後要查「上週三這個時間點資料庫長怎樣」,直接看 git log/
  git show 就查得到,不用另外架設備份系統。

  用服務帳號(Admin SDK)讀取,理由跟 sync_stock.py 一樣:資料庫規則
  鎖起來之後,訂單資料要讀到完整內容需要驗證身分。

執行方式:
  python backup_db.py
"""

import json
import sys
from datetime import datetime, timezone, timedelta

import firebase_admin
from firebase_admin import credentials, db

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

FIREBASE_DB_URL = "https://shibago-4dd3c-default-rtdb.asia-southeast1.firebasedatabase.app"
BACKUP_DIR = "db_backup"
PATHS = ["daigou-products-v1", "daigou-settings-v1", "daigou-orders-v1"]

_firebase_app = None


def firebase_app():
    global _firebase_app
    if _firebase_app is None:
        cred = credentials.ApplicationDefault()
        _firebase_app = firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DB_URL})
    return _firebase_app


def main():
    import os

    firebase_app()
    os.makedirs(BACKUP_DIR, exist_ok=True)

    # 檔名用台灣時間日期,一天一份,同一天重跑會直接覆蓋(不會一天堆出好幾份)。
    today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")

    for path in PATHS:
        data = db.reference(path).get()
        out_path = os.path.join(BACKUP_DIR, f"{path}_{today}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        count = len(data) if isinstance(data, (list, dict)) else 0
        print(f"已備份 {path} -> {out_path}({count} 筆)")


if __name__ == "__main__":
    main()
