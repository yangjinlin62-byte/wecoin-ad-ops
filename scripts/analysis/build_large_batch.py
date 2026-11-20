#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Build a large batch (120 plans) for one account within a cash budget."""
import datetime, json, os, sys, time

import common
from common import tier_from_wording
ROOT = common.ROOT
ACCOUNT = sys.argv[1] if len(sys.argv) > 1 else "account2"
COUNT = int(sys.argv[2]) if len(sys.argv) > 2 else 120
BUDGET_CAP = int(sys.argv[3]) if len(sys.argv) > 3 else 54000
FIXED_BUDGET = int((next((x for x in sys.argv if x.startswith("--budget=")), "--budget=0").split("=")[1]))
EXCLUDE_FILE = (next((x for x in sys.argv if x.startswith("--exclude=")), "--exclude=").split("=", 1)[1])
INVALID_PRODUCTS = common.INVALID_PRODUCTS
ALLOW_SINGLE = "--allow-single-video" in sys.argv
TIER_FILTER = (next((x for x in sys.argv if x.startswith("--tier=")), "--tier=").split("=", 1)[1])

SCORE = os.path.join(ROOT, "data", "analysis", "material_scorecard.json")
CATALOG = os.path.join(ROOT, "data", "catalog2" if ACCOUNT == "account2" else "catalog", "latest.json")
OUT_JSON = os.path.join(ROOT, "data", "analysis", "large_batch_" + ACCOUNT + ".json")
OUT_MD = os.path.join(ROOT, "data", "analysis", "large_batch_" + ACCOUNT + ".md")

TARGET_NAMES = {8: "成交数", 11: "成交ROI", 40: "净ROI", 42: "净成交数"}

def variants(tier):
    if tier == "399":
        return [(40, "roi", 0.8), (42, "wecoin", 500)]
    return [(8, "wecoin", 90), (11, "roi", 0.7)]

def main():
    sc = json.load(open(SCORE, encoding="utf-8"))
    products = {p["productId"]: p for p in sc.get("products", [])}
    exclude = set()
    if EXCLUDE_FILE and os.path.exists(EXCLUDE_FILE):
        for x in json.load(open(EXCLUDE_FILE, encoding="utf-8")):
            if x.get("exportId"):
                exclude.add(x["exportId"])
    cat = json.load(open(CATALOG, encoding="utf-8"))
    by_global = {}
    by_export = {}
    valid_videos = []
    for a in cat.get("accounts", []):
        for v in a.get("videos", []):
            if v.get("globalExportId"):
                by_global[v["globalExportId"]] = v
            if v.get("fullExportId"):
                by_export[v["fullExportId"]] = v
            if v.get("linkStatus") == "valid":
                valid_videos.append(v)

    reg_path = os.path.join(ROOT, "data", "analysis", "product_registry.json")
    reg = json.load(open(reg_path, encoding="utf-8")) if os.path.exists(reg_path) else {"allowedProductIds": [], "products": []}
    allowed = set(reg.get("allowedProductIds") or [])
    reg_products = {p["productId"]: p for p in reg.get("products", [])}
    min_create = int(datetime.datetime(2026, 7, 1, tzinfo=datetime.timezone(datetime.timedelta(hours=8))).timestamp())
    future_from = int(datetime.datetime.fromisoformat(common.RULES["videoWindow"]["futureFrom"]).timestamp())

    sa = []
    scored = set()
    for m in sc.get("materials", []):
        key = m.get("globalExportId") or ""
        if key:
            scored.add(key)
        layer = m.get("layer")
        if layer not in ("S", "A"):
            continue
        catv = by_global.get(key) or by_export.get(m.get("materialId") or "")
        if catv:
            if catv.get("linkStatus") != "valid":
                continue
            export_id = catv.get("fullExportId")
            product_id = catv.get("productId")
            wording = catv.get("productWording")
            author = catv.get("author")
            desc = catv.get("desc")
        else:
            continue
        account_export = (m.get("exportIds") or {}).get(ACCOUNT)
        if account_export:
            export_id = account_export
        if not export_id:
            continue
        if export_id in exclude or (product_id or "") in INVALID_PRODUCTS:
            continue
        if int(catv.get("createTime") or 0) < min_create:
            continue
        if allowed and product_id not in allowed and int(catv.get("createTime") or 0) < future_from:
            continue
        tier = (reg_products.get(product_id) or {}).get("tier") or tier_from_wording(wording)
        p = products.get(product_id or "")
        if not tier and p and p.get("priceTier") in ("59.9", "399"):
            tier = p["priceTier"]
        if not tier:
            tier = tier_from_wording(wording)
        if tier not in ("59.9", "399"):
            continue
        if TIER_FILTER and tier != TIER_FILTER:
            continue
        sa.append({
            "key": key, "layer": layer, "exportId": export_id, "productId": product_id,
            "productWording": wording, "tier": tier, "author": author, "desc": desc,
            "orders": m["orders"], "cost": m["cost"], "pay": m["pay"], "roi": m["roi"],
            "cpa": m["cpa"], "plans": m["plans"], "recent7Orders": m["recent7Orders"],
        })

    n = []
    for v in valid_videos:
        gid = v.get("globalExportId") or ""
        if not gid or gid in scored:
            continue
        pid = v.get("productId") or ""
        if v.get("fullExportId") in exclude or pid in INVALID_PRODUCTS:
            continue
        if int(v.get("createTime") or 0) < min_create:
            continue
        if allowed and pid not in allowed and int(v.get("createTime") or 0) < future_from:
            continue
        tier = (reg_products.get(pid) or {}).get("tier") or tier_from_wording(v.get("productWording"))
        p = products.get(pid)
        if not tier and p and p.get("priceTier") in ("59.9", "399"):
            tier = p["priceTier"]
        if not tier:
            tier = tier_from_wording(v.get("productWording"))
        if tier not in ("59.9", "399"):
            continue
        if TIER_FILTER and tier != TIER_FILTER:
            continue
        n.append({
            "key": gid, "layer": "N", "exportId": v.get("fullExportId"), "productId": v.get("productId"),
            "productWording": v.get("productWording"), "tier": tier, "author": v.get("author"),
            "desc": v.get("desc"), "orders": 0, "cost": 0, "pay": 0, "roi": 0, "cpa": 0,
            "plans": 0, "recent7Orders": 0, "createTime": v.get("createTime", 0),
            "likeCount": v.get("likeCount", 0), "forwardCount": v.get("forwardCount", 0),
        })
    n.sort(key=lambda x: (x.get("createTime", 0), x.get("likeCount", 0)), reverse=True)

    rows = []
    def add(material, spec, budget):
        target, kind, value = spec
        rows.append({
            "account": ACCOUNT,
            "layer": material["layer"],
            "exportId": material["exportId"],
            "productId": material.get("productId"),
            "productWording": material.get("productWording"),
            "tier": material["tier"],
            "author": material.get("author"),
            "desc": material.get("desc"),
            "target": target,
            "targetName": TARGET_NAMES[target],
            "bidKind": kind,
            "bidValue": value,
            "budgetYuan": FIXED_BUDGET or budget,
            "history": {
                "orders": material.get("orders", 0),
                "cost": material.get("cost", 0),
                "pay": material.get("pay", 0),
                "roi": material.get("roi", 0),
                "cpa": material.get("cpa", 0),
                "plans": material.get("plans", 0),
                "recent7Orders": material.get("recent7Orders", 0),
            },
        })

    # 1) 30 个 S/A 素材 × 2 个目标 = 60 条，600 元
    used_sa = 0
    for m in sa:
        if used_sa >= 30:
            break
        vs = variants(m["tier"])
        for spec in vs[:2]:
            add(m, spec, 600)
        used_sa += 1
    # 2) 10 个 S/A 素材 × 1 个目标 = 10 条，300 元
    alt = 0
    for m in sa[used_sa:]:
        if alt >= 10:
            break
        add(m, variants(m["tier"])[0], 300)
        alt += 1
    # 3) N 素材补到 120 条，300 元
    ni = 0
    while len(rows) < COUNT and ni < len(n):
        m = n[ni]
        ni += 1
        add(m, variants(m["tier"])[0], 300)

    # 如果还不够，用 S/A 继续补 300
    si = used_sa + alt
    while len(rows) < COUNT and si < len(sa):
        m = sa[si]
        si += 1
        add(m, variants(m["tier"])[0], 300)

    rows = rows[:COUNT]
    if rows and not ALLOW_SINGLE:
        raise SystemExit("默认拒绝单视频批次；如确需灰度，加 --allow-single-video")
    total_budget = sum(r["budgetYuan"] for r in rows)
    if total_budget > BUDGET_CAP:
        raise SystemExit("budget over cap: %s > %s" % (total_budget, BUDGET_CAP))

    batches = [rows[i:i + 50] for i in range(0, len(rows), 50)]
    out = {
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "account": ACCOUNT,
        "count": len(rows),
        "budgetCap": BUDGET_CAP,
        "totalBudget": total_budget,
        "layers": {k: sum(1 for r in rows if r["layer"] == k) for k in ("S", "A", "N")},
        "batches": [{"index": i + 1, "count": len(b), "budget": sum(r["budgetYuan"] for r in b), "plans": b} for i, b in enumerate(batches)],
        "plans": rows,
    }
    json.dump(out, open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    lines = ["# 账户 %s：%d 条计划" % (ACCOUNT, len(rows)), ""]
    lines.append("- 预算上限：%s 元" % BUDGET_CAP)
    lines.append("- 实际预算：%s 元" % total_budget)
    lines.append("- 分层：S %s / A %s / N %s" % (out["layers"]["S"], out["layers"]["A"], out["layers"]["N"]))
    lines.append("")
    lines.append("| 批次 | 条数 | 预算 |")
    lines.append("|---|---:|---:|")
    for b in out["batches"]:
        lines.append("| %s | %s | %s |" % (b["index"], b["count"], b["budget"]))
    lines.append("")
    lines.append("| # | 层 | 素材 | 商品层 | 目标 | 出价 | 预算 | 历史订单 | ROI |")
    lines.append("|---:|---|---|---|---|---:|---:|---:|---:|")
    for i, r in enumerate(rows[:40], 1):
        bid = ("ROI " + str(r["bidValue"])) if r["bidKind"] == "roi" else (str(r["bidValue"]) + " 元")
        lines.append("| %d | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            i, r["layer"], (r["desc"] or r["exportId"])[:22], r["tier"], r["targetName"], bid,
            r["budgetYuan"], r["history"]["orders"], r["history"]["roi"]))
    lines.append("")
    lines.append("（只展示前 40 条，完整清单见 JSON）")
    open(OUT_MD, "w", encoding="utf-8").write("\n".join(lines))
    print(OUT_JSON)
    print(OUT_MD)
    print("count", len(rows), "budget", total_budget, "layers", out["layers"], "batches", [(b["count"], b["budget"]) for b in out["batches"]])

if __name__ == "__main__":
    main()
