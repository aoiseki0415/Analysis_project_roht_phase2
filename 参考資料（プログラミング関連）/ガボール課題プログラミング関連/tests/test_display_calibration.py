import math
import unittest
from types import SimpleNamespace

from utils.display_calibration import px_per_mm, resolve_geometry, visual_deg_to_mm


def make_cfg(**overrides):
    base = dict(
        MONITOR_WIDTH_PX=None,
        MONITOR_WIDTH_MM=None,
        VIEWING_DISTANCE_MM=570,
        PATCH_SIZE_DEG=0.68,
        SPATIAL_FREQ_CPD=4.41,
        CIRCLE_DIAMETER_MM=210,
        REVOLUTION_PERIOD_S=20.0,
        FRAME_INTERVAL_MS=16,
        FALLBACK_PATCH_DIAMETER_PX=40,
        FALLBACK_CYCLES_PER_PATCH=2.5,
        FALLBACK_RADIUS_RATIO=0.3,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class PxPerMmTests(unittest.TestCase):
    def test_none_or_zero_inputs_return_none(self):
        self.assertIsNone(px_per_mm(None, 531))
        self.assertIsNone(px_per_mm(1920, None))
        self.assertIsNone(px_per_mm(0, 531))
        self.assertIsNone(px_per_mm(1920, 0))

    def test_valid_inputs_return_ratio(self):
        self.assertAlmostEqual(1920 / 531, px_per_mm(1920, 531))


class VisualDegToMmTests(unittest.TestCase):
    def test_matches_reference_formula(self):
        expected = 2 * 570 * math.tan(math.radians(0.68) / 2)
        self.assertAlmostEqual(expected, visual_deg_to_mm(0.68, 570))


class ResolveGeometryTests(unittest.TestCase):
    def test_uncalibrated_uses_fallback_values(self):
        result = resolve_geometry(make_cfg())
        self.assertFalse(result["calibrated"])
        self.assertEqual(40, result["patch_diameter_px"])
        self.assertEqual(2.5, result["cycles_per_patch"])
        self.assertIsNone(result["radius_px"])

    def test_calibrated_example_531mm_1920px(self):
        cfg = make_cfg(MONITOR_WIDTH_PX=1920, MONITOR_WIDTH_MM=531)
        result = resolve_geometry(cfg)
        self.assertTrue(result["calibrated"])

        ppmm = 1920 / 531
        expected_patch_px = round(2 * 570 * math.tan(math.radians(0.68) / 2) * ppmm)
        self.assertEqual(expected_patch_px, result["patch_diameter_px"])
        self.assertAlmostEqual(210 / 2 * ppmm, result["radius_px"], places=3)
        self.assertAlmostEqual(4.41 * 0.68, result["cycles_per_patch"], places=6)

    def test_deg_per_frame_default_config(self):
        result = resolve_geometry(make_cfg())
        self.assertAlmostEqual(0.288, result["deg_per_frame"], places=3)


if __name__ == "__main__":
    unittest.main()
