# -*- coding: utf-8 -*-
"""跑量大 bundle 批次：10 视频/条，成交数 8 与成交ROI 11 两个出单目标，预付费 + 阶梯。

build_volume_plans(acct, counts) 供 checkpoint 复用。
"""
import json
from pathlib import Path

import common
import strategy_plan


def rank_signal(m):
    return {"起量候选": 0, "观察": 1, "待测": 2, "衰退待核": 3}.get(m["signal"], 9)


def make_plan(acct, pid, mats, target, kind, bid, budget, tier="59.9"):
    return dict(account=acct, tier=tier, exportIds=[m["exportId"] for m in mats],
                target=target, bidKind=kind, bidValue=bid, budgetYuan=budget, billingMethod=0,
                materials=[dict(exportId=m["exportId"], productId=m["productId"],
                                realappid=m.get("realappid"), author=m.get("author")) for m in mats],
                strategy=dict(purpose="bundle-volume", productId=pid, arm=None))


def build_volume_plans(acct, counts, data=None):
    data = data or (Path(common.ROOT) / "data")
    ladders = {"A": [90, 91, 92, 93, 94], "B": [0.70, 0.71, 0.72], "C": [90, 91, 92]}
    targets = {"A": (8, "wecoin", 1000), "B": (11, "roi", 1000), "C": (42, "wecoin", 1000)}
    _, pools = strategy_plan.candidates(acct, "59.9", data)
    bundles = []
    for pid in sorted(pools, key=lambda p: -len(pools[p])):
        mats = sorted(pools[pid].values(), key=lambda m: (rank_signal(m), -m["recent"][1], -m["recent"][0], -m["created"]))
        for i in range(0, len(mats) - 9, 10):
            bundles.append((pid, mats[i:i + 10]))
    plans = []
    bi = 0
    for grp in ("A", "B", "C"):
        for k in range(int(counts.get(grp, 0))):
            if not bundles:
                break
            pid, mats = bundles[bi % len(bundles)]
            bi += 1
            t, kind, bud = targets[grp]
            bid = ladders[grp][k % len(ladders[grp])]
            plans.append(make_plan(acct, pid, mats, t, kind, bid, bud))
    res399 = strategy_plan.build(acct, "same-author", "399", int(counts.get("D", 0)), None, None, None)
    for p in res399["plans"]:
        p["billingMethod"] = 0
        p["layer"] = "VOLUME-D"
        p["strategy"]["purpose"] = "bundle-volume"
    plans += res399["plans"]
    return plans


def main():
    spec = {"account1": {"A": 10, "B": 4, "C": 2, "D": 2},
            "account2": {"A": 20, "B": 8, "C": 4, "D": 4}}
    for acct, counts in spec.items():
        plans = build_volume_plans(acct, counts)
        out = {"account": acct, "purpose": "bundle-volume", "count": len(plans),
               "totalBudget": sum(p["budgetYuan"] for p in plans), "plans": plans}
        path = common.ROOT + "\\data\\analysis\\bundle_volume_" + acct + ".json"
        json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(path, "plans", len(plans), "pre", out["totalBudget"])


if __name__ == "__main__":
    main()
