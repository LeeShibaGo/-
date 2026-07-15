"""
每日商品價格檢查器
------------------
用途:讀取 products_config.json 裡列出的商品網址,抓取目前價格,
跟上次記錄的價格比較,如果漲價就發 LINE 通知。

執行方式:python price_watch.py
建議搭配 GitHub Actions 排程,每天自動執行一次(見 .github/workflows/check-prices.yml,
設定步驟見 PRICE_WATCHER_SETUP.md)。

products_config.json 目前是對照 aape.jp 實際網頁結構產生的(selector 是
".price-entity",已用真實網頁驗證過)。如果之後換成別的供應商網站,
CSS selector 要針對那個網站重新確認,不能直接沿用。
"""

import json
import os
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# Windows 終端機預設編碼(cp950 等)印不出 emoji 或某些字元,商品名稱或
# 通知訊息只要出現一個這種字元,print() 就會讓整支程式當掉。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

CONFIG_PATH = Path(__file__).parent / "products_config.json"
LAST_PRICES_PATH = Path(__file__).parent / "last_prices.json"

# 模擬瀏覽器的 User-Agent,降低被網站擋下的機率(但無法保證一定不會被擋)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")


def load_json(path, default):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def extract_price_number(text):
    """把像 '¥2,200' 或 'NT$2200' 這種文字,轉成純數字 2200"""
    cleaned = re.sub(r"[^\d.]", "", text)
    return float(cleaned) if cleaned else None


def fetch_price(product):
    try:
        res = requests.get(product["url"], headers=HEADERS, timeout=15)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")
        el = soup.select_one(product["selector"])
        if not el:
            return None, "找不到價格區塊,selector 可能需要調整"
        price = extract_price_number(el.get_text())
        if price is None:
            return None, "抓到區塊但無法解析出數字"
        return price, None
    except Exception as e:
        return None, f"讀取失敗:{e}"


def send_line(message):
    """
    用 LINE Messaging API 的「廣播訊息」(broadcast)發送。
    廣播會發給這個官方帳號的『所有好友』——因為這個帳號是專門給您自己用的
    價格提醒帳號,目前只有您自己加了好友,所以效果等同於只有您會收到。
    ⚠️ 如果之後這個帳號也加了其他人為好友(例如不小心分享了 QR Code),
       他們也會收到這些內部價格通知,請務必讓這個帳號保持只有自己是好友。
    """
    if not LINE_CHANNEL_ACCESS_TOKEN:
        print("[警告] 尚未設定 LINE_CHANNEL_ACCESS_TOKEN,以下訊息只印出來,不會發送:")
        print(message)
        return
    url = "https://api.line.me/v2/bot/message/broadcast"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
    }
    payload = {
        "messages": [{"type": "text", "text": message[:4900]}],  # LINE 文字訊息長度上限約 5000 字
    }
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=15)
        if res.status_code != 200:
            print(f"[錯誤] LINE 發送失敗:{res.status_code} {res.text}")
    except Exception as e:
        print(f"[錯誤] LINE 發送失敗:{e}")


def main():
    products = load_json(CONFIG_PATH, [])
    last_prices = load_json(LAST_PRICES_PATH, {})

    if not products:
        print("products_config.json 是空的,請先加入要追蹤的商品。")
        sys.exit(0)

    increased_lines = []
    error_lines = []
    updated_prices = dict(last_prices)

    for product in products:
        name = product.get("name", product["url"])
        price, error = fetch_price(product)

        if error:
            error_lines.append(f"⚠️ {name}:{error}")
            continue

        old_price = last_prices.get(product["url"])
        updated_prices[product["url"]] = price

        if old_price is not None and price > old_price:
            increased_lines.append(f"📈 {name}:¥{old_price:.0f} → ¥{price:.0f}")

    save_json(LAST_PRICES_PATH, updated_prices)

    if increased_lines or error_lines:
        message_parts = []
        if increased_lines:
            message_parts.append("以下商品漲價了:\n" + "\n".join(increased_lines))
        if error_lines:
            message_parts.append("以下商品讀取失敗,建議檢查網址或 selector:\n" + "\n".join(error_lines))
        send_line("\n\n".join(message_parts))
    else:
        print("今天沒有商品漲價,也沒有讀取錯誤。")


if __name__ == "__main__":
    main()
