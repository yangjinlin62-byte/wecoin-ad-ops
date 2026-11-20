# -*- coding: utf-8 -*-
"""测试覆盖率台账 + 未测视频测试批。

统计每个户里 valid 但从未建过计划的视频（含新增），并按两个目标（成交数 8 / 成交ROI 11）
生成测试计划。台账写到 data/analysis/coverage_<account>.json。
"""
import argparse
import glob
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import common
import strategy_plan
from build_bundle_volume import make_plan

ROOT = common.ROOT
CATALOG = {"account1": "catalog", "account2": "catalog2"}
FLOOR = {"account1": 2500, "account2": 5000}


def min_create_ts():
    rules = json.load(open(os.path.join(ROOT, "app", "config", "rules.json"), encoding="utf-8"))
    s = rules["videoWindow"]["minCreateTime"]
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone(timedelta(hours=8)))
    return int(dt.timestamp())


def load_tested():
    """所有出现过在建单/支付文件里的 (account, fullExportId)。"""
    used = set()
    for sub in ("analysis", "ops"):
        for f in glob.glob(os.path.join(ROOT, "data", sub, "*.json")):
            try:
                d = json.load(open(f, encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(d, dict):
                continue
            acct = d.get("account") or ""
            plans = d.get("plans")
            if not isinstance(plans, list):
                plans = []
                for b in d.get("batches") or []:
                    if isinstance(b, dict):
                        plans += b.get("plans") or []
            for p in plans:
                if not isinstance(p, dict):
                    continue
                a = p.get("account") or acct
                for m in p.get("materials") or []:
                    if isinstance(m, dict) and m.get("exportId"):
                        used.add((a, m["exportId"]))
                for e in p.get("exportIds") or []:
                    used.add((a, e))
    return used


def catalog_videos(catdir):
    cat = json.load(open(os.path.join(ROOT, "data", catdir, "latest.json"), encoding="utf-8"))
    out = {}
    for a in cat.get("accounts", []):
        for v in a.get("videos", []):
            g = v.get("globalExportId")
            if g and g not in out:
                out[g] = v
    return out


def load_blocked():
    ids = set()
    seed = os.path.join(ROOT, "app", "config", "work-exclusions.json")
    if os.path.exists(seed):
        for r in json.load(open(seed, encoding="utf-8")):
            for i in r.get("ids", []):
                ids.add(i)
    folder = os.path.join(ROOT, "data", "state", "work-evidence")
    if os.path.isdir(folder):
        for f in os.listdir(folder):
            if not f.endswith(".json"):
                continue
            try:
                e = json.load(open(os.path.join(folder, f), encoding="utf-8"))
            except Exception:
                continue
            if e.get("type") == "single_quick_refund" and os.path.exists(os.path.join(folder, f[:-5] + ".released")):
                continue
            if e.get("globalId"):
                ids.add(e["globalId"])
            for i in e.get("workIds", []):
                ids.add(i)
    return ids


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundles", type=int, default=8, help="每个户建多少个测试 bundle")
    ap.add_argument("--size", type=int, default=4, help="每个 bundle 几条视频（3-5）")
    args = ap.parse_args()

    reg = json.load(open(os.path.join(ROOT, "data", "analysis", "product_registry.json"), encoding="utf-8"))
    allowed = set(reg["allowedProductIds"])
    tier_map = {p.get("productId"): p.get("tier") for p in reg.get("products", [])}
    tested = load_tested()
    min_t = min_create_ts()
    blocked = load_blocked()

    for acct in ("account1", "account2"):
        vids = catalog_videos(CATALOG[acct])
        untested = []
        for g, v in vids.items():
            if v.get("linkStatus") != "valid":
                continue
            if v.get("productId") not in allowed:
                continue
            if tier_map.get(v.get("productId")) != "59.9":
                continue
            if (v.get("createTime") or 0) < min_t:
                continue
            if v.get("isPrivate") or v.get("isChecking"):
                continue
            if not v.get("hasCart"):
                continue
            if v.get("fullExportId") in blocked or v.get("globalExportId") in blocked:
                continue
            if (acct, v.get("fullExportId")) in tested:
                continue
            untested.append(v)
        untested.sort(key=lambda v: -(v.get("created") or 0))
        ledger = {"account": acct, "total": len(vids), "untestedValid": len(untested),
                  "videos": [{"exportId": v.get("fullExportId"), "globalExportId": v.get("globalExportId"),
                              "author": v.get("author"), "productId": v.get("productId"),
                              "desc": (v.get("desc") or "")[:60], "created": v.get("created")} for v in untested]}
        p = os.path.join(ROOT, "data", "analysis", "coverage_" + acct + ".json")
        json.dump(ledger, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(p, "总视频", len(vids), "未测valid", len(untested))

        # 建测试批：同一商品下 3-5 条未测视频组成 bundle，两个目标各 1 条
        by_prod = defaultdict(list)
        for v in untested:
            by_prod[v.get("productId")].append(v)
        plans = []
        bi = 0
        for pid, vs in sorted(by_prod.items(), key=lambda kv: -len(kv[1])):
            for start in range(0, len(vs), args.size):
                if bi >= args.bundles:
                    break
                chunk = vs[start:start + args.size]
                if len(chunk) < 3:
                    continue
                mats = [{"exportId": v.get("fullExportId"), "author": v.get("author"),
                         "productId": pid, "desc": (v.get("desc") or "")[:60]} for v in chunk]
                p8 = make_plan(acct, pid, mats, 8, "wecoin", 90, 600)
                p8["billingMethod"] = 1
                p8["layer"] = "UNTESTED-8"
                plans.append(p8)
                p11 = make_plan(acct, pid, mats, 11, "roi", 0.70, 600)
                p11["billingMethod"] = 1
                p11["layer"] = "UNTESTED-ROI11"
                plans.append(p11)
                bi += 1
            if bi >= args.bundles:
                break
        out = {"account": acct, "purpose": "untested-test", "count": len(plans),
               "totalBudget": sum(p["budgetYuan"] for p in plans), "plans": plans}
        path = os.path.join(ROOT, "data", "analysis", "untested_test_" + acct + ".json")
        json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(path, "bundle", bi, "计划", len(plans), "（成交数8 + 成交ROI11 双目标）")


if __name__ == "__main__":
    main()
