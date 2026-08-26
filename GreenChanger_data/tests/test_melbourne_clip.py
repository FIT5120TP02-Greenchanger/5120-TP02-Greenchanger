import unittest

from unittest.mock import patch

from greenchanger_script.clip_to_melbourne import TARGETS, parse_args, transformation_checksum


class MelbourneClipTests(unittest.TestCase):
    def test_all_priority_one_targets_are_configured(self):
        self.assertEqual(set(TARGETS), {"address", "property", "heat", "canopy"})

    def test_spatial_membership_is_explicit(self):
        self.assertEqual(TARGETS["address"]["membership"], "point_inside")
        self.assertEqual(TARGETS["property"]["membership"], "polygon_intersects")
        self.assertEqual(TARGETS["heat"]["membership"], "cell_centroid_inside")
        self.assertEqual(TARGETS["canopy"]["membership"], "cell_centroid_inside")

    def test_checksum_is_deterministic_and_target_specific(self):
        first = transformation_checksum("input", "area", "heat")
        self.assertEqual(first, transformation_checksum("input", "area", "heat"))
        self.assertNotEqual(first, transformation_checksum("input", "area", "canopy"))

    def test_targets_may_be_omitted_to_run_all(self):
        with patch("sys.argv", ["clip_to_melbourne.py", "--confirm-shared"]):
            arguments = parse_args()
        self.assertEqual(arguments.targets, [])


if __name__ == "__main__":
    unittest.main()
