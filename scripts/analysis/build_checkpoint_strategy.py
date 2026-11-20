# -*- coding: utf-8 -*-
"""Build a checkpoint batch from the 跑量大 bundle 结构（A/B/C/D），不是旧的 3-5 条小组合。"""
import argparse
import json
import os

import common
from build_bundle_volume import build_volume_plans

ROOT = common.ROOT
RULES = common.RULES

DEFAULT_COUNTS = {"account1": {"A": 4, "B": 2, "C": 1, "D": 1},
                  "account2": {"A": 6, "B": 3, "C": 2, "D": 2}}


def build(account_id, stage, cash):
    cfg = RULES.get("checkpoint", {}).get("strategy", {})
    counts = ((cfg.get("bundle") or {}).get(account_id)) or DEFAULT_COUNTS[account_id]
    floor = float(RULES["checkpoint"]["floorYuan"][account_id])
    budget_cap = max(0.0, float(cash) - floor)
    plans = build_volume_plans(account_id, counts)
    for plan in plans:
        plan["layer"] = "VOLUME"
        plan["stage"] = stage
        plan["group"] = plan["strategy"].get("purpose", "bundle-volume")

    # 现金不够就用实时扣费：预付费填到现金上限，超出的转 billingMethod=1（不丢计划、不减量）
    running = 0
    for p in plans:
        if int(p.get("billingMethod", 0)) == 0:
            if running + int(p["budgetYuan"]) <= budget_cap:
                running += int(p["budgetYuan"])
            else:
                p["billingMethod"] = 1
    pre_total = sum(int(p["budgetYuan"]) for p in plans if int(p.get("billingMethod", 0)) == 0)
    if pre_total > budget_cap:
        raise SystemExit("cash guard: 预付费超过现金安全线")
    total = sum(int(p["budgetYuan"]) for p in plans)

    out = {"account": account_id, "stage": stage, "cash": cash, "floor": floor,
           "count": len(plans), "totalBudget": total, "preBudget": pre_total,
           "postBudget": total - pre_total, "plans": plans, "counts": counts}
    path = os.path.join(ROOT, "data", "analysis", f"checkpoint_{stage}_{account_id}.json")
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(path, "count", len(plans), "budget", total)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", required=True)
    ap.add_argument("--stage", required=True, choices=["23", "04", "08", "12", "16", "20"])
    ap.add_argument("--cash", type=float, required=True)
    args = ap.parse_args()
    build(args.account, args.stage, args.cash)
