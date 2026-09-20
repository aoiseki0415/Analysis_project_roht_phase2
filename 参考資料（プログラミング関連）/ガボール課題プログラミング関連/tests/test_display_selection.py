import unittest

from utils.display_selection import (
    consume_single_screen_test_flag,
    resolve_screen_index,
    split_single_screen_geometry,
)


class ResolveScreenIndexTests(unittest.TestCase):
    def test_uses_requested_secondary_screen(self):
        self.assertEqual(resolve_screen_index(1, 2), 1)

    def test_falls_back_to_primary_when_screen_is_missing(self):
        self.assertEqual(resolve_screen_index(1, 1), 0)

    def test_falls_back_to_primary_for_invalid_value(self):
        self.assertEqual(resolve_screen_index("participant", 2), 0)

    def test_rejects_empty_screen_list(self):
        with self.assertRaises(ValueError):
            resolve_screen_index(0, 0)


class SingleScreenTestModeTests(unittest.TestCase):
    def test_consumes_single_screen_test_flag(self):
        args, enabled = consume_single_screen_test_flag(
            ["main.py", "--single-screen-test"]
        )
        self.assertEqual(["main.py"], args)
        self.assertTrue(enabled)

    def test_leaves_normal_arguments_unchanged(self):
        args, enabled = consume_single_screen_test_flag(["main.py", "-style", "Fusion"])
        self.assertEqual(["main.py", "-style", "Fusion"], args)
        self.assertFalse(enabled)

    def test_splits_screen_into_non_overlapping_halves(self):
        left, right = split_single_screen_geometry(0, 25, 1710, 1080, gap=12)
        self.assertEqual((0, 25, 849, 1080), left)
        self.assertEqual((861, 25, 849, 1080), right)

    def test_rejects_invalid_geometry(self):
        with self.assertRaises(ValueError):
            split_single_screen_geometry(0, 0, 1, 100)


if __name__ == "__main__":
    unittest.main()
