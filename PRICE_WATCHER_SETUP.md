# 價格監控系統(price-watcher)

## 這是什麼

每天自動檢查**網站上目前真正有上架的所有商品**(直接向 Firebase 要即時
資料,跟客人在網站上看到的一樣),對每件有官網連結的商品抓取目前售價,
跟前一天記錄的價格比,漲價了就用 LINE 傳訊息通知你。

不需要手動維護商品清單——你在後台新增、刪除、換一批商品,price-watcher
隔天就會自動抓到最新的商品清單,不用像以前一樣每次換商品都要重新產生
一份 `products_config.json`。

## 運作方式

- `.github/workflows/check-prices.yml`:GitHub Actions 排程,每天台灣時間
  早上 9 點自動執行一次 `price_watch.py`,也可以手動觸發(見下方)
- `price_watch.py`:向 Firebase 要目前所有上架商品,篩選出有官網連結
  (`link` 欄位)的商品,依網域對照 CSS selector 抓取目前售價,跟
  `last_prices.json` 記錄的上次價格比較,漲價就發 LINE 通知。沒有連結的
  商品(手動新增、沒有官網來源的)會自動略過,不會出錯。
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

## 之後上架其他供應商網站的商品,怎麼做

`price_watch.py` 裡的 `SELECTOR_BY_DOMAIN` 是「網域 → 價格 CSS selector」的
對照表,目前只有 `aape.jp` 驗證過。如果之後進了其他網站的商品(例如 Dior、
Human Made 或任何新供應商),要先實際打開那個網站確認價格在哪個 CSS
selector 裡,再把新的網域加進這份對照表,不然那個網站的商品會被自動
略過、不會被追蹤(不會出錯,只是不會幫你查價)。
