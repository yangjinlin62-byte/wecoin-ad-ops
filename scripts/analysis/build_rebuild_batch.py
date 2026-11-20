# -*- coding: utf-8 -*-
"""重建被误取消的计划：按组合策略完整矩阵，两户对称；单视频=实时扣费，多视频=预付费。"""
import json
import os

import common
import strategy_plan

# (purpose, tier, count, target_override, bid_override, budget_override, billingMethod)
COMBOS = [
    ("single-test", "59.9", 8, None, None, None, 1),
    ("same-author", "59.9", 4, None, None, None, 0),
    ("same-author", "399", 3, None, None, None, 0),
    ("cross-author", "59.9", 4, None, None, None, 0),
    ("replace-one", "59.9", 4, None, None, None, 0),
    ("same-author", "59.9", 2, 11, 0.7, 1000, 0),  # 成熟放量 成交ROI(11)/1000
]


def main():
    for acct in ("account1", "account2"):
        combos = list(COMBOS)
        if acct == "account2":
            combos.append(("budget-test", "59.9", 6, 42, 90, 300, 0))  # 预算对照 300 vs 600
        plans = []
        for purpose, tier, count, target, bid, budget, billing in combos:
            cmp_budget = 600 if purpose == "budget-test" else None
            res = strategy_plan.build(acct, purpose, tier, count, target, bid, budget, cmp_budget)
            for p in res["plans"]:
                p["billingMethod"] = billing
                p["layer"] = "REBUILD"
            plans.extend(res["plans"])
        out = {"account": acct, "purpose": "rebuild", "count": len(plans),
               "totalBudget": sum(p["budgetYuan"] for p in plans), "plans": plans}
        path = os.path.join(common.ROOT, "data", "analysis", "rebuild_batch_" + acct + ".json")
        json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        pre = sum(p["budgetYuan"] for p in plans if p["billingMethod"] == 0)
        post = sum(p["budgetYuan"] for p in plans if p["billingMethod"] == 1)
        print(path, "plans", len(plans), "pre", pre, "realtime", post)


if __name__ == "__main__":
    main()
