# -*- coding: utf-8 -*-
"""Build recovery plans: fresh bundles, target 11, prebilling."""
import collections
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


def key_of(row):
    return tuple(sorted(m.get("globalExportId") or m.get("exportId") for m in row.get("materials", []) if (m.get("globalExportId") or m.get("exportId"))))


bundles = collections.defaultdict(lambda: {"orders": 0, "pay": 0, "videos": 0, "pids": set()})
for row in ROWS:
    key = key_of(row)
    if not key:
        continue
    d = bundles[key]
    d["orders"] += sum(m.get("payPv", 0) for m in row["materials"])
    d["pay"] += sum(m.get("payGmv", 0) for m in row["materials"])
    d["videos"] = len(key)
    for m in row["materials"]:
        if m.get("productId"):
            d["pids"].add(m["productId"])

# fresh 59.9 bundles, exclude the 10-video bundle already overused
candidates = []
for key, d in bundles.items():
    if {TIERS.get(p) for p in d["pids"]} != {"59.9"}:
        continue
    if not (20 <= d["videos"] <= 30):
        continue
    candidates.append((key, d))
candidates.sort(key=lambda kv: (-kv[1]["orders"], -kv[1]["pay"]))
FRESH = candidates[:2]
if len(FRESH) < 2:
    raise SystemExit("fresh bundle不足")


def build(account_id):
    cat = json.load(open(os.path.join(ROOT, "data", "catalog2" if account_id == "account2" else "catalog", "latest.json"), encoding="utf-8"))
    by = {v["globalExportId"]: v for a in cat.get("accounts", []) for v in a.get("videos", [])}
    def ids(key):
        return common.original_bundle_ids(by, key, holds)
    holds = common.work_holds(account_id)
    plans = []
    if account_id == "account2":
        for i in range(5):
            plans.append({"account": account_id, "layer": "RECOVERY", "tier": "59.9", "exportIds": ids(FRESH[0][0]), "target": 11, "targetName": "成交ROI", "bidKind": "roi", "bidValue": 0.7, "budgetYuan": 1000, "billingMethod": 0})
        for i in range(5):
            plans.append({"account": account_id, "layer": "RECOVERY", "tier": "59.9", "exportIds": ids(FRESH[1][0]), "target": 11, "targetName": "成交ROI", "bidKind": "roi", "bidValue": 0.7, "budgetYuan": 1000, "billingMethod": 0})
    else:
        plans.append({"account": account_id, "layer": "RECOVERY", "tier": "59.9", "exportIds": ids(FRESH[0][0]), "target": 11, "targetName": "成交ROI", "bidKind": "roi", "bidValue": 0.7, "budgetYuan": 600, "billingMethod": 0})
    plans = [p for p in plans if p["exportIds"]]
    common.attach_bindings(plans, by)
    out = {"account": account_id, "count": len(plans), "totalBudget": sum(p["budgetYuan"] for p in plans), "plans": plans,
           "unavailableBundles": [list(k) for k, _ in FRESH if not ids(k)]}
    path = os.path.join(ROOT, "data", "analysis", "recovery_" + account_id + ".json")
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(path, "count", len(plans), "budget", out["totalBudget"], "videos", [len(p["exportIds"]) for p in plans])


if __name__ == "__main__":
    import sys
    build(sys.argv[1] if len(sys.argv) > 1 else "account2")
