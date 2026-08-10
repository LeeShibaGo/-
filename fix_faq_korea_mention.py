# -*- coding: utf-8 -*-
"""一次性:把已經存在資料庫裡的 FAQ 文字,「日本/韓國」改成「日本」
------------------------------------------------------------
老闆決定現在只做日本代購,網站標題/說明文字都已經拿掉韓國了,但 FAQ
內容是老闆自己在後台填過、存在資料庫裡的真實文字,程式碼裡改預設值
不會影響已經存進去的內容,所以另外寫這支直接改資料庫。
"""
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

    ref = db.reference("daigou-settings-v1")
    settings = ref.get() or {}

    faq = settings.get("faq", "")
    old = "代購需要先在日本/韓國把商品買下來"
    new = "代購需要先在日本把商品買下來"
    if old in faq:
        faq = faq.replace(old, new)
        ref.child("faq").set(faq)
        print("faq 已更新,替換掉「日本/韓國」的字樣。")
    else:
        print("faq 裡沒找到那句舊文字(可能已經改過了),不動它。")

    guide = settings.get("purchaseGuide", "")
    if "韓國" in guide:
        print("提醒:purchaseGuide(代購須知)裡還有「韓國」字樣,內容比較長、格式因人而異,")
        print("這支不自動改,原文如下,麻煩自己去後台看要不要調整:")
        print(guide)
    else:
        print("purchaseGuide 裡沒有「韓國」字樣。")


if __name__ == "__main__":
    main()
