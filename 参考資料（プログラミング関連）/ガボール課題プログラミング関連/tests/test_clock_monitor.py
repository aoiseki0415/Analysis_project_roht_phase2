# tests/test_clock_monitor.py
import unittest

from utils.clock_monitor import CHECK_EVENT, DRIFT_EVENT, ClockMonitor


class ClockMonitorTests(unittest.TestCase):
    def make(self, check_interval_s=60, drift_warn_ms=100):
        monitor = ClockMonitor(
            check_interval_s=check_interval_s, drift_warn_ms=drift_warn_ms
        )
        monitor.start(1_000_000_000, 1_000_000_000)
        return monitor

    def test_first_tick_only_sets_baseline(self):
        monitor = ClockMonitor()
        self.assertFalse(monitor.started)
        self.assertEqual([], monitor.tick(1_000_000, 1_000_050))
        self.assertTrue(monitor.started)
        # baseline を取り直した直後のドリフトは 0。
        self.assertEqual(0, monitor.drift_ms(1_000_000, 1_000_050))

    def test_no_events_while_clocks_agree(self):
        monitor = self.make()
        self.assertEqual([], monitor.tick(1_000_001_000, 1_000_001_000))

    def test_check_event_emitted_on_interval(self):
        monitor = self.make(check_interval_s=60)
        self.assertEqual([], monitor.tick(1_000_030_000, 1_000_030_000))
        events = monitor.tick(1_000_060_000, 1_000_060_000)
        self.assertEqual([CHECK_EVENT], [e["event"] for e in events])
        # 直近の check からさらに間隔が空くまでは出さない。
        self.assertEqual([], monitor.tick(1_000_090_000, 1_000_090_000))
        events = monitor.tick(1_000_120_000, 1_000_120_000)
        self.assertEqual([CHECK_EVENT], [e["event"] for e in events])

    def test_drift_event_emitted_beyond_threshold(self):
        monitor = self.make(drift_warn_ms=100)
        self.assertEqual([], monitor.tick(1_000_001_000, 1_000_001_099))
        events = monitor.tick(1_000_002_000, 1_000_002_150)
        self.assertEqual([DRIFT_EVENT], [e["event"] for e in events])
        self.assertEqual(150, events[0]["drift_ms"])

    def test_drift_event_not_repeated_for_similar_drift(self):
        monitor = self.make(drift_warn_ms=100)
        monitor.tick(1_000_002_000, 1_000_002_150)  # 初回警告
        self.assertEqual([], monitor.tick(1_000_003_000, 1_000_003_180))
        self.assertEqual([], monitor.tick(1_000_004_000, 1_000_004_200))

    def test_drift_event_repeats_after_further_change(self):
        monitor = self.make(drift_warn_ms=100)
        monitor.tick(1_000_002_000, 1_000_002_150)  # 初回警告（+150ms）
        events = monitor.tick(1_000_003_000, 1_000_003_260)  # +260ms
        self.assertEqual([DRIFT_EVENT], [e["event"] for e in events])

    def test_negative_drift_detected(self):
        monitor = self.make(drift_warn_ms=100)
        events = monitor.tick(1_000_002_000, 1_000_001_800)
        self.assertEqual([DRIFT_EVENT], [e["event"] for e in events])
        self.assertEqual(-200, events[0]["drift_ms"])

    def test_return_to_baseline_does_not_warn(self):
        monitor = self.make(drift_warn_ms=100)
        monitor.tick(1_000_002_000, 1_000_002_150)
        self.assertEqual([], monitor.tick(1_000_003_000, 1_000_003_000))

    def test_check_and_drift_can_be_emitted_together(self):
        monitor = self.make(check_interval_s=60, drift_warn_ms=100)
        events = monitor.tick(1_000_060_000, 1_000_060_500)
        self.assertEqual([CHECK_EVENT, DRIFT_EVENT], [e["event"] for e in events])

    def test_summary_tracks_max_drift_and_warn_count(self):
        monitor = self.make(drift_warn_ms=100)
        monitor.tick(1_000_002_000, 1_000_002_150)
        monitor.tick(1_000_003_000, 1_000_002_700)  # -300ms（絶対値が最大）
        monitor.tick(1_000_004_000, 1_000_004_050)
        summary = monitor.summary()
        self.assertEqual(-300, summary["max_drift_ms"])
        self.assertEqual(2, summary["warn_count"])
        self.assertEqual(0, summary["baseline_offset_ms"])
        self.assertEqual(100, summary["drift_warn_ms"])

    def test_start_rebaselines_and_resets(self):
        monitor = self.make(drift_warn_ms=100)
        monitor.tick(1_000_002_000, 1_000_002_150)
        monitor.start(1_000_010_000, 1_000_010_150)
        self.assertEqual(150, monitor.summary()["baseline_offset_ms"])
        self.assertEqual(0, monitor.summary()["max_drift_ms"])
        self.assertEqual(0, monitor.summary()["warn_count"])
        # 新しい基準からのずれで判定する。
        self.assertEqual([], monitor.tick(1_000_011_000, 1_000_011_150))

    def test_event_carries_both_clocks(self):
        monitor = self.make(drift_warn_ms=100)
        events = monitor.tick(1_000_002_000, 1_000_002_150)
        self.assertEqual(1_000_002_000, events[0]["mono_ms"])
        self.assertEqual(1_000_002_150, events[0]["sys_ms"])
        self.assertIn("offset_ms=150", events[0]["detail"])
        self.assertIn("drift_ms=150", events[0]["detail"])


if __name__ == "__main__":
    unittest.main()
