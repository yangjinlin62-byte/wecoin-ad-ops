#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Generate a daily catalog report from data/catalog/latest.json."""
import json, os, time
from collections import Counter

ROOT = r"F:\微信豆投流助手"
SRC = os.path.join(ROOT, "data", "catalog", "latest.json")
OUT = os.path.join(ROOT, "data", "analysis", "catalog_report.md")

def main():
    j = json.load(open(SRC, encoding="utf-8"))
    lines = []
    lines.append("# 视频号带货目录日报")
    lines.append("")
    lines.append("- 同步时间：" + j.get("syncedAt", ""))
    lines.append("- 账号数：" + str(len(j.get("accounts", []))))
    lines.append("")
    lines.append("| 账号 | 视频总数 | 带货可投 | 失效商品链接 | 流量视频（无链接） |")
    lines.append("|---|---:|---:|---:|---:|")
    total = Counter()
    for a in j.get("accounts", []):
        c = a.get("counts", {})
        for k, v in c.items():
            total[k] += v
        lines.append("| %s | %s | %s | %s | %s |" % (a["nickName"], c.get("total", 0), c.get("valid", 0), c.get("invalid", 0), c.get("no_link", 0)))
    lines.append("| **合计** | **%s** | **%s** | **%s** | **%s** |" % (total["total"], total["valid"], total["invalid"], total["no_link"]))
    lines.append("")
    lines.append("## 失效商品链接（排除）")
    lines.append("")
    lines.append("这些是带货视频，但当前商品链接已失效；不进入新建计划。")
    lines.append("")
    for a in j.get("accounts", []):
        inv = [v for v in a.get("videos", []) if v.get("linkStatus") == "invalid"]
        if not inv:
            continue
        lines.append("### " + a["nickName"] + "（" + str(len(inv)) + " 条）")
        for v in inv[:8]:
            lines.append("- `%s` %s → %s（productId %s）" % (
                v.get("exportId", "")[:18], (v.get("desc") or "")[:40], v.get("productWording") or "", v.get("productId") or ""))
        lines.append("")
    lines.append("## 说明")
    lines.append("")
    lines.append("- `valid`：当前有商品链接，可进入选品池。")
    lines.append("- `invalid`：当前有商品链接，但商品链接已失效（例如寻悟文化早前的 3 天训练营链接）。")
    lines.append("- `no_link`：没有商品链接，属于流量视频，不投放。")
    lines.append("")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write("\n".join(lines))
    print(OUT)
    print("total", dict(total))

if __name__ == "__main__":
    main()
