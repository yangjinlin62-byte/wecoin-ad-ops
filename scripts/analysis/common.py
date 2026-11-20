# -*- coding: utf-8 -*-
"""Shared Python access to app/config/rules.json."""
import json
import os
from pathlib import Path

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RULES_PATH = os.path.join(ROOT, "app", "config", "rules.json")

with open(RULES_PATH, encoding="utf-8") as f:
    RULES = json.load(f)

INVALID_PRODUCTS = set((RULES.get("invalidProducts") or {}).keys())
ACCOUNTS = {a["id"]: a for a in RULES.get("accounts", [])}
AUTHOR_USERNAMES = [a["username"] for a in RULES.get("authors", [])]


def tier_from_wording(wording):
    text = wording or ""
    if "私享" in text or "罗明荣" in text or "数字创富课闭门" in text or "赢在数字创富课闭门" in text:
        return "399"
    if "直播课" in text or "训练营" in text or "3天课" in text or "数字经济" in text or "数字创富3天" in text:
        return "59.9"
    return "unknown"


def account(account_id):
    if account_id not in ACCOUNTS:
        raise SystemExit("unknown account: " + account_id)
    return ACCOUNTS[account_id]


def work_holds(account_id):
    with open(os.path.join(ROOT,"app","config","work-exclusions.json"), encoding="utf-8") as f:
        ids = {eid for row in json.load(f) for eid in row["ids"]}
    for path in (Path(ROOT)/"data/state/work-evidence").glob("*.json"):
        event = json.loads(path.read_text(encoding="utf-8"))
        if event["type"] == "single_quick_refund" and path.with_suffix(".released").exists():
            continue
        if event.get("globalId"):
            ids.add(event["globalId"])
        if event["account"] == account_id:
            ids.update(event["workIds"])
    return ids


def deleted_videos():
    path = Path(ROOT)/"data/state/deleted_videos.json"
    if not path.exists():
        return set()
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        return {eid for eid in (obj.get("exportIds") or [])}
    except Exception:
        return set()


def original_bundle_ids(by_global, key, holds=()):
    """Historical bundles without a recorded binding version require all members intact."""
    result = []
    for gid in key:
        v = by_global.get(gid)
        if (not v or gid in holds or v.get("fullExportId") in holds or not v.get("fullExportId") or v.get("linkStatus") != "valid"
                or not v.get("productId") or not v.get("realappid") or v.get("hasCart") is False
                or v.get("isPrivate") or v.get("isChecking") or v.get("bindingChangedAt")):
            return []
        result.append(v["fullExportId"])
    return result


def attach_bindings(plans, by_global):
    by_full = {v.get("fullExportId"): v for v in by_global.values()}
    for plan in plans:
        plan["materials"] = [dict(exportId=eid, productId=by_full[eid]["productId"],
                                  realappid=by_full[eid].get("realappid")) for eid in plan["exportIds"]]
