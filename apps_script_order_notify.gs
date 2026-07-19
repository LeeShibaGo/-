/**
 * 客人下單即時 LINE 通知
 * ------------------------------------------------------------
 * 網站送出訂單的同時,會呼叫這支部署好的網址,這裡收到後立刻轉發一則
 * LINE 訊息給老闆。跟現有的 15 分鐘輪詢(check_orders.py)是獨立的兩條路,
 * 這支負責「秒級到達」,GitHub 排程繼續當備援(萬一這支失敗,最多 15 分鐘後
 * 還是會補通知)。
 *
 * 部署步驟(在 script.google.com):
 *   1. 新增專案,把這段程式碼整個貼進去,把下面的 LINE_TOKEN 換成你的金鑰
 *   2. 右上角「部署」→「新增部署作業」→ 類型選「網頁應用程式」
 *   3. 「具有存取權的使用者」選「所有人」,「執行身分」選「我」
 *   4. 部署後會拿到一個網址(https://script.google.com/macros/s/.../exec),
 *      把這個網址貼給我,我接到 index.html 的下單按鈕上
 */

const LINE_TOKEN = "在這裡貼上你的 LINE_CHANNEL_ACCESS_TOKEN";

function doPost(e) {
  try {
    const order = JSON.parse(e.postData.contents);
    const lines = [`🛒 新訂單 ${order.code || order.id || "?"}`];
    lines.push(`客人:${order.name || "?"} / ${order.phone || "?"}`);
    (order.items || []).forEach(it => {
      const opt = [it.color, it.size].filter(Boolean).join(" ");
      lines.push(`・${it.name || "?"}${opt ? "(" + opt + ")" : ""} x${it.qty || 1}`);
    });
    lines.push(`總額 NT$${Number(order.total || 0).toLocaleString()} / 訂金 NT$${Number(order.deposit || 0).toLocaleString()}`);
    if (order.note) lines.push(`備註:${order.note}`);

    UrlFetchApp.fetch("https://api.line.me/v2/bot/message/broadcast", {
      method: "post",
      contentType: "application/json",
      headers: { Authorization: "Bearer " + LINE_TOKEN },
      payload: JSON.stringify({ messages: [{ type: "text", text: lines.join("\n").slice(0, 4900) }] }),
      muteHttpExceptions: true,
    });

    return ContentService.createTextOutput(JSON.stringify({ ok: true }))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({ ok: false, error: String(err) }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

/** 部署後可以直接開網址測試(GET request)確認有沒有跑起來 */
function doGet() {
  return ContentService.createTextOutput("ShibaGo order notify is running.");
}
