# tests/test_precise_time.py
import time
import unittest

from utils.precise_time import (
    format_local,
    now_pair,
    sys_unixtime_ms,
    timezone_info,
    unixtime_ms,
    unixtime_s,
)


class TestPreciseTime(unittest.TestCase):
    def test_close_to_wall_clock(self):
        """壁時計との差はアンカー誤差（1 tick 未満）＋実行遅延の範囲に収まる。"""
        diff_ms = abs(unixtime_ms() - int(time.time() * 1000))
        self.assertLess(diff_ms, 200)

    def test_monotonic_non_decreasing(self):
        samples = [unixtime_ms() for _ in range(1000)]
        self.assertEqual(samples, sorted(samples))

    def test_advances_after_sleep(self):
        t0 = unixtime_ms()
        time.sleep(0.02)
        t1 = unixtime_ms()
        self.assertGreaterEqual(t1 - t0, 10)

    def test_ms_and_s_consistent(self):
        diff_ms = abs(unixtime_s() * 1000 - unixtime_ms())
        self.assertLess(diff_ms, 10)

    def test_finer_than_wall_tick(self):
        """15.6ms（Windows の壁時計 tick）より細かい分解能を持つこと。

        50ms のサンプリングで観測できる異なる ms 値は、µs 分解能なら約 50 個、
        15.6ms 分解能なら 4〜5 個に留まる。閾値 10 で判別する。
        """
        deadline = time.perf_counter() + 0.05
        seen = set()
        while time.perf_counter() < deadline:
            seen.add(unixtime_ms())
        self.assertGreaterEqual(len(seen), 10)


class TestClockPair(unittest.TestCase):
    """EmotivPro との突合のため、mono と sys を対で取得できること。"""

    def test_now_pair_returns_two_close_clocks(self):
        mono_ms, sys_ms = now_pair()
        self.assertIsInstance(mono_ms, int)
        self.assertIsInstance(sys_ms, int)
        # 同一瞬間の取得なので、差はアンカー誤差＋実行遅延に収まる。
        self.assertLess(abs(mono_ms - sys_ms), 200)

    def test_sys_unixtime_matches_time_time(self):
        self.assertLess(abs(sys_unixtime_ms() - int(time.time() * 1000)), 50)

    def test_timezone_info_shape(self):
        info = timezone_info()
        self.assertIn("name", info)
        self.assertTrue(info["utc_offset"].startswith("UTC"))
        self.assertEqual(
            info["utc_offset_s"],
            -(time.altzone if time.localtime().tm_isdst > 0 else time.timezone),
        )

    def test_format_local_is_millisecond_precision(self):
        text = format_local(1_785_000_000_123)
        self.assertRegex(text, r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}$")
        self.assertTrue(text.endswith(".123"))


if __name__ == "__main__":
    unittest.main()
