"""Reconcile a strategy draft to local order snapshots and save DSH's decision."""
import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from strategy_plan import BJ, binding_key, common, load


def review(draft, mapping, data):
    account, purpose = draft["account"], draft["purpose"]
    path = data / common.account(account)["dataDir"] / "materials.jsonl"
    ids = [x["promotionId"] for x in mapping.values() if x.get("promotionId")]
    if len(ids) != len(set(ids)) or any(str(i) not in {str(n) for n in range(1, len(draft["plans"])+1)} for i in mapping):
        raise ValueError("订单号重复或草稿行号越界")
    wanted = set(ids)
    observed = {}
    with path.open(encoding="utf-8-sig") as stream:
        for line in stream:
            if line.strip():
                row = json.loads(line)
                if row.get("promotionId") in wanted:
                    observed[row["promotionId"]] = row
    results = []
    for index, plan in enumerate(draft["plans"], 1):
        entry = mapping.get(str(index), {})
        order = observed.get(entry.get("promotionId"))
        result = dict(planNo=index, productId=plan["strategy"]["productId"], exportIds=plan["exportIds"],
                      target=plan["target"], bid=plan["bidValue"], budget=plan["budgetYuan"],
                      comparison=plan["strategy"]["comparison"], arm=plan["strategy"]["arm"],
                      promotionId=entry.get("promotionId"), decision="待补证")
        results.append(result)
        result["bindings"] = binding_key(plan["materials"])
        if not order:
            result["reason"] = "缺订单关联或本地效果快照"
            continue
        if purpose == "budget-test" and entry.get("actualBid") is None:
            result["reason"] = "预算对照缺实际出价回读"
            continue
        if entry.get("actualBid") is not None and entry["actualBid"] != plan["bidValue"]:
            result["reason"] = "实际出价已变化，需另作比较"
            continue
        result["bidEvidence"] = "回执映射提供" if entry.get("actualBid") is not None else "仅草稿值"
        materials = order.get("materials", [])
        observed_shops = {m.get("exportId"): m.get("realappid") for m in materials}
        if any(m.get("realappid") and observed_shops.get(m["exportId"]) != m["realappid"] for m in plan["materials"]):
            result["reason"] = "店铺绑定变化或缺失"
            continue
        if (sorted(m.get("exportId") or "" for m in materials) != sorted(plan["exportIds"]) or
                str(order.get("target")) != str(plan["target"]) or order.get("budget") != plan["budgetYuan"]*100 or
                {m.get("productId") for m in materials} != {result["productId"]}):
            result["reason"] = "订单配置与草稿不一致，需核对映射"
            continue
        if order.get("spend") is None or any(m.get(k) is None for m in materials for k in ("netPv", "netGmv")):
            result["reason"] = "缺消耗、净单或净额字段"
            continue
        cost = order["spend"]
        net = sum(m["netPv"] for m in materials)
        gmv = sum(m["netGmv"] for m in materials)
        result.update(costCents=cost, attributedNetOrders=net, attributedNetGmvCents=gmv,
                      netRoi=gmv/cost if cost else None, orderCreated=order.get("createTime"))
        reason = entry.get("reason")
        if cost and reason and entry.get("decision") in ("继续复验","暂缓复制"):
            result.update(decision=entry["decision"], reason=reason)
        else:
            result["reason"] = "低交付或尚无明确复盘判断"
    covered = [r for r in results if "costCents" in r]
    cost = sum(r["costCents"] for r in covered)
    gmv = sum(r["attributedNetGmvCents"] for r in covered)
    pairs = []
    if purpose == "budget-test":
        for pair in sorted({r["comparison"] for r in results}):
            arms = sorted((r for r in results if r["comparison"] == pair), key=lambda r: r["budget"])
            both = len(arms) == 2 and all("costCents" in r for r in arms)
            pairs.append(dict(comparison=pair, rows=[r["planNo"] for r in arms], covered=both,
                              highMinusLowCostCents=arms[1]["costCents"]-arms[0]["costCents"] if both else None,
                              highMinusLowNetOrders=arms[1]["attributedNetOrders"]-arms[0]["attributedNetOrders"] if both else None))
    return dict(account=account, purpose=purpose, tier=draft["plans"][0]["tier"], groups=results,
                summary=dict(planned=len(results), covered=len(covered), missing=len(results)-len(covered),
                             costCents=cost if covered else None,
                             attributedNetOrders=sum(r["attributedNetOrders"] for r in covered) if covered else None,
                             attributedNetGmvCents=gmv if covered else None, netRoi=gmv/cost if cost else None),
                budgetPairs=pairs, snapshotFile=str(path), snapshotFileModified=datetime.fromtimestamp(path.stat().st_mtime,BJ).isoformat(),
                basis="订单累计消耗、素材归因净单净额；文件修改时间不能代表指标更新时间")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("draft", type=Path)
    parser.add_argument("mapping", type=Path)
    args = parser.parse_args()
    data = Path(common.ROOT)/"data"
    result = review(load(args.draft), load(args.mapping), data)
    result["draft"] = str(args.draft.resolve())
    folder = data/"analysis/strategy-reviews"
    folder.mkdir(exist_ok=True)
    path = folder/f"{result['account']}-{result['purpose']}-{time.time_ns()}.json"
    with path.open("x", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(path)
