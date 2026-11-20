#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Generate a 10-plan preview from the material scorecard + catalog."""
import json, os, time, sys
from collections import defaultdict

ROOT = r"F:\微信豆投流助手"
ACCOUNT = sys.argv[1] if len(sys.argv) > 1 else "account2"
COUNT = int(sys.argv[2]) if len(sys.argv) > 2 else 10
SCORE = os.path.join(ROOT, "data", "analysis", "material_scorecard.json")
CATALOG = os.path.join(ROOT, "data", "catalog2" if ACCOUNT == "account2" else "catalog", "latest.json")
if not os.path.exists(CATALOG):
    CATALOG = os.path.join(ROOT, "data", "catalog", "latest.json")
OUT_JSON = os.path.join(ROOT, "data", "analysis", "plan_preview.json")
OUT_MD = os.path.join(ROOT, "data", "analysis", "plan_preview.md")

TARGET_NAMES = {"8": "成交数", "11": "成交ROI", "40": "净ROI", "42": "净成交数"}

def tier_from_wording(w):
    text = w or ""
    if "私享" in text or "罗明荣" in text or "数字创富课闭门" in text or "赢在数字创富课闭门" in text:
        return "399"
    if "直播课" in text or "训练营" in text or "3天课" in text or "数字经济" in text or "数字创富3天" in text:
        return "59.9"
    return "unknown"

def build_catalog():
    j = json.load(open(CATALOG, encoding="utf-8"))
    by_global = {}
    by_export = {}
    valid = []
    for a in j.get("accounts", []):
        for v in a.get("videos", []):
            if v.get("globalExportId"):
                by_global[v["globalExportId"]] = v
            if v.get("fullExportId"):
                by_export[v["fullExportId"]] = v
            if v.get("linkStatus") == "valid":
                valid.append(v)
    return by_global, by_export, valid

def spec_for(tier, layer, index):
    """Return list of (target, bidKind, bidValue, budgetYuan)."""
    if tier == "399":
        if layer == "S":
            return [
                (40, "roi", 0.8, 600),
                (42, "wecoin", 500, 600),
            ][index % 2:index % 2 + 1] or [(40, "roi", 0.8, 600)]
        return [(40, "roi", 0.8, 600 if layer == "A" else 300)]
    # 59.9 / unknown
    if layer == "S":
        return [
            (8, "wecoin", 90, 600),
            (11, "roi", 0.7, 600),
            (42, "wecoin", 90, 600),
        ][index % 3:index % 3 + 1] or [(8, "wecoin", 90, 600)]
    return [(8, "wecoin", 90, 600 if layer == "A" else 300)]

def main():
    sc = json.load(open(SCORE, encoding="utf-8"))
    products = {p["productId"]: p for p in sc.get("products", [])}
    by_global, by_export, valid_videos = build_catalog()
    scored_globals = set()
    rows = []

    for m in sc.get("materials", []):
        key = m.get("globalExportId") or ""
        cat = by_global.get(key) or by_export.get(m.get("materialId") or "")
        if key:
            scored_globals.add(key)
        if cat:
            status = cat.get("linkStatus")
            export_id = cat.get("fullExportId")
            product_id = cat.get("productId")
            product_wording = cat.get("productWording")
            author = cat.get("author")
            desc = cat.get("desc")
        else:
            status = "invalid" if m.get("invalidProduct") else "unknown"
            export_id = m.get("globalExportId") or ""
            product_id = (m.get("productIds") or [""])[0]
            product_wording = (m.get("productWordings") or [""])[0]
            author = (m.get("authors") or [""])[0]
            desc = ""
        if status in ("invalid", "no_link"):
            continue
        account_export = (m.get("exportIds") or {}).get(ACCOUNT)
        if account_export:
            export_id = account_export
        # tier from catalog productId, else from material productIds
        tier = None
        for pid in ([product_id] if product_id else []) + list(m.get("productIds") or []):
            p = products.get(pid)
            if p and p.get("priceTier") in ("59.9", "399"):
                tier = p["priceTier"]
                break
        if tier is None:
            tier = tier_from_wording(product_wording)
        rows.append({
            "layer": m["layer"],
            "key": m["key"],
            "exportId": export_id,
            "materialId": m.get("materialId"),
            "author": author,
            "desc": desc,
            "productId": product_id,
            "productWording": product_wording,
            "tier": tier or "unknown",
            "orders": m["orders"],
            "cost": m["cost"],
            "pay": m["pay"],
            "roi": m["roi"],
            "cpa": m["cpa"],
            "plans": m["plans"],
            "recent7Orders": m["recent7Orders"],
        })

    s = [x for x in rows if x["layer"] == "S"]
    a = [x for x in rows if x["layer"] == "A"]
    # N: valid catalog videos never scored
    n = []
    for v in valid_videos:
        gid = v.get("globalExportId") or ""
        if gid and gid in scored_globals:
            continue
        if not gid:
            continue
        n.append({
            "layer": "N",
            "key": gid,
            "exportId": v.get("fullExportId"),
            "materialId": v.get("exportId"),
            "author": v.get("author"),
            "desc": v.get("desc"),
            "productId": v.get("productId"),
            "productWording": v.get("productWording"),
            "tier": ((products.get(v.get("productId") or "") or {}).get("priceTier")) or tier_from_wording(v.get("productWording")) or "unknown",
            "orders": 0, "cost": 0, "pay": 0, "roi": 0, "cpa": 0, "plans": 0, "recent7Orders": 0,
            "createTime": v.get("createTime", 0),
            "likeCount": v.get("likeCount", 0),
            "forwardCount": v.get("forwardCount", 0),
        })
    n.sort(key=lambda x: (x.get("createTime", 0), x.get("likeCount", 0)), reverse=True)

    s_n = min(len(s), 5 if COUNT <= 10 else 8)
    n_n = min(len(n), 2 if COUNT <= 10 else 4)
    a_n = max(0, COUNT - s_n - n_n)
    selected = []
    for i, x in enumerate(s[:s_n]):
        selected.append((x, spec_for(x["tier"], "S", i)))
    for i, x in enumerate(a[:a_n]):
        selected.append((x, spec_for(x["tier"], "A", i)))
    for i, x in enumerate(n[:n_n]):
        selected.append((x, spec_for(x["tier"], "N", i)))
    # 补齐
    for i, x in enumerate(a[a_n:]):
        if len(selected) >= COUNT:
            break
        selected.append((x, spec_for(x["tier"], "A", i + a_n)))
    for i, x in enumerate(n[n_n:]):
        if len(selected) >= COUNT:
            break
        selected.append((x, spec_for(x["tier"], "N", i + n_n)))

    preview = []
    for x, specs in selected:
        for (target, bid_kind, bid_value, budget) in specs:
            preview.append({
                "account": ACCOUNT,
                "layer": x["layer"],
                "exportId": x["exportId"] or x.get("globalExportId"),
                "materialId": x["materialId"],
                "author": x["author"],
                "desc": x["desc"],
                "productId": x["productId"],
                "productWording": x["productWording"],
                "tier": x["tier"],
                "target": target,
                "targetName": TARGET_NAMES.get(str(target), str(target)),
                "bidKind": bid_kind,
                "bidValue": bid_value,
                "budgetYuan": budget,
                "history": {
                    "orders": x["orders"],
                    "cost": x["cost"],
                    "pay": x["pay"],
                    "roi": x["roi"],
                    "cpa": x["cpa"],
                    "plans": x["plans"],
                    "recent7Orders": x["recent7Orders"],
                },
            })

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    json.dump({"generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S"), "plans": preview}, open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    lines = ["# 首波 %d 条计划预览" % COUNT, ""]
    lines.append("| # | 层 | 素材 | 作者 | 商品层 | 目标 | 出价 | 预算 | 历史订单 | 历史ROI | CPA |")
    lines.append("|---:|---|---|---|---|---|---:|---:|---:|---:|---:|")
    for i, p in enumerate(preview, 1):
        bid = ("ROI " + str(p["bidValue"])) if p["bidKind"] == "roi" else (str(p["bidValue"]) + " 元")
        lines.append("| %d | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            i, p["layer"], (p["desc"] or p["exportId"])[:24], p["author"], p["tier"],
            p["targetName"], bid, p["budgetYuan"], p["history"]["orders"], p["history"]["roi"], p["history"]["cpa"]))
    lines.append("")
    lines.append("说明：S/A 来自素材级历史，N 来自当前有链接但没投过的视频。")
    open(OUT_MD, "w", encoding="utf-8").write("\n".join(lines))
    print(OUT_JSON)
    print(OUT_MD)
    print("S", len(s), "A", len(a), "N", len(n), "plans", len(preview))

if __name__ == "__main__":
    main()
