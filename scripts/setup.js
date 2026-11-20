#!/usr/bin/env node
"use strict";

/**
 * 首次安装：探测 CDP、拉投放账户、扫商品、生成 config/rules.json
 *
 * 用法：
 *   node scripts/setup.js --port=9444
 *   node scripts/setup.js --port=9444,9445
 *
 * 它只做「探测 + 写配置」，不建单、不支付。
 */

const fs = require("fs");
const path = require("path");
const { Live } = require("./lib/live");

const ROOT = path.resolve(__dirname, "..");
const CONFIG_DIR = path.join(ROOT, "config");
const RULES_PATH = path.join(CONFIG_DIR, "rules.json");

function arg(name, fallback) {
  const hit = process.argv.slice(2).find((a) => a.startsWith("--" + name + "="));
  return hit ? hit.slice(name.length + 3) : fallback;
}

async function probe(port) {
  const live = new Live(Number(port), "setup-" + port);
  await live.connect();

  // 投放账户 + 管理员
  const prep = await live.api("MMFinderPromotionDspApisvr/getUserPrepare", { baseReq: { featureFlag: 26 } });
  const d = prep.data || {};
  const ci = ((d.corporateUserInfo || {}).corporateInfo) || {};
  const accountName = ci.finderNickname || ci.nickname || null;
  const company = ci.authInfo && ci.authInfo.companyAuthInfo ? ci.authInfo.companyAuthInfo.companyName : null;
  const admin = ci.adminWxUsername || null;
  const wecoin = Number((d.userWecoinInfo || {}).balance || 0);

  // 商品目录（从订单里出现的商品来推断）
  let products = [];
  try {
    const j = await live.api("MMFinderPromotionOrderApiSvr/getPromotionOrderList", { req: { page: 1, pageSize: 50 } });
    const list = ((j.data || {}).resp || {}).orderList || [];
    const seen = new Map();
    for (const o of list) {
      for (const m of ((o.feedMaterialList) || [])) {
        const pid = m.productId || (m.finderObject && m.finderObject.productId);
        if (pid && !seen.has(String(pid))) seen.set(String(pid), (m.productName || "").slice(0, 30));
      }
    }
    products = [...seen.entries()].map(([id, name]) => ({ id, name }));
  } catch (e) { /* 商品扫描失败不阻断 */ }

  const excl = ci.excludeUinPackageIds || [];
  live.close();
  return { port: Number(port), accountName, company, admin, wecoin, products, excl };
}

(async () => {
  const ports = String(arg("port", "9444")).split(",").map((s) => s.trim()).filter(Boolean);
  const accounts = [];

  for (const port of ports) {
    process.stdout.write(`探测 ${port} ... `);
    try {
      const p = await probe(port);
      if (!p.accountName) {
        console.log("✗ 未登录（页面可能停在登录页）");
        continue;
      }
      console.log("✓ " + p.accountName);
      console.log(`   公司: ${p.company || "-"} | 管理员: ${p.admin || "-"} | 微信豆: ${p.wecoin}`);
      if (p.products.length) {
        console.log("   商品（前 10）:");
        p.products.slice(0, 10).forEach((x) => console.log(`     ${x.id}  ${x.name}`));
      }
      accounts.push({
        id: "account" + (accounts.length + 1),
        label: p.accountName,
        operator: p.admin || "",
        cdpPort: p.port,
        cashFloor: 3000,
        excludeUinPackageIds: p.excl
      });
    } catch (e) {
      console.log("✗ " + e.message.slice(0, 80));
    }
  }

  if (!accounts.length) {
    console.error("\n没有探测到任何可用账户。请确认：");
    console.error("1. Chrome 已用 --remote-debugging-port 启动");
    console.error("2. 已在该窗口扫码登录");
    console.error("3. 页面停在订单列表");
    process.exit(1);
  }

  fs.mkdirSync(CONFIG_DIR, { recursive: true });
  const rules = {
    version: 1,
    accounts,
    authors: [
      "老罗数字新机遇", "老罗Web4.0风向", "老罗数字财富说", "老罗数字说",
      "老罗数字资产", "老罗数字经济学", "老罗数字商业说", "老罗趋势洞察", "老罗数字新机遇"
    ],
    targeting: { ageRange: [], note: "[] 不限年龄；[2,3,4] = 25-49 岁" },
    videoWindow: { minCreateTime: "2026-07-01T00:00:00+08:00" },
    batch: { maxVideos: 60, maxPlans: 50, allowedBudgets: [300, 600, 800, 1000, 1200, 1300, 1400, 1500, 2000] },
    bidCaps: {
      "成交数": { min: 90, max: 110, hardMax: 130 },
      "成交ROI": { min: 0.6, max: 0.8, recommended: 0.7 },
      "净ROI": { min: 0.6, max: 0.8, recommended: 0.7 },
      "净成交数": { min: 600, max: 700, budgetMultiplier: 2 }
    },
    productTiers: { "10000501804864": "59.9", "10001808219265": "399" },
    billing: { default: "mix" },
    invalidProducts: {},
    errorCodes: {}
  };

  fs.writeFileSync(RULES_PATH, JSON.stringify(rules, null, 2) + "\n", "utf8");
  console.log(`\n✓ 已生成 ${RULES_PATH}`);
  console.log(`  账户数: ${accounts.length}`);
  console.log("\n下一步：");
  console.log("  1. 打开 config/rules.json 确认 label / cashFloor / productTiers");
  console.log("  2. 运行 node scripts/ops/cli.js catalog sync --account=" + accounts[0].id);
})().catch((e) => {
  console.error("setup 失败:", e.message);
  process.exit(1);
});
