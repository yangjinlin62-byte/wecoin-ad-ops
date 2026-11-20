"use strict";

const crypto = require("crypto");
const rules = require("./rules");

const TARGET_NAMES = {
  8: "商品成交数",
  11: "商品成交ROI",
  40: "商品净ROI",
  42: "商品净成交数"
};

function rand64() {
  return crypto.randomBytes(8).readBigUInt64BE().toString();
}

function dateStamp(date = new Date()) {
  const d = date;
  return (
    d.getFullYear() +
    "年" +
    String(d.getMonth() + 1).padStart(2, "0") +
    "月" +
    String(d.getDate()).padStart(2, "0") +
    "日"
  );
}

function exportIdsOf(plan) {
  if (Array.isArray(plan.exportIds) && plan.exportIds.length) return plan.exportIds.slice();
  if (Array.isArray(plan.materialExportIds) && plan.materialExportIds.length) return plan.materialExportIds.slice();
  if (plan.exportId) return [plan.exportId];
  return [];
}

function normalizePlan(plan) {
  const exportIds = exportIdsOf(plan);
  const target = Number(plan.target != null ? plan.target : plan.promotionTarget);
  const bidKind = plan.bidKind || (plan.roi != null ? "roi" : "wecoin");
  const bidValue = Number(plan.bidValue != null ? plan.bidValue : plan.roi != null ? plan.roi : plan.wecoinBid != null ? plan.wecoinBid : 0);
  const budgetYuan = Number(plan.budgetYuan != null ? plan.budgetYuan : plan.budget || 0);
  const billingMethod = Number(plan.billingMethod != null ? plan.billingMethod : 0);
  const pricingMethod = Number(plan.pricingMethod != null ? plan.pricingMethod : 1);
  return {
    ...plan,
    exportIds,
    target,
    bidKind,
    bidValue,
    budgetYuan,
    billingMethod,
    pricingMethod,
    tier: plan.tier || "unknown"
  };
}

function buildSuggest(plan, accountId, options = {}) {
  const p = normalizePlan(plan);
  const targeting = rules.loadRules().targeting || {};
  const suggest = {
    gender: [],
    ageRange: Array.isArray(targeting.ageRange) ? targeting.ageRange.slice() : [],
    cityIds: [],
    interestTagV3: [],
    gameCategories: [],
    roomInfo: { roomId: [] },
    similarUsernameList: [],
    wecoinBid: "0",
    roiBidX100: null,
    liveUinPackageIds: [],
    excludeUinPackageIds:
      options.excludeUinPackageIds != null
        ? options.excludeUinPackageIds.slice()
        : rules.packageIdsFor(accountId),
    enableSearchRelaxTargeting: true
  };
  if (p.bidKind === "roi" || [11, 40].includes(p.target)) {
    suggest.roi = p.bidValue;
    suggest.roiBidX100 = Math.round(p.bidValue * 100);
  } else {
    suggest.wecoinBid = String(Math.round(p.bidValue * 1000));
  }
  return suggest;
}

function buildCreateReq(plan, accountId, options = {}) {
  const p = normalizePlan(plan);
  if (!p.exportIds.length) throw new Error("plan 没有 exportId");
  if (!TARGET_NAMES[p.target]) throw new Error("不支持的 promotionTarget: " + p.target);
  if (!p.budgetYuan) throw new Error("plan 没有预算");
  return {
    sequence: p.sequence || rand64(),
    materialExportIds: p.exportIds,
    feedPromotionOrderInfo: {
      promotionTarget: p.target,
      promotionType: 2,
      estimatedWecoinAmount: String(Math.round(p.budgetYuan * 10)),
      suggest: buildSuggest(p, accountId, options),
      duration: "86400",
      pricingMethod: p.pricingMethod,
      dynamicAudit: false
    },
    voucherIds: [],
    multiplyVoucherIds: [],
    classification: 0,
    projectInfo: {},
    billingMethod: p.billingMethod,
    orderName: p.orderName || dateStamp() + " " + (TARGET_NAMES[p.target] || "投放"),
    deviceInfo: { deviceTypeId: 3 },
    currencyChoice: rules.paymentRules().currencyChoice || 2
  };
}

function buildSingleCreateReq(plan, accountId, options = {}) {
  const p = normalizePlan(plan);
  if (!p.exportIds.length) throw new Error("plan 没有 exportId");
  if (!TARGET_NAMES[p.target]) throw new Error("不支持的 promotionTarget: " + p.target);
  if (!p.budgetYuan) throw new Error("plan 没有预算");
  return {
    sequence: p.sequence || rand64(),
    materialExportIds: p.exportIds,
    feedPromotionOrderInfo: {
      promotionTarget: p.target,
      promotionType: 2,
      estimatedWecoinAmount: String(Math.round(p.budgetYuan * 10)),
      suggest: buildSuggest(p, accountId, options),
      duration: "86400",
      pricingMethod: p.pricingMethod,
      dynamicAudit: false,
      internalInfo: { isInternal: false }
    },
    voucherIds: [],
    multiplyVoucherIds: [],
    classification: 0,
    projectInfo: {},
    billingMethod: p.billingMethod,
    orderName: p.orderName || dateStamp() + " " + (TARGET_NAMES[p.target] || "投放"),
    deviceInfo: { deviceTypeId: 3 },
    currencyChoice: rules.paymentRules().currencyChoice || 2,
    baseReq: { featureFlag: 26 }
  };
}

function buildBatchPayload(plans, accountId, options = {}) {
  const list = plans.map((p) => normalizePlan(p));
  if (!list.length) throw new Error("empty plans");
  if (list.length > rules.batchLimits().maxPlans) {
    throw new Error("计划数超过单批上限 " + rules.batchLimits().maxPlans);
  }
  return {
    opId: options.opId || rand64(),
    createReqs: list.map((p) => buildCreateReq(p, accountId, options)),
    baseReq: { featureFlag: 26 }
  };
}

function buildPayReqs(plans) {
  return plans.map((p) => ({ promotionId: p.promotionId, pcSdkFlag: 1 }));
}

function fingerprint(plan, accountId) {
  const p = normalizePlan(plan);
  const ids = p.exportIds.slice().sort().join(",");
  const raw = [accountId, ids, p.target, p.budgetYuan, p.billingMethod, dateStamp()].join("|");
  return crypto.createHash("sha1").update(raw).digest("hex");
}

module.exports = {
  TARGET_NAMES,
  rand64,
  dateStamp,
  exportIdsOf,
  normalizePlan,
  buildSuggest,
  buildCreateReq,
  buildSingleCreateReq,
  buildBatchPayload,
  buildPayReqs,
  fingerprint
};
