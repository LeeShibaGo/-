# -*- coding: utf-8 -*-
"""
一次性:清空首頁最上面「起飛時間/回台時間」橫幅
------------------------------------------------------------
用途:
  2026-09-30 老闆截圖反映首頁上面那條深色橫幅(起飛時間 2026/08/29、
  回台時間 2026/09/16)已經過期,要求先拿掉。這條橫幅完全由
  daigou-settings-v1 裡的 departureTime/returnTime(還有沒在用的
  countdownTarget/countdownLabel)驅動,index.html 的 renderAll() 本來
  就會在這幾個欄位都是空字串時自動隱藏整條橫幅(見 index.html 裡
  「起飛/回台時間橫幅」那段註解),不用改任何前端程式碼,只要把資料庫
  裡這幾個欄位清空就好。

  之後要恢復,老闆自己到後台「店家資訊」分頁重新填「起飛時間」/
  「回台時間」存檔就會自動顯示,不需要再跑腳本。

執行方式(透過 GitHub Actions 手動觸發):
  GitHub 網頁 -> 這個 repo -> Actions 分頁 -> 左邊選
  "One-off: clear flight banner dates" -> 右邊 "Run workflow" 按鈕
"""

import sys

import firebase_admin
from firebase_admin import credentials, db

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

FIREBASE_DB_URL = "https://shibago-4dd3c-default-rtdb.asia-southeast1.firebasedatabase.app"
SETTINGS_PATH = "daigou-settings-v1"
FIELDS_TO_CLEAR = ["departureTime", "returnTime", "countdownTarget", "countdownLabel"]


def main():
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DB_URL})

    ref = db.reference(SETTINGS_PATH)
    settings = ref.get() or {}

    changed = {}
    for field in FIELDS_TO_CLEAR:
        old = settings.get(field)
        if old:
            changed[field] = old
            ref.child(field).set("")

    if not changed:
        print("這幾個欄位本來就是空的,不用改。")
        return

    for field, old in changed.items():
        print(f"{field}:「{old}」-> 清空")
    print("完成!首頁的起飛/回台時間橫幅會自動隱藏。")


if __name__ == "__main__":
    main()
