# -*- coding: utf-8 -*-
"""Minimal cross-language rules checks."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import common


class RulesTest(unittest.TestCase):
    def test_authors_are_nine(self):
        self.assertEqual(len(common.AUTHOR_USERNAMES), 9)

    def test_invalid_products_include_known_deleted_links(self):
        for pid in ("14000809072233", "14000801182038", "10000501804864"):
            self.assertIn(pid, common.INVALID_PRODUCTS)

    def test_tier_mapping(self):
        self.assertEqual(common.tier_from_wording("数字创富课闭门私享3天"), "399")
        self.assertEqual(common.tier_from_wording("赢在数字创富3天课"), "59.9")
        self.assertEqual(common.tier_from_wording("未知商品"), "unknown")

    def test_product_registry_has_allowed_products(self):
        import json
        import os
        path = os.path.join(common.ROOT, "data", "analysis", "product_registry.json")
        reg = json.load(open(path, encoding="utf-8"))
        self.assertGreater(len(reg.get("allowedProductIds", [])), 0)
        for p in reg.get("products", []):
            if p.get("allowed"):
                self.assertIn(p["tier"], ("59.9", "399"))
                self.assertFalse(p.get("invalid"))


if __name__ == "__main__":
    unittest.main()
