import tempfile
from pathlib import Path
import unittest

import numpy as np
from pyproj import Transformer
import rasterio
from rasterio.transform import from_origin

from greenchanger_data.dea_land_cover import (
    aggregate_land_cover,
    continental_cog_url,
)


class DeaLandCoverTests(unittest.TestCase):
    def test_official_cog_url_is_versioned(self):
        url = continental_cog_url(2025)
        self.assertIn("ga_ls_landcover_class_cyear_3/2-0-0", url)
        self.assertTrue(url.endswith("2025--P1Y_level3.tif"))

    def test_level3_pixels_are_aggregated_to_percentages(self):
        to_map = Transformer.from_crs(4326, 7855, always_xy=True)
        to_wgs = Transformer.from_crs(7855, 4326, always_xy=True)
        centre_x, centre_y = to_map.transform(144.96, -37.81)
        left = centre_x - 500
        top = centre_y + 500
        values = np.full((10, 10), 112, dtype="uint8")
        values[:, 5:] = 215
        west, south = to_wgs.transform(left, top - 1000)
        east, north = to_wgs.transform(left + 1000, top)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "land_cover.tif"
            with rasterio.open(
                path, "w", driver="GTiff", height=10, width=10, count=1,
                dtype="uint8", crs="EPSG:7855",
                transform=from_origin(left, top, 100, 100), nodata=255,
            ) as destination:
                destination.write(values, 1)
            rows = list(aggregate_land_cover(
                path, year=2025, bbox_wgs84=(west, south, east, north),
                grid_size_m=500,
            ))

        self.assertGreaterEqual(len(rows), 4)
        for row in rows:
            total = sum(row[field] for field in (
                "cultivated_vegetation_pct",
                "natural_terrestrial_vegetation_pct",
                "natural_aquatic_vegetation_pct",
                "artificial_surface_pct",
                "natural_bare_surface_pct",
                "water_pct",
            ))
            self.assertAlmostEqual(total, 100.0, places=2)
            self.assertIn(row["dominant_level3_code"], (112, 215))


if __name__ == "__main__":
    unittest.main()
