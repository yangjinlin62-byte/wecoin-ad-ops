# -*- coding: utf-8 -*-
"""Build a checkpoint batch: 59.9 ladder + 399 low-spend product tests."""
import argparse
import collections
import json
import os

import common

ROOT = common.ROOT
RULES = common.RULES
SCORE = json.load(open(os.path.join(ROOT, "data", "analysis", "material_scorecard.json"), encoding="utf-8"))
TIERS = {p["productId"]: p.get("priceTier") for p in SCORE.get("products", [])}
REG = json.load(open(os.path.join(ROOT, "data", "analysis", "product_registry.json"), encoding="utf-8"))
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


B599 = pick("59.9", 15, 50, 4)
B399 = pick("399", 5, 20, 1)
if len(B599) < 2 or not B399:
    raise SystemExit("historical bundle不足")


def build(account_id, stage, cash):
    cat = json.load(open(os.path.join(ROOT, "data", "catalog2" if account_id == "account2" else "catalog", "latest.json"), encoding="utf-8"))
    by = {v["globalExportId"]: v for a in cat.get("accounts", []) for v in a.get("videos", [])}
    def ids(key):
        return common.original_bundle_ids(by, key, holds)
    holds = common.work_holds(account_id)
    a_ids = [ids(k) for k, _ in B599]
    c_ids = ids(B399[0][0])

    low_links = [p for p in REG["products"] if p.get("tier") == "399" and p.get("allowed") and float(p.get("costYuan") or 0) < 150]
    low_links.sort(key=lambda p: float(p.get("costYuan") or 0))
    link_videos = {}
    for p in low_links:
        vals = [v["fullExportId"] for a in cat.get("accounts", []) for v in a.get("videos", [])
                if v.get("productId") == p["productId"] and v.get("linkStatus") == "valid"
                and v.get("globalExportId") not in holds and v.get("fullExportId") not in holds
                and int(v.get("createTime", 0)) >= 1782864000]
        if vals:
            link_videos[p["productId"]] = vals
    low_links = [p for p in low_links if p["productId"] in link_videos]

    cfg = RULES["checkpoint"]["stages"][stage][account_id]
    w_count = int(cfg["w599"])
    p_count = int(cfg["p399"])
    floor = float(RULES["checkpoint"]["floorYuan"][account_id])
    budget_cap = max(0, cash - floor)

    # 59.9 target mix: 11 50%, 8 25%, 42 15%, 40 rest
    n11 = max(1, round(w_count * 0.5))
    n8 = max(1, round(w_count * 0.25))
    n42 = max(1, round(w_count * 0.15)) if w_count >= 6 else 0
    n40 = w_count - n11 - n8 - n42
    ladder11 = [0.70, 0.71, 0.72]
    ladder8 = [90, 91, 92]
    ladder42 = [90, 91, 92]
    ladder40 = [0.78, 0.80]
    budget599 = 1000 if account_id == "account2" else 600
    plans = []
    def add(tier, group, export_ids, target, kind, value, budget):
        if not export_ids:
            return
        plans.append({"account": account_id, "layer": "CHECKPOINT", "stage": stage, "group": group, "tier": tier,
                      "exportIds": export_ids, "target": target,
                      "targetName": {8: "成交数", 11: "成交ROI", 40: "净ROI", 42: "净成交数"}[target],
                      "bidKind": kind, "bidValue": value, "budgetYuan": budget, "billingMethod": 0})
    for i in range(n11):
        add("59.9", "L11", a_ids[i % len(a_ids)], 11, "roi", ladder11[i % 3], budget599)
    for i in range(n8):
        add("59.9", "L8", a_ids[i % len(a_ids)], 8, "wecoin", ladder8[i % 3], budget599)
    for i in range(n42):
        add("59.9", "L42", a_ids[i % len(a_ids)], 42, "wecoin", ladder42[i % 3], budget599)
    for i in range(n40):
        add("59.9", "L40", a_ids[i % len(a_ids)], 40, "roi", ladder40[i % 2], 600)

    # 399 low-spend links: alternate new-only / mix with 399 winner
    for i in range(p_count if low_links else 0):
        link = low_links[i % len(low_links)]
        vids = link_videos[link["productId"]][:5]
        mixed = (i % 2 == 1)
        export_ids = list(vids)
        if mixed or len(export_ids) < 2:
            export_ids += c_ids[: max(2, 8 - len(export_ids))]
            export_ids = list(dict.fromkeys(export_ids))[:10]
        if len(export_ids) < 2:
            continue
        group = "P399_MIX" if mixed else "P399_NEW"
        bid = [600, 650, 700][i % 3]
        add("399", group, export_ids, 42, "wecoin", bid, max(600, bid * 2))
    if p_count > 0:
        add("399", "P399_ROI", c_ids[:10], 40, "roi", 0.8, 600)

    # cash guard: drop 59.9 from the tail first, keep 399 tests
    total = sum(p["budgetYuan"] for p in plans)
    while total > budget_cap and any(p["tier"] == "59.9" for p in plans):
        for idx in range(len(plans) - 1, -1, -1):
            if plans[idx]["tier"] == "59.9":
                total -= plans[idx]["budgetYuan"]
                plans.pop(idx)
                break
    # keep at least one 399 test; drop the rest until the cash guard fits
    while total > budget_cap and len([p for p in plans if p["tier"] == "399"]) > 1:
        for idx in range(len(plans) - 1, -1, -1):
            if plans[idx]["tier"] == "399":
                total -= plans[idx]["budgetYuan"]
                plans.pop(idx)
                break
    if total > budget_cap:
        raise SystemExit("cash guard: 399 最低测试量也超过现金安全线")

    common.attach_bindings(plans, by)
    out = {"account": account_id, "stage": stage, "cash": cash, "floor": floor,
           "unavailableBundles": [list(k) for k, _ in B599+B399 if not ids(k)],
           "count": len(plans), "totalBudget": total, "plans": plans,
           "lowSpendLinks": [p["productId"] for p in low_links]}
    path = os.path.join(ROOT, "data", "analysis", "checkpoint_" + stage + "_" + account_id + ".json")
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(path, "count", len(plans), "budget", total, "links", len(low_links), "bundleVideos", [len(x) for x in a_ids])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", required=True)
    ap.add_argument("--stage", required=True, choices=["23", "04", "08"])
    ap.add_argument("--cash", type=float, required=True)
    args = ap.parse_args()
    build(args.account, args.stage, args.cash)
