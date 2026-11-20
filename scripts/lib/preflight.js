"use strict";

const fs = require("fs");
const path = require("path");
const rules = require("./rules");
const payload = require("./payload");
const products = require("./products");
const workEvidence = require("./work_evidence");

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

function loadPlanFile(file) {
  const data = readJson(file);
  if (Array.isArray(data)) return data;
  if (Array.isArray(data.plans)) return data.plans;
  if (Array.isArray(data.batches)) return data.batches.flatMap((b) => b.plans || []);
  throw new Error("计划文件里没有 plans 数组: " + file);
}

function loadCatalog(accountId) {
  const file = path.join(rules.catalogDir(accountId), "latest.json");
  if (!fs.existsSync(file)) return { file, missing: true, byFull: new Map(), byGlobal: new Map(), mtime: 0 };
  const data = readJson(file);
  const byFull = new Map();
  const byGlobal = new Map();
  for (const account of data.accounts || []) {
    for (const video of account.videos || []) {
      if (video.fullExportId) byFull.set(video.fullExportId, video);
      if (video.globalExportId) byGlobal.set(video.globalExportId, video);
    }
  }
  return { file, missing: false, byFull, byGlobal, mtime: fs.statSync(file).mtimeMs, syncedAt: data.syncedAt };
}

function tierFromWording(w) {
  const text = w || "";
  if (text.includes("私享") || text.includes("罗明荣") || text.includes("数字创富课闭门") || text.includes("赢在数字创富课闭门")) return "399";
  if (text.includes("直播课") || text.includes("训练营") || text.includes("3天课") || text.includes("数字经济") || text.includes("数字创富3天")) return "59.9";
  return null;
}

function loadProductTiers() {
  const file = path.join(rules.ROOT, "data", "analysis", "material_scorecard.json");
  if (!fs.existsSync(file)) return {};
  try {
    const data = readJson(file);
    const map = {};
    for (const p of data.products || []) {
      if (p.productId && (p.priceTier === "59.9" || p.priceTier === "399")) map[p.productId] = p.priceTier;
    }
    return map;
  } catch (_) {
    return {};
  }
}

function tierOfVideo(video, productTiers) {
  if (!video) return null;
  return productTiers[video.productId] || tierFromWording(video.productWording) || null;
}

function preflight(plans, options = {}) {
  const accountId = options.account || "account2";
  const account = rules.requireAccount(accountId);
  const limits = rules.batchLimits();
  const payment = rules.paymentRules();
  const catalog = options.catalog || loadCatalog(accountId);
  const productTiers = loadProductTiers();
  const registry = products.loadRegistry();
  const workHolds = workEvidence.blocked(accountId);
  const blockers = [];
  const warnings = [];
  const add = (list, code, title, detail) => list.push({ code, title, detail });
  if (!registry.allowed || !registry.allowed.size) {
    add(warnings, "PRODUCT_REGISTRY_MISSING", "缺实际投放商品表", "先运行 build_product_registry.py");
  }

  if (catalog.missing) {
    add(blockers, "CATALOG_MISSING", "选品目录缺失", "缺少 " + catalog.file);
  } else {
    const ageHours = (Date.now() - Date.parse(catalog.syncedAt)) / 3600000;
    if (!Number.isFinite(ageHours) || ageHours > 12) {
      add(warnings, "CATALOG_STALE", "目录观察时间需复核", Number.isFinite(ageHours) ? "距同步 " + ageHours.toFixed(1) + " 小时" : "缺同步时间");
    }
  }

  const normalized = (plans || []).map((p) => payload.normalizePlan(p));
  if (!normalized.length) add(blockers, "EMPTY", "计划为空", "没有可提交的计划");
  if (normalized.length > limits.maxPlans) {
    add(blockers, "TOO_MANY", "超过单批上限", normalized.length + " > " + limits.maxPlans);
  }

  let totalBudget = 0;
  let preBudget = 0;
  let postBudget = 0;
  let totalVideos = 0;
  const fingerprints = new Map();
  const tiers = new Map();
  let julSepCount = 0;
  let newProductCount = 0;

  normalized.forEach((plan, index) => {
    const n = index + 1;
    const label = "第 " + n + " 条";
    const videos = plan.exportIds || [];
    const isBoost = plan.mode === "boost" || Number(plan.pricingMethod) === 0;
    if (!videos.length) {
      add(blockers, "NO_VIDEO", label + " 没有视频", "exportIds 为空");
      return;
    }
    totalVideos += videos.length;
    const intentionalSingle = videos.length === 1 && (options.allowSingleVideo || plan.strategy?.purpose === "single-test");
    if (videos.length < limits.minVideos && !intentionalSingle) {
      add(blockers, "SINGLE_VIDEO", label + " 视频数不足", videos.length + " 个视频；规则要求至少 " + limits.minVideos + " 个");
    }
    if (videos.length > limits.maxVideos) {
      add(blockers, "TOO_MANY_VIDEOS", label + " 视频过多", videos.length + " > " + limits.maxVideos);
    }
    const boostBudgetOk = isBoost && [100, 300, 600].includes(Number(plan.budgetYuan));
    if (!limits.allowedBudgets.includes(Number(plan.budgetYuan)) && !boostBudgetOk) {
      add(blockers, "BUDGET_NOT_ALLOWED", label + " 预算不在白名单", plan.budgetYuan + " 元");
    }
    if (Number(plan.budgetYuan) === 100 && !isBoost) {
      add(blockers, "BUDGET_100", label + " 使用 100 元预算", "docs/05：100 元 ROI 0.27，最差");
    }
    totalBudget += Number(plan.budgetYuan) || 0;
    if (Number(plan.billingMethod) === 1) postBudget += Number(plan.budgetYuan) || 0;
    else preBudget += Number(plan.budgetYuan) || 0;

    if (!plan.target) add(blockers, "NO_TARGET", label + " 没有目标", "");
    if (!(plan.bidValue > 0) && !isBoost) add(blockers, "NO_BID", label + " 没有有效出价", String(plan.bidValue));
    if (!isBoost && plan.bidKind === "wecoin" && plan.budgetYuan > 0 && plan.bidValue / plan.budgetYuan > 0.8) {
      add(warnings, "BID_RATIO", label + " 出价占预算偏高", Math.round((plan.bidValue / plan.budgetYuan) * 100) + "%");
    }
    if (!isBoost && Number(plan.target) === 42 && Number(plan.bidValue) === 500 && Number(plan.budgetYuan) < 600) {
      add(blockers, "BID_RANGE", label + " 399 净成交数 500 元配低预算", "预算 " + plan.budgetYuan + " 元；11770120 出价超范围");
    }
    const tierCaps = (rules.loadRules().bidCaps || {})[String(plan.tier || "")] || {};
    const cap = Number(tierCaps[String(plan.target)] || 0);
    if (!isBoost && cap > 0 && plan.bidKind === "wecoin" && Number(plan.bidValue) > cap) {
      add(blockers, "BID_ABOVE_CAP", label + " 出价超过该商品层上限", "出价 " + plan.bidValue + " > 上限 " + cap + "；11770120");
    }
    const br = ((rules.loadRules().bidBudgetRules || {})[String(plan.tier || "")] || {})[String(plan.target)];
    if (!isBoost && br && plan.bidKind === "wecoin" && Number(plan.bidValue) > 0) {
      const threshold = Number(br.applyMultiplierAbove || 0);
      const minBudget = Number(plan.bidValue) > threshold ? Number(plan.bidValue) * Number(br.multiplier || 2) : Number(br.minBudgetYuan || 0);
      if (Number(plan.budgetYuan) < minBudget) {
        add(blockers, "BID_BUDGET_RATIO", label + " 预算低于出价要求", "出价 " + plan.bidValue + " 需要预算至少 " + minBudget + "；当前 " + plan.budgetYuan + "；11770120");
      }
    }

    const videoTiers = new Set();
    let hasJulSep = false;
    let hasNewProduct = false;
    for (const exportId of videos) {
      const video = catalog.byFull.get(exportId) || catalog.byGlobal.get(exportId) || null;
      if (!video) {
        add(blockers, "VIDEO_NOT_FOUND", label + " 视频不在目录", exportId);
        continue;
      }
      if (products.isTooOld(video)) {
        add(blockers, "VIDEO_TOO_OLD", label + " 视频早于 7 月", "createTime " + video.createTime + "；只投 2026-07-01 之后");
      }
      if (products.isJulSep(video)) hasJulSep = true;
      const hold = workHolds.get(video.globalExportId) || workHolds.get(video.fullExportId);
      if (hold) add(blockers, "WORK_EXCLUDED", label + " 作品停投", exportId + " / " + hold);
      if (video.isPrivate || video.isChecking || video.hasCart === false) {
        add(blockers, "VIDEO_UNAVAILABLE", label + " 作品不可见、审核中或已撤掉购物车", exportId);
      }
      const frozen = (plan.materials || []).find(m => m.exportId === exportId);
      if ((frozen?.productId && frozen.productId !== video.productId) ||
          (frozen?.realappid && frozen.realappid !== video.realappid) ||
          (plan.strategy?.productId && plan.strategy.productId !== video.productId)) {
        add(blockers, "BINDING_CHANGED", label + " 作品挂链与草稿不一致", exportId);
      } else if (video.bindingChangedAt && (!frozen?.productId || !frozen?.realappid)) {
        add(blockers, "BINDING_RECHECK", label + " 挂链曾变更，请核当前商品与店铺并更新草稿", exportId);
      }
      if (video.linkStatus !== "valid") {
        add(blockers, "VIDEO_INVALID", label + " 视频链接不可投", (video.desc || exportId) + " / " + video.linkStatus);
      }
      if (video.linkStatus === "valid" && (!video.productId || video.realappid === "")) {
        add(blockers, "LINK_UNRESOLVED", label + " 缺商品或店铺绑定", exportId);
      }
      if (video.productId && products.isInvalidProduct(video.productId)) {
        add(blockers, "PRODUCT_INVALID", label + " 商品链接已失效", video.productId + " " + (video.productWording || ""));
      }
      const futureVideo = products.isFuture(video);
      if (!futureVideo && registry.allowed && registry.allowed.size && video.productId && !products.isAllowedProduct(video.productId)) {
        add(blockers, "PRODUCT_NOT_ACTIVE", label + " 商品不在 8-11 月实际投放清单", video.productId + " " + (video.productWording || ""));
      }
      if (futureVideo && registry.allowed && registry.allowed.size && video.productId && !products.isAllowedProduct(video.productId)) {
        hasNewProduct = true;
      }
      const productTier = (products.product(video.productId) || {}).tier;
      if (productTier === "other") {
        add(blockers, "PRODUCT_TIER_OTHER", label + " 商品层为其他", video.productId + " " + (video.productWording || ""));
      }
      const vt = productTier || tierOfVideo(video, productTiers);
      if (vt) videoTiers.add(vt);
    }
    if (hasJulSep) julSepCount += 1;
    if (hasNewProduct) newProductCount += 1;
    if (plan.tier && plan.tier !== "unknown") videoTiers.add(plan.tier);
    if (videoTiers.size > 1) {
      add(blockers, "MIXED_TIER", label + " 混了 59.9 和 399", [...videoTiers].join(" / "));
    }
    if (videoTiers.size === 1) {
      const tier = [...videoTiers][0];
      tiers.set(tier, (tiers.get(tier) || 0) + 1);
      const tierRule = rules.loadRules().productTiers[tier];
      if (!isBoost && tierRule && Number(plan.budgetYuan) < tierRule.minBudget) {
        add(blockers, "TIER_BUDGET", label + " " + tier + " 预算低于下限", plan.budgetYuan + " < " + tierRule.minBudget);
      }
    } else if (!plan.tier || plan.tier === "unknown") {
      add(warnings, "TIER_UNKNOWN", label + " 商品层未知", "建议先确认 59.9/399");
    }

    const fp = payload.fingerprint(plan, accountId);
    const prev = fingerprints.get(fp);
    const maxSame = limits.maxSameFingerprint || 1;
    if (prev && prev.count >= maxSame) {
      add(blockers, "DUPLICATE", label + " 同指纹超过 " + maxSame + " 条", "第 " + prev.index + " 条起重复；同一账户/视频组/目标/预算");
    } else if (prev) {
      prev.count += 1;
    } else {
      fingerprints.set(fp, { count: 1, index: n });
    }
  });

  if (julSepCount) {
    add(warnings, "JUL_SEP_LINK", julSepCount + " 条计划含 7-9 月视频", "已校验当前目录有效性和实际投放商品；上线前再复核一次链接");
  }
  if (newProductCount) {
    add(warnings, "NEW_PRODUCT_ALLOWED", newProductCount + " 条计划含未来新视频商品", "未来新视频只要有有效商品链接即放行；建单前确认商品层和优惠后价格");
  }

  const cash = options.cash != null ? Number(options.cash) : null;
  if (cash != null && preBudget > cash - account.cashFloor) {
    add(blockers, "CASH", "预扣预算余额不足", "需预扣 " + preBudget + " 元，可用 " + (cash - account.cashFloor) + " 元（保留 " + account.cashFloor + "）");
  }
  if (cash != null && postBudget > 0 && cash < (rules.loadRules().billing.postMinCashYuan || 500)) {
    add(blockers, "POST_CASH", "实时扣费余额过低", "实时扣费至少保留 " + (rules.loadRules().billing.postMinCashYuan || 500) + " 元，当前 " + cash);
  }
  if (options.previousUnpaid > 0) {
    add(blockers, "PAYMENT_GATE", "上一批还有未支付", options.previousUnpaid + " 条未支付；先支付再建下一批");
  }

  const allSingle = normalized.length > 0 && normalized.every((p) => (p.exportIds || []).length === 1);
  if (allSingle && !options.allowSingleVideo && normalized.some(p => p.strategy?.purpose !== "single-test")) {
    add(blockers, "ALL_SINGLE", "整批都是单视频", "docs/05：单视频 ROI 0.30/0.445，最差；请改 2-20 视频一组");
  }

  return {
    ok: blockers.length === 0,
    account: accountId,
    plans: normalized,
    count: normalized.length,
    videos: totalVideos,
    totalBudget,
    preBudget,
    postBudget,
    tiers: Object.fromEntries(tiers),
    catalog: { file: catalog.file, syncedAt: catalog.syncedAt || null, ageHours: catalog.mtime ? Math.round(((Date.now() - catalog.mtime) / 3600000) * 10) / 10 : null },
    blockers,
    warnings,
    stats: {
      minVideos: limits.minVideos,
      maxVideos: limits.maxVideos,
      allowedBudgets: limits.allowedBudgets
    }
  };
}

function preflightFile(file, options = {}) {
  return preflight(loadPlanFile(file), options);
}

module.exports = {
  loadPlanFile,
  loadCatalog,
  preflight,
  preflightFile
};
