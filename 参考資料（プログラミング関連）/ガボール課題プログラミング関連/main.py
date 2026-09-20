# main.py
# ガボール課題アプリのエントリポイント。
#
# 本アプリは EEG を取得しない（Emotiv Cortex API 不使用）。EEG は EmotivPro 側で
# 実験者が手動計測・手動エクスポートし、解析時に PC 壁時計のタイムスタンプで突合する。
# Cortex Serviceや認証情報は不要。納品先では公式Pythonのvenvから起動する。
# 詳細は docs/20260731_cortex-removal-emotivpro-sync_requirements.md を参照。

from PyQt5.QtWidgets import QApplication, QMessageBox
from gui.controller_gui import ControllerGUI
from gui.exp_feedback_gui import ExperimentWindow
import exp_config
import sys
from utils.app_paths import application_root
from utils.display_selection import (
    consume_single_screen_test_flag,
    resolve_screen_index,
    split_single_screen_geometry,
)
from utils.precise_time import format_local, now_pair, timezone_info
from utils.external_settings import apply_external_settings, SettingsError


def place_window_on_screen(window, screen):
    """トップレベルウィンドウを指定画面の中央へ配置する。"""
    window.winId()
    window_handle = window.windowHandle()
    if window_handle is not None:
        window_handle.setScreen(screen)
    window.adjustSize()
    frame = window.frameGeometry()
    frame.moveCenter(screen.availableGeometry().center())
    window.move(frame.topLeft())


def show_controller_window(app, controller_window):
    """実験者Consoleをメインモニターへ表示する。"""
    primary_screen = app.primaryScreen()
    if primary_screen is not None:
        place_window_on_screen(controller_window, primary_screen)
        print(
            "[Display] Controller window -> primary screen "
            f"name={primary_screen.name()!r}"
        )
    controller_window.show()


def show_experiment_window(app, exp_window):
    """被験者画面を設定されたモニターへ移動して表示する。"""
    screens = app.screens()
    if not screens:
        print("[Display] No screen information; using the default window placement.")
        if exp_config.FULLSCREEN:
            exp_window.showFullScreen()
        else:
            exp_window.show()
        return

    for index, screen in enumerate(screens):
        geometry = screen.geometry()
        primary = " primary" if screen is app.primaryScreen() else ""
        print(
            f"[Display] screen[{index}] name={screen.name()!r} "
            f"geometry={geometry.width()}x{geometry.height()}"
            f"+{geometry.x()}+{geometry.y()}{primary}"
        )

    requested_index = exp_config.PARTICIPANT_SCREEN_INDEX
    target_index = resolve_screen_index(requested_index, len(screens))
    if target_index != requested_index:
        print(
            "[Display] Warning: PARTICIPANT_SCREEN_INDEX="
            f"{requested_index!r} is unavailable; falling back to screen[0]."
        )

    target_screen = screens[target_index]
    # QWidgetのネイティブウィンドウを作成して表示先QScreenを明示する。
    # setScreenだけでは仮想デスクトップ上を移動しない場合があるため、対象画面の
    # 中央へ通常時座標も移してからフルスクリーン化する。
    place_window_on_screen(exp_window, target_screen)

    print(
        f"[Display] Participant window -> screen[{target_index}] "
        f"name={target_screen.name()!r}, fullscreen={exp_config.FULLSCREEN}"
    )
    if exp_config.FULLSCREEN:
        exp_window.showFullScreen()
    else:
        exp_window.show()


def show_single_screen_test_windows(app, controller_window, exp_window):
    """1画面上でConsoleと被験者画面を左右に並べて表示する。"""
    screen = app.primaryScreen()
    if screen is None:
        print("[Display] No screen information; using normal window placement.")
        controller_window.show()
        exp_window.show()
        return

    area = screen.availableGeometry()
    controller_geometry, participant_geometry = split_single_screen_geometry(
        area.x(), area.y(), area.width(), area.height()
    )
    controller_window.setGeometry(*controller_geometry)
    exp_window.setGeometry(*participant_geometry)
    controller_window.show()
    exp_window.show()
    print(
        "[Display] Single-screen test mode: Console=left, "
        "Participant=right, fullscreen=False"
    )


def print_clock_info():
    """起動時の PC 時刻・タイムゾーンを標準出力へ残す（計測前確認の支援）。"""
    tz = timezone_info()
    _, sys_ms = now_pair()
    print(f"[App] Gabor task v{exp_config.APP_VERSION} (no EEG acquisition)")
    print(f"[App] PC time: {format_local(sys_ms)} / {tz['name']} {tz['utc_offset']}")
    print(
        "[App] EEG は EmotivPro 側で計測・エクスポートし、"
        "解析時にタイムスタンプで突合します。"
    )


def main():
    qt_argv, single_screen_test = consume_single_screen_test_flag(sys.argv)
    app = QApplication(qt_argv)
    try:
        settings_path = apply_external_settings(exp_config, application_root())
    except SettingsError as exc:
        QMessageBox.critical(
            None,
            "設定ファイルエラー",
            f"{exc}\n\nsettings.jsonを修正してから、もう一度起動してください。",
        )
        return 2
    if settings_path:
        print(f"[Settings] Loaded: {settings_path}")
    print_clock_info()

    controller_window = ControllerGUI()

    exp_window = ExperimentWindow(
        trials_per_block=exp_config.DEFAULT_TRIALS_PER_BLOCK,
        num_blocks=exp_config.DEFAULT_NUM_BLOCKS,
        external_logger=controller_window.redirect_log_from_task,
        max_angle_input=exp_config.DEFAULT_MAX_TILT_DEG,
        controller_window=controller_window,
    )
    controller_window.exp_window = exp_window

    if single_screen_test:
        show_single_screen_test_windows(app, controller_window, exp_window)
    else:
        show_controller_window(app, controller_window)
        show_experiment_window(app, exp_window)
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
