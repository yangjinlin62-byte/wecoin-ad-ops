"use strict";

const rules = require("./rules");

function codeInfo(code) {
  return (rules.errorCodes() || {})[String(code)] || {
    cause: "未知错误",
    action: "manual",
    retry: false
  };
}

function classifyCreateResult(result) {
  const items = (result && result.items) || [];
  const ok = [];
  const failed = [];
  for (const item of items) {
    if (!item || item.errorCode) {
      const info = codeInfo(item && item.errorCode);
      failed.push({
        sequence: item && item.sequence,
        promotionId: item && item.promotionId,
        errorCode: item && item.errorCode,
        errorMessage: item && item.errorMessage,
        cause: info.cause,
        action: info.action,
        retry: !!info.retry
      });
    } else {
      ok.push(item);
    }
  }
  return { ok, failed, total: items.length };
}

function isSafeRetry(errorCode) {
  return String(errorCode) === "11770028";
}

function paidStatus(order) {
  const cash = order && order.paymentInfo && order.paymentInfo.cashInfo;
  if (!cash) return "unknown";
  if (Number(cash.depositStatus) === 2) return "paid";
  if (Number(cash.depositStatus) === 1) return "unpaid";
  return "unknown";
}

function paidAmountYuan(order) {
  const cash = order && order.paymentInfo && order.paymentInfo.cashInfo;
  return cash ? Number(cash.payAmountInCents || 0) / 100 : 0;
}

module.exports = {
  codeInfo,
  classifyCreateResult,
  isSafeRetry,
  paidStatus,
  paidAmountYuan
};
