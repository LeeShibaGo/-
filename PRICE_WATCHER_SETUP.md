# 價格監控系統(price-watcher)

## 這是什麼

每天自動檢查 `products_config.json` 裡列出的 AAPE 商品頁,如果跟前一天記錄的
價格比,漲價了就用 LINE 傳訊息通知你。目前清單是從上架的 251 件 AAPE 商品
自動產生的(網址 + 價格 selector),之後如果換了一批商品,要記得重新產生
這份清單(拿 `aape_curated_250.json` 或新一批商品清單重跑一次匯出邏輯)。

## 運作方式

- `.github/workflows/check-prices.yml`:GitHub Actions 排程,每天台灣時間
  早上 9 點自動執行一次 `price_watch.py`,也可以手動觸發(見下方)
- `price_watch.py`:讀 `products_config.json`,抓每個網址目前的價格,
  跟 `last_prices.json` 記錄的上次價格比較,漲價就發 LINE 通知
- `last_prices.json`:每次執行後,GitHub Actions 會自動把最新價格記錄
  commit 回這個檔案,下次比對才有依據(第一次執行不會有任何通知,
  因為還沒有「上一次」的紀錄可以比較)

## 你需要做的事(一次性設定)

1. **把 LINE Channel Access Token 存成 GitHub 的 Secret**(不會經過任何人看到明文):
   - 到 GitHub 上這個 repo 的頁面 → 點「Settings」
   - 左側選單「Secrets and variables」→「Actions」
   - 點「New repository secret」
   - Name 填:`LINE_CHANNEL_ACCESS_TOKEN`
   - Value 貼上你的 LINE Channel Access Token
   - 按「Add secret」

2. **確認排程有生效**:
   - 到 repo 頁面上方「Actions」分頁
   - 應該會看到「Daily AAPE price check」這個工作流程
   - 可以先手動測試:點進去 → 右側「Run workflow」按鈕 → 手動觸發一次,
     看看有沒有正常跑完(不會報錯就算成功,就算沒有漲價,你也不會收到通知,
     這是正常的)

3. **確認 LINE 官方帳號設定正確**:
   - 這支程式用的是「廣播訊息」,會發給這個官方帳號的所有好友
   - 請確認目前只有你自己加了這個官方帳號好友,避免之後有其他人也加了好友,
     不小心收到這些內部用的漲價通知

## 之後想換一批商品追蹤價格,怎麼做

`products_config.json` 就是純文字的商品清單,格式是:
```json
[{"name": "商品名稱", "url": "商品頁網址", "selector": ".price-entity"}]
```
只要換掉裡面的網址清單,重新 commit 上去,下次排程就會用新清單追蹤。
如果換了新的供應商網站(不是 aape.jp),CSS selector 也要對照那個網站
重新確認,不能直接沿用 `.price-entity`(這個是專門對應 aape.jp 的)。
