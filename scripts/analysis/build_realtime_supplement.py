# -*- coding: utf-8 -*-
"""Build a real-time-billing supplement for account 1 from proven winners."""
import json
import os
import sys

import common

ROOT = common.ROOT
ACCOUNT = sys.argv[1] if len(sys.argv) > 1 else "account1"
CAT = json.load(open(os.path.join(ROOT, "data", "catalog2" if ACCOUNT == "account2" else "catalog", "latest.json"), encoding="utf-8"))
REG = json.load(open(os.path.join(ROOT, "data", "analysis", "product_registry.json"), encoding="utf-8"))
P399 = {p["productId"] for p in REG.get("products", []) if p.get("tier") == "399" and p.get("allowed")}
BY = {v["globalExportId"]: v for a in CAT.get("accounts", []) for v in a.get("videos", [])}


def ids_by_suffix(suffixes):
    out = []
    for g, v in BY.items():
        if v.get("linkStatus") == "valid" and any(g.endswith(s) for s in suffixes):
            out.append(v["fullExportId"])
    return list(dict.fromkeys(out))


w599 = ids_by_suffix(["6nQaTI4upw", "B0GHUtNtFQ", "w_zXTDfBwQ", "h_yple3r_w"])
w399 = [v["fullExportId"] for g, v in BY.items() if v.get("linkStatus") == "valid" and v.get("productId") in P399]
w399 = list(dict.fromkeys(w399))[:11]
if len(w599) < 3 or len(w399) < 5:
    raise SystemExit("winner videos missing")

plans = []
def add(tier, target, export_ids):
    plans.append({
        "account": ACCOUNT, "layer": "REALTIME_SUPPLEMENT", "tier": tier,
        "exportIds": export_ids, "target": target,
        "targetName": {8: "成交数", 11: "成交ROI", 40: "净ROI", 42: "净成交数"}[target],
        "bidKind": "roi" if target in (11, 40) else "wecoin",
        "bidValue": 0.7 if target == 11 else (0.8 if target == 40 else 90),
        "budgetYuan": 600, "billingMethod": 1, "pricingMethod": 1
    })

for t in (8, 11, 40, 42):
    add("59.9", t, w599)
for t in (8, 11, 40, 42):
    add("399", t, w399)

out = {"account": ACCOUNT, "count": len(plans), "totalBudget": sum(p["budgetYuan"] for p in plans), "plans": plans}
path = os.path.join(ROOT, "data", "analysis", "realtime_supplement_" + ACCOUNT + ".json")
json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(path, "count", len(plans), "budget", out["totalBudget"], "599", len(w599), "399", len(w399))
