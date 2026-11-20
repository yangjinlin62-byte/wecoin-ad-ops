# -*- coding: utf-8 -*-
"""Rebuild plans from yesterday's actual order-producing videos."""
import json
import os
import sys

import common

ROOT = common.ROOT
ACCOUNT = sys.argv[1] if len(sys.argv) > 1 else "account2"
SUFFIXES = ["6nQaTI4upw", "NFSIsaRyxNg", "L2uXCtNKyGuk", "LyuMCVGNQrdk", "h_yple3r_w", "JemDCc3ED2Ak"]
CAT = json.load(open(os.path.join(ROOT, "data", "catalog2" if ACCOUNT == "account2" else "catalog", "latest.json"), encoding="utf-8"))
BY = {v["globalExportId"]: v for a in CAT.get("accounts", []) for v in a.get("videos", [])}
ids = []
for s in SUFFIXES:
    for g, v in BY.items():
        if g.endswith(s) and v.get("linkStatus") == "valid":
            ids.append(v["fullExportId"])
            break
ids = list(dict.fromkeys(ids))
if len(ids) < 3:
    raise SystemExit("winner videos missing")

plans = []
for target in (8, 11, 40, 42):
    plans.append({
        "account": ACCOUNT, "layer": "WINNER_REBUILD", "tier": "59.9",
        "exportIds": ids, "target": target,
        "targetName": {8: "成交数", 11: "成交ROI", 40: "净ROI", 42: "净成交数"}[target],
        "bidKind": "roi" if target in (11, 40) else "wecoin",
        "bidValue": 0.7 if target == 11 else (0.8 if target == 40 else 90),
        "budgetYuan": 600, "billingMethod": 1 if ACCOUNT == "account1" else 0
    })
out = {"account": ACCOUNT, "count": len(plans), "totalBudget": sum(p["budgetYuan"] for p in plans), "plans": plans}
path = os.path.join(ROOT, "data", "analysis", "winner_rebuild_" + ACCOUNT + ".json")
json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(path, "count", len(plans), "videos", len(ids), "billing", plans[0]["billingMethod"], "missing", [x for x in SUFFIXES if not any(x in i for i in ids)])
