# -*- coding: utf-8 -*-
"""一次性:FAQ「運費怎麼計算?」改成「國際運費已含在售價裡、不另外加收,只另外算國內取貨運費」(2026-11-21 老闆指示),只改這一句,其他 FAQ 原封不動。"""
import sys

from firebase_admin import db

from sync_stock import firebase_app

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

OLDS = [
    "分成兩段:國際運費依商品重量計算,國內取貨運費依您選擇的取貨方式(賣貨便/7-11店到店/面交)計算,結帳時都會自動算給您看。",
    "不另外收國際運費,只收國內取貨運費,依您選擇的取貨方式(賣貨便/7-11店到店/面交)計算,結帳時會自動算給您看。",
]
NEW = "國際運費已經包含在商品售價裡,不另外加收;結帳時只會另外計算國內取貨運費,依您選擇的取貨方式(賣貨便/7-11店到店/面交)計算,會自動算給您看。"

firebase_app()
ref = db.reference("/daigou-settings-v1/faq")
faq = ref.get()
OLD = next((o for o in OLDS if isinstance(faq, str) and o in faq), None)
if OLD is None:
    print("找不到舊的運費說明(可能已經改過),沒有動。")
else:
    print("舊 FAQ 備份(前 600 字):", faq[:600].replace("\n", " | "))
    ref.set(faq.replace(OLD, NEW))
    print("完成!FAQ 運費說明已更新。")
