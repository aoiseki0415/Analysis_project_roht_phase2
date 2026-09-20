import unittest

from utils.task_logic import (
    break_duration_s,
    format_countdown,
    gabor_position,
    practice_should_end,
    sample_interval_ms,
    tilt_display_angle,
)


class FakeRng:
    """random.Random 互換の最小限のフェイク（決定的なテスト用）。"""

    def __init__(self, random_value, randint_value):
        self._random_value = random_value
        self._randint_value = randint_value
        self.last_randint_args = None

    def random(self):
        return self._random_value

    def randint(self, low, high):
        self.last_randint_args = (low, high)
        return self._randint_value


class PracticeShouldEndTests(unittest.TestCase):
    def test_below_min_trials_never_ends(self):
        rts = [1000] * 29
        self.assertFalse(
            practice_should_end(rts, min_trials=30, threshold_ms=1500, window=5)
        )

    def test_ends_when_recent_average_at_threshold(self):
        rts = [3000] * 25 + [1500] * 5
        self.assertEqual(30, len(rts))
        self.assertTrue(
            practice_should_end(rts, min_trials=30, threshold_ms=1500, window=5)
        )

    def test_does_not_end_when_recent_average_above_threshold(self):
        rts = [3000] * 25 + [1501] * 5
        self.assertEqual(30, len(rts))
        self.assertFalse(
            practice_should_end(rts, min_trials=30, threshold_ms=1500, window=5)
        )


class SampleIntervalMsTests(unittest.TestCase):
    def test_short_range_used_when_below_probability(self):
        rng = FakeRng(random_value=0.1, randint_value=999)
        result = sample_interval_ms(rng, (500, 1500), (1500, 3000), short_prob=0.8)
        self.assertEqual((500, 1500), rng.last_randint_args)
        self.assertEqual(999, result)

    def test_long_range_used_when_above_probability(self):
        rng = FakeRng(random_value=0.9, randint_value=2000)
        result = sample_interval_ms(rng, (500, 1500), (1500, 3000), short_prob=0.8)
        self.assertEqual((1500, 3000), rng.last_randint_args)
        self.assertEqual(2000, result)


class BreakDurationTests(unittest.TestCase):
    def test_long_break_only_after_midpoint_block(self):
        for block in range(1, 7):
            expected = 300 if block == 3 else 120
            self.assertEqual(
                expected,
                break_duration_s(block, num_blocks=6, short_s=120, long_s=300),
            )

    def test_explicit_long_after_overrides_midpoint(self):
        self.assertEqual(
            300,
            break_duration_s(
                2, num_blocks=6, short_s=120, long_s=300, long_after=2
            ),
        )
        self.assertEqual(
            120,
            break_duration_s(
                3, num_blocks=6, short_s=120, long_s=300, long_after=2
            ),
        )


class TiltDisplayAngleTests(unittest.TestCase):
    def test_linear_progress_before_reaching_target(self):
        # 33ms/度で 5 度 → 165ms で到達。中間 66ms では 2 度。
        self.assertAlmostEqual(2.0, tilt_display_angle(66.0, 10, 33.0), places=6)

    def test_clamped_at_target_after_reaching(self):
        self.assertEqual(10, tilt_display_angle(10_000, 10, 33.0))

    def test_preserves_sign_of_target(self):
        self.assertAlmostEqual(-2.0, tilt_display_angle(66.0, -10, 33.0), places=6)

    def test_speed_independent_of_refresh_rate(self):
        # 同じ経過時間なら、描画フレーム数（=リフレッシュレート）に関係なく
        # 同じ角度になる（実時間ベースであることの確認）。
        angle_60hz = tilt_display_angle(99.0, 10, 33.0)
        angle_144hz = tilt_display_angle(99.0, 10, 33.0)
        self.assertEqual(angle_60hz, angle_144hz)
        self.assertAlmostEqual(3.0, angle_60hz, places=6)

    def test_zero_ms_per_deg_returns_target(self):
        self.assertEqual(10, tilt_display_angle(50.0, 10, 0))


class FormatCountdownTests(unittest.TestCase):
    def test_formats_minutes_and_seconds(self):
        self.assertEqual("02:00", format_countdown(120))
        self.assertEqual("04:59", format_countdown(299))
        self.assertEqual("00:05", format_countdown(5))

    def test_negative_clamped_to_zero(self):
        self.assertEqual("00:00", format_countdown(-3))


class GaborPositionTests(unittest.TestCase):
    def test_representative_directions(self):
        cases = [
            (0, (1.0, 0.0)),
            (90, (0.0, 1.0)),
            (180, (-1.0, 0.0)),
            (270, (0.0, -1.0)),
        ]
        for angle, expected in cases:
            with self.subTest(angle=angle):
                x, y = gabor_position(0.0, 0.0, 1.0, angle)
                self.assertAlmostEqual(expected[0], x, places=6)
                self.assertAlmostEqual(expected[1], y, places=6)


if __name__ == "__main__":
    unittest.main()
