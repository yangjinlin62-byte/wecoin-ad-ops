# -*- coding: utf-8 -*-
"""Build a low-budget boost (NoBid) rescue batch for one account."""
import json
import os
import sys

import common

ROOT = common.ROOT
ACCOUNT = sys.argv[1] if len(sys.argv) > 1 else "account2"
CAT = json.load(open(os.path.join(ROOT, "data", "catalog2" if ACCOUNT == "account2" else "catalog", "latest.json"), encoding="utf-8"))
REG = json.load(open(os.path.join(ROOT, "data", "analysis", "product_registry.json"), encoding="utf-8"))
P399 = {p["productId"] for p in REG.get("products", []) if p.get("tier") == "399" and p.get("allowed")}
BY = {v["globalExportId"]: v for a in CAT.get("accounts", []) for v in a.get("videos", [])}


def ids_by_suffix(suffixes):
    out = []
    for g, v in BY.items():
        if v.get("linkStatus") != "valid":
            continue
        if any(g.endswith(s) for s in suffixes):
            out.append(v["fullExportId"])
    return list(dict.fromkeys(out))


def ids_prefix(prefix):
    return [v["fullExportId"] for g, v in BY.items() if v.get("linkStatus") == "valid" and g.startswith(prefix)]


w599 = ids_by_suffix(["6nQaTI4upw", "B0GHUtNtFQ", "w_zXTDfBwQ", "h_yple3r_w"])
# historical 399 winner bundle: use valid 399 videos from the known winner prefix set
w399 = [v["fullExportId"] for g, v in BY.items() if v.get("linkStatus") == "valid" and v.get("productId") in P399]
w399 = list(dict.fromkeys(w399))[:11]
if len(w599) < 3:
    raise SystemExit("59.9 winner videos missing")
if len(w399) < 5:
    raise SystemExit("399 winner videos missing")

plans = []
def add(tier, target, budget, export_ids):
    plans.append({
        "account": ACCOUNT, "layer": "BOOST", "mode": "boost", "tier": tier,
        "exportIds": export_ids, "target": target,
        "targetName": {8: "成交数", 11: "成交ROI", 40: "净ROI", 42: "净成交数"}[target],
        "bidKind": "none", "bidValue": 0, "budgetYuan": budget,
        "billingMethod": 0, "pricingMethod": 0
    })

# 成交/净成交 100；ROI/净ROI 300
add("59.9", 8, 100, w599)
add("59.9", 42, 100, w599)
add("59.9", 11, 300, w599)
add("59.9", 40, 300, w599)
add("399", 8, 100, w399)
add("399", 42, 100, w399)
add("399", 11, 300, w399)
add("399", 40, 300, w399)

out = {"account": ACCOUNT, "count": len(plans), "totalBudget": sum(p["budgetYuan"] for p in plans), "plans": plans}
path = os.path.join(ROOT, "data", "analysis", "boost_" + ACCOUNT + ".json")
json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(path, "count", len(plans), "budget", out["totalBudget"], "599", len(w599), "399", len(w399))
