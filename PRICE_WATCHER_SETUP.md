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

## 目前支援的網站

- **aape.jp**:`SELECTOR_BY_DOMAIN` 用 CSS selector `.price-entity`,已驗證。
- **beams.co.jp**:`SELECTOR_BY_DOMAIN` 用 CSS selector `.item-price`,已用瀏覽器
  實際確認過是對的(注意:泛用的 `.price` 這個 class 在同一頁會同時抓到
  「推薦商品」輪播裡其他商品的價格,不能用,`.item-price` 才是唯一對應到
  當前商品的)。⚠️ 但這個網站對非瀏覽器連線有網路層級的封鎖(不是回
  403,是直接連線逾時),在某些執行環境下(包含目前開發用的這台機器)
  會連不上、一直逾時失敗。**GitHub Actions 的伺服器能不能連到 beams.co.jp
  還沒有實際驗證過**,選好第一次執行後請到 repo 的「Actions」分頁看有沒有
  正常跑完,如果 beams.co.jp 的商品一直顯示讀取失敗,代表 GitHub Actions
  的網路也連不到,那就沒辦法追蹤這個網站的價格了。
- **on.com**:因為價格的 CSS class 是自動產生的雜湊字串(例如
  `_price_4bgex_172`),每次官網重新部署都可能改變,而且同一頁還會混到
  其他推薦商品的價格,不適合用 CSS selector。改用 `EXTRACTOR_BY_DOMAIN`
  對照表,裡面是一個自訂函式,直接讀取頁面裡 schema.org 的 JSON-LD 商品
  資料(跟批次上架時抓商品資料用的是同一份,比較穩定),已實測抓到正確
  價格。

## 之後上架其他供應商網站的商品,怎麼做

先實際打開那個網站的商品頁面確認價格在哪裡:
- 如果是一般的 CSS class(而且沒有跟其他商品的價格混在一起),把新的網域
  加進 `SELECTOR_BY_DOMAIN` 就好。
- 如果 class 名稱看起來是自動產生的亂碼、或是同一頁會抓到多個商品的價格
  分不清楚哪個才是對的,可以參考 `extract_on_price()` 的做法,改成寫一個
  自訂函式加進 `EXTRACTOR_BY_DOMAIN`,直接從頁面裡的結構化資料
  (schema.org JSON-LD 之類)抓價格,會比 CSS selector 穩定。

沒設定的網域,那個網站的商品會被自動略過、不會被追蹤(不會出錯,只是
不會幫你查價)。
