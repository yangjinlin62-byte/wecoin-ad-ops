"use strict";

const fs = require("fs");
const path = require("path");
const { Live } = require("../lib/live");
const rules = require("../lib/rules");

const ROOT = rules.ROOT;
const OUT = path.join(ROOT, "data", "analysis", "current_performance.json");

function read(file, fallback) {
  try { return JSON.parse(fs.readFileSync(file, "utf8")); } catch (_) { return fallback; }
}

function plansFor(accountId) {
  const map = new Map();
  const ops = path.join(ROOT, "data", "ops");
  for (const name of fs.readdirSync(ops)) {
    if (!name.endsWith(".json")) continue;
    if (!(name.startsWith("realtime-pay-" + accountId + "-") || name.startsWith("pay-cli-" + accountId + "-"))) continue;
    const data = read(path.join(ops, name), null);
    if (!data) continue;
    const list = data.plans || (data.batches || []).flatMap((b) => b.plans || []);
    for (const p of list) {
      if (!p.promotionId) continue;
      const group = name.startsWith("realtime-pay-") ? "realtime" : "prebilling";
      if (!map.has(p.promotionId)) map.set(p.promotionId, { ...p, group });
    }
  }
  return [...map.values()];
}

function agg(map, key, rec) {
  if (!map[key]) map[key] = { key, plans: 0, spend: 0, pay: 0, orders: 0, zero: 0, started: 0 };
  const x = map[key];
  x.plans += 1;
  x.spend += rec.spend;
  x.pay += rec.pay;
  x.orders += rec.orders;
  if (!rec.spend) x.zero += 1;
  if (rec.started) x.started += 1;
}

(async () => {
  const all = [];
  const cash = [];
  for (const acct of rules.loadRules().accounts) {
    const live = new Live(acct.cdpPort, "perf-" + acct.id);
    await live.connect();
    const w = await live.api("MMFinderPromotionDspApisvr/inquiryUserWalletInfo", {});
    const cs = (((w.data || {}).userWalletInfo || {}).currencies) || [];
    cash.push({ account: acct.id, cashYuan: Number((cs.find((c) => c.currencyType === 10000) || {}).balance || 0) / 100 });
    const plans = plansFor(acct.id);
    let n = 0;
    for (const p of plans) {
      n += 1;
      try {
        const j = await live.api("MmFinderPromotionApiSvr/getFeedPromotionOrderDetail", { promotionId: p.promotionId, baseReq: { featureFlag: 26 } });
        const o = ((j.data || {}).order) || {};
        const oi = o.orderInfo || {};
        let pay = 0, orders = 0;
        for (const m of o.feedMaterialList || []) {
          const ind = m.indicator || {};
          pay += Number(ind.feedProductPayGmv || 0) / 100;
          orders += Number(ind.feedProductPayPv || 0);
        }
        all.push({
          account: acct.id, group: p.group, promotionId: p.promotionId, status: oi.status,
          started: Number(oi.actualStartts) > 0, target: oi.promotionTarget,
          budget: Number(oi.quota || p.budgetYuan * 10 || 0) / 10,
          spend: Number(oi.cost || 0) / 100, pay, orders, roi: Number(oi.cost || 0) > 0 ? pay / (Number(oi.cost || 0) / 100) : 0,
          billingMethod: oi.billingMethod, orderName: oi.orderName
        });
      } catch (e) {
        all.push({ account: acct.id, group: p.group, promotionId: p.promotionId, error: e.message });
      }
      if (n % 20 === 0) console.log(acct.id, n, "/", plans.length);
      await new Promise((r) => setTimeout(r, 100));
    }
    live.close();
  }
  const byAccount = {}, byGroup = {}, byTarget = {}, byBudget = {};
  for (const r of all) {
    if (r.error) continue;
    agg(byAccount, r.account, r);
    agg(byGroup, r.account + "/" + r.group, r);
    agg(byTarget, String(r.target), r);
    agg(byBudget, String(r.budget), r);
  }
  const total = all.filter((r) => !r.error).reduce((a, r) => ({ plans: a.plans + 1, spend: a.spend + r.spend, pay: a.pay + r.pay, orders: a.orders + r.orders, zero: a.zero + (r.spend ? 0 : 1) }), { plans: 0, spend: 0, pay: 0, orders: 0, zero: 0 });
  total.roi = total.spend ? total.pay / total.spend : 0;
  total.cpa = total.orders ? total.spend / total.orders : 0;
  const fmt = (m) => Object.values(m).map((x) => ({ ...x, roi: x.spend ? Number((x.pay / x.spend).toFixed(3)) : 0, cpa: x.orders ? Number((x.spend / x.orders).toFixed(1)) : 0 }));
  const out = { generatedAt: new Date().toISOString(), cash, total, byAccount: fmt(byAccount), byGroup: fmt(byGroup), byTarget: fmt(byTarget), byBudget: fmt(byBudget), plans: all.sort((a, b) => b.spend - a.spend) };
  fs.writeFileSync(OUT, JSON.stringify(out, null, 1), "utf8");
  console.log(OUT);
  console.log(JSON.stringify({ cash, total, byGroup: out.byGroup, byTarget: out.byTarget, byBudget: out.byBudget }, null, 1));
})().catch((e) => { console.error("FAILED", e && e.stack ? e.stack : e); process.exit(1); });
