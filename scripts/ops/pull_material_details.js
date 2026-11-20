"use strict";

const fs = require("fs");
const path = require("path");
const { Live } = require("../lib/live");

const ROOT = path.join(__dirname, "..", "..");
const port = Number(process.argv[2] || 9445);
const dirName = process.argv[3] || "history2";
const outDir = path.join(ROOT, "data", dirName);
const outFile = path.join(outDir, "materials.jsonl");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const LIMIT = Number(process.argv[4] || 0);
const CONCURRENCY = Number(process.argv[5] || 3);

function loadOrders() {
  const files = fs.readdirSync(outDir).filter((f) => /^orders_p\d+\.json$/.test(f)).sort();
  const byId = new Map();
  for (const f of files) {
    const j = JSON.parse(fs.readFileSync(path.join(outDir, f), "utf8"));
    const list = (((j.data || {}).resp || {}).orderList) || [];
    for (const o of list) if (!byId.has(o.promotionId)) byId.set(o.promotionId, o);
  }
  return byId;
}

function parseRealAppId(p) {
  try {
    const q = String(p || "").split("?")[1] || "";
    return new URLSearchParams(q).get("realappid") || "";
  } catch (_) {
    return "";
  }
}

(async () => {
  const orders = loadOrders();
  const done = new Set();
  if (fs.existsSync(outFile)) {
    for (const line of fs.readFileSync(outFile, "utf8").split("\n")) {
      if (!line.trim()) continue;
      try { done.add(JSON.parse(line).promotionId); } catch (_) {}
    }
  }
  const targets = [...orders.values()]
    .filter((o) => Number(o.actualCostQuota || 0) > 0 && !done.has(o.promotionId))
    .sort((a, b) => Number(b.createTime || 0) - Number(a.createTime || 0))
    .slice(0, LIMIT || undefined);
  console.log("orders total", orders.size, "already done", done.size, "todo", targets.length);

  const live = new Live(port, "details-fast-" + dirName);
  await live.connect();
  await live.ensureHeaders();
  const cookieResp = await live.cdp.send("Network.getCookies", { urls: ["https://channels.weixin.qq.com"] });
  const cookie = (cookieResp.cookies || []).map((c) => `${c.name}=${c.value}`).join("; ");
  const headers = {
    ...live.headers,
    Cookie: cookie,
    Origin: "https://channels.weixin.qq.com",
    Referer: "https://channels.weixin.qq.com/promote/pages/platform/order-list",
  };
  const base = `${live.origin}/promote/api/web/transfer/MmFinderPromotionApiSvr/getFeedPromotionOrderDetail?${live.query}`;

  async function apiFast(body) {
    const r = await fetch(base, { method: "POST", headers, body: JSON.stringify(body) });
    const text = await r.text();
    if (r.status !== 201) throw new Error(`HTTP ${r.status} ${text.slice(0, 150)}`);
    return JSON.parse(text);
  }

  const stream = fs.createWriteStream(outFile, { flags: "a", encoding: "utf8" });
  let index = 0;
  let finished = 0;
  async function worker() {
    while (true) {
      const i = index++;
      if (i >= targets.length) return;
      const o = targets[i];
      try {
        const j = await apiFast({ promotionId: o.promotionId, baseReq: { featureFlag: 26 } });
        const order = ((j.data || {}).order) || {};
        const oi = order.orderInfo || {};
        const mats = (order.feedMaterialList || []).map((m) => {
          const f = m.finderObject || {};
          const ind = m.indicator || {};
          const sj = f.shoppingcartJumpinfo || {};
          return {
            materialId: (f.exportId || "").split("/").pop(),
            exportId: f.exportId || "",
            globalExportId: f.globalExportId || "",
            author: ((f.accountInfo || {}).nickName) || "",
            cost: Number(ind.cost || 0),
            payPv: Number(ind.feedProductPayPv || 0),
            payGmv: Number(ind.feedProductPayGmv || 0),
            roi: Number(ind.feedProductPayRoi || 0),
            netPv: Number(ind.feedProductNetPayPv || 0),
            netGmv: Number(ind.feedProductNetPayGmv || 0),
            productId: sj.productId || "",
            productWording: sj.wording || "",
            realappid: parseRealAppId(sj.path),
          };
        });
        const rec = {
          promotionId: o.promotionId,
          createTime: Number(o.createTime || 0),
          orderName: o.orderName || oi.orderName || "",
          target: oi.promotionTarget || o.promotionTarget,
          bidInfo: o.bidInfo || order.bidInfo || {},
          budget: Number(oi.quota || o.totalQuota || 0),
          spend: Number(oi.cost || o.actualCostQuota || 0),
          materials: mats,
        };
        stream.write(JSON.stringify(rec) + "\n");
      } catch (e) {
        console.log("FAIL", o.promotionId, e.message);
      }
      finished += 1;
      if (finished % 20 === 0) console.log("done", finished, "/", targets.length);
      await sleep(30);
    }
  }

  await Promise.all(Array.from({ length: CONCURRENCY }, () => worker()));
  stream.end();
  console.log("finished", finished);
  live.close();
})().catch((e) => {
  console.error("FAILED", e && e.stack ? e.stack : e);
  process.exit(1);
});
