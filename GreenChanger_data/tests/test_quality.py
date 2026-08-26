import unittest

from greenchanger_data.quality import validate_record_stream, validate_records


class QualityTests(unittest.TestCase):
    def test_stream_validation_detects_duplicates_across_records(self):
        rows = [
            {"source_address_id": "1", "full_address": "One", "geometry_wkt": "POINT (1 1)"},
            {"source_address_id": "1", "full_address": "Duplicate", "geometry_wkt": "POINT (2 2)"},
            {"source_address_id": "2", "full_address": "Two", "geometry_wkt": "POINT (3 3)"},
        ]
        rules = [
            {"code": "REQ", "type": "required", "fields": ["source_address_id", "full_address", "geometry_wkt"]},
            {"code": "UNIQUE", "type": "unique", "fields": ["source_address_id"]},
        ]
        report = validate_record_stream("address", lambda: iter(rows), rules, threshold_pct=95)
        self.assertEqual(report.total_records, 3)
        self.assertEqual(report.failed_indices, (0, 1))
        self.assertFalse(report.passed_gate)

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

    def test_gate_uses_unrounded_rate(self):
        records = [{"id": "a"}, {"id": ""}, {"id": ""}]
        rules = [{"code": "REQUIRED", "type": "required", "fields": ["id"]}]
        report = validate_records("fixture", records, rules, threshold_pct=33.332)
        self.assertEqual(report.pass_rate, 33.33)
        self.assertTrue(report.passed_gate)


if __name__ == "__main__":
    unittest.main()
