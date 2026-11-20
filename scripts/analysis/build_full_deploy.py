# -*- coding: utf-8 -*-
"""完整投放批次：59.9(8/11/42 大bundle) + 399(40/42) + 实时扣费 single-test 59.9。"""
import json
from pathlib import Path

import common
import strategy_plan
from build_bundle_volume import build_volume_plans


def main():
    data = Path(common.ROOT) / "data"
    # 完整批次（比 checkpoint 的每档大，属于一次性投放）
    counts = {"account1": {"A": 10, "B": 4, "C": 2, "D": 2},
              "account2": {"A": 20, "B": 8, "C": 4, "D": 4}}
    for acct, c in counts.items():
        plans = build_volume_plans(acct, c, data)  # 59.9 A/B/C(8/11/42) + 399 D(净ROI40)，全预付费

        # 399 净成交 42（复验），预付费
        res399_42 = strategy_plan.build(acct, "same-author", "399", c["D"], 42, 600, 1200)
        for p in res399_42["plans"]:
            p["billingMethod"] = 0
            p["layer"] = "VOLUME-399-42"
            p["strategy"]["purpose"] = "bundle-volume"
        plans += res399_42["plans"]

        # 实时扣费 single-test 59.9（扩在投额度，billingMethod=1）
        res_rt = strategy_plan.build(acct, "single-test", "59.9", 8)
        for p in res_rt["plans"]:
            p["billingMethod"] = 1
            p["layer"] = "REALTIME-SINGLE"
        plans += res_rt["plans"]

        out = {"account": acct, "purpose": "full-deploy", "count": len(plans),
               "totalBudget": sum(p["budgetYuan"] for p in plans), "plans": plans}
        path = common.ROOT + "\\data\\analysis\\full_deploy_" + acct + ".json"
        json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        pre = sum(p["budgetYuan"] for p in plans if p["billingMethod"] == 0)
        post = sum(p["budgetYuan"] for p in plans if p["billingMethod"] == 1)
        print(path, "plans", len(plans), "pre", pre, "realtime", post)


if __name__ == "__main__":
    main()
