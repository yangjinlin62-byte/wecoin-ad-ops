"""Generate local, purpose-specific proposals from one advertising account's saved data."""
import argparse
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import common

BJ = timezone(timedelta(hours=8))
PURPOSES = ("single-test", "same-author", "cross-author", "replace-one", "budget-test")


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def history_windows(path, binding_since=None):
    # Repeated exports of the same order are observations, not additional plans.
    latest = {}
    with path.open(encoding="utf-8-sig") as stream:
        for line in stream:
            if line.strip():
                row = json.loads(line)
                latest[row["promotionId"]] = row
    last = max((int(row.get("createTime") or 0) for row in latest.values()), default=0)
    end = datetime.fromtimestamp(last, BJ).replace(hour=0, minute=0, second=0, microsecond=0)
    stats = defaultdict(lambda: [[0, 0, 0, 0], [0, 0, 0, 0]])
    for row in latest.values():
        age = (end.timestamp() - int(row.get("createTime") or 0)) / 86400
        if not 0 < age <= 14:
            continue
        for m in row.get("materials", []):
            if not m.get("globalExportId") or any(m.get(k) is None for k in ("cost", "netPv", "netGmv")):
                continue
            key = (m["globalExportId"], m.get("productId"), m.get("realappid"))
            if int(row.get("createTime") or 0) < (binding_since or {}).get(key, 0):
                continue
            window = stats[key][int(age > 7)]
            for i, key in enumerate(("cost", "netPv", "netGmv")):
                window[i] += int(m[key])
            window[3] += int(m["cost"] > 0)
    return end, stats


def signal(recent, prior):
    cost, orders, gmv, samples = recent
    old_cost, old_orders, old_gmv, old_samples = prior
    if not cost:
        return "待测" if not old_cost else "近期缺交付"
    if (samples >= 2 and old_samples >= 2 and old_orders and
            orders / cost < old_orders / old_cost and gmv / cost < old_gmv / old_cost):
        return "衰退待核"
    return "起量候选" if orders and samples >= 2 else "观察"


def candidates(account, tier, data):
    cfg = common.account(account)
    cat = load(data / cfg["catalogDir"] / "latest.json")
    reg = load(data / "analysis/product_registry.json")
    products = {p["productId"]: p for p in reg["products"]}
    allowed = set(reg["allowedProductIds"])
    since = {(v.get("globalExportId"), v.get("productId"), v.get("realappid")):
             datetime.fromisoformat(v["bindingChangedAt"].replace("Z","+00:00")).timestamp()
             for a in cat["accounts"] for v in a["videos"] if v.get("bindingChangedAt")}
    end, stats = history_windows(data / cfg["dataDir"] / "materials.jsonl", since)
    future = datetime.fromisoformat(common.RULES["videoWindow"]["futureFrom"]).timestamp()
    pools = defaultdict(dict)
    holds = common.work_holds(account)
    deleted = common.deleted_videos()
    synced_at = cat.get("syncedAt")
    if synced_at:
        try:
            age_h = (datetime.now(timezone.utc) - datetime.fromisoformat(synced_at.replace("Z", "+00:00"))).total_seconds() / 3600
            if age_h > 6:
                print(f"警告：{account} 目录已 {age_h:.1f} 小时未同步，可能残留已删除视频，建议先 catalog sync", file=__import__("sys").stderr)
        except Exception:
            pass
    for author in cat["accounts"]:
        for v in author.get("videos", []):
            pid, eid = v.get("productId"), v.get("fullExportId")
            date = int(v.get("createTime") or 0)
            if (not pid or not eid or not v.get("globalExportId") or v.get("linkStatus") != "valid"
                    or not v.get("realappid") or v.get("hasCart") is False):
                continue
            if date < datetime(2026, 9, 25, tzinfo=BJ).timestamp() or pid in common.INVALID_PRODUCTS:
                continue
            if date < future and pid not in allowed or v.get("isPrivate") or v.get("isChecking"):
                continue
            if eid in holds or v["globalExportId"] in holds:
                continue
            if eid in deleted or v["globalExportId"] in deleted:
                continue
            product = products.get(pid, {})
            if product.get("invalid") or (product.get("tier") or common.tier_from_wording(v.get("productWording"))) != tier:
                continue
            creator = v.get("username") or author.get("username")
            if not creator:
                continue
            recent, prior = stats[(v["globalExportId"], pid, v["realappid"])]
            pools[pid][eid] = dict(exportId=eid, globalExportId=v.get("globalExportId"), authorId=creator, author=v.get("author"),
                                   productId=pid, realappid=v["realappid"], created=date, desc=v.get("desc"),
                                   catalogAsOf=cat.get("syncedAt"), detectedAt=v.get("detectedAt"),
                                   bindingChangedAt=v.get("bindingChangedAt"),
                                   signal=signal(recent, prior), recent=recent, prior=prior)
    return end, pools


def groups(materials, purpose):
    # Ranking is a candidate signal from attributed material metrics, not standalone ROI.
    ranked = sorted(materials, key=lambda m: (-m["recent"][1], -m["prior"][1], -m["created"], m["exportId"]))
    authors = defaultdict(list)
    for m in ranked:
        authors[m["authorId"]].append(m)
    if purpose == "single-test":
        for m in sorted(ranked, key=lambda m: (m["recent"][3]+m["prior"][3], -m["created"])):
            yield [[m]]
    elif purpose in ("same-author", "budget-test"):
        for pool in authors.values():
            for i in range(0, len(pool)-2, 5):
                yield [pool[i:i+5]]
    elif purpose == "cross-author":
        mixed = [pool[i] for i in range(max(map(len, authors.values()), default=0))
                 for pool in authors.values() if i < len(pool)]
        for i in range(0, len(mixed)-2, 5):
            group = mixed[i:i+5]
            if len({m["authorId"] for m in group}) >= 2:
                yield [group]
    else:
        for pool in authors.values():
            anchors = [m for m in pool if m["signal"] == "起量候选"]
            fading = [m for m in pool if m["signal"] == "衰退待核"]
            new = [m for m in pool if m["signal"] == "待测"]
            if len(anchors) >= 2:
                for old, candidate in zip(fading, new):
                    yield [anchors[:2]+[old], anchors[:2]+[candidate]]


def binding_key(group):
    return sorted((m["exportId"], m.get("realappid") or "", m.get("bindingChangedAt") or "") for m in group)


def build(account, purpose, tier, count, target_override=None, bid_override=None, budget_override=None, compare_budget=None):
    if purpose == "budget-test":
        if (count % 2 or budget_override is None or compare_budget is None or
                not 0 < budget_override < compare_budget):
            raise ValueError("预算对照需要偶数条计划，并指定较低 --budget 和较高 --compare-budget")
    elif compare_budget is not None:
        raise ValueError("--compare-budget 仅用于 budget-test")
    data = Path(common.ROOT)/"data"
    end, pools = candidates(account, tier, data)
    memory = {}
    for path in sorted((data/"analysis/strategy-reviews").glob(f"{account}-{purpose}-*.json")):
        review = load(path)
        if review["tier"] == tier:
            for item in review["groups"]:
                if "bindings" not in item:
                    continue
                key = (item["productId"], item["target"], item["bid"], item["budget"],
                       tuple(tuple(b) for b in item["bindings"]))
                if item["decision"] != "待补证":
                    memory[key] = (item["decision"], path.name)
    scaling = purpose in ("same-author", "cross-author")
    target, kind, bid, budget = ((42, "wecoin", 90, 600 if scaling else 300) if tier == "59.9"
                                 else (40, "roi", 0.8, 600))
    if target_override is not None:
        if target_override != target and bid_override is None:
            raise ValueError("切换目标需同时指定对应单位的出价")
        target = target_override
        kind = "wecoin" if target in (8,42) else "roi"
    bid = bid if bid_override is None else bid_override
    budget = budget if budget_override is None else budget_override
    plans = []
    if purpose == "single-test":
        # 每天的新增/待测素材必须优先全部测试：跨商品按“有消耗记录数”升序，新素材(0样本)排最前。
        ordered = []
        for pid in sorted(pools):
            for g in groups(pools[pid].values(), "single-test"):
                ordered.append((pid, g[0][0]))
        ordered.sort(key=lambda pm: (pm[1]["recent"][3] + pm[1]["prior"][3], -pm[1]["created"], pm[1]["exportId"]))
        for pid, m in ordered:
            if len(plans) >= count:
                break
            previous = memory.get((pid, target, bid, budget, tuple(binding_key([m]))))
            if previous and previous[0] == "暂缓复制":
                continue
            plans.append(dict(account=account, tier=tier, exportIds=[m["exportId"]],
                              target=target, bidKind=kind, bidValue=bid, budgetYuan=budget,
                              materials=[m], strategy=dict(purpose=purpose, productId=pid,
                              previousReview=previous, comparison=None, arm=None)))
        return dict(account=account, purpose=purpose, requested=count, count=len(plans),
                    totalBudget=sum(p["budgetYuan"] for p in plans), plans=plans,
                    historyCutoffExclusive=end.isoformat(), metricOrder=["消耗分","净单","净额分","有消耗记录数"],
                    basis="本广告户有素材明细的计划，按创建日分近7日和前7日，使用累计归因值；组合需按实际开始年龄另行复盘。",
                    shortage=max(0, count-len(plans)))
    for pid in sorted(pools):
        for experiment in groups(pools[pid].values(), purpose):
            budgets = [budget] * len(experiment)
            if purpose == "budget-test":
                experiment = [experiment[0], experiment[0]]
                budgets = [budget, compare_budget] if len(plans) % 4 == 0 else [compare_budget, budget]
            previous = [memory.get((pid, target, bid, amount, tuple(binding_key(group))))
                        for group, amount in zip(experiment, budgets)]
            if any(record and record[0] == "暂缓复制" for record in previous):
                continue
            if len(plans)+len(experiment) > count:
                break
            pair = len(plans)+1
            for arm, group in enumerate(experiment):
                arm_name = None
                if purpose == "budget-test":
                    arm_name = "低预算" if budgets[arm] == budget else "高预算"
                elif len(experiment) == 2:
                    arm_name = "保留" if arm == 0 else "替换"
                plans.append(dict(account=account, tier=tier, exportIds=[m["exportId"] for m in group],
                                  target=target, bidKind=kind, bidValue=bid, budgetYuan=budgets[arm],
                                  materials=group, strategy=dict(purpose=purpose, productId=pid,
                                  previousReview=previous[arm], comparison=pair if len(experiment)==2 else None,
                                  arm=arm_name)))
    return dict(account=account, purpose=purpose, requested=count, count=len(plans),
                totalBudget=sum(p["budgetYuan"] for p in plans), plans=plans,
                historyCutoffExclusive=end.isoformat(), metricOrder=["消耗分","净单","净额分","有消耗记录数"],
                basis="本广告户有素材明细的计划，按创建日分近7日和前7日，使用累计归因值；组合需按实际开始年龄另行复盘。",
                shortage=count-len(plans))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("account", choices=common.ACCOUNTS)
    parser.add_argument("purpose", choices=PURPOSES)
    parser.add_argument("tier", choices=["59.9","399"])
    parser.add_argument("count", type=int, choices=range(1,51))
    parser.add_argument("output", type=Path)
    parser.add_argument("--target", type=int, choices=(8,11,40,42))
    parser.add_argument("--bid", type=float)
    parser.add_argument("--budget", type=int)
    parser.add_argument("--compare-budget", type=int)
    args = parser.parse_args()
    result = build(args.account, args.purpose, args.tier, args.count, args.target, args.bid, args.budget, args.compare_budget)
    with args.output.open("x", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
