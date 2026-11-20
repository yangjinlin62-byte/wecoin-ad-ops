#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Build material-level scorecard from order-detail JSONL files."""
import json, os, sys, time
from collections import defaultdict

import common
from common import tier_from_wording
ROOT = common.ROOT
INVALID_PRODUCTS = common.INVALID_PRODUCTS

def load_jsonl(path):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return rows

def money(cents):
    return round(float(cents or 0) / 100.0, 2)

def main():
    paths = [
        ("account1", os.path.join(ROOT, "data", "history", "materials.jsonl")),
        ("account2", os.path.join(ROOT, "data", "history2", "materials.jsonl")),
    ]
    materials = {}
    products = {}
    total_orders = 0
    for acct, p in paths:
        rows = load_jsonl(p)
        total_orders += len(rows)
        for r in rows:
            for m in r.get("materials", []):
                key = m.get("globalExportId") or m.get("exportId") or m.get("materialId")
                if not key:
                    continue
                pid = m.get("productId") or ""
                if pid:
                    pr = products.setdefault(pid, {
                        "productId": pid,
                        "wordings": set(),
                        "realappids": set(),
                        "authors": set(),
                        "plans": 0,
                        "cost": 0,
                        "pay": 0,
                        "orders": 0,
                        "netPay": 0,
                        "netPv": 0,
                    })
                    pr["wordings"].add(m.get("productWording") or "")
                    pr["realappids"].add(m.get("realappid") or "")
                    pr["authors"].add(m.get("author") or "")
                    pr["plans"] += 1
                    pr["cost"] += int(m.get("cost") or 0)
                    pr["pay"] += int(m.get("payGmv") or 0)
                    pr["orders"] += int(m.get("payPv") or 0)
                    pr["netPay"] += int(m.get("netGmv") or 0)
                    pr["netPv"] += int(m.get("netPv") or 0)
                d = materials.setdefault(key, {
                    "key": key,
                    "materialId": m.get("materialId", ""),
                    "globalExportId": m.get("globalExportId", ""),
                    "accounts": set(),
                    "exportIds": {},
                    "authors": set(),
                    "productIds": set(),
                    "productWordings": set(),
                    "targets": set(),
                    "plans": 0,
                    "payingPlans": 0,
                    "wins": 0,
                    "cost": 0,
                    "pay": 0,
                    "orders": 0,
                    "netPay": 0,
                    "netPv": 0,
                    "first": 0,
                    "last": 0,
                    "recent7Cost": 0,
                    "recent7Pay": 0,
                    "recent7Orders": 0,
                    "targetStats": defaultdict(lambda: {"cost": 0, "pay": 0, "orders": 0, "plans": 0}),
                    "invalidProduct": False,
                })
                d["accounts"].add(acct)
                if m.get("exportId"):
                    d["exportIds"][acct] = m["exportId"]
                if m.get("author"):
                    d["authors"].add(m["author"])
                if m.get("productId"):
                    d["productIds"].add(m["productId"])
                    if m["productId"] in INVALID_PRODUCTS:
                        d["invalidProduct"] = True
                if m.get("productWording"):
                    d["productWordings"].add(m["productWording"])
                d["targets"].add(r.get("target"))
                d["plans"] += 1
                cost = int(m.get("cost") or 0)
                pay = int(m.get("payGmv") or 0)
                orders = int(m.get("payPv") or 0)
                d["cost"] += cost
                d["pay"] += pay
                d["orders"] += orders
                d["netPay"] += int(m.get("netGmv") or 0)
                d["netPv"] += int(m.get("netPv") or 0)
                d["first"] = min(d["first"] or r.get("createTime", 0), r.get("createTime", 0))
                d["last"] = max(d["last"], r.get("createTime", 0))
                if orders > 0:
                    d["payingPlans"] += 1
                if pay > cost:
                    d["wins"] += 1
                ts = int(r.get("createTime") or 0)
                if ts >= time.time() - 7 * 86400:
                    d["recent7Cost"] += cost
                    d["recent7Pay"] += pay
                    d["recent7Orders"] += orders
                t = r.get("target")
                st = d["targetStats"][str(t)]
                st["cost"] += cost
                st["pay"] += pay
                st["orders"] += orders
                st["plans"] += 1

    # finalize
    out = []
    for d in materials.values():
        cost = d["cost"]
        pay = d["pay"]
        orders = d["orders"]
        roi = pay / cost if cost else 0
        cpa = cost / orders if orders else 0
        best_target = None
        best_score = -1
        for t, st in d["targetStats"].items():
            s = st["orders"] * 1000000 + (st["pay"] / st["cost"] if st["cost"] else 0) * 10000
            if s > best_score:
                best_score = s
                best_target = {
                    "target": t,
                    "cost": money(st["cost"]),
                    "pay": money(st["pay"]),
                    "orders": st["orders"],
                    "roi": round(st["pay"] / st["cost"], 3) if st["cost"] else 0,
                    "plans": st["plans"],
                }
        if orders >= 3 and roi >= 1.0 and cost >= 10000:
            layer = "S"
        elif orders >= 1 and roi >= 0.6:
            layer = "A"
        elif cost >= 10000 and orders == 0:
            layer = "B"
        elif cost >= 20000 and roi < 0.3:
            layer = "C"
        else:
            layer = "observe"
        out.append({
            "key": d["key"],
            "materialId": d["materialId"],
            "globalExportId": d["globalExportId"],
            "accounts": sorted(d["accounts"]),
            "exportIds": d.get("exportIds", {}),
            "authors": sorted(d["authors"]),
            "productIds": sorted(d["productIds"]),
            "productWordings": sorted(d["productWordings"]),
            "invalidProduct": d["invalidProduct"],
            "plans": d["plans"],
            "payingPlans": d["payingPlans"],
            "wins": d["wins"],
            "cost": money(cost),
            "pay": money(pay),
            "orders": orders,
            "roi": round(roi, 3),
            "cpa": round(money(cpa), 2),
            "netPay": money(d["netPay"]),
            "netPv": d["netPv"],
            "first": d["first"],
            "last": d["last"],
            "recent7Cost": money(d["recent7Cost"]),
            "recent7Pay": money(d["recent7Pay"]),
            "recent7Orders": d["recent7Orders"],
            "bestTarget": best_target,
            "layer": layer,
        })

    out.sort(key=lambda x: (-x["orders"], -x["pay"], -x["roi"]))
    product_out = []
    for pid, pr in products.items():
        aov_yuan = money(pr["pay"] / pr["orders"]) if pr["orders"] else 0
        if 40 <= aov_yuan <= 80:
            tier = "59.9"
        elif 300 <= aov_yuan <= 600:
            tier = "399"
        else:
            tier = "other"
        if tier == "other":
            for w in pr["wordings"]:
                t = tier_from_wording(w)
                if t != "unknown":
                    tier = t
                    break
        product_out.append({
            "productId": pid,
            "wordings": sorted(x for x in pr["wordings"] if x),
            "realappids": sorted(x for x in pr["realappids"] if x),
            "authors": sorted(x for x in pr["authors"] if x),
            "plans": pr["plans"],
            "cost": money(pr["cost"]),
            "pay": money(pr["pay"]),
            "orders": pr["orders"],
            "aov": round(aov_yuan, 2),
            "roi": round(pr["pay"] / pr["cost"], 3) if pr["cost"] else 0,
            "netPay": money(pr["netPay"]),
            "netPv": pr["netPv"],
            "priceTier": tier,
        })
    product_out.sort(key=lambda x: (-x["orders"], -x["pay"]))
    os.makedirs(os.path.join(ROOT, "data", "analysis"), exist_ok=True)
    with open(os.path.join(ROOT, "data", "analysis", "material_scorecard.json"), "w", encoding="utf-8") as f:
        json.dump({
            "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "orders": total_orders,
            "materials": out,
            "products": product_out,
        }, f, ensure_ascii=False, indent=1)

    from collections import Counter
    layers = Counter(x["layer"] for x in out)
    print("orders", total_orders, "materials", len(out), "layers", dict(layers))
    print("S top:")
    for x in [y for y in out if y["layer"] == "S"][:20]:
        print(x["key"][:30], "orders", x["orders"], "cost", x["cost"], "pay", x["pay"], "roi", x["roi"], "cpa", x["cpa"], "authors", x["authors"], "product", x["productWordings"])
    print("A top:")
    for x in [y for y in out if y["layer"] == "A"][:20]:
        print(x["key"][:30], "orders", x["orders"], "cost", x["cost"], "pay", x["pay"], "roi", x["roi"], "cpa", x["cpa"], "authors", x["authors"])
    print("products top:")
    for p in product_out[:20]:
        print(p["productId"], p["priceTier"], "aov", p["aov"], "orders", p["orders"], "cost", p["cost"], "pay", p["pay"], "roi", p["roi"], p["wordings"][:2])

if __name__ == "__main__":
    main()
