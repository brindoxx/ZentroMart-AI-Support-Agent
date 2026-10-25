"""Exercise CSV edge cases and prevent row values entering inspection reports."""

import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from zentromart.config import PROJECT_ROOT
from zentromart.dataset import (
    TableSpec, check_relationship, inspect_dataset, read_table, summarize_table,
)


class DatasetTests(unittest.TestCase):
    def read_fixture(self, text):
        with patch.object(Path, "open", return_value=io.StringIO(text, newline="")):
            return read_table(Path("fixture.csv"))

    def test_csv_preserves_leading_zeros_blanks_and_multiline_values(self):
        columns, rows = self.read_fixture(
            'order_id,transcript,refund_reference\r\n'
            '00123456,"customer: hello\nagent: welcome",\r\n'
        )
        self.assertEqual(columns, ["order_id", "transcript", "refund_reference"])
        self.assertEqual(rows[0]["order_id"], "00123456")
        self.assertEqual(rows[0]["refund_reference"], "")
        self.assertEqual(rows[0]["transcript"], "customer: hello\nagent: welcome")

    def test_malformed_csv_is_rejected_without_echoing_cell_contents(self):
        for text in (
            "id,id\n1,2\n", "id,\n1,2\n", "id,text\n1\n",
            "id,text\n1,2,3\n", 'id,text\n1,"unclosed', "",
        ):
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.read_fixture(text)

    def test_primary_key_check_uses_the_whole_composite_key(self):
        rows = [
            {"order_id": "01", "line_no": "1", "name": "PRIVATE_SENTINEL"},
            {"order_id": "01", "line_no": "2", "name": "PRIVATE_SENTINEL"},
            {"order_id": "01", "line_no": "2", "name": "PRIVATE_SENTINEL"},
            {"order_id": "02", "line_no": "", "name": "PRIVATE_SENTINEL"},
        ]
        summary = summarize_table(
            ["order_id", "line_no", "name"], rows,
            TableSpec("items.csv", ("order_id", "line_no"), 4),
        )
        self.assertEqual(summary["duplicate_key_rows"], 1)
        self.assertEqual(summary["blank_key_rows"], 1)
        self.assertEqual(summary["empty_cells"]["line_no"], 1)
        self.assertNotIn("PRIVATE_SENTINEL", json.dumps(summary))

    def test_missing_key_column_is_reported_clearly(self):
        with self.assertRaisesRegex(ValueError, "missing required columns: order_id"):
            summarize_table(["name"], [], TableSpec("items.csv", ("order_id",), 0))

    def test_relationship_check_distinguishes_missing_parent_and_blank(self):
        result = check_relationship(
            [{"customer_id": "C01"}, {"customer_id": "C99"}, {"customer_id": ""}],
            "customer_id", [{"id": "C01"}], "id",
        )
        self.assertEqual(result, {
            "checked_rows": 2, "blank_reference_rows": 1, "broken_reference_rows": 1
        })

    def test_supplied_dataset_report_contains_only_aggregates_and_schema(self):
        report = inspect_dataset(PROJECT_ROOT / "dataset")
        self.assertEqual(report["issues"], [])
        self.assertEqual(report["tables"]["orders"]["rows"], 1000)
        self.assertEqual(report["knowledge_base"]["unique_sections"], 84)
        self.assertEqual(report["practice"]["conversations"], 23)
        _, customers = read_table(PROJECT_ROOT / "dataset/data/customers.csv")
        serialized = json.dumps(report)
        for field in ("phone", "email", "name"):
            self.assertNotIn(customers[0][field], serialized)
        _, questions = read_table(PROJECT_ROOT / "dataset/practice/questions.csv")
        self.assertNotIn(questions[0]["reference_answer"], serialized)


if __name__ == "__main__":
    unittest.main()
