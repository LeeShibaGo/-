/**
 * Firebase Cloud Functions - 綠界(ECPay)金流串接
 * ------------------------------------------------------------
 * 2026-09-30 老闆開通綠界正式環境金鑰,要求「線上刷卡/ATM」跟現有的
 * 「LINE 確認 + 手動轉帳」並存,客人自己選,不強迫改用線上付款。
 *
 * 為什麼不能純前端做:
 *   綠界要求每一筆交易都附上一組「檢查碼」(CheckMacValue),用
 *   MerchantID + HashKey + HashIV 算出來,綠界收到後重算一次比對,
 *   確認這筆請求真的是這個商店送出的,不是別人偽造的。如果這個運算
 *   寫在客人瀏覽器看得到的網頁 JS 裡,等於把 HashKey/HashIV 整組公開
 *   給所有訪客看,任何人都能偷看原始碼、拿去偽造「已付款成功」的假
 *   通知,訂單金額也能被亂改,查都查不出來。
 *
 *   正規做法一定要有一台「客人看不到程式碼」的後台伺服器幫忙算這組
 *   檢查碼,而且綠界真正的付款結果也是這台伺服器透過「背景通知」
 *   (Server 對 Server,不是客人的瀏覽器轉回來那步)才會知道——這樣
 *   客人在綠界頁面付完錢後就算直接關掉分頁,我們也不會漏接這筆付款。
 *   這裡用 Firebase Cloud Functions 扮演這台伺服器,跟網站原本用的
 *   Firebase 專案是同一個,串接起來不用再多開一個服務。
 *
 * 兩支函式:
 *   - ecpayCheckout:客人在「訂單已送出」畫面點「信用卡付款」/「ATM
 *     轉帳」,瀏覽器直接整頁導到這個網址(?code=訂單編碼&method=
 *     credit/atm),這裡讀訂單金額、算好檢查碼,回傳一個會自動送出的
 *     表單,把客人導去綠界的付款頁面。用整頁導轉(不是 fetch),沒有
 *     CORS 的問題。
 *   - ecpayNotify:綠界的伺服器完成付款後會直接呼叫這個網址通知,
 *     驗證檢查碼沒問題後,才把訂單狀態從「待確認訂金」推進到
 *     「已收訂金」——這一步等同於老闆手動核對轉帳後按的那個按鈕,
 *     差別是這裡是自動的。
 *
 * CheckMacValue 演算法照抄綠界官方 Node.js SDK(npm: ecpay_aio_nodejs,
 * lib/ecpay_payment/helper.js)的原文邏輯,不是自己重新推導——這是真的
 * 會動到錢的地方,照抄驗證過的官方實作,不自己猜格式。
 *
 * 金鑰(ECPAY_MERCHANT_ID / ECPAY_HASH_KEY / ECPAY_HASH_IV)不會進
 * git——是部署時由 GitHub Actions 從 repo secrets 寫進 functions/.env
 * (.gitignore 已排除這個檔案),部署完成後這份明文金鑰不會留在 repo 裡,
 * 只存在 Cloud Functions 執行環境裡。
 */

const functions = require('firebase-functions');
const admin = require('firebase-admin');
const crypto = require('crypto');

admin.initializeApp();

// 台灣(彰化)機房,離客人近、延遲低,網址也會固定是
// https://asia-east1-shibago-4dd3c.cloudfunctions.net/ecpayCheckout 等等。
const REGION = 'asia-east1';
const PROJECT_ID = 'shibago-4dd3c';
const ORDERS_PATH = 'daigou-orders-v1';
const SITE_URL = 'https://leeshibago.github.io/-/';

const MERCHANT_ID = process.env.ECPAY_MERCHANT_ID;
const HASH_KEY = process.env.ECPAY_HASH_KEY;
const HASH_IV = process.env.ECPAY_HASH_IV;

// 老闆給的是正式環境金鑰,固定用正式環境網址。之後如果要切回測試環境
// 測新功能,把這行換成 https://payment-stage.ecpay.com.tw/Cashier/AioCheckOut/V5
// (測試環境要另外用綠界的測試商店金鑰,不能混用正式金鑰打測試網址)。
const ECPAY_CHECKOUT_URL = 'https://payment.ecpay.com.tw/Cashier/AioCheckOut/V5';

// ---- 以下兩個函式是綠界官方 Node.js SDK(ecpay_aio_nodejs)helper.js
// 的 urlencode_dot_net() / gen_chk_mac_value() 原文邏輯直接照搬 ----
function urlEncodeDotNet(str){
  let enc = encodeURIComponent(str).toLowerCase();
  enc = enc.replace(/'/g, '%27');
  enc = enc.replace(/~/g, '%7e');
  enc = enc.replace(/%20/g, '+');
  return enc;
}

function genCheckMacValue(params){
  const keys = Object.keys(params).sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase()));
  const ordered = {};
  keys.forEach(k => { ordered[k] = params[k]; });
  // 這裡故意透過 JSON.stringify 再字串取代組出 key=value&key=value 的形式
  // (逐一寫迴圈拼字串效果一樣,但照抄官方 SDK 原文邏輯,連同這個小技巧
  // 一起搬過來,降低跟官方實作兜不起來的風險)。注意:params 裡每個值
  // 都必須是字串,不能是數字——否則 JSON.stringify 不會幫數字加引號,
  // 這裡的字串取代規則就會兜不起來。
  let raw = JSON.stringify(ordered).toLowerCase().replace(/":"/g, '=');
  raw = raw.replace(/","|{"|"}/g, '&');
  raw = urlEncodeDotNet(`HashKey=${HASH_KEY}${raw}HashIV=${HASH_IV}`);
  return crypto.createHash('sha256').update(raw).digest('hex').toUpperCase();
}

function formatTradeDate(d){
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Taipei', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  }).formatToParts(d);
  const get = (type) => parts.find(p => p.type === type).value;
  return `${get('year')}/${get('month')}/${get('day')} ${get('hour')}:${get('minute')}:${get('second')}`;
}

function escapeHtmlAttr(str){
  return String(str).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function sendMessagePage(res, status, message){
  res.set('Content-Type', 'text/html; charset=utf-8');
  res.status(status).send(`<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>柴代購 ShibaGo</title></head>
<body style="font-family:'Noto Sans TC',sans-serif; padding:60px 20px; text-align:center; color:#141F2B; background:#F4EFE2;">
  <p style="font-size:16px; line-height:1.8;">${escapeHtmlAttr(message)}</p>
  <a href="${SITE_URL}" style="color:#A6392C;">回到首頁</a>
</body></html>`);
}

// 客人在「訂單已送出」畫面點「信用卡付款」/「ATM 轉帳」,瀏覽器直接
// 整頁導到這個網址(GET ?code=訂單編碼&method=credit|atm),讀訂單、
// 算檢查碼,回傳一個自動送出的表單把客人導去綠界付款頁。
exports.ecpayCheckout = functions.region(REGION).https.onRequest(async (req, res) => {
  try{
    if(!MERCHANT_ID || !HASH_KEY || !HASH_IV){
      sendMessagePage(res, 500, '綠界金鑰還沒設定好,請聯繫網站管理員。');
      return;
    }
    const code = String(req.query.code || '').trim().toUpperCase();
    const method = String(req.query.method || '').trim().toLowerCase();
    if(!code || !['credit', 'atm'].includes(method)){
      sendMessagePage(res, 400, '付款連結不正確,請回到網站重新操作。');
      return;
    }

    const snap = await admin.database().ref(`${ORDERS_PATH}/${code}`).once('value');
    const order = snap.val();
    if(!order){
      sendMessagePage(res, 404, '找不到這筆訂單,請確認訂單編碼是否正確。');
      return;
    }
    if(order.ecpay && order.ecpay.rtnCode === '1'){
      sendMessagePage(res, 200, '這筆訂單已經付款完成了,不用再付一次。');
      return;
    }

    const amount = Math.round(Number(order.deposit) || 0);
    if(amount < 1){
      sendMessagePage(res, 400, '這筆訂單的金額有問題,請聯繫老闆確認。');
      return;
    }

    // MerchantTradeNo 前 6 碼固定是我們自己的訂單編碼(跟 index.html 的
    // generateOrderCode() 一樣是 6 碼),後面接一段時間戳記+亂數避免
    // 同一張訂單重新嘗試付款時撞號被綠界擋掉;ecpayNotify 收到通知時
    // 取前 6 碼還原訂單編碼。
    const tradeNo = (code + Date.now().toString(36) + Math.random().toString(36).slice(2, 6))
      .slice(0, 20)
      .toUpperCase();

    const itemName = (order.items || [])
      .map(it => `${it.name}${it.size ? '(' + it.size + ')' : ''} x${it.qty}`)
      .join('#')
      .slice(0, 200) || '柴代購商品';

    const params = {
      MerchantID: MERCHANT_ID,
      MerchantTradeNo: tradeNo,
      MerchantTradeDate: formatTradeDate(new Date()),
      PaymentType: 'aio',
      TotalAmount: String(amount),
      TradeDesc: '柴代購訂單訂金',
      ItemName: itemName,
      ReturnURL: `https://${REGION}-${PROJECT_ID}.cloudfunctions.net/ecpayNotify`,
      ChoosePayment: method === 'credit' ? 'Credit' : 'ATM',
      ClientBackURL: SITE_URL,
      EncryptType: '1',
      InvoiceMark: 'N',
    };
    params.CheckMacValue = genCheckMacValue(params);

    // 記一下這次付款嘗試用的 MerchantTradeNo(方便日後對帳、追查問題),
    // 不影響訂單本身的顯示。
    await admin.database().ref(`${ORDERS_PATH}/${code}/ecpayAttempts/${tradeNo}`).set({
      method, amount, createdAt: Date.now(),
    });

    const formInputs = Object.keys(params)
      .map(k => `<input type="hidden" name="${escapeHtmlAttr(k)}" value="${escapeHtmlAttr(params[k])}">`)
      .join('');
    res.set('Content-Type', 'text/html; charset=utf-8');
    res.status(200).send(`<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>轉往綠界付款頁...</title></head>
<body>
  <p style="font-family:'Noto Sans TC',sans-serif; text-align:center; margin-top:60px;">正在轉往付款頁面,請稍候...</p>
  <form id="ecpayForm" method="post" action="${ECPAY_CHECKOUT_URL}">${formInputs}</form>
  <script>document.getElementById('ecpayForm').submit();</script>
</body></html>`);
  } catch(err){
    console.error('ecpayCheckout error', err);
    sendMessagePage(res, 500, '系統發生錯誤,請稍後再試或聯繫老闆。');
  }
});

// 綠界的伺服器完成付款(或 ATM 取號)後,直接呼叫這個網址通知——這是
// 伺服器對伺服器的背景通知,不是客人的瀏覽器,客人中途關掉視窗也不影響
// 這則通知。一定要驗證 CheckMacValue,不然任何人都能偽造「付款成功」
// 的假通知,把別人的訂單標記成已付款。
exports.ecpayNotify = functions.region(REGION).https.onRequest(async (req, res) => {
  try{
    const body = req.body || {};
    const received = body.CheckMacValue;
    const toVerify = { ...body };
    delete toVerify.CheckMacValue;

    if(!received || genCheckMacValue(toVerify) !== received){
      console.error('ecpayNotify CheckMacValue 驗證失敗', body);
      res.status(400).send('0|CheckMacValueError');
      return;
    }

    const tradeNo = String(body.MerchantTradeNo || '');
    const code = tradeNo.slice(0, 6);
    if(!code){
      console.error('ecpayNotify 收到的通知沒有 MerchantTradeNo', body);
      res.status(200).send('1|OK'); // 檢查碼有過,只是解析不出訂單,重送也沒用,先回 OK 避免綠界一直重試
      return;
    }

    const orderRef = admin.database().ref(`${ORDERS_PATH}/${code}`);
    const snap = await orderRef.once('value');
    const order = snap.val();
    if(!order){
      console.error(`ecpayNotify 找不到訂單:${code}`, body);
      res.status(200).send('1|OK');
      return;
    }

    const rtnCode = String(body.RtnCode || '');
    const ecpayInfo = {
      rtnCode,
      rtnMsg: body.RtnMsg || '',
      tradeNo: body.TradeNo || '',
      merchantTradeNo: tradeNo,
      paymentType: body.PaymentType || '',
      tradeAmt: body.TradeAmt || '',
      paymentDate: body.PaymentDate || '',
      updatedAt: Date.now(),
    };
    if(rtnCode === '2' && body.BankCode){
      // ATM 取號通知(客人還沒真的轉帳),先把虛擬帳號存起來,老闆在
      // 後台訂單明細裡看得到,方便有需要時提醒客人。
      ecpayInfo.bankCode = body.BankCode;
      ecpayInfo.vAccount = body.vAccount || '';
      ecpayInfo.expireDate = body.ExpireDate || '';
    }

    const updates = { ecpay: ecpayInfo };
    if(rtnCode === '1'){
      // 真正付款成功——只有訂單還停在「待確認訂金」才自動推進,避免蓋掉
      // 老闆已經手動往後推進的狀態(例如已經進到採購中或已出貨)。
      if(order.status === '待確認訂金'){
        updates.status = '已收訂金';
        updates.statusTimestamps = { ...(order.statusTimestamps || {}), '已收訂金': Date.now() };
      }
    }
    await orderRef.update(updates);

    res.status(200).send('1|OK');
  } catch(err){
    console.error('ecpayNotify error', err);
    // 發生非預期錯誤時故意不回 1|OK,讓綠界之後重試通知,而不是默默漏接
    // 這筆付款。
    res.status(500).send('0|ServerError');
  }
});
