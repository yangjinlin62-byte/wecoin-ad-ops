"use strict";

const fs = require("fs");
const path = require("path");
const { execFileSync } = require("child_process");
const { Live } = require("../lib/live");
const rules = require("../lib/rules");
const preflightLib = require("../lib/preflight");

const ROOT = rules.ROOT;
const arg = (name, d) => {
  const hit = process.argv.find((x) => x.startsWith("--" + name + "="));
  return hit ? hit.split("=").slice(1).join("=") : d;
};
const stage = arg("stage", "23");
const only = arg("account", "");
const confirm = process.argv.includes("--confirm=YES");
const force = process.argv.includes("--force");
const localDate = new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Shanghai" });
const stateDir = path.join(ROOT, "data", "state");
fs.mkdirSync(stateDir, { recursive: true });
const stateFile = path.join(stateDir, "checkpoint_" + localDate + "_" + stage + ".json");
const reportBase = path.join(ROOT, "data", "analysis", "checkpoint_" + localDate + "_" + stage);

function parseJsonOutput(text) {
  const s = String(text || "");
  const start = s.indexOf("{");
  if (start < 0) throw new Error("no JSON in output");
  let depth = 0, inStr = false, esc = false;
  for (let i = start; i < s.length; i += 1) {
    const ch = s[i];
    if (inStr) {
      if (esc) esc = false;
      else if (ch === "\\") esc = true;
      else if (ch === '"') inStr = false;
      continue;
    }
    if (ch === '"') inStr = true;
    else if (ch === "{") depth += 1;
    else if (ch === "}") {
      depth -= 1;
      if (depth === 0) return JSON.parse(s.slice(start, i + 1));
    }
  }
  throw new Error("unterminated JSON in output");
}

function read(p, d) { try { return JSON.parse(fs.readFileSync(p, "utf8")); } catch (_) { return d; } }
function run(cmd, args) {
  return execFileSync(cmd, args, { cwd: ROOT, encoding: "utf8", timeout: 15 * 60 * 1000, maxBuffer: 20 * 1024 * 1024 });
}
function latestPayFile(account) {
  const ops = path.join(ROOT, "data", "ops");
  const names = fs.readdirSync(ops).filter((n) => n.endsWith(".json") && (n.startsWith("pay-recovered-" + account + "-") || n.startsWith("pay-cli-" + account + "-")));
  names.sort((a, b) => fs.statSync(path.join(ops, b)).mtimeMs - fs.statSync(path.join(ops, a)).mtimeMs);
  return names.length ? path.join(ops, names[0]) : "";
}

(async () => {
  if (fs.existsSync(stateFile) && !force) {
    console.log("checkpoint already ran", stateFile);
    console.log(fs.readFileSync(path.join(ROOT, "data", "analysis", "checkpoint_" + localDate + "_" + stage + ".md"), "utf8").slice(0, 4000));
    return;
  }
  const report = { stage, date: localDate, startedAt: new Date().toISOString(), accounts: [], ok: true };
  const accounts = only ? [only] : ["account1", "account2"];
  for (const account of accounts) {
    const entry = { account, cash: null, pending: null, plans: 0, budget: 0, preflight: null, create: null, payment: null, verify: null, error: null };
    const live = new Live(rules.requireAccount(account).cdpPort, "cp-" + account + "-" + stage);
    try {
      await live.connect();
      const w = await live.api("MMFinderPromotionDspApisvr/inquiryUserWalletInfo", {});
      const cs = (((w.data || {}).userWalletInfo || {}).currencies) || [];
      entry.cash = Number((cs.find((c) => c.currencyType === 10000) || {}).balance || 0) / 100;

      // any recent payment file still waiting for payment blocks new creation
      const pf = latestPayFile(account);
      if (pf) {
        const data = read(pf, {});
        const plans = data.plans || (data.batches || []).flatMap((b) => b.plans || []);
        let pending = null;
        for (const p of plans) {
          if (!p.promotionId) continue;
          const d = await live.api("MmFinderPromotionApiSvr/getFeedPromotionOrderDetail", { promotionId: p.promotionId, baseReq: { featureFlag: 26 } });
          const oi = (((d.data || {}).order) || {}).orderInfo || {};
          const dep = Number(((oi.paymentInfo || {}).cashInfo || {}).depositStatus);
          if (Number(oi.status) === 1 && dep !== 2) {
            pending = { file: pf, first: p.promotionId, status: oi.status, depositStatus: dep, total: plans.length };
            break;
          }
        }
        if (pending) {
          entry.pending = pending;
          report.ok = false;
          report.accounts.push(entry);
          console.log(account, "pending payment, skip", entry.pending);
          continue;
        }
      }

      const outFile = path.join(ROOT, "data", "analysis", "checkpoint_" + stage + "_" + account + ".json");
      const checkpointRules = rules.loadRules().checkpoint || {};
      const strategyEnabled = !!(checkpointRules.strategy && checkpointRules.strategy.enabled);
      const builder = strategyEnabled ? "build_checkpoint_strategy.py" : "build_checkpoint_batch.py";
      run("python", [path.join(ROOT, "app", "analysis", builder), "--account=" + account, "--stage=" + stage, "--cash=" + entry.cash]);
      const batch = read(outFile, null);
      if (!batch) throw new Error("builder no output");
      entry.plans = batch.count;
      entry.budget = batch.totalBudget;
      const pfCheck = preflightLib.preflight(batch.plans, { account, cash: entry.cash, allowSingleVideo: false });
      entry.preflight = { ok: pfCheck.ok, blockers: pfCheck.blockers, warnings: pfCheck.warnings.slice(0, 10) };
      if (!pfCheck.ok) {
        report.ok = false;
        report.accounts.push(entry);
        console.log(account, "preflight failed", JSON.stringify(pfCheck.blockers).slice(0, 1000));
        continue;
      }
      if (!confirm) {
        console.log(account, "dry-run", batch.count, "plans", batch.totalBudget, "cash", entry.cash);
        report.accounts.push(entry);
        continue;
      }
      const createOut = run("node", [path.join(ROOT, "app", "ops", "cli.js"), "create", "--file=" + outFile, "--account=" + account, "--cash=" + entry.cash, "--confirm=YES", "--json"]);
      const summary = parseJsonOutput(createOut);
      entry.create = summary;
      if (summary.payFile) {
        // 预付费走批量支付（1 次请求付 N 条，低频，避免平台限流）
        run("node", [path.join(ROOT, "app", "ops", "pay_batch.js"), "--file=" + summary.payFile, "--account=" + account]);
        entry.payment = { method: "batch-payFeedPromotionTask", file: summary.payFile };
        const payData = read(summary.payFile, {});
        const plans = payData.plans || (payData.batches || []).flatMap((b) => b.plans || []);
        let paid = 0, pending = 0;
        for (const p of plans) {
          const d = await live.api("MmFinderPromotionApiSvr/getFeedPromotionOrderDetail", { promotionId: p.promotionId, baseReq: { featureFlag: 26 } });
          const oi = (((d.data || {}).order) || {}).orderInfo || {};
          const dep = Number(((oi.paymentInfo || {}).cashInfo || {}).depositStatus);
          if (dep === 2) paid += 1; else pending += 1;
        }
        entry.verify = { total: plans.length, paid, pending };
        if (pending) report.ok = false;
      }
      if (summary.realtimePayFile) {
        run("node", [path.join(ROOT, "app", "ops", "pay_realtime.js"), "--file=" + summary.realtimePayFile, "--account=" + account]);
        entry.realtimePay = summary.realtimePayFile;
      }
    } catch (e) {
      if (/cash guard/i.test(String(e.message || ""))) {
        entry.skipped = "cash_below_floor";
        entry.error = null;
      } else {
        entry.error = e.message;
        report.ok = false;
      }
    } finally {
      live.close();
    }
    report.accounts.push(entry);
    console.log(account, JSON.stringify(entry).slice(0, 2000));
  }
  report.finishedAt = new Date().toISOString();
  fs.writeFileSync(reportBase + ".json", JSON.stringify(report, null, 1), "utf8");
  const lines = ["# Checkpoint " + localDate + " " + stage + ":00", "", "- ok: " + report.ok, ""];
  for (const a of report.accounts) {
    lines.push("## " + a.account, "", "- 现金: " + a.cash, "- pending: " + JSON.stringify(a.pending), "- 计划: " + a.plans + " / 预算 " + a.budget, "- 预检: " + JSON.stringify(a.preflight), "- 建单: " + JSON.stringify(a.create), "- 支付: " + JSON.stringify(a.payment), "- 复核: " + JSON.stringify(a.verify), "- 错误: " + a.error, "");
  }
  fs.writeFileSync(reportBase + ".md", lines.join("\n"), "utf8");
  fs.writeFileSync(stateFile, JSON.stringify({ date: localDate, stage, status: report.ok ? "ok" : "partial", report: reportBase + ".json" }, null, 1), "utf8");
  console.log("report", reportBase + ".md");
})().catch((e) => { console.error("FAILED", e && e.stack ? e.stack : e); process.exit(1); });
