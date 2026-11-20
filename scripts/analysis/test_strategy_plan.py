import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import strategy_plan as planner
from strategy_review import review


class StrategyTest(unittest.TestCase):
    def test_original_bundle_requires_every_member(self):
        live = dict(fullExportId="x",productId="p",realappid="s",linkStatus="valid")
        by = {"x":live,"y":dict(live,fullExportId="y")}
        self.assertEqual(planner.common.original_bundle_ids(by, ["x","y"]), ["x","y"])
        self.assertEqual(planner.common.original_bundle_ids(by, ["x","missing"]), [])
        by["y"]["bindingChangedAt"] = "2026-11-08"
        self.assertEqual(planner.common.original_bundle_ids(by, ["x","y"]), [])

    def test_budget_pairs_change_only_budget_and_alternate_order(self):
        pool = {i: dict(exportId=str(i), authorId="one", recent=[0]*4, prior=[0]*4, created=i)
                for i in range(10)}
        with tempfile.TemporaryDirectory() as tmp, patch.object(planner.common, "ROOT", tmp), patch.object(
                planner, "candidates", return_value=(datetime.now(timezone.utc), {"sku": pool})):
            plans = planner.build("account2","budget-test","59.9",4,42,90,300,600)["plans"]
            self.assertEqual([p["budgetYuan"] for p in plans], [300,600,600,300])
            for first, second in (plans[:2],plans[2:]):
                for field in ("account","tier","exportIds","target","bidKind","bidValue","materials"):
                    self.assertEqual(first[field], second[field])
                self.assertEqual(first["strategy"]["comparison"], second["strategy"]["comparison"])
            with self.assertRaises(ValueError):
                planner.build("account2","budget-test","59.9",3,42,90,300,600)

    def test_review_changes_only_matching_future_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)/"data"
            history = data/"history"
            history.mkdir(parents=True)
            mat = dict(exportId="video-a", authorId="author", signal="观察", recent=[100,0,0,1],
                       prior=[0]*4, created=1)
            with patch.object(planner.common, "ROOT", tmp), patch.object(planner, "candidates",
                    return_value=(datetime.now(timezone.utc), {"sku": {"video-a": mat}})):
                draft = planner.build("account1", "single-test", "59.9", 1)
                row = dict(promotionId="order", spend=5000, target=42, budget=30000,
                           materials=[dict(exportId="video-a", productId="sku", netPv=0, netGmv=0)])
                (history/"materials.jsonl").write_text(json.dumps(row), encoding="utf-8")
                result = review(draft, {"1":{"promotionId":"order","decision":"暂缓复制","reason":"合成复核样本"}}, data)
                review_dir = data/"analysis/strategy-reviews"
                review_dir.mkdir(parents=True)
                (review_dir/"account1-single-test-1.json").write_text(json.dumps(result), encoding="utf-8")
                self.assertEqual(planner.build("account1","single-test","59.9",1)["count"], 0)
                self.assertEqual(planner.build("account1","single-test","59.9",1,bid_override=91)["count"], 1)
                self.assertEqual(review(draft, {}, data)["groups"][0]["decision"], "待补证")
                row["materials"][0]["netPv"] = None
                (history/"materials.jsonl").write_text(json.dumps(row), encoding="utf-8")
                self.assertEqual(review(draft, {"1":{"promotionId":"order"}}, data)["groups"][0]["decision"], "待补证")
