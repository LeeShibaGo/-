# -*- coding: utf-8 -*-
"""一次性:補救 storageSet 遺失身分驗證 bug 期間沒有真的存進去的訂單狀態
------------------------------------------------------------
用途:
  index.html 的 storageSet() 在資料庫規則鎖起來之後,一直沒有帶登入身分
  的 ID token,導致後台任何寫入(包括這筆訂單狀態更新)實際上都被 Firebase
  拒絕、沒有真的存進去,只是後台畫面自己樂觀顯示成功。這支程式把老闆
  已經在後台操作過、但沒有真的存進去的這筆訂單狀態補回來。

  第一版用姓名+總額+訂金比對,結果沒找到——查了才發現這筆訂單存的
  total/deposit 其實是帶小數的 1841.72304,畫面上用 fmtMoney() 四捨五入
  顯示成 NT$1,842,不是真的整數 1842,比對失敗。改成直接用訂單編碼
  (查資料庫查到的 N9PNM7)比對,不會再錯。

  用服務帳號(Admin SDK)寫入,因為資料庫規則已經鎖起來。

執行方式(透過 GitHub Actions 手動觸發):
  GitHub 網頁 -> 這個 repo -> Actions 分頁 -> 左邊選
  "One-off: fix order status (李哲寧)" -> 右邊 "Run workflow" 按鈕
"""

import sys
import time

import firebase_admin
from firebase_admin import credentials, db

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

FIREBASE_DB_URL = "https://shibago-4dd3c-default-rtdb.asia-southeast1.firebasedatabase.app"
ORDERS_PATH = "daigou-orders-v1"

MATCH_CODE = "N9PNM7"
NEW_STATUS = "採購中"


def main():
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DB_URL})

    order = db.reference(f"{ORDERS_PATH}/{MATCH_CODE}").get()
    if not order:
        print(f"找不到訂單編碼 {MATCH_CODE}")
        return

    matched_code = MATCH_CODE
    print(f"找到訂單 {matched_code},目前狀態:{order.get('status')}")

    order.setdefault("statusTimestamps", {})
    now = int(time.time() * 1000)
    for s in ("待確認訂金", "已收訂金", NEW_STATUS):
        order["statusTimestamps"].setdefault(s, now)
    order["status"] = NEW_STATUS

    db.reference(f"{ORDERS_PATH}/{matched_code}").set(order)
    print(f"已把訂單 {matched_code} 的狀態補存為「{NEW_STATUS}」")


if __name__ == "__main__":
    main()
