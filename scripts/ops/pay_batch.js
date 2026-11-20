"use strict";

/**
 * 批量支付：createBatchPayFeedPromotionTask（1 次请求支付 N 条）+ 注入收银台 + 核验。
 * 目的：降低请求频率，避免平台"操作过于频繁"限流。
 *
 * 用法：
 *   node app/ops/pay_batch.js --file=data/ops/pay-cli-account1-xxx.json --account=account1
 */
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const { Live } = require("../lib/live");
const rules = require("../lib/rules");
const { createLedger } = require("../lib/ledger");

const file = (process.argv.find((x) => x.startsWith("--file=")) || "").split("=").slice(1).join("=");
const account = (process.argv.find((x) => x.startsWith("--account=")) || "--account=account2").split("=")[1];
if (!file) throw new Error("missing --file");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function injectAndWait(live, token, ids) {
  const url = "https://webeans.my-qcloud.com/sdk/#/consume/qrcode?" + token + "&theme=light";
  const expr = `(function(){try{var old=document.getElementById('__pay_iframe');if(old)old.remove();}catch(e){}var f=document.createElement('iframe');f.id='__pay_iframe';f.src=${JSON.stringify(url)};f.style.cssText='position:fixed;top:0;left:0;width:100%;height:100%;border:none;z-index:999999;background:#fff;';document.body.appendChild(f);return 'ok';})()`;
  await live.evaluate(expr, 15000);
  // 收银台按条数逐条扣款：条数越多越久（用户经验：50 条要几分钟）。
  // 采用轮询：每 10s 查一次，直到全部扣款或超时（最多 15 分钟）。
  const maxMs = 900000;
  const start = Date.now();
  let paidCount = 0;
  const paidSet = new Set();
  while (Date.now() - start < maxMs) {
    await sleep(10000);
    for (let page = 1; page <= 3; page += 1) {
      const j = await live.api("MMFinderPromotionOrderApiSvr/getPromotionOrderList", { req: { page, pageSize: 50 } });
      const list = ((j.data || {}).resp || {}).orderList || [];
      for (const o of list) {
        if (ids.includes(o.promotionId)) {
          const st = Number(o.exportStatus);
          if (st === 2 || st === 9) paidSet.add(o.promotionId);
        }
      }
      if (list.length < 50) break;
    }
    paidCount = paidSet.size;
    console.log("  waited", Math.round((Date.now() - start) / 1000) + "s, paid", paidCount, "/", ids.length);
    if (paidCount >= ids.length) break;
  }
  await live.evaluate("(function(){var f=document.getElementById('__pay_iframe');if(f)f.remove();return 'removed'})()", 15000);
  return paidSet;
}

(async () => {
  const data = JSON.parse(fs.readFileSync(file, "utf8"));
  const plans = data.plans || (data.batches || []).flatMap((b) => b.plans || []);
  const ids = plans.map((p) => p.promotionId).filter(Boolean);
  if (!ids.length) {
    console.log("no promotionIds");
    return;
  }
  const live = new Live(rules.requireAccount(account).cdpPort, "pay-batch-" + account);
  await live.connect();
  const ledger = createLedger();
  const opId = BigInt("0x" + crypto.randomBytes(8).toString("hex")).toString();
  const body = { opId, payReqs: ids.map((id) => ({ promotionId: id, pcSdkFlag: 1 })), baseReq: { featureFlag: 26 } };
  console.log("batch create", opId, "ids", ids.length);

  const cr = await live.api("MmFinderPromotionApiSvr/createBatchPayFeedPromotionTask", body);
  const taskId = (cr.data || {}).taskId;
  if (!taskId) {
    console.log("no taskId", JSON.stringify(cr).slice(0, 300));
    return;
  }

  let status = 0;
  let pcSdkInfo = "";
  for (let i = 0; i < 30; i += 1) {
    await sleep(2000);
    const rr = await live.api("MmFinderPromotionApiSvr/getBatchPayFeedPromotionTaskResult", { taskId, baseReq: { featureFlag: 26 } });
    const res = (rr.data || {}).result || {};
    status = Number(res.status || 0);
    if (res.pcSdkInfo) pcSdkInfo = res.pcSdkInfo;
    console.log("task", taskId, "status", status, (res.currentSize || 0) + "/" + (res.totalSize || 0));
    if (status === 2 || status === 3 || status === 4) break;
  }

  let paidSet = new Set();
  if (pcSdkInfo) {
    console.log("inject cashier", String(pcSdkInfo).slice(0, 40));
    paidSet = await injectAndWait(live, pcSdkInfo, ids);
  } else {
    console.log("no pcSdkInfo returned");
  }

  // 核验（用注入后轮询到的已付集合）
  const started = paidSet.size;
  const missing = ids.filter((id) => !paidSet.has(id));
  console.log("batch done started", started, "/", ids.length, missing.length ? "未支付:" + missing.slice(0, 8).join(",") : "");
  ledger.append({ type: "batch_payment", account, count: ids.length, started, status, pcSdkInfo: !!pcSdkInfo, taskId });
  live.close();
})().catch((e) => {
  console.error("FAILED", e && e.stack ? e.stack : e);
  process.exit(1);
});
