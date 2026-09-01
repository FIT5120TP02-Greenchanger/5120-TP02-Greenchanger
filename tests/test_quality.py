import unittest

from greenchanger_data.quality import validate_records


class QualityTests(unittest.TestCase):
    RULES = [
        {"code": "REQUIRED", "type": "required", "fields": ["id", "value"]},
        {"code": "UNIQUE", "type": "unique", "fields": ["id"]},
        {
            "code": "RANGE",
            "type": "range",
            "field": "value",
            "minimum": 0,
            "maximum": 100,
        },
    ]

    def test_valid_records_pass_gate(self):
        records = [{"id": "a", "value": "10"}, {"id": "b", "value": 100}]
        report = validate_records("fixture", records, self.RULES)

        self.assertTrue(report.passed_gate)
        self.assertEqual(report.pass_rate, 100.0)
        self.assertEqual(report.failing_records, 0)

    def test_failures_are_calculated_at_record_level(self):
        records = [
            {"id": "a", "value": "10"},
            {"id": "a", "value": "101"},
            {"id": "", "value": "50"},
        ]
        report = validate_records("fixture", records, self.RULES)

        self.assertFalse(report.passed_gate)
        self.assertEqual(report.failing_records, 3)
        self.assertEqual(report.pass_rate, 0.0)
        self.assertEqual(report.failed_indices, (0, 1, 2))

    def test_empty_dataset_fails_gate(self):
        report = validate_records("fixture", [], self.RULES)
        self.assertFalse(report.passed_gate)
        self.assertEqual(report.pass_rate, 0.0)


if __name__ == "__main__":
    unittest.main()
