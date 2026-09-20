import csv
import os
import tempfile
import unittest

from utils.event_logger import EventLogger


class EventLoggerTests(unittest.TestCase):
    def test_base_name_matches_eeg_export_naming(self):
        with tempfile.TemporaryDirectory() as directory:
            base = "P01_drops_20260716_153636"
            logger = EventLogger(directory, base_name=base)
            self.assertEqual(f"{base}_events.csv", os.path.basename(logger.path))

    def test_falls_back_to_legacy_name_without_base(self):
        with tempfile.TemporaryDirectory() as directory:
            logger = EventLogger(directory)
            name = os.path.basename(logger.path)
            self.assertTrue(name.startswith("gabor_events_"))
            self.assertTrue(name.endswith(".csv"))

    def test_creates_file_with_two_clock_header_on_init(self):
        with tempfile.TemporaryDirectory() as directory:
            logger = EventLogger(directory)
            with open(logger.path, newline="", encoding="utf-8") as file:
                rows = list(csv.reader(file))
            self.assertEqual(
                [["UnixTime(ms)", "SysUnixTime(ms)", "Event", "Detail"]], rows
            )

    def test_existing_session_log_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            base = "P01_drops_20260731_153636"
            logger = EventLogger(directory, base_name=base)
            logger.log("experiment_start")
            with self.assertRaises(FileExistsError):
                EventLogger(directory, base_name=base)
            with open(logger.path, newline="", encoding="utf-8") as file:
                rows = list(csv.reader(file))
            self.assertEqual("experiment_start", rows[-1][2])

    def test_log_twice_results_in_three_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            logger = EventLogger(directory)
            logger.log("block_start", "block=1")
            logger.log("block_end", "block=1")
            with open(logger.path, newline="", encoding="utf-8") as file:
                rows = list(csv.reader(file))
            self.assertEqual(3, len(rows))

    def test_log_records_both_clocks_when_omitted(self):
        with tempfile.TemporaryDirectory() as directory:
            logger = EventLogger(directory)
            logger.log("block_start")
            with open(logger.path, newline="", encoding="utf-8") as file:
                rows = list(csv.reader(file))
            mono_ms, sys_ms = int(rows[-1][0]), int(rows[-1][1])
            self.assertGreater(mono_ms, 0)
            self.assertGreater(sys_ms, 0)
            # 同一瞬間に取得しているので両者はごく近い。
            self.assertLess(abs(mono_ms - sys_ms), 1000)

    def test_log_uses_explicit_clock_pair(self):
        with tempfile.TemporaryDirectory() as directory:
            logger = EventLogger(directory)
            logger.log(
                "custom_event",
                "detail-text",
                unixtime_ms=123456789,
                sys_unixtime_ms=123456800,
            )
            with open(logger.path, newline="", encoding="utf-8") as file:
                rows = list(csv.reader(file))
            self.assertEqual(
                ["123456789", "123456800", "custom_event", "detail-text"], rows[-1]
            )

    def test_log_rejects_single_clock(self):
        """片方だけの指定は 2 系統の時計の対応を壊すため許可しない。"""
        with tempfile.TemporaryDirectory() as directory:
            logger = EventLogger(directory)
            with self.assertRaises(ValueError):
                logger.log("custom_event", unixtime_ms=123456789)
            with self.assertRaises(ValueError):
                logger.log("custom_event", sys_unixtime_ms=123456789)


if __name__ == "__main__":
    unittest.main()
