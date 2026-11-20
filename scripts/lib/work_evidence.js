"use strict";
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const rules = require("./rules");
const products = require("./products");
const seed = require("../config/work-exclusions.json");
const folder = path.join(rules.ROOT, "data/state/work-evidence");

// One immutable business receipt per file. Replaying identical evidence is idempotent.
function record(event, dir = folder) {
  const { type, account, orderId, reason, workIds, globalId, paidAt, refundAt, refundCause, refundState } = event;
  rules.requireAccount(account);
  if (type === "clear_quick_refund") {
    if (!/^[a-f0-9]{64}$/.test(event.eventId) || !reason?.trim()) throw new Error("需要原事件ID与复核依据");
    const original = JSON.parse(fs.readFileSync(path.join(dir,event.eventId+".json"),"utf8"));
    if (original.account !== account || original.type !== "single_quick_refund") throw new Error("仅可复核本户快速退款事件");
    const file = path.join(dir,event.eventId+".released");
    if (!fs.existsSync(file)) {
      const tmp = file+"."+process.pid+".tmp";
      fs.writeFileSync(tmp, JSON.stringify({reason,at:new Date().toISOString()}), "utf8");
      fs.renameSync(tmp,file);
    }
    return event.eventId;
  }
  if (!["platform_violation","single_quick_refund"].includes(type) || !reason?.trim() ||
      !Array.isArray(workIds) || !workIds.length || workIds.some(id => typeof id !== "string" || !id.trim())) {
    throw new Error("需要证据类型、精确作品ID及原因");
  }
  if (type === "single_quick_refund" && (!orderId || event.materialCount !== 1 || workIds.length !== 1 || !paidAt || !refundAt ||
      !["退款中","已退款"].includes(refundState) || !["待核","作品违规"].includes(refundCause) ||
      !(Date.parse(refundAt) >= Date.parse(paidAt)))) {
    throw new Error("快速退款需要单素材实际订单、支付时间、退款观察时间");
  }
  if (type === "platform_violation" && workIds.length !== 1) throw new Error("违规回执须指明一条作品");
  const row = { type, account, orderId: orderId || null, reason, workIds, globalId: globalId || null,
    paidAt: paidAt || null, refundAt: refundAt || null, refundCause: refundCause || null,
    refundState: refundState || null, materialCount: event.materialCount || null,
    elapsedSeconds: type === "single_quick_refund" ? (Date.parse(refundAt)-Date.parse(paidAt))/1000 : null };
  const id = crypto.createHash("sha256").update(JSON.stringify(row)).digest("hex");
  fs.mkdirSync(dir, {recursive:true});
  const file = path.join(dir, id + ".json");
  if (!fs.existsSync(file)) {
    const tmp = file + "." + process.pid + ".tmp";
    fs.writeFileSync(tmp, JSON.stringify(row, null, 2), "utf8");
    fs.renameSync(tmp, file);
  }
  return id;
}

function blocked(account, dir = folder) {
  const ids = new Map(seed.flatMap(r => r.ids.map(id => [id, r.reason])));
  if (!fs.existsSync(dir)) return ids;
  for (const file of fs.readdirSync(dir).filter(n => n.endsWith(".json"))) {
    const e = JSON.parse(fs.readFileSync(path.join(dir,file),"utf8"));
    if (e.type === "single_quick_refund" && fs.existsSync(path.join(dir,file.slice(0,-5)+".released"))) continue;
    const aliases = [...(e.globalId ? [e.globalId] : []), ...(e.account === account ? e.workIds : [])];
    for (const id of aliases) {
      if (!ids.has(id) || ids.get(id) === "single_quick_refund") ids.set(id,e.type);
    }
  }
  return ids;
}

function disposition(video, holds, wasCommerce=false) {
  const commerce = Boolean(video.productId || video.hasCart || wasCommerce);
  const kind = commerce ? "带货视频" : "流量视频";
  const matches = [holds.get(video.globalExportId), holds.get(video.fullExportId)].filter(Boolean);
  const hold = matches.find(value => value !== "single_quick_refund") || matches[0];
  let status;
  if (hold) status = hold === "single_quick_refund" ? "快速退款停投待核" : "作品禁投";
  else if (video.isPrivate || video.isChecking) status = "私密或审核中";
  else if (!commerce) status = "无带货链接";
  else if (!video.productId || !video.realappid || video.hasCart === false || video.linkStatus !== "valid" ||
           products.isInvalidProduct(video.productId)) status = "挂链不可用或待核";
  else status = "带货候选";
  return {kind,status};
}

function screenPayments(account, plans) {
  const cat = JSON.parse(fs.readFileSync(path.join(rules.catalogDir(account),"latest.json"),"utf8"));
  return screenFromCatalog(cat, plans, blocked(account));
}

function screenFromCatalog(cat, plans, holds) {
  const by = new Map();
  for (const a of cat.accounts) for (const v of a.videos) {
    by.set(v.fullExportId,v);
    if (v.globalExportId) by.set(v.globalExportId,v);
  }
  const allowed = [], held = [];
  for (const p of plans) {
    let reason = null;
    const ids = p.exportIds || p.materialExportIds || (p.exportId ? [p.exportId] : []);
    if (!ids.length) reason = "付款记录缺作品ID";
    for (const id of ids) {
      const v = by.get(id);
      const state = v ? disposition(v,holds).status : "作品当前未见";
      if (state !== "带货候选") { reason = state; break; }
      const m = (p.materials || []).find(x => x.exportId === id);
      if ((m?.productId && m.productId !== v.productId) || (m?.realappid && m.realappid !== v.realappid) ||
          (v.bindingChangedAt && (!m?.productId || !m?.realappid))) {
        reason = "商品或店铺绑定需复核"; break;
      }
    }
    if (reason) held.push({promotionId:p.promotionId, reason});
    else allowed.push(p);
  }
  return {allowed,held};
}

function dailyWorks(cat, diff, account) {
  const holds = blocked(account), known = new Set(cat.commerceHistory || []);
  const changed = new Map(diff.changes.filter(c=>c.current).map(c=>[c.globalExportId || c.current.exportId,c]));
  const authors = cat.accounts.map(a => {
    const counts = {}, events = [];
    for (const v of a.videos) {
      const workId = v.globalExportId || v.fullExportId;
      const state = disposition(v, holds, known.has(JSON.stringify([a.username,workId])));
      const key = state.kind + "/" + state.status;
      counts[key] = (counts[key] || 0) + 1;
      const change = changed.get(workId);
      if (change || holds.has(v.fullExportId) || holds.has(v.globalExportId)) {
        events.push({event:change?.event || "既有停投", title:v.desc, workId, ...state});
      }
    }
    return {author:a.nickName,counts,events};
  });
  return {account,syncedAt:cat.syncedAt,authors,missing:diff.changes.filter(c=>!c.current)};
}

module.exports = { record, blocked, disposition, screenPayments, screenFromCatalog, dailyWorks };
