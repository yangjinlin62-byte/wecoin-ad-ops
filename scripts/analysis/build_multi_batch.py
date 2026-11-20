#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Build 15 multi-video plans per account (5-video 399, 4-video 59.9)."""
import datetime, json, os, sys, time

import common
ROOT = common.ROOT
ACCOUNT = sys.argv[1] if len(sys.argv) > 1 else "account1"
COUNT = int(sys.argv[2]) if len(sys.argv) > 2 else 15
SCORE = os.path.join(ROOT, "data", "analysis", "material_scorecard.json")
CATALOG = os.path.join(ROOT, "data", "catalog2" if ACCOUNT == "account2" else "catalog", "latest.json")
OUT = os.path.join(ROOT, "data", "analysis", "multi_batch_" + ACCOUNT + ".json")

INVALID = common.INVALID_PRODUCTS
TARGET_NAMES = {8:"成交数",11:"成交ROI",40:"净ROI",42:"净成交数"}

def main():
    sc = json.load(open(SCORE, encoding="utf-8"))
    prods = {p["productId"]: p for p in sc.get("products", [])}
    cat = json.load(open(CATALOG, encoding="utf-8"))
    by = {v["globalExportId"]: v for a in cat.get("accounts", []) for v in a.get("videos", [])}
    reg_path = os.path.join(ROOT, "data", "analysis", "product_registry.json")
    reg = json.load(open(reg_path, encoding="utf-8")) if os.path.exists(reg_path) else {"allowedProductIds": [], "products": []}
    allowed = set(reg.get("allowedProductIds") or [])
    reg_products = {p["productId"]: p for p in reg.get("products", [])}
    min_create = int(datetime.datetime(2026, 7, 1, tzinfo=datetime.timezone(datetime.timedelta(hours=8))).timestamp())
    future_from = int(datetime.datetime.fromisoformat(common.RULES["videoWindow"]["futureFrom"]).timestamp())
    pools = {"59.9": [], "399": []}
    holds = common.work_holds(ACCOUNT)
    for m in sc.get("materials", []):
        if m.get("layer") not in ("S", "A"):
            continue
        v = by.get(m.get("globalExportId"))
        if v and (v.get("globalExportId") in holds or v.get("fullExportId") in holds):
            continue
        if not v or v.get("linkStatus") != "valid":
            continue
        pid = v.get("productId") or ""
        if pid in INVALID:
            continue
        created = int(v.get("createTime") or 0)
        if created < min_create:
            continue
        if created < future_from and allowed and pid not in allowed:
            continue
        p = prods.get(pid)
        tier = (reg_products.get(pid) or {}).get("tier") or (p.get("priceTier") if p else None) or common.tier_from_wording(v.get("productWording"))
        if tier not in ("59.9", "399"):
            continue
        eid = (m.get("exportIds") or {}).get(ACCOUNT) or v.get("fullExportId")
        if not eid:
            continue
        pools[tier].append({
            "exportId": eid, "productId": pid, "productWording": v.get("productWording"),
            "author": v.get("author"), "desc": v.get("desc"), "tier": tier,
            "orders": m.get("orders", 0), "cost": m.get("cost", 0), "pay": m.get("pay", 0),
            "roi": m.get("roi", 0), "cpa": m.get("cpa", 0), "plans": m.get("plans", 0),
        })
    for t in pools:
        pools[t].sort(key=lambda x: (-x["orders"], -x["roi"]))

    plans = []
    def add_bundle(bundle, tier, target, kind, value, budget, idx):
        plans.append({
            "account": ACCOUNT,
            "layer": "MULTI",
            "tier": tier,
            "exportIds": [x["exportId"] for x in bundle],
            "materials": bundle,
            "target": target,
            "targetName": TARGET_NAMES[target],
            "bidKind": kind,
            "bidValue": value,
            "budgetYuan": budget,
            "history": {
                "orders": sum(x["orders"] for x in bundle),
                "cost": round(sum(x["cost"] for x in bundle), 2),
                "pay": round(sum(x["pay"] for x in bundle), 2),
                "roi": round(sum(x["pay"] for x in bundle) / sum(x["cost"] for x in bundle), 3) if sum(x["cost"] for x in bundle) else 0,
            },
        })

    # 399: 2 plans x 5 videos, 600 each
    b399 = pools["399"][:10]
    for i in range(min(2, len(b399) // 5)):
        bundle = b399[i * 5:(i + 1) * 5]
        if i == 0:
            add_bundle(bundle, "399", 40, "roi", 0.8, 600, i)
        else:
            add_bundle(bundle, "399", 42, "wecoin", 500, 600, i)
    # 59.9: fill remaining, 4 videos each, 300
    b599 = pools["59.9"]
    idx = 0
    while len(plans) < COUNT and idx * 4 + 4 <= len(b599):
        bundle = b599[idx * 4:(idx + 1) * 4]
        if idx % 2 == 0:
            add_bundle(bundle, "59.9", 8, "wecoin", 90, 300, idx)
        else:
            add_bundle(bundle, "59.9", 11, "roi", 0.7, 300, idx)
        idx += 1

    plans = plans[:COUNT]
    out = {
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "account": ACCOUNT,
        "count": len(plans),
        "totalBudget": sum(p["budgetYuan"] for p in plans),
        "plans": plans,
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(OUT)
    print("count", len(plans), "budget", out["totalBudget"], "tiers", {t: sum(1 for p in plans if p["tier"] == t) for t in ("399", "59.9")})
    print("videos", sum(len(p["exportIds"]) for p in plans), "unique", len(set(x for p in plans for x in p["exportIds"])))
    for p in plans[:5]:
        print(p["tier"], p["targetName"], p["bidValue"], p["budgetYuan"], "videos", len(p["exportIds"]), p["history"])

if __name__ == "__main__":
    main()
