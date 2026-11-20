# -*- coding: utf-8 -*-
"""复盘数据准备：把两户订单、素材归因、台账合并成一份干净数据集。"""
import json
import os
from collections import defaultdict

ROOT = r"F:\微信豆投流助手"


def load_orders():
    meta = {}
    for acct, d in (("account1", "history"), ("account2", "history2")):
        for fn in os.listdir(os.path.join(ROOT, "data", d)):
            if not fn.startswith("orders_p") or not fn.endswith(".json"):
                continue
            obj = json.load(open(os.path.join(ROOT, "data", d, fn), encoding="utf-8"))
            ol = (((obj.get("data") or {}).get("resp") or {}).get("orderList") or [])
            for o in ol:
                pid = o.get("promotionId")
                if not pid:
                    continue
                pay = o.get("paymentInfo") or {}
                bi = o.get("bidInfo") or {}
                bid = None
                if bi:
                    bid = bi.get("roi") or bi.get("wecoinBid") or bi.get("bid") or None
                meta[pid] = {
                    "account": acct,
                    "target": o.get("promotionTarget"),
                    "budgetYuan": (int(o.get("totalQuota") or 0) / 100),
                    "billingMethod": pay.get("billingMethod"),
                    "pricingMethod": o.get("pricingMethod"),
                    "exportStatus": o.get("exportStatus"),
                    "createTime": o.get("createTime"),
                    "startTime": o.get("startTime"),
                    "videoCount": len(o.get("materialInfos") or []),
                    "bid": bid,
                    "orderName": o.get("orderName"),
                }
    return meta


def load_materials():
    agg = {}
    for acct, d in (("account1", "history"), ("account2", "history2")):
        path = os.path.join(ROOT, "data", d, "materials.jsonl")
        if not os.path.exists(path):
            continue
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            pid = row.get("promotionId")
            if not pid:
                continue
            mats = row.get("materials") or []
            netPv = sum(int(m.get("netPv") or 0) for m in mats)
            netGmv = sum(int(m.get("netGmv") or 0) for m in mats)
            spend = int(row.get("spend") or 0)
            bi = row.get("bidInfo") or {}
            bid = bi.get("roi") or bi.get("wecoinBid") or bi.get("bid") or None
            agg[pid] = {
                "target": row.get("target"),
                "budgetYuan": (int(row.get("budget") or 0) / 100),
                "bid": bid,
                "spendYuan": spend / 100,
                "netPv": netPv,
                "netGmvYuan": netGmv / 100,
                "roi": (netGmv / spend) if spend else None,
                "materialCount": len(mats),
                "createTime": row.get("createTime"),
            }
    return agg


def load_dsh_pids():
    pids = set()
    path = os.path.join(ROOT, "data", "state", "ledger.jsonl")
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except Exception:
            continue
        for pid in e.get("promotionIds") or []:
            pids.add(pid)
        if e.get("promotionId"):
            pids.add(e["promotionId"])
        for item in (e.get("result") or {}).get("items") or []:
            if item.get("promotionId"):
                pids.add(item["promotionId"])
    return pids


def main():
    orders = load_orders()
    mats = load_materials()
    dsh = load_dsh_pids()
    rows = []
    # merge: orders 提供扣费/状态，materials 提供消耗/净单/净额
    all_pids = set(orders) | set(mats)
    for pid in sorted(all_pids):
        o = orders.get(pid, {})
        m = mats.get(pid, {})
        acct = o.get("account") or ("account2" if pid.startswith("1793980800") or pid.startswith("1794067200") else "")
        rows.append({
            "promotionId": pid,
            "account": acct,
            "createTime": o.get("createTime") or m.get("createTime"),
            "startTime": o.get("startTime"),
            "target": o.get("target") or m.get("target"),
            "bid": o.get("bid") if o.get("bid") is not None else m.get("bid"),
            "budgetYuan": o.get("budgetYuan") or m.get("budgetYuan"),
            "billingMethod": o.get("billingMethod"),
            "pricingMethod": o.get("pricingMethod"),
            "exportStatus": o.get("exportStatus"),
            "spendYuan": m.get("spendYuan", 0),
            "netPv": m.get("netPv", 0),
            "netGmvYuan": m.get("netGmvYuan", 0),
            "roi": m.get("roi"),
            "videoCount": o.get("videoCount") or m.get("materialCount"),
            "source": "DSH" if pid in dsh else "历史/用户",
            "orderName": o.get("orderName"),
        })
    out = {"generatedAt": "2026-11-10T09:40+08:00", "orders": rows,
           "summary": {
               "totalOrders": len(rows),
               "dshOrders": sum(1 for r in rows if r["source"] == "DSH"),
               "totalSpendYuan": round(sum(r["spendYuan"] for r in rows), 2),
               "totalNetPv": sum(r["netPv"] for r in rows),
           }}
    path = os.path.join(ROOT, "data", "analysis", "review_dataset.json")
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(path, "orders", len(rows), "DSH", out["summary"]["dshOrders"],
          "spend", out["summary"]["totalSpendYuan"], "netPv", out["summary"]["totalNetPv"])


if __name__ == "__main__":
    main()
