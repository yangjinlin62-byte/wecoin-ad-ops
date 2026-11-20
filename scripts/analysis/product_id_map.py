# -*- coding: utf-8 -*-
"""Map store product IDs (backend, 1000...) to ad-platform productIds (catalog/orders)."""
import datetime
import json
import os
import re

import common

ROOT = common.ROOT
REG = json.load(open(os.path.join(ROOT, "data", "analysis", "product_registry.json"), encoding="utf-8"))
CAT = json.load(open(os.path.join(ROOT, "data", "catalog2", "latest.json"), encoding="utf-8"))
STORE = common.RULES.get("storeProducts", {})
INVALID = set(common.INVALID_PRODUCTS)

# ad productIds actually seen in catalog / orders
AD_IDS = {p["productId"] for p in REG.get("products", [])}
CATALOG_IDS = {v.get("productId") for a in CAT.get("accounts", []) for v in a.get("videos", []) if v.get("productId")}


def norm(text):
    text = text or ""
    text = re.sub(r"[【】《》\s（）()+\-—_/]", "", text)
    text = text.replace("直播专属", "").replace("3天闭门课", "3天课").replace("三天课", "3天课")
    return text


rows = []
for sid, s in STORE.items():
    exact = sid in AD_IDS or sid in CATALOG_IDS or sid in INVALID
    candidates = []
    if not exact:
        target = norm(s.get("title"))
        for pid in sorted(AD_IDS | CATALOG_IDS):
            p = next((x for x in REG.get("products", []) if x["productId"] == pid), None)
            if not p:
                continue
            if p.get("tier") and s.get("tier") and p["tier"] != s["tier"]:
                continue
            for w in p.get("wordings", []):
                if norm(w) and (norm(w) in target or target in norm(w)):
                    candidates.append({"productId": pid, "tier": p["tier"], "wording": w})
                    break
    rows.append({
        "storeProductId": sid,
        "title": s.get("title"),
        "priceYuan": s.get("priceYuan"),
        "tier": s.get("tier"),
        "status": s.get("status"),
        "exactAdProductId": sid if exact else None,
        "titleCandidates": candidates[:5],
        "note": "ID 完全一致" if exact else ("需按标题/价格人工确认" if candidates else "投流订单/目录中未出现，暂无法映射")
    })

out = {
    "generatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "note": "店铺后台 ID 与投流 productId 不一定一致；exactAdProductId 才是可直接用于建单的 ID。",
    "storeProducts": rows,
}
path = os.path.join(ROOT, "data", "analysis", "product_id_map.json")
json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(path)
for r in rows:
    print(r["storeProductId"], r["status"], "exact" if r["exactAdProductId"] else "no-exact", "candidates", len(r["titleCandidates"]), r["title"][:30])
