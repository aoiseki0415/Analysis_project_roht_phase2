"""配布フォルダのsettings.jsonを安全にexp_configへ反映する。"""

import json
import os


class SettingsError(ValueError):
    """外部設定を安全に読み込めない場合のエラー。"""


SETTING_RULES = {
    "FULLSCREEN": lambda value: type(value) is bool,
    "PARTICIPANT_SCREEN_INDEX": (
        lambda value: type(value) is int and value >= 0
    ),
    "EXIT_FULLSCREEN_ON_FINISH": lambda value: type(value) is bool,
    "MONITOR_WIDTH_PX": (
        lambda value: value is None or (type(value) is int and value > 0)
    ),
    "MONITOR_WIDTH_MM": (
        lambda value: value is None or (
            type(value) in {int, float} and value > 0
        )
    ),
    "VIEWING_DISTANCE_MM": (
        lambda value: type(value) in {int, float} and value > 0
    ),
}


def apply_external_settings(config_module, app_root):
    """settings.jsonがあれば検証して反映し、パスを返す。無ければNone。"""
    path = os.path.join(app_root, "settings.json")
    if not os.path.exists(path):
        return None

    try:
        with open(path, encoding="utf-8") as file:
            values = json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        raise SettingsError(f"settings.json を読み込めません: {exc}") from exc

    if not isinstance(values, dict):
        raise SettingsError("settings.json の最上位は { } にしてください。")

    unknown = sorted(set(values) - set(SETTING_RULES))
    if unknown:
        raise SettingsError(f"未対応の設定名があります: {', '.join(unknown)}")

    invalid = [
        name for name, value in values.items() if not SETTING_RULES[name](value)
    ]
    if invalid:
        raise SettingsError(f"設定値が不正です: {', '.join(invalid)}")

    for name, value in values.items():
        setattr(config_module, name, value)
    return path
