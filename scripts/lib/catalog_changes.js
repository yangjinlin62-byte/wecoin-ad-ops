"use strict";

const fs = require("fs");
const path = require("path");

function pageCursor(data, seen, page) {
  if (!data || !Array.isArray(data.objects)) throw new Error("素材页缺少作品列表");
  const flag = data.continueFlag;
  if ([false, 0, "0"].includes(flag)) return null;
  // Older responses can omit the default false value on a short final page.
  if (flag == null && data.objects.length < 20 && !data.lastBuf) return null;
  if (![true, 1, "1"].includes(flag) || !data.lastBuf || seen.has(data.lastBuf) || page >= 60) {
    throw new Error("素材分页未确认结束，保留上次目录");
  }
  seen.add(data.lastBuf);
  return data.lastBuf;
}

function index(snapshot) {
  const works = new Map();
  const authors = new Set();
  for (const author of snapshot.accounts) {
    if (!author.username || authors.has(author.username) || !Array.isArray(author.videos)) {
      throw new Error("作者目录缺失或重复");
    }
    authors.add(author.username);
    for (const v of author.videos) {
      const id = JSON.stringify([author.username, v.globalExportId || v.fullExportId]);
      if ((!v.globalExportId && !v.fullExportId) || works.has(id)) throw new Error("作品标识缺失或重复");
      works.set(id, v);
    }
  }
  return { works, authors };
}

function binding(v) {
  return { productId: v.productId || "", shop: v.realappid || "", hasCart: v.hasCart,
    linkStatus: v.linkStatus, private: v.isPrivate, checking: v.isChecking, exportId: v.fullExportId };
}

function compare(previous, current) {
  const currentIndex = index(current);
  const changes = [];
  const commerce = new Set(previous?.commerceHistory || []);
  for (const snapshot of [previous,current]) {
    for (const author of snapshot?.accounts || []) for (const v of author.videos) {
      if (v.productId || v.hasCart) commerce.add(JSON.stringify([author.username,v.globalExportId || v.fullExportId]));
    }
  }
  current.commerceHistory = [...commerce];
  if (!previous) return { baseline: true, previousAt: null, currentAt: current.syncedAt, changes };
  if (previous.sourcePort !== current.sourcePort || !(Date.parse(previous.syncedAt) < Date.parse(current.syncedAt))) {
    throw new Error("目录账户或观察顺序不一致");
  }
  const old = index(previous);
  for (const [key, v] of currentIndex.works) {
    const before = old.works.get(key);
    const state = binding(v);
    const record = { author: v.author, title: v.desc, globalExportId: v.globalExportId, current: state };
    if (!before) {
      v.detectedAt = current.syncedAt;
      const published = Number(v.createTime) * 1000;
      const newlyPublished = published > Date.parse(previous.syncedAt) && published <= Date.parse(current.syncedAt);
      changes.push({ ...record, event: newlyPublished ? "新发布" : "新检出", before: null });
    } else {
      if (before.detectedAt) v.detectedAt = before.detectedAt;
      if (before.bindingChangedAt) v.bindingChangedAt = before.bindingChangedAt;
      const prior = binding(before);
      if (prior.productId !== state.productId || prior.shop !== state.shop) v.bindingChangedAt = current.syncedAt;
      if (JSON.stringify(prior) !== JSON.stringify(state)) {
        changes.push({ ...record, event: "状态变化", before: prior });
      }
    }
  }
  for (const [key, v] of old.works) {
    if (!currentIndex.works.has(key)) {
      const [author] = JSON.parse(key);
      changes.push({ event: currentIndex.authors.has(author) ? "本次未见" : "作者未覆盖",
        author: v.author, title: v.desc, globalExportId: v.globalExportId, before: binding(v), current: null });
    }
  }
  return { baseline: false, previousAt: previous.syncedAt, currentAt: current.syncedAt, changes };
}

function latestChanges(dir, snapshot) {
  const read = name => JSON.parse(fs.readFileSync(path.join(dir, name), "utf8"));
  const current = snapshot || read("latest.json");
  if (current.catalogChanges) return current.catalogChanges;
  for (const name of fs.readdirSync(dir).filter(n => /^catalog-.*\.json$/.test(n)).sort().reverse()) {
    const previous = read(name);
    if (Date.parse(previous.syncedAt) < Date.parse(current.syncedAt)) return compare(previous, current);
  }
  return compare(null, current);
}

module.exports = { pageCursor, compare, latestChanges };
