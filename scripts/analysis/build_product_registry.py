# -*- coding: utf-8 -*-
"""Build the actual-invested product registry for the 2026-08-01..11-06 window."""
import datetime
import json
import os

import common

ROOT = common.ROOT
START = int(datetime.datetime(2026, 8, 1, tzinfo=datetime.timezone(datetime.timedelta(hours=8))).timestamp())
END = int(datetime.datetime(2026, 11, 7, tzinfo=datetime.timezone(datetime.timedelta(hours=8))).timestamp())
OUT = os.path.join(ROOT, "data", "analysis", "product_registry.json")

score = json.load(open(os.path.join(ROOT, "data", "analysis", "material_scorecard.json"), encoding="utf-8"))
tiers = {p["productId"]: p.get("priceTier") for p in score.get("products", [])}

agg = {}
for name in ("history", "history2"):
    file = os.path.join(ROOT, "data", name, "materials.jsonl")
    if not os.path.exists(file):
        continue
    with open(file, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            ts = int(row.get("createTime") or 0)
            if not (START <= ts < END):
                continue
            for m in row.get("materials", []):
                pid = m.get("productId") or ""
                if not pid:
                    continue
                d = agg.setdefault(pid, {
                    "productId": pid, "wordings": set(), "cost": 0, "pay": 0,
                    "orders": 0, "plans": 0, "first": 0, "last": 0,
                })
                if m.get("productWording"):
                    d["wordings"].add(m["productWording"])
                d["cost"] += int(m.get("cost") or 0)
                d["pay"] += int(m.get("payGmv") or 0)
                d["orders"] += int(m.get("payPv") or 0)
                d["plans"] += 1
                d["first"] = min(d["first"] or ts, ts)
                d["last"] = max(d["last"], ts)

products = []
for pid, d in agg.items():
    tier = tiers.get(pid) or "other"
    if tier not in ("59.9", "399") and d["pay"] > 0 and d["orders"] > 0:
        aov = d["pay"] / d["orders"] / 100
        tier = "59.9" if 40 <= aov <= 80 else "399" if 300 <= aov <= 600 else "other"
    invalid = pid in common.INVALID_PRODUCTS
    products.append({
        "productId": pid,
        "wordings": sorted(d["wordings"]),
        "tier": tier,
        "costYuan": round(d["cost"] / 100, 2),
        "payYuan": round(d["pay"] / 100, 2),
        "orders": d["orders"],
        "plans": d["plans"],
        "first": d["first"],
        "last": d["last"],
        "invalid": invalid,
        "allowed": tier in ("59.9", "399") and d["cost"] > 0 and not invalid,
    })

products.sort(key=lambda p: -p["costYuan"])
allowed = [p["productId"] for p in products if p["allowed"]]
out = {
    "generatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "window": {"from": "2026-08-01", "to": "2026-11-06"},
    "allowedProductIds": allowed,
    "products": products,
    "storeProducts": common.RULES.get("storeProducts", {}),
}
json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(OUT)
print("products", len(products), "allowed", len(allowed), "other", sum(1 for p in products if p["tier"] == "other"))
for p in products[:10]:
    print(p["productId"], p["tier"], p["costYuan"], p["orders"], p["wordings"][:2], "allowed" if p["allowed"] else "NO")
