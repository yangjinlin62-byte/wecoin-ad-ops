# -*- coding: utf-8 -*-
"""16:00 跑量+测试批次：跑量=原版赢家重建+有价值视频拆组（预付费+梯度）；测试=新视频/替换/预算对照。399 已在上批实时扣费覆盖，本批不重复。"""
import json
import os

import common
import strategy_plan
from build_checkpoint_strategy import micro_vary


def build(acct):
    # 跑量（预付费，梯度）
    volume = []
    volume += strategy_plan.build(acct, "same-author", "59.9", 10, 11, 0.7, 1000)["plans"]  # 原版赢家重建+有价值拆组
    volume += strategy_plan.build(acct, "same-author", "59.9", 6, None, None, None)["plans"]   # 净成交数 90 阶梯
    volume += strategy_plan.build(acct, "cross-author", "59.9", 4, None, None, None)["plans"]  # 多作者
    volume = micro_vary(volume)
    for p in volume:
        p["billingMethod"] = 0
        p["layer"] = "VOLUME"

    # 测试
    tests = []
    tests += strategy_plan.build(acct, "single-test", "59.9", 8, None, None, None)["plans"]     # 新视频（实时）
    tests += strategy_plan.build(acct, "replace-one", "59.9", 4, None, None, None)["plans"]     # 替换对照（预付费，2臂同价）
    for p in tests:
        p["billingMethod"] = 1 if p["strategy"]["purpose"] == "single-test" else 0
        p["layer"] = "TEST"
    if acct == "account2":
        tests += strategy_plan.build(acct, "budget-test", "59.9", 6, 42, 90, 300, 600)["plans"]  # 预算对照
        for p in tests:
            if p["strategy"]["purpose"] == "budget-test":
                p["billingMethod"] = 0
                p["layer"] = "TEST"

    plans = volume + tests
    out = {"account": acct, "purpose": "1600-volume-test", "count": len(plans),
           "totalBudget": sum(p["budgetYuan"] for p in plans), "plans": plans}
    path = os.path.join(common.ROOT, "data", "analysis", "batch1600_" + acct + ".json")
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    pre = sum(p["budgetYuan"] for p in plans if p["billingMethod"] == 0)
    post = sum(p["budgetYuan"] for p in plans if p["billingMethod"] == 1)
    print(path, "plans", len(plans), "pre", pre, "realtime", post)


if __name__ == "__main__":
    for a in ("account1", "account2"):
        build(a)
