#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");
const rules = require("../lib/rules");
const payload = require("../lib/payload");
const preflightLib = require("../lib/preflight");
const errors = require("../lib/errors");
const { createLedger } = require("../lib/ledger");
const { Live } = require("../lib/live");

const argv = process.argv.slice(2);
const command = argv[0] || "help";
const sub = argv[1] || "";
const JSON_OUT = argv.includes("--json");
const CONFIRM = argv.includes("--confirm=YES");
const PYTHON = process.env.PYTHON || "python";

function arg(name, fallback = "") {
  const hit = argv.find((x) => x.startsWith("--" + name + "="));
  return hit ? hit.split("=").slice(1).join("=") : fallback;
}
function has(name) {
  return argv.includes("--" + name);
}
function out(obj, human) {
  if (JSON_OUT) console.log(JSON.stringify(obj, null, 1));
  else if (human) console.log(human);
  else console.log(JSON.stringify(obj, null, 1));
}
function fail(message, code = 2) {
  if (JSON_OUT) console.log(JSON.stringify({ ok: false, error: message }));
  else console.error("错误: " + message);
  process.exit(code);
}
function readJson(file) {
  return JSON.parse(fs.readFileSync(file, "utf8"));
}
function run(cmd, args) {
  const r = spawnSync(cmd, args, { cwd: rules.ROOT, stdio: "inherit", shell: false });
  if (r.status !== 0) process.exit(r.status || 1);
}
function runQuiet(cmd, args) {
  const r = spawnSync(cmd, args, { cwd: rules.ROOT, encoding: "utf8" });
  if (r.status !== 0) {
    if (r.stdout) process.stdout.write(r.stdout);
    if (r.stderr) process.stderr.write(r.stderr);
    process.exit(r.status || 1);
  }
  return r;
}

function createdFile(accountId) {
  return path.join(rules.ROOT, "data", "ops", "created_" + accountId + ".json");
}
function loadCreated(accountId) {
  const file = createdFile(accountId);
  if (!fs.existsSync(file)) return [];
  try { return readJson(file); } catch (_) { return []; }
}
function trackedIds(accountId) {
  const set = new Set(loadCreated(accountId).map((x) => x.promotionId).filter(Boolean));
  const opsDir = path.join(rules.ROOT, "data", "ops");
  const names = ["pay_multi_" + accountId + ".json", "pay_batches_" + accountId + ".json"];
  if (fs.existsSync(opsDir)) {
    for (const name of fs.readdirSync(opsDir)) {
      if ((name.startsWith("pay-cli-" + accountId + "-") || name.startsWith("realtime-pay-" + accountId + "-") || name.startsWith("pay-recovered-" + accountId + "-")) && name.endsWith(".json")) names.push(name);
    }
  }
  for (const name of names) {
    const file = path.join(opsDir, name);
    if (!fs.existsSync(file)) continue;
    try {
      const data = readJson(file);
      const plans = Array.isArray(data) ? data : data.plans || (data.batches || []).flatMap((b) => b.plans || []);
      for (const p of plans) if (p.promotionId) set.add(p.promotionId);
    } catch (_) {}
  }
  return [...set];
}
async function accountSnapshot(account) {
  const live = new Live(account.cdpPort, "cli-" + account.id);
  try {
    await live.connect();
    const prep = await live.api("MMFinderPromotionDspApisvr/getUserPrepare", {});
    const data = prep.data || {};
    const corp = (data.corporateUserInfo || {}).corporateInfo || {};
    const wallet = await live.api("MMFinderPromotionDspApisvr/inquiryUserWalletInfo", {});
    const currencies = ((wallet.data || {}).userWalletInfo || {}).currencies || [];
    const cash = currencies.find((c) => c.currencyType === 10000);
    return {
      account: account.id,
      label: account.label,
      port: account.cdpPort,
      operator: ((data.corporateUserInfo || {}).currentOperator || {}).userAttr || {},
      corporate: corp.corporateName || corp.nickname || "",
      wecoin: (data.userWecoinInfo || {}).balance || 0,
      cashYuan: cash ? Number(cash.balance || 0) / 100 : null,
      accountStatus: data.accountStatus
    };
  } finally {
    live.close();
  }
}

async function accountInfo() {
  const accounts = arg("account") ? [rules.requireAccount(arg("account"))] : rules.loadRules().accounts;
  const rows = [];
  for (const account of accounts) {
    try {
      rows.push(await accountSnapshot(account));
    } catch (e) {
      rows.push({ account: account.id, error: e.message });
    }
  }
  const human = rows.map((r) => r.error
    ? `${r.account}: 失败 ${r.error}`
    : `${r.account} ${r.corporate} / ${(r.operator || {}).nickname || ""} 现金 ${r.cashYuan} 微信豆 ${r.wecoin}`).join("\n");
  out({ ok: rows.every((r) => !r.error), accounts: rows }, human);
  if (rows.some((r) => r.error)) process.exitCode = 2;
}

function catalogSync() {
  const accounts = arg("account") ? [rules.requireAccount(arg("account"))] : rules.loadRules().accounts;
  for (const account of accounts) {
    run(process.execPath, [path.join(rules.ROOT, "scripts", "ops", "sync_catalog.js"), String(account.cdpPort), account.catalogDir]);
  }
}

function ordersPull() {
  const accounts = arg("account") ? [rules.requireAccount(arg("account"))] : rules.loadRules().accounts;
  const days = arg("days", "90");
  for (const account of accounts) {
    run(process.execPath, [path.join(rules.ROOT, "scripts", "ops", "pull_account_orders.js"), String(account.cdpPort), account.dataDir, days]);
  }
}

function materialsPull() {
  const accounts = arg("account") ? [rules.requireAccount(arg("account"))] : rules.loadRules().accounts;
  for (const account of accounts) {
    run(process.execPath, [path.join(rules.ROOT, "scripts", "ops", "pull_material_details.js"), String(account.cdpPort), account.dataDir]);
  }
}

function score() {
  runQuiet(PYTHON, [path.join(rules.ROOT, "scripts", "analysis", "material_scorecard.py")]);
  runQuiet(PYTHON, [path.join(rules.ROOT, "scripts", "analysis", "build_product_registry.py")]);
  const file = path.join(rules.ROOT, "data", "analysis", "material_scorecard.json");
  const data = readJson(file);
  const regFile = path.join(rules.ROOT, "data", "analysis", "product_registry.json");
  const reg = fs.existsSync(regFile) ? readJson(regFile) : { allowedProductIds: [], products: [] };
  const layers = {};
  for (const m of data.materials || []) layers[m.layer] = (layers[m.layer] || 0) + 1;
  out({
    ok: true,
    orders: data.orders,
    materials: (data.materials || []).length,
    layers,
    allowedProducts: (reg.allowedProductIds || []).length,
    otherProducts: (reg.products || []).filter((p) => p.tier === "other").length,
    file
  }, "素材评分: " + JSON.stringify(layers) + "；实际投放商品 " + (reg.allowedProductIds || []).length);
}

function preflightSummary(result) {
  const { plans, ...rest } = result;
  return rest;
}

function preflightCmd() {
  const file = arg("file");
  if (!file) fail("缺少 --file=计划文件");
  const result = preflightLib.preflightFile(file, {
    account: arg("account", "account2"),
    cash: arg("cash") ? Number(arg("cash")) : null,
    previousUnpaid: Number(arg("previous-unpaid", "0")),
    allowSingleVideo: has("allow-single-video")
  });
  const human = result.ok
    ? `预检通过: ${result.count} 条 / ${result.videos} 视频 / ${result.totalBudget} 元`
    : `预检失败: ${result.blockers.length} 个阻断\n` + result.blockers.map((b) => `- [${b.code}] ${b.title}: ${b.detail}`).join("\n");
  out(preflightSummary(result), human);
  if (!result.ok) process.exitCode = 2;
}

function plan() {
  const account = arg("account", "account2");
  const count = arg("count", "15");
  if (arg("purpose")) {
    const purpose = arg("purpose");
    rules.requireAccount(account);
    const file = path.join(rules.ROOT, "data", "analysis", `strategy_${account}_${Date.now()}.json`);
    const overrides = ["target", "bid", "budget", "compare-budget"].filter(k => arg(k)).map(k => `--${k}=${arg(k)}`);
    runQuiet(PYTHON, [path.join(rules.ROOT, "scripts", "analysis", "strategy_plan.py"), account, purpose, arg("tier", "59.9"), count, file, ...overrides]);
    const pf = preflightLib.preflightFile(file, { account });
    out({ ok: pf.ok, file, preflight: preflightSummary(pf) }, `组合候选 ${file}，${pf.count} 条，预检 ${pf.ok ? "通过" : "待处理"}`);
    if (!pf.ok) process.exitCode = 2;
    return;
  }
  runQuiet(PYTHON, [path.join(rules.ROOT, "scripts", "analysis", "build_multi_batch.py"), account, count]);
  const file = path.join(rules.ROOT, "data", "analysis", "multi_batch_" + account + ".json");
  const result = preflightLib.preflightFile(file, { account });
  out({ ok: result.ok, file, preflight: preflightSummary(result) }, result.ok ? "计划已生成并预检通过: " + file : "计划已生成，但预检未通过");
  if (!result.ok) process.exitCode = 2;
}

async function verify() {
  const accounts = arg("account") ? [rules.requireAccount(arg("account"))] : rules.loadRules().accounts;
  const rows = [];
  const reconcilePlans = [];
  for (const account of accounts) {
    const ids = trackedIds(account.id);
    const live = new Live(account.cdpPort, "verify-" + account.id);
    try {
      await live.connect();
      const set = new Set(ids);
      const map = new Map();
      for (let page = 1; page <= 10 && map.size < ids.length; page += 1) {
        const j = await live.api("MMFinderPromotionOrderApiSvr/getPromotionOrderList", { req: { page, pageSize: 50 }, baseReq: { featureFlag: 26 } });
        for (const o of (((j.data || {}).resp || {}).orderList) || []) {
          if (set.has(o.promotionId)) map.set(o.promotionId, o);
        }
      }
      let paid = 0;
      let paidYuan = 0;
      const unpaid = [];
      for (const id of ids) {
        const order = map.get(id);
        if (!order) { unpaid.push({ promotionId: id, status: "missing" }); continue; }
        const status = errors.paidStatus(order);
        reconcilePlans.push({ promotionId: id, paid: status === "paid", depositStatus: ((order.paymentInfo || {}).cashInfo || {}).depositStatus });
        if (status === "paid") { paid += 1; paidYuan += errors.paidAmountYuan(order); }
        else unpaid.push({ promotionId: id, status, depositStatus: ((order.paymentInfo || {}).cashInfo || {}).depositStatus });
      }
      rows.push({ account: account.id, total: ids.length, found: map.size, paid, paidYuan, unpaid: unpaid.length, unpaidItems: unpaid.slice(0, 5) });
    } catch (e) {
      rows.push({ account: account.id, error: e.message });
    } finally {
      live.close();
    }
  }
  if (has("write-ledger") && reconcilePlans.length) {
    createLedger().append({ type: "reconcile", account: "all", plans: reconcilePlans });
  }
  const human = rows.map((r) => r.error
    ? `${r.account}: 失败 ${r.error}`
    : `${r.account}: 已付 ${r.paid}/${r.total}，金额 ${r.paidYuan} 元，未付 ${r.unpaid}`).join("\n");
  out({ ok: rows.every((r) => !r.error && r.unpaid === 0), accounts: rows }, human);
  if (rows.some((r) => r.error || r.unpaid > 0)) process.exitCode = 2;
}

async function create() {
  const file = arg("file");
  if (!file) fail("缺少 --file=计划文件");
  const account = arg("account", "account2");
  let cash = arg("cash") ? Number(arg("cash")) : null;
  if (cash == null) {
    try {
      const snap = await accountSnapshot(rules.requireAccount(account));
      cash = snap.cashYuan;
    } catch (_) {}
  }
  const pf = preflightLib.preflightFile(file, { account, cash, previousUnpaid: Number(arg("previous-unpaid", "0")), allowSingleVideo: has("allow-single-video") });
  if (!pf.ok) {
    out(preflightSummary(pf), "预检未通过，拒绝建单");
    process.exit(2);
  }
  const body = payload.buildBatchPayload(pf.plans, account);
  const seqToPlan = new Map(body.createReqs.map((req, index) => [req.sequence, pf.plans[index]]));
  const outDir = path.join(rules.ROOT, "data", "ops");
  fs.mkdirSync(outDir, { recursive: true });
  const ts = new Date().toISOString().replace(/[:.]/g, "-");
  const payloadFile = path.join(outDir, "cli-create-" + account + "-" + ts + ".json");
  fs.writeFileSync(payloadFile, JSON.stringify(body, null, 1), "utf8");
  if (!CONFIRM) {
    out({ ok: true, dryRun: true, payloadFile, opId: body.opId, count: pf.count, budgetYuan: pf.totalBudget }, "DRY RUN: " + payloadFile + "（加 --confirm=YES 提交）");
    return;
  }
  const ledger = createLedger();
  ledger.append({ type: "batch_created", batchId: body.opId, account, count: pf.count, budgetYuan: pf.totalBudget, payloadFile });
  const live = new Live(rules.requireAccount(account).cdpPort, "cli-create-" + account);
  try {
    await live.connect();
    const resp = await live.api("MmFinderPromotionApiSvr/createBatchFeedPromotionTask", body);
    const taskId = resp && resp.data && resp.data.taskId;
    if (!taskId) fail("建单没有返回 taskId", 3);
    let result = null;
    for (let i = 0; i < 80; i += 1) {
      await new Promise((r) => setTimeout(r, 2500));
      const t = await live.api("MmFinderPromotionApiSvr/getBatchFeedPromotionTaskResult", { taskId, baseReq: { featureFlag: 26 } });
      result = (t.data || {}).result || {};
      if (result.status === 2) break;
    }
    if (!result || result.status !== 2) fail("建单轮询超时", 3);
    const cls = errors.classifyCreateResult(result);
    for (const failed of cls.failed) {
      if (String(failed.errorCode) === "11770122") {
        const plan = seqToPlan.get(failed.sequence) || {};
        const pid = plan.productId || ((plan.materials || [])[0] || {}).productId;
        if (pid) {
          rules.addInvalidProduct(pid, "11770122 商品已删除（自动登记）");
          failed.registeredProduct = pid;
          ledger.append({ type: "registry_update", productId: pid, reason: "11770122", batchId: body.opId });
        }
      }
    }
    ledger.append({ type: "batch_result", batchId: body.opId, taskId, ok: cls.ok.length, failed: cls.failed.length, total: cls.total, result });
    const payPlans = cls.ok.map((item) => ({
      ...(seqToPlan.get(item.sequence) || {}),
      promotionId: item.promotionId
    })).filter((p) => Number(p.billingMethod) !== 1);
    const postCount = cls.ok.filter((item) => Number((seqToPlan.get(item.sequence) || {}).billingMethod) === 1).length;
    let payFile = "";
    if (payPlans.length) {
      payFile = path.join(outDir, "pay-cli-" + account + "-" + ts + ".json");
      fs.writeFileSync(payFile, JSON.stringify({ batches: [{ index: 1, plans: payPlans }] }, null, 1), "utf8");
    }
    const postPlans = cls.ok.map((item) => ({ ...(seqToPlan.get(item.sequence) || {}), promotionId: item.promotionId })).filter((p) => Number(p.billingMethod) === 1);
    let realtimePayFile = "";
    if (postPlans.length) {
      realtimePayFile = path.join(outDir, "realtime-pay-" + account + "-" + ts + ".json");
      fs.writeFileSync(realtimePayFile, JSON.stringify({ plans: postPlans }, null, 1), "utf8");
    }
    const summary = { ok: cls.failed.length === 0, opId: body.opId, taskId, okCount: cls.ok.length, failed: cls.failed.length, failures: cls.failed.slice(0, 10), payFile, realtimePayFile, postBillingCount: postCount };
    out(summary, `建单完成: 成功 ${cls.ok.length} / 失败 ${cls.failed.length}` + (postCount ? `；实时扣费 ${postCount} 条，无需整条预付` : ""));
    if (cls.failed.length) process.exitCode = 2;
  } finally {
    live.close();
  }
}

async function pay() {
  const file = arg("file");
  if (!file) fail("缺少 --file=支付批次文件（plans[].promotionId）");
  const data = readJson(file);
  const requested = Array.isArray(data) ? data : data.plans || (data.batches || []).flatMap((b) => b.plans || []);
  if (!requested.length) fail("支付文件没有 plans");
  const account = arg("account", "account2");
  const {allowed: plans, held} = require("../lib/work_evidence").screenPayments(account, requested);
  if (held.length) console.error("暂缓付款", JSON.stringify(held));
  if (!plans.length) fail("本批作品均需复核");
  const body = { opId: payload.rand64(), payReqs: payload.buildPayReqs(plans), baseReq: { featureFlag: 26 } };
  if (!CONFIRM) {
    out({ ok: true, dryRun: true, count: plans.length }, "DRY RUN: 加 --confirm=YES 支付");
    return;
  }
  const live = new Live(rules.requireAccount(account).cdpPort, "cli-pay-" + account);
  try {
    await live.connect();
    const resp = await live.api("MmFinderPromotionApiSvr/createBatchPayFeedPromotionTask", body);
    const taskId = resp && resp.data && resp.data.taskId;
    if (!taskId) fail("支付没有返回 taskId", 3);
    let result = null;
    for (let i = 0; i < 80; i += 1) {
      await new Promise((r) => setTimeout(r, 2000));
      const t = await live.api("MmFinderPromotionApiSvr/getBatchPayFeedPromotionTaskResult", { taskId, baseReq: { featureFlag: 26 } });
      result = (t.data || {}).result || {};
      if (result.status === 2) break;
    }
    if (!result || result.status !== 2) fail("支付轮询超时", 3);
    const outDir = path.join(rules.ROOT, "data", "ops");
    const payFile = path.join(outDir, "cli-pay-" + account + "-" + Date.now() + ".json");
    fs.writeFileSync(payFile, JSON.stringify({ taskId, data: { result } }, null, 1), "utf8");
    createLedger().append({ type: "payment_result", batchId: arg("batch", taskId), account, promotionIds: plans.map((p) => p.promotionId), amountFen: result.amount || 0, payFile });
    out({ ok: true, taskId, amountYuan: Number(result.amount || 0) / 100, pcSdkInfo: result.pcSdkInfo ? "(present)" : "", payFile }, `支付任务完成: ${Number(result.amount || 0) / 100} 元`);
    if (has("inject") && result.pcSdkInfo) {
      run(process.execPath, [path.join(rules.ROOT, "scripts", "ops", "inject_cashier_port.js"), payFile, String(rules.requireAccount(account).cdpPort), "cashier-" + account + ".jpg"]);
    }
  } finally {
    live.close();
  }
}

function daily() {
  const catalogFile = path.join(rules.ROOT, "data", "catalog", "latest.json");
  const scoreFile = path.join(rules.ROOT, "data", "analysis", "material_scorecard.json");
  const catalog = fs.existsSync(catalogFile) ? readJson(catalogFile) : null;
  const scorecard = fs.existsSync(scoreFile) ? readJson(scoreFile) : null;
  const regFile = path.join(rules.ROOT, "data", "analysis", "product_registry.json");
  const registry = fs.existsSync(regFile) ? readJson(regFile) : null;
  const accounts = rules.loadRules().accounts.map((a) => {
    const multiFile = path.join(rules.ROOT, "data", "analysis", "multi_batch_" + a.id + ".json");
    let multi = 0;
    if (fs.existsSync(multiFile)) {
      try { multi = (readJson(multiFile).plans || []).length; } catch (_) {}
    }
    return {
      id: a.id,
      created: loadCreated(a.id).length,
      multi,
      catalog: a.catalogDir,
      dataDir: a.dataDir
    };
  });
  let catalogCounts = {};
  if (catalog) {
    for (const a of catalog.accounts || []) {
      for (const [k, v] of Object.entries(a.counts || {})) catalogCounts[k] = (catalogCounts[k] || 0) + v;
    }
  }
  const layers = {};
  if (scorecard) for (const m of scorecard.materials || []) layers[m.layer] = (layers[m.layer] || 0) + 1;
  const ledger = createLedger().summary();
  const brief = {
    generatedAt: new Date().toISOString(),
    accounts,
    catalog: catalog ? { syncedAt: catalog.syncedAt, counts: catalogCounts } : null,
    materials: scorecard ? { orders: scorecard.orders, materials: (scorecard.materials || []).length, layers } : null,
    products: registry ? { window: registry.window, allowed: (registry.allowedProductIds || []).length, other: (registry.products || []).filter((p) => p.tier === "other").length } : null,
    ledger: { events: ledger.events, batches: ledger.batches.length, paid: ledger.paid, unpaid: ledger.unpaid },
    alerts: []
  };
  if (!catalog) brief.alerts.push("目录缺失");
  if (!scorecard) brief.alerts.push("素材评分缺失");
  if (!registry) brief.alerts.push("实际投放商品表缺失");
  if (catalogCounts.invalid) brief.alerts.push("失效商品链接 " + catalogCounts.invalid + " 条");
  const dir = path.join(rules.ROOT, "data", "report");
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, "daily-brief.json"), JSON.stringify(brief, null, 1), "utf8");
  const md = [
    "# 今日简报 " + brief.generatedAt.slice(0, 10),
    "",
    "- 账户: " + accounts.map((a) => a.id + " 单视频 " + a.created + " / 多视频 " + a.multi).join(" | "),
    catalog ? "- 目录: " + JSON.stringify(catalogCounts) + "（" + catalog.syncedAt + "）" : "- 目录缺失",
    scorecard ? "- 素材: " + JSON.stringify(layers) : "- 素材评分缺失",
    registry ? "- 实际商品: 可投 " + (registry.allowedProductIds || []).length + " / 其他 " + (registry.products || []).filter((p) => p.tier === "other").length : "- 实际商品表缺失",
    "- 台账: " + JSON.stringify(brief.ledger),
    brief.alerts.length ? "- 告警: " + brief.alerts.join("；") : "- 告警: 无"
  ].join("\n");
  fs.writeFileSync(path.join(dir, "daily-brief.md"), md, "utf8");
  out(brief, md);
}

function report() {
  const args = argv.slice(1).filter((x) => x !== "--json");
  const r = spawnSync(process.execPath, [path.join(rules.ROOT, "app", "report", "build.js"), ...args], { cwd: rules.ROOT, stdio: "inherit" });
  if (r.status !== 0) process.exit(r.status || 1);
}

async function doctor() {
  const checks = [];
  for (const account of rules.loadRules().accounts) {
    const url = "http://127.0.0.1:" + account.cdpPort + "/json/version";
    let ok = false;
    try {
      const r = await fetch(url, { signal: AbortSignal.timeout(1500) });
      ok = r.ok;
    } catch (_) {}
    checks.push({ name: "chrome-" + account.id, ok, detail: url });
  }
  const files = [
    ["catalog", path.join(rules.ROOT, "data", "catalog", "latest.json")],
    ["catalog2", path.join(rules.ROOT, "data", "catalog2", "latest.json")],
    ["scorecard", path.join(rules.ROOT, "data", "analysis", "material_scorecard.json")],
    ["live_headers", path.join(rules.ROOT, "_analysis", "live_headers.json")],
    ["ledger", path.join(rules.ROOT, "data", "state", "ledger.jsonl")]
  ];
  for (const [name, file] of files) {
    checks.push({ name, ok: fs.existsSync(file), detail: file, ageHours: fs.existsSync(file) ? Math.round((Date.now() - fs.statSync(file).mtimeMs) / 360000) / 10 : null });
  }
  out({ ok: checks.every((c) => c.ok), checks }, checks.map((c) => `${c.ok ? "OK" : "缺失"} ${c.name} ${c.ageHours != null ? c.ageHours + "h" : ""}`).join("\n"));
}

(async () => {
  if (command === "account" && sub === "info") return accountInfo();
  if (command === "catalog" && sub === "sync") return catalogSync();
  if (command === "catalog" && sub === "evidence") {
    const event = readJson(arg("file"));
    const dir = rules.catalogDir(event.account);
    const videos = readJson(path.join(dir,"latest.json")).accounts.flatMap(a => a.videos);
    const hit = videos.find(v => event.workIds?.includes(v.fullExportId) || event.workIds?.includes(v.globalExportId));
    if (hit?.globalExportId && event.globalId && event.globalId !== hit.globalExportId) fail("作品全局ID不一致");
    if (hit?.globalExportId) event.globalId = hit.globalExportId;
    console.log(require("../lib/work_evidence").record(event));
    return;
  }
  if (command === "catalog" && sub === "daily") {
    const account = arg("account","account2");
    const dir = rules.catalogDir(account);
    const cat = readJson(path.join(dir,"latest.json"));
    const diff = require("../lib/catalog_changes").latestChanges(dir,cat);
    console.log(JSON.stringify(require("../lib/work_evidence").dailyWorks(cat,diff,account),null,2));
    return;
  }
  if (command === "catalog" && sub === "changes") {
    const { latestChanges } = require("../lib/catalog_changes");
    const changes = latestChanges(rules.catalogDir(arg("account", "account2")));
    return console.log(JSON.stringify(changes, null, 2));
  }
  if (command === "orders" && sub === "pull") return ordersPull();
  if (command === "materials" && sub === "pull") return materialsPull();
  if (command === "score") return score();
  if (command === "preflight") return preflightCmd();
  if (command === "plan") return plan();
  if (command === "verify") return verify();
  if (command === "create") return create();
  if (command === "pay") return pay();
  if (command === "daily") return daily();
  if (command === "report") return report();
  if (command === "doctor") return doctor();
  console.log(`用法:
  node app/ops/cli.js account info [--account=account2] [--json]
  node app/ops/cli.js catalog sync [--account=account2]
  node app/ops/cli.js catalog daily --account=account2
  node app/ops/cli.js catalog evidence --file=业务事件.json
  node app/ops/cli.js orders pull [--account=account2] [--days=90]
  node app/ops/cli.js materials pull [--account=account2]
  node app/ops/cli.js score
  node app/ops/cli.js plan --account=account2 --count=15
  node app/ops/cli.js preflight --file=path [--cash=10000] [--json]
  node app/ops/cli.js plan --account=account2 --purpose=single-test|same-author|cross-author|replace-one --tier=59.9 --count=4
  node app/ops/cli.js plan --account=account2 --purpose=budget-test --tier=59.9 --count=6 --target=42 --bid=90 --budget=300 --compare-budget=600
  node app/ops/cli.js create --file=path --confirm=YES
  node app/ops/cli.js pay --file=path --confirm=YES [--inject]
  node app/ops/cli.js verify [--json]
  node app/ops/cli.js daily [--json]
  node app/ops/cli.js report [--date=YYYY-MM-DD]
  node app/ops/cli.js doctor`);
})();
