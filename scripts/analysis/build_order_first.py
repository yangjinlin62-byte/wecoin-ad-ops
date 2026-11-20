# -*- coding: utf-8 -*-
"""Build order-first plans from the best historical 59.9 and 399 bundles."""
import collections
import datetime
import json
import os

import common

ROOT = common.ROOT
SCORE = json.load(open(os.path.join(ROOT, "data", "analysis", "material_scorecard.json"), encoding="utf-8"))
TIERS = {p["productId"]: p.get("priceTier") for p in SCORE.get("products", [])}
ROWS = []
for name in ("history", "history2"):
    path = os.path.join(ROOT, "data", name, "materials.jsonl")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            if line.strip():
                ROWS.append(json.loads(line))


def bundle_key(row):
    return tuple(sorted(m.get("globalExportId") or m.get("exportId") for m in row.get("materials", []) if (m.get("globalExportId") or m.get("exportId"))))


bundles = collections.defaultdict(lambda: {"plans": 0, "spend": 0, "pay": 0, "orders": 0, "videos": 0, "pids": set()})
for row in ROWS:
    key = bundle_key(row)
    if not key:
        continue
    d = bundles[key]
    d["plans"] += 1
    d["spend"] += sum(m.get("cost", 0) for m in row["materials"])
    d["pay"] += sum(m.get("payGmv", 0) for m in row["materials"])
    d["orders"] += sum(m.get("payPv", 0) for m in row["materials"])
    d["videos"] = len(key)
    for m in row["materials"]:
        if m.get("productId"):
            d["pids"].add(m["productId"])


def best_bundle(tier, min_videos, max_videos):
    candidates = []
    for key, d in bundles.items():
        tiers = {TIERS.get(pid) for pid in d["pids"]}
        if tiers == {tier} and min_videos <= d["videos"] <= max_videos and d["orders"] > 0:
            candidates.append((key, d))
    candidates.sort(key=lambda kv: (-kv[1]["orders"], -kv[1]["pay"]))
    return candidates[0]


BUNDLE_599, RAW_599 = best_bundle("59.9", 6, 12)
BUNDLE_399, RAW_399 = best_bundle("399", 5, 20)
STATS_599 = {k: RAW_599[k] for k in ("plans", "spend", "pay", "orders", "videos")}
STATS_399 = {k: RAW_399[k] for k in ("plans", "spend", "pay", "orders", "videos")}


def build(account_id):
    cat = json.load(open(os.path.join(ROOT, "data", "catalog2" if account_id == "account2" else "catalog", "latest.json"), encoding="utf-8"))
    by = {v["globalExportId"]: v for a in cat.get("accounts", []) for v in a.get("videos", [])}
    def ids_for(bundle):
        return [by[g]["fullExportId"] for g in bundle if g in by and by[g].get("linkStatus") == "valid"]
    a_ids = ids_for(BUNDLE_599)
    c_ids = ids_for(BUNDLE_399)
    if len(a_ids) < 6 or len(c_ids) < 5:
        raise SystemExit("bundle 有效视频不足: 59.9=%s 399=%s" % (len(a_ids), len(c_ids)))
    counts = {"A": 6, "B": 2, "C": 2} if account_id == "account2" else {"A": 4, "B": 2, "C": 2}
    plans = []
    for i in range(counts["A"]):
        plans.append({"account": account_id, "layer": "ORDER_FIRST", "group": "A", "tier": "59.9", "exportIds": a_ids, "target": 8, "targetName": "成交数", "bidKind": "wecoin", "bidValue": 90, "budgetYuan": 1000, "bundleStats": STATS_599})
    for i in range(counts["B"]):
        plans.append({"account": account_id, "layer": "ORDER_FIRST", "group": "B", "tier": "59.9", "exportIds": a_ids, "target": 11, "targetName": "成交ROI", "bidKind": "roi", "bidValue": 0.7, "budgetYuan": 1000, "bundleStats": STATS_599})
    for i in range(counts["C"]):
        plans.append({"account": account_id, "layer": "ORDER_FIRST", "group": "C", "tier": "399", "exportIds": c_ids, "target": 40, "targetName": "净ROI", "bidKind": "roi", "bidValue": 0.8, "budgetYuan": 600, "bundleStats": STATS_399})
    out = {"account": account_id, "generatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(), "count": len(plans), "totalBudget": sum(p["budgetYuan"] for p in plans), "plans": plans}
    path = os.path.join(ROOT, "data", "analysis", "order_first_" + account_id + ".json")
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(path, "plans", len(plans), "budget", out["totalBudget"], "59.9 videos", len(a_ids), "399 videos", len(c_ids))


if __name__ == "__main__":
    import sys
    build(sys.argv[1] if len(sys.argv) > 1 else "account2")
