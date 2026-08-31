/**
 * 客人下單 / 站內客服留言 即時 LINE 通知
 * ------------------------------------------------------------
 * 網站送出訂單、或客人在站內客服留言,都會呼叫這支部署好的網址,
 * 這裡收到後立刻轉發一則 LINE 訊息給老闆(都是廣播到同一個柴代購
 * LINE 官方帳號,只有老闆自己是好友,效果等同私訊)。
 * 跟現有的 15 分鐘輪詢(check_orders.py,目前只涵蓋訂單)是獨立的路,
 * 這支負責「秒級到達」,GitHub 排程繼續當訂單的備援(萬一這支失敗,
 * 最多 15 分鐘後訂單通知還是會補上;客服留言目前沒有排程備援,
 * 這支是唯一的通知管道,失敗的話老闆要靠自己開後台的「客服訊息」
 * 分頁才看得到)。
 *
 * 2026-09-01:原本只處理訂單,新增 type 欄位分流——沒有 type(舊格式,
 * 前端訂單通知一直都是這樣傳)當作訂單處理,type === "chat" 是新的
 * 客服留言通知,兩種各自組不同的訊息文字。
 *
 * 部署步驟(在 script.google.com):
 *   1. 新增專案,把這段程式碼整個貼進去,把下面的 LINE_TOKEN 換成你的金鑰
 *   2. 右上角「部署」→「新增部署作業」→ 類型選「網頁應用程式」
 *   3. 「具有存取權的使用者」選「所有人」,「執行身分」選「我」
 *   4. 部署後會拿到一個網址(https://script.google.com/macros/s/.../exec),
 *      把這個網址貼給我,我接到 index.html 的下單按鈕上
 *
 * 更新既有部署(這次改版適用):直接改這支程式碼內容存檔還不會生效,
 * 要去「部署」→「管理部署作業」→ 點現有那個部署旁邊的鉛筆(編輯)圖示
 * → 版本選「新版本」→ 部署,網址不會變,舊的 index.html 呼叫方式不用改。
 */

const LINE_TOKEN = "在這裡貼上你的 LINE_CHANNEL_ACCESS_TOKEN";

function sendLineBroadcast(text) {
  UrlFetchApp.fetch("https://api.line.me/v2/bot/message/broadcast", {
    method: "post",
    contentType: "application/json",
    headers: { Authorization: "Bearer " + LINE_TOKEN },
    payload: JSON.stringify({ messages: [{ type: "text", text: text.slice(0, 4900) }] }),
    muteHttpExceptions: true,
  });
}

function formatOrderMessage(order) {
  const lines = [`🛒 新訂單 ${order.code || order.id || "?"}`];
  lines.push(`客人:${order.name || "?"} / ${order.phone || "?"}`);
  (order.items || []).forEach(it => {
    const opt = [it.color, it.size].filter(Boolean).join(" ");
    lines.push(`・${it.name || "?"}${opt ? "(" + opt + ")" : ""} x${it.qty || 1}`);
  });
  lines.push(`總額 NT$${Number(order.total || 0).toLocaleString()} / 訂金 NT$${Number(order.deposit || 0).toLocaleString()}`);
  if (order.note) lines.push(`備註:${order.note}`);
  return lines.join("\n");
}

function formatChatMessage(payload) {
  const lines = [`💬 站內客服新留言`];
  lines.push(`客人:${payload.name || "(未填稱呼)"}${payload.email ? " / " + payload.email : ""}`);
  lines.push(payload.text || "");
  lines.push("請到後台「客服訊息」分頁回覆。");
  return lines.join("\n");
}

function doPost(e) {
  try {
    const payload = JSON.parse(e.postData.contents);
    const text = payload.type === "chat" ? formatChatMessage(payload) : formatOrderMessage(payload);
    sendLineBroadcast(text);
    return ContentService.createTextOutput(JSON.stringify({ ok: true }))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({ ok: false, error: String(err) }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

/** 部署後可以直接開網址測試(GET request)確認有沒有跑起來 */
function doGet() {
  return ContentService.createTextOutput("ShibaGo order/chat notify is running.");
}
