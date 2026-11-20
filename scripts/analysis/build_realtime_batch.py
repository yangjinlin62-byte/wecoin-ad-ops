# -*- coding: utf-8 -*-
"""生成两户的纯实时扣费批次（不预扣现金），用于现金贴底时先建计划、等退款回笼。"""
import json
import os

import common
import strategy_plan
from build_checkpoint_strategy import micro_vary

COMBOS = [
    ("single-test", "59.9", 8),
    ("same-author", "59.9", 4),
    ("same-author", "399", 3),
    ("cross-author", "59.9", 4),
]


def main():
    for acct in ("account1", "account2"):
        plans = []
        for purpose, tier, count in COMBOS:
            res = strategy_plan.build(acct, purpose, tier, count)
            plans.extend(res["plans"])
        plans = micro_vary(plans)
        for p in plans:
            p["billingMethod"] = 1
            p["layer"] = "REALTIME"
        out = {"account": acct, "purpose": "realtime-mix", "count": len(plans),
               "totalBudget": sum(p["budgetYuan"] for p in plans), "plans": plans}
        path = os.path.join(common.ROOT, "data", "analysis", "realtime_batch_" + acct + ".json")
        json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(path, "plans", len(plans), "budget", out["totalBudget"])


if __name__ == "__main__":
    main()
