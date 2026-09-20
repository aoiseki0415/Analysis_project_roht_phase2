# utils/task_logic.py
# 課題進行に関する純粋ロジック（PyQt5非依存）。GaborCanvas から呼び出される。

import numpy as np


def practice_should_end(rts_ms, min_trials, threshold_ms, window):
    """練習フェーズを終了してよいか判定する。

    ``len(rts_ms) >= min_trials`` かつ直近 ``window`` 件の反応時間の平均が
    ``threshold_ms`` 以下であれば ``True`` を返す。
    """
    if len(rts_ms) < min_trials:
        return False

    recent = rts_ms[-window:]
    if not recent:
        return False

    average_rt = sum(recent) / len(recent)
    return average_rt <= threshold_ms


def sample_interval_ms(rng, short_range, long_range, short_prob):
    """試行間隔（ms）をサンプリングする。

    ``rng.random() < short_prob`` なら ``short_range``、それ以外は
    ``long_range`` から ``rng.randint`` で一様にサンプリングする。
    """
    if rng.random() < short_prob:
        low, high = short_range
    else:
        low, high = long_range
    return rng.randint(low, high)


def gabor_position(center_x, center_y, radius, motion_angle_deg):
    """円周上のガボールパッチの座標 (x, y) を返す。"""
    angle_rad = np.deg2rad(motion_angle_deg)
    x = center_x + radius * np.cos(angle_rad)
    y = center_y + radius * np.sin(angle_rad)
    return x, y


def tilt_display_angle(elapsed_ms, target_deg, ms_per_deg):
    """傾斜アニメーションの表示角（度）を経過時間から算出する。

    傾斜開始（オンセット）からの経過時間 ``elapsed_ms`` に対し、1度あたり
    ``ms_per_deg`` ミリ秒かけて ``target_deg`` へ線形に到達させる。到達後は
    ``target_deg`` で頭打ち。リフレッシュレートやフレーム落ちに依存せず、傾斜の
    速度・到達時間を一定に保つための実時間ベース算出。``target_deg`` の符号
    （傾斜方向）を保持する。
    """
    if ms_per_deg <= 0:
        return float(target_deg)
    magnitude = min(elapsed_ms / ms_per_deg, abs(target_deg))
    sign = 1.0 if target_deg >= 0 else -1.0
    return sign * magnitude


def format_countdown(seconds):
    """残り秒数を ``mm:ss`` 形式の文字列にする（負値は 00:00 に丸める）。"""
    total = max(0, int(seconds))
    minutes, secs = divmod(total, 60)
    return f"{minutes:02d}:{secs:02d}"


def break_duration_s(finished_block, num_blocks, short_s, long_s, long_after=None):
    """``finished_block`` 完了後の休憩秒数を返す。

    ``long_after``（``None`` なら ``num_blocks // 2``）と一致するブロック完了後は
    ``long_s``、それ以外は ``short_s`` を返す。
    """
    if long_after is None:
        long_after = num_blocks // 2

    if finished_block == long_after:
        return long_s
    return short_s
