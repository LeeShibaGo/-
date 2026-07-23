# -*- coding: utf-8 -*-
"""新訂單 LINE 通知
------------------------------------------------------------
用途:
  客人在網站下單後,老闆原本要自己開後台才看得到訂單。
  這支程式由 GitHub Actions 每 15 分鐘執行一次,檢查 Firebase 裡
  有沒有「上次檢查之後」的新訂單,有的話用 LINE 推播訂單摘要給老闆。

  LINE 發送方式與 sync_stock.py 相同(官方帳號廣播,只有老闆自己
  是好友,效果等同私訊)。已通知過的訂單 id 記錄在 last_seen_orders.json,
  由 workflow 自動 commit 回 repo,不會重複通知。

測試方式:
  python check_orders.py --test
  會直接發送一則測試訊息到 LINE(不檢查訂單),用來確認通知管道正常。
"""

import json
import os
import sys
from pathlib import Path

import requests

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

FIREBASE_DB_URL = "https://shibago-4dd3c-default-rtdb.asia-southeast1.firebasedatabase.app"
ORDERS_KEY = "daigou-orders-v1"
SEEN_PATH = Path(__file__).parent / "last_seen_orders.json"
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")


def send_line(message):
    if not LINE_CHANNEL_ACCESS_TOKEN:
        print("[警告] 尚未設定 LINE_CHANNEL_ACCESS_TOKEN,以下訊息只印出來,不會發送:")
        print(message)
        return False
    res = requests.post(
        "https://api.line.me/v2/bot/message/broadcast",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
        },
        json={"messages": [{"type": "text", "text": message[:4900]}]},
        timeout=15,
    )
    if res.status_code != 200:
        print(f"[錯誤] LINE 發送失敗:{res.status_code} {res.text}")
        return False
    return True


def fmt_order(o):
    lines = [f"🛒 新訂單 {o.get('code', o.get('id', '?'))}"]
    lines.append(f"客人:{o.get('name', '?')} / {o.get('phone', '?')}")
    for it in o.get("items", []):
        opt = " ".join(x for x in [it.get("color"), it.get("size")] if x)
        opt = f"({opt})" if opt else ""
        lines.append(f"・{it.get('name', '?')}{opt} x{it.get('qty', 1)}")
    lines.append(f"總額 NT${o.get('total', 0):,.0f} / 訂金 NT${o.get('deposit', 0):,.0f}")
    if o.get("note"):
        lines.append(f"備註:{o['note']}")
    return "\n".join(lines)


def main():
    if "--test" in sys.argv:
        ok = send_line("✅ 測試訊息:新訂單 LINE 通知已設定成功!之後客人下單,15 分鐘內會收到這樣的通知。")
        print("測試訊息已發送" if ok else "測試訊息發送失敗")
        return

    res = requests.get(f"{FIREBASE_DB_URL}/{ORDERS_KEY}.json", timeout=30)
    res.raise_for_status()
    data = res.json() or []
    orders = [o for o in (data if isinstance(data, list) else data.values()) if o]

    seen = set()
    if SEEN_PATH.exists():
        with open(SEEN_PATH, encoding="utf-8") as f:
            seen = set(json.load(f))

    first_run = not seen and orders
    new_orders = [o for o in orders if o.get("id") and o["id"] not in seen]

    if first_run:
        # 第一次執行:把現有訂單全部記為已看過,不轟炸舊訂單通知
        print(f"第一次執行,登記現有 {len(orders)} 筆訂單為已通知,不發送。")
    else:
        for o in sorted(new_orders, key=lambda x: x.get("time", 0)):
            if send_line(fmt_order(o)):
                print(f"已通知:{o.get('code', o['id'])}")
        if not new_orders:
            print("沒有新訂單。")

    with open(SEEN_PATH, "w", encoding="utf-8") as f:
        json.dump(sorted({o["id"] for o in orders if o.get("id")} | seen), f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
