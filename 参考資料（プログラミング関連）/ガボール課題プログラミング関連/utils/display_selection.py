"""モニター表示先と1画面テスト用レイアウトを決める純粋関数。"""


SINGLE_SCREEN_TEST_FLAG = "--single-screen-test"


def resolve_screen_index(requested_index, screen_count):
    """有効な画面番号を返す。無効値や1画面環境ではメイン画面（0）へ戻す。"""
    if screen_count <= 0:
        raise ValueError("screen_count must be positive")

    try:
        index = int(requested_index)
    except (TypeError, ValueError):
        return 0

    if 0 <= index < screen_count:
        return index
    return 0


def consume_single_screen_test_flag(argv):
    """独自フラグをQtへ渡す引数から除き、モードの有効/無効を返す。"""
    args = list(argv)
    enabled = SINGLE_SCREEN_TEST_FLAG in args
    qt_args = [arg for arg in args if arg != SINGLE_SCREEN_TEST_FLAG]
    return qt_args, enabled


def split_single_screen_geometry(x, y, width, height, gap=12):
    """1画面を左右に分けた（Console, 被験者画面）の座標を返す。"""
    if width < 2 or height < 1:
        raise ValueError("screen geometry is too small")

    safe_gap = min(max(int(gap), 0), width - 2)
    usable_width = width - safe_gap
    left_width = usable_width // 2
    right_width = usable_width - left_width
    left = (x, y, left_width, height)
    right = (x + left_width + safe_gap, y, right_width, height)
    return left, right
