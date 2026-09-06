# -*- coding: utf-8 -*-
"""
一次性:清掉站內客服聊天功能的測試帳號留下的資料
------------------------------------------------------------
用途:
  2026-09 上線站內客服訊息功能時,測試過程中用真實帳號密碼在正式網站上
  註冊過一個測試帳號(email: shibago-test-chat-1788204955176@example.com,
  Firebase Auth 的 uid 是 IGapwN7jDUhxGqreDCBBBPsXyyh1),測完功能後
  一直沒清掉,留在老闆後台「客服訊息」列表裡造成困惑。

  這支只清資料庫裡的兩份資料:
    - daigou-customers-v1/{uid}(客人資料卡)
    - daigou-messages-v1/{uid}(那一串測試對話)
  Firebase Authentication 裡那個帳號本身(登入用的 email/密碼)沒辦法
  用這支清掉——刪帳號要在 Firebase 主控台「Authentication → Users」
  手動刪,那邊不歸這支服務帳號管。不過帳號本身留著不會有安全疑慮,
  只是列表乾淨與否的問題,不刪也沒關係。

執行方式(透過 GitHub Actions 手動觸發):
  GitHub 網頁 -> 這個 repo -> Actions 分頁 -> 左邊選
  "One-off: clean up test chat account" -> 右邊 "Run workflow" 按鈕
"""

import sys

import firebase_admin
from firebase_admin import credentials, db

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

FIREBASE_DB_URL = "https://shibago-4dd3c-default-rtdb.asia-southeast1.firebasedatabase.app"
TEST_UID = "IGapwN7jDUhxGqreDCBBBPsXyyh1"


def main():
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DB_URL})

    db.reference(f"daigou-customers-v1/{TEST_UID}").delete()
    print(f"已刪除 daigou-customers-v1/{TEST_UID}")

    db.reference(f"daigou-messages-v1/{TEST_UID}").delete()
    print(f"已刪除 daigou-messages-v1/{TEST_UID}")

    print("完成!Firebase Authentication 裡的帳號本身要老闆自己到主控台刪。")


if __name__ == "__main__":
    main()
