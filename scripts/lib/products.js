"use strict";

const fs = require("fs");
const path = require("path");
const rules = require("./rules");

const FILE = path.join(rules.ROOT, "data", "analysis", "product_registry.json");
let cached = null;

function loadRegistry(force = false) {
  if (cached && !force) return cached;
  if (!fs.existsSync(FILE)) {
    cached = { allowedProductIds: [], products: [], map: new Map(), allowed: new Set() };
    return cached;
  }
  const data = JSON.parse(fs.readFileSync(FILE, "utf8"));
  const map = new Map();
  for (const p of data.products || []) map.set(p.productId, p);
  cached = { ...data, map, allowed: new Set(data.allowedProductIds || []) };
  return cached;
}

function isAllowedProduct(productId) {
  return !!(productId && loadRegistry().allowed.has(productId));
}

function product(productId) {
  return loadRegistry().map.get(productId) || null;
}

function isInvalidProduct(productId) {
  const p = product(productId);
  return !!(p && p.invalid) || rules.isInvalidProduct(productId);
}

function minCreateTime() {
  return Math.floor(new Date(rules.loadRules().videoWindow.minCreateTime).getTime() / 1000);
}

function julSepEnd() {
  return Math.floor(new Date(rules.loadRules().videoWindow.julSepEnd).getTime() / 1000);
}

function futureFrom() {
  return Math.floor(new Date(rules.loadRules().videoWindow.futureFrom).getTime() / 1000);
}

function isFuture(video) {
  return Number(video && video.createTime) >= futureFrom();
}

function isTooOld(video) {
  const t = Number(video && video.createTime) || 0;
  return t < minCreateTime();
}

function isJulSep(video) {
  const t = Number(video && video.createTime);
  return t >= minCreateTime() && t < julSepEnd();
}

module.exports = {
  FILE,
  loadRegistry,
  isAllowedProduct,
  product,
  isInvalidProduct,
  minCreateTime,
  julSepEnd,
  futureFrom,
  isFuture,
  isTooOld,
  isJulSep
};
