"use strict";

const fs = require("fs");
const path = require("path");
const rules = require("./rules");

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function defaultFile() {
  return path.join(rules.stateDir(), "ledger.jsonl");
}

function createLedger(file = defaultFile()) {
  ensureDir(path.dirname(file));
  function append(event) {
    const row = { ts: new Date().toISOString(), ...event };
    fs.appendFileSync(file, JSON.stringify(row) + "\n", "utf8");
    return row;
  }
  function read() {
    if (!fs.existsSync(file)) return [];
    return fs
      .readFileSync(file, "utf8")
      .split("\n")
      .filter(Boolean)
      .map((line) => {
        try { return JSON.parse(line); } catch (_) { return null; }
      })
      .filter(Boolean);
  }
  function summary() {
    const events = read();
    const batches = new Map();
    const plans = new Map();
    for (const e of events) {
      if (e.type === "batch_created") {
        batches.set(e.batchId, { ...(batches.get(e.batchId) || {}), ...e, paid: false });
      } else if (e.type === "batch_result") {
        const b = batches.get(e.batchId) || { batchId: e.batchId };
        b.ok = e.ok;
        b.failed = e.failed;
        b.total = e.total;
        batches.set(e.batchId, b);
      } else if (e.type === "payment_result") {
        for (const id of e.promotionIds || []) plans.set(id, { promotionId: id, paid: true, batchId: e.batchId });
      } else if (e.type === "reconcile") {
        for (const p of e.plans || []) plans.set(p.promotionId, { ...(plans.get(p.promotionId) || {}), ...p });
      }
    }
    return {
      file,
      events: events.length,
      batches: [...batches.values()],
      paid: [...plans.values()].filter((p) => p.paid).length,
      unpaid: [...plans.values()].filter((p) => p.paid === false).length
    };
  }
  function snapshot() {
    const out = path.join(path.dirname(file), "current.json");
    const data = summary();
    fs.writeFileSync(out, JSON.stringify(data, null, 1), "utf8");
    return out;
  }
  return { file, append, read, summary, snapshot };
}

module.exports = { defaultFile, createLedger };
