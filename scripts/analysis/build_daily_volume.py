# -*- coding: utf-8 -*-
"""Daily volume batch: 59.9 four targets + 399 bid ladder, 50 plans/account."""
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


def pick(tier, lo, hi, n):
    out = []
    for key, d in bundles.items():
        if {TIERS.get(p) for p in d["pids"]} == {tier} and lo <= d["videos"] <= hi and d["orders"] > 0:
            out.append((key, d))
    out.sort(key=lambda kv: (-kv[1]["orders"], -kv[1]["pay"]))
    return out[:n]


B599 = pick("59.9", 20, 50, 4)
B399 = pick("399", 5, 20, 1)
if len(B599) < 4 or not B399:
    raise SystemExit("bundle不足")


def build(account_id):
    cat = json.load(open(os.path.join(ROOT, "data", "catalog2" if account_id == "account2" else "catalog", "latest.json"), encoding="utf-8"))
    by = {v["globalExportId"]: v for a in cat.get("accounts", []) for v in a.get("videos", [])}
    def ids(key):
        return common.original_bundle_ids(by, key, holds)
    holds = common.work_holds(account_id)
    a_ids = [ids(k) for k, _ in B599]
    c_ids = ids(B399[0][0])
    plans = []
    def add(tier, group, export_ids, target, kind, value, budget):
        if not export_ids:
            return
        plans.append({
            "account": account_id, "layer": "DAILY_VOLUME", "group": group, "tier": tier,
            "exportIds": export_ids, "target": target,
            "targetName": {8: "成交数", 11: "成交ROI", 40: "净ROI", 42: "净成交数"}[target],
            "bidKind": kind, "bidValue": value, "budgetYuan": budget, "billingMethod": 0
        })
    # 59.9: 16 target 11, 12 target 8, 6 target 42, 6 target 40
    for i in range(16):
        add("59.9", "W11", a_ids[i % 4], 11, "roi", 0.7, 1000)
    for i in range(12):
        add("59.9", "W8", a_ids[i % 4], 8, "wecoin", 90, 1000)
    for i in range(6):
        add("59.9", "W42", a_ids[i % 4], 42, "wecoin", 90, 1000)
    for i in range(6):
        add("59.9", "W40", a_ids[i % 4], 40, "roi", 0.8, 600)
    # 399: bid ladder, target 42
    for _ in range(4):
        add("399", "B600", c_ids, 42, "wecoin", 600, 1200)
    for _ in range(3):
        add("399", "B650", c_ids, 42, "wecoin", 650, 1300)
    for _ in range(2):
        add("399", "B700", c_ids, 42, "wecoin", 700, 1400)
    add("399", "B40", c_ids, 40, "roi", 0.8, 600)
    common.attach_bindings(plans, by)
    out = {"account": account_id, "count": len(plans), "totalBudget": sum(p["budgetYuan"] for p in plans), "plans": plans,
           "unavailableBundles": [list(k) for k, _ in B599+B399 if not ids(k)]}
    path = os.path.join(ROOT, "data", "analysis", "daily_volume_" + account_id + ".json")
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(path, "count", len(plans), "budget", out["totalBudget"], "bundle videos", [len(x) for x in a_ids])


if __name__ == "__main__":
    import sys
    build(sys.argv[1] if len(sys.argv) > 1 else "account2")
