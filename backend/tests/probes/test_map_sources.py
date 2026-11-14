import json
import unittest
from pathlib import Path
from tools import probe_maps

REFERENCE_DIR = Path(__file__).resolve().parents[3] / "contracts" / "reference" / "maps"


class MapSourceParsingTests(unittest.TestCase):
    def test_terrain_probe_uses_a_bounded_exact_range(self):
        class Response:
            def __init__(self, status, headers, body=b""):
                self.status = status
                self.headers = headers
                self.body = body

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def read(self, limit):
                self.read_limit = limit
                return self.body

        class Opener:
            def __init__(self, responses):
                self.responses = iter(responses)
                self.requests = []

            def open(self, request, timeout):
                self.requests.append((request, timeout))
                return next(self.responses)

        opener = Opener([
            Response(200, {"content-length": "100"}),
            Response(206, {"content-range": "bytes 0-7/100"}, b"12345678"),
        ])
        result = probe_maps.head_and_range(
            opener, probe_maps.DEM_SOURCES["connecting_ridge_5m"][0], 8, 3
        )
        self.assertEqual(result["range_bytes_read"], 8)
        self.assertEqual(result["content_range"], "bytes 0-7/100")
        self.assertEqual([request.get_method() for request, _ in opener.requests], ["HEAD", "GET"])
        self.assertEqual(opener.requests[1][0].get_header("Range"), "bytes=0-7")
        self.assertEqual(opener.requests[1][1], 3)

    def test_terrain_probe_rejects_wrong_range_responses(self):
        class Response:
            def __init__(self, status, headers, body=b""):
                self.status = status
                self.headers = headers
                self.body = body

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def read(self, limit):
                return self.body

        class Opener:
            def __init__(self):
                self.responses = iter([
                    Response(200, {"content-length": "100"}),
                    Response(206, {"content-range": "bytes 1-8/100"}, b"12345678"),
                ])

            def open(self, request, timeout):
                return next(self.responses)

        with self.assertRaisesRegex(ValueError, "exact bounded byte-range"):
            probe_maps.head_and_range(
                Opener(), probe_maps.DEM_SOURCES["connecting_ridge_5m"][0], 8, 3
            )

    def test_saved_global_capabilities_preserve_crs_units_and_extent(self):
        document = (REFERENCE_DIR / "moon_trek_global_capabilities.xml").read_bytes()
        layer = probe_maps.parse_wmts(document)["layers"][0]
        self.assertEqual(layer["id"], "LRO_WAC_Mosaic_Global_303ppd_v02")
        self.assertEqual(layer["tile_matrix_set"], "default028mm")
        self.assertEqual(layer["crs"], "urn:ogc:def:crs:EPSG::104903")
        self.assertEqual(layer["coordinate_units"], "degrees")
        self.assertEqual(layer["extent"], [-180, -90, 180, 90])
        self.assertEqual(layer["formats"], ["image/jpeg"])

    def test_saved_south_pole_capabilities_preserve_unresolved_crs_and_units(self):
        document = (REFERENCE_DIR / "moon_trek_south_pole_capabilities.xml").read_bytes()
        layer = probe_maps.parse_wmts(document)["layers"][0]
        self.assertEqual(layer["id"], "WAC_POLE_ILL_PCT_SOUTH_100M")
        self.assertEqual(layer["crs"], "urn:ogc:def:crs:EPSG::0")
        self.assertIsNone(layer["coordinate_units"])
        self.assertEqual(layer["formats"], ["image/png"])

    def test_missing_layer_id_is_rejected(self):
        document = (REFERENCE_DIR / "moon_trek_global_capabilities.xml").read_bytes()
        with self.assertRaisesRegex(ValueError, "Expected WMTS layer ID is absent"):
            probe_maps.parse_wmts(document, "unverified-layer")

    def test_malformed_or_unsafe_capabilities_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Malformed WMTS"):
            probe_maps.parse_wmts(b"<Capabilities>")
        with self.assertRaisesRegex(ValueError, "DTD or entity"):
            probe_maps.parse_wmts(b"<!DOCTYPE x><Capabilities/>")
        document = (REFERENCE_DIR / "moon_trek_global_capabilities.xml").read_bytes()
        with self.assertRaisesRegex(ValueError, "malformed extent"):
            probe_maps.parse_wmts(document.replace(b"-180.0 -90.0", b"NaN -90.0", 1))

    def test_saved_lroc_wms_capabilities_preserve_lunar_crs_and_image_formats(self):
        document = (REFERENCE_DIR / "lroc_wms_capabilities.xml").read_bytes()
        parsed = probe_maps.parse_wms(document)
        layer = next(item for item in parsed["layers"] if item["id"] == "luna_wac_roi_south_summer")
        self.assertEqual(layer["crs"], "IAU2000:30100")
        self.assertEqual(layer["coordinate_units"], "degrees")
        self.assertEqual(parsed["formats"][0], "image/png")

    def test_visual_products_are_not_classified_as_numerical_terrain(self):
        self.assertEqual(probe_maps.classify_product("GeoTIFF", True), "numerical_terrain")
        self.assertEqual(
            probe_maps.classify_product("GeoTIFF", False), "imagery_or_derived_visualization"
        )
        self.assertEqual(
            probe_maps.classify_product("image/png", False), "imagery_or_derived_visualization"
        )

    def test_catalog_matches_the_agreed_layer_response_shape(self):
        catalog_path = REFERENCE_DIR.parent.parent / "catalog" / "map_layers.json"
        catalog = json.loads(catalog_path.read_text())
        required = {
            "id",
            "name",
            "provider",
            "service_type",
            "crs_id",
            "coordinate_units",
            "extent",
            "attribution",
            "source_url",
            "tile_matrix_set",
            "access_url_template",
        }
        self.assertEqual(set(catalog), {"items"})
        for layer in catalog["items"]:
            self.assertEqual(set(layer), required)
            self.assertIn(layer["provider"], {"moon_trek", "lroc"})
            self.assertIn(layer["service_type"], {"wmts", "wms"})
            self.assertIn(layer["coordinate_units"], {"degrees", "metres"})
            self.assertEqual(len(layer["extent"]), 4)
        self.assertNotIn("WAC_POLE_ILL_PCT_SOUTH_100M", {item["id"] for item in catalog["items"]})

    def test_saved_dem_header_observations_are_numeric_terrain_not_display_images(self):
        observations = json.loads((REFERENCE_DIR / "pgda_dem_header_observations.json").read_text())
        for product in [*observations["site_products"], observations["regional_pole_product"]]:
            self.assertEqual(product["bits_per_sample"], 32)
            self.assertEqual(product["sample_format"], "IEEE floating point")
            self.assertEqual(product["no_data"], "nan")
            self.assertEqual(probe_maps.classify_product("GeoTIFF", True), "numerical_terrain")
        regional = observations["regional_pole_product"]
        self.assertIn("south pole", regional["documented_footprint"])
        self.assertEqual(regional["range_status"], 206)


if __name__ == "__main__":
    unittest.main()
