# -*- coding: utf-8 -*-
"""
一次性:把 MERRIES(妙而舒)商品名稱從日文改成繁體中文
------------------------------------------------------------
用途:
  scrape_merries.py 當初只是直接拿花王官網(kao-kirei.com)的日文商品
  名稱塞進資料庫,從來沒有翻譯過——2026-09-03 老闆發現這 20 件商品名稱
  整批都還是日文,要求對照台灣代理商momoshop的「妙而舒」分類頁做翻譯。

  比對後發現一個重點:momoshop 賣的是台灣代理版(瞬吸舒爽/極透舒膚兩條
  產品線),但資料庫這 20 件是「日本境內限定版」的另外三條產品線
  (ファーストプレミアム/ずっと肌さらエアスルー/ぐっすりパンツ),
  查過日本官網跟多個代購站都沒有官方認證的日版對應中文名——這兩條
  不是同一批商品,不能照抄 momoshop 頁面上的名字硬套。

  跟老闆確認過:
    - ファーストプレミアム(新生兒專用頂級系列)→「頂級新生兒系列」
    - ずっと肌さらエアスルー(全系列主力透氣線,新生兒~28kg都有)
      → 老闆要求「盡量跟台灣看得到的名字一樣」,這條線是全尺寸範圍
      主力產品,跟 momoshop 賣的「瞬吸舒爽」(NB~XL 全尺寸)在產品定位
      上對得起來,所以採用「瞬吸舒爽」這個台灣看得到的名字。
    - ぐっすりパンツ(夜用褲,「ぐっすり」=熟睡/安睡)→「安睡褲」,
      這個字面意思很明確,不需要對照台灣譯名。
    - するりんキレイおしりふき(濕紙巾)→「潔淨柔濕巾」,一樣是字面
      翻譯,不涉及需要對照的產品線命名問題。

  尺寸換算(日系尿布通用慣例,S/M/L/ビッグ/ビッグより大きい 對應國際
  尺碼 S/M/L/XL/XXL)、片數、體重/公克數這些數字資訊都是確定的,
  直接照抄原始規格,不是翻譯的部分。

  只改 name 欄位,其他欄位(jpy/weight/subtype/link/image...)完全不動。
  用 name 完全比對(不是模糊比對),對不到的商品會印出警告、不會動它,
  避免改錯或漏改。

執行方式(透過 GitHub Actions 手動觸發):
  GitHub 網頁 -> 這個 repo -> Actions 分頁 -> 左邊選
  "One-off: rename MERRIES products to Chinese" -> 右邊 "Run workflow" 按鈕
"""

import sys

import firebase_admin
from firebase_admin import credentials, db

from sync_stock import build_products_index

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

FIREBASE_DB_URL = "https://shibago-4dd3c-default-rtdb.asia-southeast1.firebasedatabase.app"
PRODUCTS_PATH = "daigou-products-v1"
PRODUCTS_INDEX_PATH = "daigou-products-index-v1"

# key:原始日文名稱(跟資料庫裡目前存的一字不差) -> value:新的繁體中文名稱
NAME_MAP = {
    "メリーズ　ファーストプレミアム　新生児用３０００ｇまで":
        "【妙而舒】頂級新生兒系列 黏貼型 新生兒用(未滿3000g適用)",
    "メリーズ ファーストプレミアム 新生児用 5000gまで":
        "【妙而舒】頂級新生兒系列 黏貼型 新生兒用(未滿5000g適用)",
    "メリーズ　ファーストプレミアム　Ｓサイズ５４枚入り":
        "【妙而舒】頂級新生兒系列 黏貼型 S號(54片入)",
    "メリーズ　ファーストプレミアムＭサイズ　４８枚":
        "【妙而舒】頂級新生兒系列 黏貼型 M號(48片入)",
    "メリーズ　ファーストプレミアムパンツ　Ｓサイズ５２枚入り":
        "【妙而舒】頂級新生兒系列 褲型 S號(52片入)",
    "メリーズ　ファーストプレミアムパンツ　Ｍサイズ４６枚入り":
        "【妙而舒】頂級新生兒系列 褲型 M號(46片入)",
    "メリーズ　ファーストプレミアムパンツ　Ｌサイズ３６枚入り":
        "【妙而舒】頂級新生兒系列 褲型 L號(36片入)",
    "メリーズ　ファーストプレミアムパンツ　ビッグサイズ３２枚入り":
        "【妙而舒】頂級新生兒系列 褲型 XL號(32片入)",
    "メリーズ　ずっと肌さらエアスルー　新生児用５０００ｇまで":
        "【妙而舒】瞬吸舒爽 黏貼型 新生兒用(未滿5000g適用)",
    "メリーズ　ずっと肌さらエアスルー　 Sサイズ（4～8kg）":
        "【妙而舒】瞬吸舒爽 黏貼型 S號(4-8kg適用)",
    "メリーズ　ずっと肌さらエアスルー　Mサイズ（6～11kg）":
        "【妙而舒】瞬吸舒爽 黏貼型 M號(6-11kg適用)",
    "メリーズ　ずっと肌さらエアスルー　パンツ 　Sサイズ （4～8kg）":
        "【妙而舒】瞬吸舒爽 褲型 S號(4-8kg適用)",
    "メリーズ　ずっと肌さらエアスルー　パンツ　 Mサイズ （6～12kg）":
        "【妙而舒】瞬吸舒爽 褲型 M號(6-12kg適用)",
    "メリーズ　ずっと肌さらエアスルー　パンツ　 Lサイズ （9～14kg）":
        "【妙而舒】瞬吸舒爽 褲型 L號(9-14kg適用)",
    "メリーズ　ずっと肌さらエアスルー　パンツ　ビッグサイズ （12～22kg）":
        "【妙而舒】瞬吸舒爽 褲型 XL號(12-22kg適用)",
    "メリーズ　ずっと肌さらエアスルー　パンツ　 ビッグより大きいサイズ （15～28kg）":
        "【妙而舒】瞬吸舒爽 褲型 XXL號(15-28kg適用)",
    "メリーズ　ぐっすりパンツ　 Lサイズ（9～15kg）":
        "【妙而舒】安睡褲(夜用) L號(9-15kg適用)",
    "メリーズ　ぐっすりパンツ　 ビッグサイズ（12～22kg）":
        "【妙而舒】安睡褲(夜用) XL號(12-22kg適用)",
    "メリーズ　ぐっすりパンツ　 ビッグより大きいサイズ（15～28kg）":
        "【妙而舒】安睡褲(夜用) XXL號(15-28kg適用)",
    "メリーズ するりんキレイおしりふき トイレに流せるタイプ ［64枚入り×3コパック］":
        "【妙而舒】潔淨柔濕巾 可沖馬桶款(64片×3包)",
}


def main():
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DB_URL})

    products = db.reference(PRODUCTS_PATH).get()
    if isinstance(products, dict):
        products = list(products.values())
    products = [p for p in products if p]

    remaining = dict(NAME_MAP)
    renamed = 0
    for p in products:
        if p.get("brand") != "Merries":
            continue
        old_name = p.get("name")
        new_name = remaining.pop(old_name, None)
        if new_name:
            print(f"改名:{old_name}\n  -> {new_name}")
            p["name"] = new_name
            renamed += 1

    print(f"\n共改名 {renamed} 件商品。")
    if remaining:
        print(f"警告:有 {len(remaining)} 筆對照表裡的名稱在資料庫裡找不到完全相符的商品,"
              "沒有被改到,可能是名稱跟現在資料庫裡的不完全一樣(例如全形/半形空格差異):")
        for old_name in remaining:
            print(f"  - {old_name}")

    db.reference(PRODUCTS_PATH).set(products)
    print("已寫回 Firebase,完成!")

    db.reference(PRODUCTS_INDEX_PATH).set(build_products_index(products))
    print("索引已更新,完成!")


if __name__ == "__main__":
    main()
