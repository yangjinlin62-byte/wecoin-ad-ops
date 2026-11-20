# -*- coding: utf-8 -*-
"""赢家集中打法：按全历史净单最高的 3 个商品，各 10 视频大 bundle，复制 21 条目标 8。"""
import json
import os
from collections import defaultdict
from pathlib import Path

import common
import strategy_plan
from build_bundle_volume import make_plan

ROOT = common.ROOT
FLOOR = {"account1": 2500, "account2": 5000}
CASH = {"account1": 18453.90, "account2": 22662.41}


def load_full():
    full = defaultdict(int)
    f2g = {}
    for d in ("history", "history2"):
        p = os.path.join(ROOT, "data", d, "materials.jsonl")
        if not os.path.exists(p):
            continue
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            for m in row.get("materials") or []:
                gid = m.get("globalExportId")
                e = m.get("exportId")
                if e and gid:
                    f2g[e] = gid
                if gid:
                    full[gid] += int(m.get("netPv") or 0)
    return full, f2g


def main():
    data = Path(ROOT) / "data"
    full, f2g = load_full()
    ladder = [90, 91, 92, 93, 94]

    def npv(m):
        return full.get(m.get("globalExportId") or f2g.get(m["exportId"], ""), 0)

    for acct in ("account1", "account2"):
        _, pools = strategy_plan.candidates(acct, "59.9", data)
        prods = []
        for pid, pool in pools.items():
            mats = sorted(pool.values(), key=lambda m: -npv(m))
            if len(mats) >= 10:
                prods.append((max(npv(m) for m in mats), pid, mats[:10]))
        prods.sort(key=lambda x: -x[0])
        bundles = [(pid, mats) for _, pid, mats in prods[:3]]
        cap = max(0.0, CASH[acct] - FLOOR[acct])
        plans = []
        total = 0
        for k in range(21):
            pid, mats = bundles[k % len(bundles)]
            p = make_plan(acct, pid, mats, 8, "wecoin", ladder[k % len(ladder)], 1000)
            if total + p["budgetYuan"] > cap:
                continue
            plans.append(p)
            total += p["budgetYuan"]
        out = {"account": acct, "purpose": "winner-concentrated", "count": len(plans),
               "totalBudget": total, "plans": plans}
        path = ROOT + "\\data\\analysis\\winner_conc_" + acct + ".json"
        json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(path, "plans", len(plans), "budget", total, "products", [(x[0], x[1]) for x in bundles])


if __name__ == "__main__":
    main()
