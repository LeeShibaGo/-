# -*- coding: utf-8 -*-
"""一次性:補上 UNIQLO x NEEDLES 開襟外套三個顏色各自的圖片
------------------------------------------------------------
用途:
  這件商品(p_uniqlo_needles_1785655033387_1)當初手動上架時,
  colors[] 裡三個顏色都沒有各自的 image 欄位,畫面顯示邏輯抓不到
  colors[i].image 就會整個 fallback 回商品最上層的 image,導致切換
  顏色時照片完全不會變。這支程式補上三個顏色各自正確的官網圖片:

    灰色   -> uniqlo.com/jp E483980-000 COL08(DARK GRAY)
    米白色 -> uniqlo.com/jp E483980-000 COL31(BEIGE)
    黑紫色 -> uniqlo.com/jp E484125-000 COL09(黑底紫條紋,款式編號不同)

  用服務帳號(Admin SDK)寫入,因為資料庫規則已經鎖起來。

執行方式(透過 GitHub Actions 手動觸發):
  GitHub 網頁 -> 這個 repo -> Actions 分頁 -> 左邊選
  "One-off: fix NEEDLES images" -> 右邊 "Run workflow" 按鈕
"""

import sys

import firebase_admin
from firebase_admin import credentials, db

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

FIREBASE_DB_URL = "https://shibago-4dd3c-default-rtdb.asia-southeast1.firebasedatabase.app"
PRODUCTS_PATH = "daigou-products-v1"
TARGET_ID = "p_uniqlo_needles_1785655033387_1"

COLOR_IMAGES = {
    "灰色": "https://image.uniqlo.com/UQ/ST3/jp/imagesgoods/483980/item/jpgoods_08_483980_3x4.jpg",
    "米白色": "https://image.uniqlo.com/UQ/ST3/jp/imagesgoods/483980/item/jpgoods_31_483980_3x4.jpg",
    "黑紫色": "https://image.uniqlo.com/UQ/ST3/jp/imagesgoods/484125/item/jpgoods_09_484125_3x4.jpg",
}


def main():
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DB_URL})

    products = db.reference(PRODUCTS_PATH).get()
    if isinstance(products, dict):
        products = list(products.values())
    products = [p for p in products if p]

    target = next((p for p in products if p.get("id") == TARGET_ID), None)
    if not target:
        print(f"找不到商品 {TARGET_ID},沒有東西可以改")
        return

    for c in target.get("colors", []):
        img = COLOR_IMAGES.get(c.get("name"))
        if img:
            c["image"] = img
            print(f"已設定 {c['name']} -> {img}")

    db.reference(PRODUCTS_PATH).set(products)
    print("已寫回 Firebase,完成!")


if __name__ == "__main__":
    main()
