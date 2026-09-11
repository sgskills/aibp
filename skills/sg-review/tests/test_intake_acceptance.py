"""Independent intake edge cases, all synthetic; frozen before implementation."""
from __future__ import annotations
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(os.environ.get("SG_REVIEW_ROOT", Path(__file__).resolve().parents[1])).resolve()
sys.path.insert(0, str(ROOT / "scripts"))
import review_stats as runtime


class IntakeAcceptanceTests(unittest.TestCase):
    def test_conflicting_synonym_text_fields_do_not_silently_choose_first(self):
        data = {"reviews": [{"review_text": "合成评价：包装完整", "评价正文": "合成评价：包装破损"}]}
        try:
            result = runtime.analyze_payload(data)
        except runtime.ReviewInputError:
            return
        self.assertEqual(result["audit"]["valid_review_count"], 0)
        self.assertEqual(result["normalized_reviews"], [])

    def test_objects_and_arrays_are_not_review_text(self):
        for text in ({"instruction": "合成对象不应当作正文"}, ["合成数组不应当作正文"]):
            with self.subTest(text=text):
                try:
                    result = runtime.analyze_payload({"reviews": [{"review_text": text}]})
                except runtime.ReviewInputError:
                    continue
                self.assertEqual(result["audit"]["valid_review_count"], 0)

    def test_csv_excess_cells_are_not_silently_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "synthetic.csv"
            path.write_text("review_text,rating\n合成评价,5,额外未映射敏感值\n", encoding="utf-8")
            with self.assertRaises(runtime.ReviewInputError):
                runtime.load_input(path)

    def test_decimal_rating_number_and_string_have_same_meaning(self):
        for rating in (1, 1.5, 2.7, 4.5, 5):
            with self.subTest(rating=rating):
                self.assertEqual(runtime.parse_rating(rating), runtime.parse_rating(str(rating)))
        for invalid in ("0.5", "5.1", "NaN", "Infinity"):
            self.assertIsNone(runtime.parse_rating(invalid))


if __name__ == "__main__":
    unittest.main()
