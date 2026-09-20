import json
import os
import tempfile
import unittest
from types import SimpleNamespace

from utils.external_settings import apply_external_settings, SettingsError


class ExternalSettingsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.config = SimpleNamespace()

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, value):
        path = os.path.join(self._tmp.name, "settings.json")
        with open(path, "w", encoding="utf-8") as file:
            json.dump(value, file)
        return path

    def test_missing_file_keeps_defaults(self):
        self.assertIsNone(apply_external_settings(self.config, self._tmp.name))

    def test_valid_settings_are_applied(self):
        path = self.write(
            {
                "FULLSCREEN": True,
                "PARTICIPANT_SCREEN_INDEX": 1,
                "MONITOR_WIDTH_PX": 1920,
                "MONITOR_WIDTH_MM": 509,
                "VIEWING_DISTANCE_MM": 570,
            }
        )
        self.assertEqual(
            path, apply_external_settings(self.config, self._tmp.name)
        )
        self.assertEqual(1920, self.config.MONITOR_WIDTH_PX)
        self.assertEqual(509, self.config.MONITOR_WIDTH_MM)

    def test_unknown_setting_is_rejected(self):
        self.write({"TYPO_WIDTH": 1920})
        with self.assertRaises(SettingsError):
            apply_external_settings(self.config, self._tmp.name)

    def test_invalid_value_is_rejected(self):
        self.write({"MONITOR_WIDTH_PX": -1})
        with self.assertRaises(SettingsError):
            apply_external_settings(self.config, self._tmp.name)

    def test_invalid_json_is_rejected(self):
        path = os.path.join(self._tmp.name, "settings.json")
        with open(path, "w", encoding="utf-8") as file:
            file.write("{")
        with self.assertRaises(SettingsError):
            apply_external_settings(self.config, self._tmp.name)


if __name__ == "__main__":
    unittest.main()
