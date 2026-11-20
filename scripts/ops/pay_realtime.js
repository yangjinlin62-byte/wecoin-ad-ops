"use strict";

const fs = require("fs");
const path = require("path");
const { Live } = require("../lib/live");
const rules = require("../lib/rules");
const { createLedger } = require("../lib/ledger");

const file = (process.argv.find((x) => x.startsWith("--file=")) || "").split("=").slice(1).join("=");
const account = (process.argv.find((x) => x.startsWith("--account=")) || "--account=account2").split("=")[1];
const limit = Number((process.argv.find((x) => x.startsWith("--limit=")) || "--limit=0").split("=")[1]);
if (!file) throw new Error("missing --file");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function injectCashier(live, token) {
  const url = "https://webeans.my-qcloud.com/sdk/#/consume/qrcode?" + token + "&theme=light";
  const expr = `(function(){try{var old=document.getElementById('__pay_iframe');if(old)old.remove();}catch(e){}var f=document.createElement('iframe');f.id='__pay_iframe';f.src=${JSON.stringify(url)};f.style.cssText='position:fixed;top:0;left:0;width:100%;height:100%;border:none;z-index:999999;background:#fff;';document.body.appendChild(f);return 'ok';})()`;
  await live.evaluate(expr, 15000);
  await sleep(4000);
  await live.evaluate("(function(){var f=document.getElementById('__pay_iframe');if(f)f.remove();return 'removed'})()", 15000);
}

function recordDeleted(exportIds) {
  const p = path.join(rules.ROOT, "data", "state", "deleted_videos.json");
  let cur = [];
  try { cur = (JSON.parse(fs.readFileSync(p, "utf8")).exportIds) || []; } catch (_) {}
  const set = new Set(cur);
  for (const e of exportIds || []) set.add(e);
  fs.writeFileSync(p, JSON.stringify({ exportIds: [...set], updatedAt: new Date().toISOString() }, null, 1), "utf8");
}

(async () => {
  const data = JSON.parse(fs.readFileSync(file, "utf8"));
  let plans = data.plans || (data.batches || []).flatMap((b) => b.plans || []);
  if (limit) plans = plans.slice(0, limit);
  const live = new Live(rules.requireAccount(account).cdpPort, "pay-realtime-" + account);
  await live.connect();
  const ledger = createLedger();
  let ok = 0;
  let consecutiveTimeout = 0;
  for (const plan of plans) {
    const screen = require("../lib/work_evidence").screenPayments(account, [plan]);
    if (screen.held.length) {
      console.error("暂缓付款", JSON.stringify(screen.held));
      continue;
    }
    const id = plan.promotionId;
    try {
      const pr = await live.api("MmFinderPromotionApiSvr/payFeedPromotion", { promotionId: id, pcSdkFlag: 1, baseReq: { featureFlag: 26 } });
      const detail = ((pr.data || {}).promotionPayDetail || [])[0] || {};
      const token = ((detail.cashPayInfo || {}).pcSdkInfo) || "";
      if (token) await injectCashier(live, token);
      let ord = {};
      let started = false;
      let stopped = false;
      for (let tries = 0; tries < 6; tries += 1) {
        await sleep(10000);
        const d = await live.api("MmFinderPromotionApiSvr/getFeedPromotionOrderDetail", { promotionId: id, baseReq: { featureFlag: 26 } });
        ord = (((d.data || {}).order) || {}).orderInfo || {};
        if (Number(ord.status) === 2 || Number(ord.actualStartts) > 0) { started = true; break; }
        if (Number(ord.status) === 6) { stopped = true; break; } // 加热前取消：视频被删/审核未过，不继续等
      }
      if (started) ok += 1;
      ledger.append({ type: "realtime_payment", account, promotionId: id, status: ord.status, started, stopped, token: !!token });
      console.log(id, "status", ord.status, "started", started, "stopped", stopped, "cost", ord.cost);
      if (stopped) recordDeleted(plan.exportIds);
      if (started || stopped) {
        consecutiveTimeout = 0;
      } else {
        consecutiveTimeout += 1;
        if (consecutiveTimeout >= 3) {
          console.error("连续 3 条实时扣费未到 status=2，疑似免密失效，停止本批：", id);
          break;
        }
      }
    } catch (e) {
      console.log("FAIL", id, e.message);
    }
    await sleep(500);
  }
  live.close();
  console.log("done started", ok, "/", plans.length);
})().catch((e) => { console.error("FAILED", e && e.stack ? e.stack : e); process.exit(1); });
