# tests/test_session_checklist.py
import os
import tempfile
import unittest

from utils.session_checklist import (
    POST_CHECKS,
    PRE_CHECKS,
    append_post_session,
    write_pre_session,
)

BASE = "P01_drops_20260731_142305"
START_MONO_MS = 1_785_000_000_000
START_SYS_MS = 1_785_000_000_020


def pre_info(**overrides):
    info = {
        "base": BASE,
        "participant_id": "P01",
        "drop_condition": "drops",
        "app_version": "2.0.0",
        "start_unixtime_ms": START_MONO_MS,
        "start_sys_unixtime_ms": START_SYS_MS,
        "timezone": {"name": "JST", "utc_offset": "UTC+09:00", "utc_offset_s": 32400},
        "behave_dir": "/data/P01/20260731/behave",
        "eeg_dir": "/data/P01/20260731/eeg",
        "eeg_expected_name": f"{BASE}_eeg",
    }
    info.update(overrides)
    return info


class SessionChecklistTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self._tmp.name, f"{BASE}_checklist.md")

    def tearDown(self):
        self._tmp.cleanup()

    def read(self):
        with open(self.path, encoding="utf-8") as file:
            return file.read()

    def test_pre_session_contains_session_info(self):
        write_pre_session(self.path, pre_info())
        text = self.read()
        self.assertIn(BASE, text)
        self.assertIn("P01", text)
        self.assertIn("drops", text)
        self.assertIn("2.0.0", text)
        self.assertIn("JST", text)
        self.assertIn("UTC+09:00", text)
        self.assertIn(str(START_SYS_MS), text)

    def test_pre_session_contains_all_pre_checks(self):
        write_pre_session(self.path, pre_info())
        text = self.read()
        for item in PRE_CHECKS:
            self.assertIn(f"- [ ] {item}", text)

    def test_pre_session_does_not_overwrite_existing_checklist(self):
        write_pre_session(self.path, pre_info())
        with self.assertRaises(FileExistsError):
            write_pre_session(self.path, pre_info(participant_id="P02"))
        self.assertNotIn("P02", self.read())

    def test_pre_session_states_eeg_naming_rule(self):
        write_pre_session(self.path, pre_info())
        text = self.read()
        self.assertIn(f"{BASE}_eeg", text)
        self.assertIn("/data/P01/20260731/eeg", text)

    def test_pre_session_states_sync_columns(self):
        write_pre_session(self.path, pre_info())
        text = self.read()
        self.assertIn("SysUnixTime(ms)", text)
        self.assertIn("clock_check", text)
        self.assertIn("timezone_change", text)

    def test_post_session_appends_without_losing_pre(self):
        write_pre_session(self.path, pre_info())
        append_post_session(
            self.path,
            {
                "outcome": "completed",
                "end_unixtime_ms": START_MONO_MS + 3_600_000,
                "end_sys_unixtime_ms": START_SYS_MS + 3_600_000,
                "duration_s": 3600,
                "clock": {"max_drift_ms": 12, "warn_count": 0, "drift_warn_ms": 100},
                "files": [f"{BASE}_block1_results.csv"],
            },
        )
        text = self.read()
        self.assertIn("## 計測前チェック", text)
        self.assertIn("## セッション実績（自動記入）", text)
        self.assertIn("正常終了", text)
        self.assertIn("1時間00分00秒", text)
        self.assertIn("+12 ms", text)
        self.assertIn(f"{BASE}_block1_results.csv", text)
        for item in POST_CHECKS:
            self.assertIn(f"- [ ] {item}", text)

    def test_post_session_marks_abort(self):
        write_pre_session(self.path, pre_info())
        append_post_session(
            self.path,
            {
                "outcome": "aborted",
                "end_unixtime_ms": START_MONO_MS + 60_000,
                "end_sys_unixtime_ms": START_SYS_MS + 60_000,
                "duration_s": 60,
                "clock": {"max_drift_ms": 0, "warn_count": 0, "drift_warn_ms": 100},
                "files": [],
            },
        )
        self.assertIn("中断（Abort）", self.read())

    def test_post_session_flags_drift_warning(self):
        write_pre_session(self.path, pre_info())
        append_post_session(
            self.path,
            {
                "outcome": "completed",
                "end_unixtime_ms": START_MONO_MS + 60_000,
                "end_sys_unixtime_ms": START_SYS_MS + 60_000,
                "duration_s": 60,
                "clock": {"max_drift_ms": -450, "warn_count": 2, "drift_warn_ms": 100},
                "files": [],
            },
        )
        text = self.read()
        self.assertIn("-450 ms", text)
        self.assertIn("警告 2 件", text)
        self.assertIn("clock_drift", text)

    def test_post_session_has_reject_channel_field(self):
        write_pre_session(self.path, pre_info())
        append_post_session(
            self.path,
            {
                "outcome": "completed",
                "end_unixtime_ms": START_MONO_MS,
                "end_sys_unixtime_ms": START_SYS_MS,
                "duration_s": 0,
                "clock": {"max_drift_ms": 0, "warn_count": 0, "drift_warn_ms": 100},
            },
        )
        text = self.read()
        self.assertIn("リジェクトチャンネル", text)
        self.assertIn("エクスポートファイル名", text)


if __name__ == "__main__":
    unittest.main()
