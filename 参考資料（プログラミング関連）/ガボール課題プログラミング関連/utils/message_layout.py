"""被験者向けメッセージの読みやすい文字サイズを求める。"""

import unicodedata


def _visual_width_units(text):
    """全角を1、半角を0.55として、おおよその表示幅を返す。"""
    return sum(
        1.0 if unicodedata.east_asian_width(char) in {"W", "F", "A"} else 0.55
        for char in text
    )


def message_font_size_px(
    width,
    height,
    text,
    min_px=24,
    max_px=42,
    horizontal_ratio=0.84,
    vertical_ratio=0.76,
):
    """明示改行を保ったまま収まる、おおよそのフォントサイズを返す。"""
    if width <= 0 or height <= 0:
        return min_px

    lines = str(text).split("\n") or [""]
    longest = max((_visual_width_units(line) for line in lines), default=1.0)
    longest = max(longest, 1.0)
    line_count = max(len(lines), 1)

    horizontal_limit = int(width * horizontal_ratio / longest)
    vertical_limit = int(height * vertical_ratio / (line_count * 1.35))
    return max(min_px, min(max_px, horizontal_limit, vertical_limit))
