# utils/display_calibration.py
# モニターキャリブレーション（視距離・解像度）から刺激ジオメトリ(px)を解決する
# 純粋ロジック（PyQt5非依存）。

import math


def px_per_mm(monitor_width_px, monitor_width_mm):
    """1mmあたりのピクセル数を返す。

    どちらかが ``None``/``0`` ならキャリブレーション未設定として ``None`` を返す。
    """
    if not monitor_width_px or not monitor_width_mm:
        return None
    return monitor_width_px / monitor_width_mm


def visual_deg_to_mm(deg, viewing_distance_mm):
    """視角（度）を視距離 ``viewing_distance_mm`` における物理サイズ（mm）に変換する。"""
    return 2 * viewing_distance_mm * math.tan(math.radians(deg) / 2)


def resolve_geometry(cfg):
    """``exp_config`` 相当のオブジェクトから刺激ジオメトリ(px)を解決する。

    モニターキャリブレーション（``MONITOR_WIDTH_PX`` / ``MONITOR_WIDTH_MM``）が
    未設定の場合は、従来の固定px値（フォールバック）を返す。
    """
    ppmm = px_per_mm(cfg.MONITOR_WIDTH_PX, cfg.MONITOR_WIDTH_MM)
    calibrated = ppmm is not None

    if calibrated:
        patch_diameter_px = round(
            visual_deg_to_mm(cfg.PATCH_SIZE_DEG, cfg.VIEWING_DISTANCE_MM) * ppmm
        )
        cycles_per_patch = cfg.SPATIAL_FREQ_CPD * cfg.PATCH_SIZE_DEG
        radius_px = cfg.CIRCLE_DIAMETER_MM / 2 * ppmm
    else:
        patch_diameter_px = cfg.FALLBACK_PATCH_DIAMETER_PX
        cycles_per_patch = cfg.FALLBACK_CYCLES_PER_PATCH
        radius_px = None

    deg_per_frame = 360 / (cfg.REVOLUTION_PERIOD_S * 1000 / cfg.FRAME_INTERVAL_MS)

    return {
        "calibrated": calibrated,
        "patch_diameter_px": patch_diameter_px,
        "cycles_per_patch": cycles_per_patch,
        "radius_px": radius_px,
        "deg_per_frame": deg_per_frame,
    }
