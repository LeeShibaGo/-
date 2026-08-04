# -*- coding: utf-8 -*-
"""一次性:補救 storageSet 遺失身分驗證 bug 期間沒有真的存進去的訂單狀態
------------------------------------------------------------
用途:
  index.html 的 storageSet() 在資料庫規則鎖起來之後,一直沒有帶登入身分
  的 ID token,導致後台任何寫入(包括這筆訂單狀態更新)實際上都被 Firebase
  拒絕、沒有真的存進去,只是後台畫面自己樂觀顯示成功。這支程式把老闆
  已經在後台操作過、但沒有真的存進去的這筆訂單狀態補回來。

  用訂購人姓名+總額+訂金三個條件一起比對,避免同名訂單比對錯筆。

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

MATCH_NAME = "李哲寧"
MATCH_TOTAL = 1842
MATCH_DEPOSIT = 1842
NEW_STATUS = "採購中"


def main():
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DB_URL})

    orders = db.reference(ORDERS_PATH).get() or {}
    if isinstance(orders, list):
        orders = {str(i): o for i, o in enumerate(orders) if o}

    matched_code = None
    for code, o in orders.items():
        if not o:
            continue
        if o.get("name") == MATCH_NAME and o.get("total") == MATCH_TOTAL and o.get("deposit") == MATCH_DEPOSIT:
            matched_code = code
            break

    if not matched_code:
        print(f"找不到符合條件的訂單(姓名={MATCH_NAME}, 總額={MATCH_TOTAL}, 訂金={MATCH_DEPOSIT})")
        return

    order = orders[matched_code]
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
