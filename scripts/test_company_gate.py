"""公司门槛单元测试。只用标准库，不访问网络，不改 data/official.json。"""
import json, os, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import company_gate as cg

WL_PATH = os.path.join(ROOT, "data", "company_whitelist.json")

class TestWhitelistFile(unittest.TestCase):
    def setUp(self):
        self.wl = cg.load_whitelist(WL_PATH)

    def test_exactly_twenty_and_ranks(self):
        rows = self.wl["top20"]
        self.assertEqual(len(rows), 20)
        self.assertEqual([r["rank"] for r in rows], list(range(1, 21)))
        self.assertEqual(rows[0]["company"], "易方达基金管理有限公司")
        self.assertEqual(rows[19]["company"], "交银施罗德基金管理有限公司")
        self.assertAlmostEqual(rows[19]["mixed_yi"], 837.6572, places=3)
        self.assertEqual(self.wl["unit"], "亿元")
        self.assertEqual(self.wl["period"], "2026-06-30")
        self.assertEqual(self.wl["period_end"], "2026-06-30")
        self.assertIn("GetGmbdChart", self.wl["source_api"])
        self.assertIn("未说明份额是否去重", self.wl["share_class"])

    def test_no_silent_total_or_nonmmf(self):
        self.assertEqual(self.wl["field"], "混合型")
        for item in ("公司总规模排名", "非货币市场公募规模", "权益规模", "单只基金规模"):
            self.assertIn(item, self.wl["not_used"])
        self.assertTrue(any("2026-09-30" in x for x in self.wl["not_used"]))
        self.assertIn("fundType=002", self.wl["classification"])

class TestMatching(unittest.TestCase):
    def setUp(self):
        self.wl = cg.load_whitelist(WL_PATH)

    def test_official_six(self):
        cases = [
            ("国联安基金", False, None),
            ("国联安基金管理有限公司", False, None),
            ("南方基金", True, 8),
            ("南方基金管理股份有限公司", True, 8),
            ("万家基金", False, None),
            ("万家基金管理有限公司", False, None),
            ("鹏华基金", True, 14),
            ("华宝基金", False, None),
            ("富国基金", True, 6),
            ("富国基金管理有限公司", True, 6),
        ]
        for name, expect, rank in cases:
            got = cg.check(name, self.wl)
            self.assertEqual(got["pass"], expect, name)
            if expect:
                self.assertEqual(got["rank"], rank, name)

    def test_missing_company_fails(self):
        for name in (None, "", "  "):
            got = cg.check(name, self.wl)
            self.assertFalse(got["pass"])
            self.assertEqual(got["reason"], "缺基金管理人")

    def test_unloaded_whitelist_fails(self):
        got = cg.check("南方基金", None)
        self.assertFalse(got["pass"])
        self.assertEqual(got["reason"], "白名单未加载")

    def test_no_confuse_similar_names(self):
        # 国联 ≠ 国联安；东方 ≠ 东方红；中信无唯一匹配；华泰无唯一匹配
        self.assertFalse(cg.check("国联基金", self.wl)["pass"])
        self.assertFalse(cg.check("国联", self.wl)["pass"])
        self.assertFalse(cg.check("东方基金", self.wl)["pass"])
        self.assertFalse(cg.check("东方", self.wl)["pass"])
        self.assertTrue(cg.check("东方红资产管理", self.wl)["pass"])
        self.assertEqual(cg.check("东方红资产管理", self.wl)["matched"], "上海东方证券资产管理有限公司")
        self.assertEqual(cg.check("东方红资产管理", self.wl)["rank"], 16)
        self.assertFalse(cg.check("中信", self.wl)["pass"])
        self.assertFalse(cg.check("华泰", self.wl)["pass"])
        self.assertTrue(cg.check("华泰柏瑞基金", self.wl)["pass"])  # 2026-06-30 第17名
        self.assertFalse(cg.check("博时基金", self.wl)["pass"])  # 2026-06-30 已出前二十
        self.assertFalse(cg.check("平安基金", self.wl)["pass"])  # 第21名，卡在门外
        self.assertFalse(cg.check("圆信永丰基金", self.wl)["pass"])
        self.assertTrue(cg.check("汇添富基金", self.wl)["pass"])
        self.assertTrue(cg.check("易方达基金", self.wl)["pass"])

    def test_alias_conflict_rejected(self):
        data = {
            "top20": [
                {"rank": i, "company": "公司%02d基金管理有限公司" % i, "aliases": ["X"] if i in (1, 2) else [], "mixed_yi": 1000 - i}
                for i in range(1, 21)
            ]
        }
        path = os.path.join(tempfile.gettempdir(), "bad_whitelist.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        with self.assertRaises(ValueError):
            cg.load_whitelist(path)

if __name__ == "__main__":
    unittest.main(verbosity=2)
