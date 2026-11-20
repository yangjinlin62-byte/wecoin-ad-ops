"use strict";

const fs = require("fs");
const path = require("path");
const { Live } = require("../lib/live");

const ROOT = path.join(__dirname, "..", "..");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const port = Number(process.argv[2] || 9445);
const outDir = path.join(ROOT, "data", process.argv[3] || "history2");
const cutoffDays = Number(process.argv[4] || 90);

(async () => {
  fs.mkdirSync(outDir, { recursive: true });
  const live = new Live(port, "orders-" + port);
  await live.connect();
  let total = 0;
  const cutoff = Math.floor(Date.now() / 1000) - cutoffDays * 86400;
  for (let page = 1; page <= 200; page += 1) {
    const j = await live.api("MMFinderPromotionOrderApiSvr/getPromotionOrderList", { req: { page, pageSize: 50 } });
    const list = (((j.data || {}).resp || {}).orderList) || [];
    fs.writeFileSync(path.join(outDir, "orders_p" + String(page).padStart(3, "0") + ".json"), JSON.stringify(j, null, 1), "utf8");
    total += list.length;
    const times = list.map((o) => Number(o.createTime || 0)).filter(Boolean);
    const minT = times.length ? Math.min(...times) : 0;
    console.log("page", page, "n", list.length, "min", new Date(minT * 1000).toISOString());
    if (list.length < 50) break;
    if (minT && minT < cutoff) break;
    await sleep(500);
  }
  console.log("done total", total);
  live.close();
})().catch((e) => {
  console.error("FAILED", e && e.stack ? e.stack : e);
  process.exit(1);
});
