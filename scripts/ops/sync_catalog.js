"use strict";

const fs = require("fs");
const path = require("path");
const { Live } = require("../lib/live");
const rules = require("../lib/rules");
const { pageCursor, compare } = require("../lib/catalog_changes");

const ROOT = path.join(__dirname, "..", "..");
const PORT = Number(process.argv[2] || 9444);
const OUT_NAME = process.argv[3] || "catalog";
const OUT_DIR = path.join(ROOT, "data", OUT_NAME);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function parseRealAppId(p) {
  try {
    const q = String(p || "").split("?")[1] || "";
    return new URLSearchParams(q).get("realappid") || "";
  } catch (_) {
    return "";
  }
}

(async () => {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const live = new Live(PORT, "catalog-" + PORT);
  await live.connect();

  const authorResp = await live.api("MmFinderPromotionApiSvr/getTargetAuthor", {
    promotionOrderType: 2,
    baseReq: { featureFlag: 26 },
  });
  const accounts = (((authorResp.data || {}).accountInfos) || []).map((a) => ({
    username: a.username,
    nickName: a.nickName,
    headImgUrl: a.headImgUrl,
  }));
  console.log("authors", accounts.length);
  for (const a of accounts) console.log(" -", a.nickName, a.username);

  const wanted = new Set(rules.getAuthors().map((a) => a.username));
  const selected = accounts.filter((a) => wanted.has(a.username));
  if (selected.length !== 9) {
    throw new Error("规则要求 9 个作者，getTargetAuthor 只匹配到 " + selected.length + " 个；检查 rules.authors");
  }
  console.log("selected", selected.length);

  const result = {
    syncedAt: new Date().toISOString(),
    sourcePort: PORT,
    accounts: [],
    summary: {},
  };

  for (const acct of selected) {
    let lastBuf = null;
    let page = 0;
    const videos = [];
    const cursors = new Set();
    while (page < 60) {
      page += 1;
      const body = { encryptedUsername: acct.username, limit: 20, flag: 0 };
      if (lastBuf) body.lastBuf = lastBuf;
      const j = await live.api("MmFinderPromotionApiSvr/getFinderObject", body);
      const d = j.data;
      const nextCursor = pageCursor(d, cursors, page);
      for (const o of d.objects || []) {
        const f = o.finderObject || o;
        const sj = f.shoppingcartJumpinfo || {};
        const productId = sj.productId || "";
        const realappid = parseRealAppId(sj.path);
        let linkStatus = "valid";
        if (!productId) linkStatus = "no_link";
        else if (rules.isInvalidProduct(productId)) linkStatus = "invalid";
        videos.push({
          exportId: (f.exportId || "").split("/").pop(),
          fullExportId: f.exportId || "",
          globalExportId: f.globalExportId || "",
          author: acct.nickName,
          username: acct.username,
          desc: (f.description || "").slice(0, 200),
          // 目录接口其实带封面（wxapp.tc.qq.com），之前没存；看板要用
          cover: f.coverUrl || "",
          createTime: f.createTime || 0,
          likeCount: f.likeCount || 0,
          commentCount: f.commentCount || 0,
          forwardCount: f.forwardCount || 0,
          favCount: f.favCount || 0,
          hasCart: !!(f.flag || {}).hasShoppingCart,
          isPrivate: !!(f.flag || {}).isPrivate,
          isChecking: !!(f.flag || {}).isChecking,
          isPromoting: !!(f.flag || {}).isPromoting,
          productId,
          productWording: sj.wording || "",
          realappid,
          linkStatus,
        });
      }
      lastBuf = nextCursor;
      if (!lastBuf) break;
      await sleep(250);
    }

    const counts = { total: videos.length, valid: 0, invalid: 0, no_link: 0 };
    for (const v of videos) counts[v.linkStatus] += 1;
    result.accounts.push({ ...acct, pages: page, counts, videos });
    result.summary[acct.nickName] = counts;
    console.log(acct.nickName, "videos", videos.length, "valid", counts.valid, "invalid", counts.invalid, "no_link", counts.no_link);
    await sleep(400);
  }

  const ts = new Date().toISOString().replace(/[:.]/g, "-");
  const file = path.join(OUT_DIR, "catalog-" + ts + ".json");
  const latest = path.join(OUT_DIR, "latest.json");
  const previous = fs.existsSync(latest) ? JSON.parse(fs.readFileSync(latest, "utf8")) : null;
  result.catalogChanges = compare(previous, result);
  result.workSummary = require("../lib/work_evidence").dailyWorks(result, result.catalogChanges, rules.requireAccount(PORT).id);
  const serialized = JSON.stringify(result, null, 1);
  fs.writeFileSync(file, serialized, { encoding: "utf8", flag: "wx" });
  const temporary = latest + "." + process.pid + ".tmp";
  fs.writeFileSync(temporary, serialized, "utf8");
  fs.renameSync(temporary, latest);
  console.log("saved", file);
  live.close();
})().catch((e) => {
  console.error("FAILED", e && e.stack ? e.stack : e);
  process.exit(1);
});
