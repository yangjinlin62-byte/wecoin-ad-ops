"use strict";

const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
const RULES_PATH = path.join(ROOT, "config", "rules.json");
let cached = null;

function loadRules(force = false) {
  if (cached && !force) return cached;
  const rules = JSON.parse(fs.readFileSync(RULES_PATH, "utf8"));
  if (!Array.isArray(rules.accounts) || !rules.accounts.length) {
    throw new Error("rules.json: accounts 为空");
  }
  if (!Array.isArray(rules.authors) || !rules.authors.length) {
    throw new Error("rules.json: authors 为空");
  }
  cached = rules;
  return rules;
}

function getAccount(idOrPort) {
  const rules = loadRules();
  const key = String(idOrPort);
  return rules.accounts.find((a) => a.id === key || String(a.cdpPort) === key) || null;
}

function requireAccount(idOrPort) {
  const account = getAccount(idOrPort);
  if (!account) throw new Error("未知账户: " + idOrPort);
  return account;
}

function getAuthors() {
  return loadRules().authors.slice();
}

function invalidProducts() {
  return loadRules().invalidProducts || {};
}

function isInvalidProduct(productId) {
  return !!(productId && invalidProducts()[productId]);
}

function addInvalidProduct(productId, reason = "11770122 商品已删除") {
  if (!productId) return null;
  const data = loadRules();
  if (data.invalidProducts[productId]) return data.invalidProducts[productId];
  data.invalidProducts[productId] = {
    reason,
    firstSeen: new Date().toISOString().slice(0, 10)
  };
  fs.writeFileSync(RULES_PATH, JSON.stringify(data, null, 2) + "\n", "utf8");
  cached = data;
  return data.invalidProducts[productId];
}

function packageIdsFor(accountId) {
  const account = requireAccount(accountId);
  return Array.isArray(account.excludeUinPackageIds) ? account.excludeUinPackageIds.slice() : [];
}

function allowedBudgets() {
  return loadRules().batch.allowedBudgets.slice();
}

function isAllowedBudget(budgetYuan) {
  return allowedBudgets().includes(Number(budgetYuan));
}

function batchLimits() {
  return loadRules().batch;
}

function paymentRules() {
  return loadRules().payment;
}

function errorCodes() {
  return loadRules().errorCodes || {};
}

function dataDir(accountId) {
  return path.join(ROOT, "data", requireAccount(accountId).dataDir);
}

function catalogDir(accountId) {
  return path.join(ROOT, "data", requireAccount(accountId).catalogDir);
}

function stateDir() {
  return path.join(ROOT, "data", "state");
}

function logsDir() {
  return path.join(ROOT, "data", "logs");
}

module.exports = {
  ROOT,
  RULES_PATH,
  loadRules,
  getAccount,
  requireAccount,
  getAuthors,
  invalidProducts,
  isInvalidProduct,
  addInvalidProduct,
  packageIdsFor,
  allowedBudgets,
  isAllowedBudget,
  batchLimits,
  paymentRules,
  errorCodes,
  dataDir,
  catalogDir,
  stateDir,
  logsDir
};
