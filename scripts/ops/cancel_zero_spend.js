"use strict";

// 一次性：取消「加热中且真实消耗严格为 0 且超过 N 小时」的计划，释放预扣费现金。
// 真实消耗以订单详情 cost（分）为准，不用列表的 actualCostQuota（该字段对几分/几元消耗会显示 0）。
// 用法：node app/ops/cancel_zero_spend.js [--dry] [--hours=10]
const { Live } = require("../lib/live");
const rules = require("../lib/rules");

const dry = process.argv.includes("--dry");
const hoursArg = (process.argv.find((x) => x.startsWith("--hours=")) || "--hours=10").split("=")[1];
const AGE_HOURS = Number(hoursArg) || 10;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function detailCost(live, promotionId) {
  const d = await live.api("MmFinderPromotionApiSvr/getFeedPromotionOrderDetail", { promotionId, baseReq: { featureFlag: 26 } });
  const oi = ((((d.data || {}).order) || {}).orderInfo) || {};
  return Number(oi.cost || 0);
}

(async () => {
  const now = Math.floor(Date.now() / 1000);
  let totalCandidates = 0;
  let totalBudget = 0;
  for (const acct of rules.loadRules().accounts) {
    const live = new Live(acct.cdpPort, "cancel-zero-" + acct.id);
    try {
      await live.connect();
      let all = [];
      for (let page = 1; page <= 8; page += 1) {
        const j = await live.api("MMFinderPromotionOrderApiSvr/getPromotionOrderList", { req: { page, pageSize: 50, exportStatus: [9] } });
        const list = ((j.data || {}).resp || {}).orderList || [];
        all = all.concat(list);
        if (list.length < 50) break;
        await sleep(120);
      }
      const candidates = [];
      for (const o of all) {
        const create = Number(o.createTime || 0);
        const ageH = (now - create) / 3600;
        if (create <= 0 || ageH < AGE_HOURS) continue;
        let cost = -1;
        try { cost = await detailCost(live, o.promotionId); } catch (e) { continue; }
        if (cost !== 0) continue;
        candidates.push({ o, ageH });
      }
      console.log(acct.id, "active(9)", all.length, "| 真实0消耗 >= " + AGE_HOURS + "h:", candidates.length);
      for (const { o, ageH } of candidates) {
        const budget = Number(o.totalQuota || 0) / 100;
        totalCandidates += 1;
        totalBudget += budget;
        if (dry) {
          console.log("  [dry]", o.promotionId, "age", ageH.toFixed(1) + "h", "budget", budget, (o.orderName || "").slice(0, 24));
        } else {
          try {
            const r = await live.api("MmFinderPromotionApiSvr/cancelFeedPromotion", { promotionId: o.promotionId, baseReq: { featureFlag: 26 } });
            const err = (r.data && r.data.baseResp && r.data.baseResp.errcode) || 0;
            console.log("  cancel", o.promotionId, "age", ageH.toFixed(1) + "h", "budget", budget, "errcode", err);
          } catch (e) {
            console.log("  cancel FAIL", o.promotionId, e.message);
          }
          await sleep(300);
        }
      }
    } catch (e) {
      console.log(acct.id, "FAIL", e.message);
    } finally {
      live.close();
    }
  }
  console.log("TOTAL", dry ? "[dry]" : "", "candidates", totalCandidates, "可释放预算(元)", totalBudget.toFixed(0));
})().catch((e) => { console.error("FAILED", e && e.stack ? e.stack : e); process.exit(1); });
