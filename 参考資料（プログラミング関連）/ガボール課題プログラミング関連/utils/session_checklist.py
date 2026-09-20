# utils/session_checklist.py
# セッションチェックリスト（<base>_checklist.md）の生成（PyQt5非依存）。
#
# SBツール「Emotiv脳波計測・データ同期 引継ぎ資料」の計測前／計測後確認項目を
# セッションごとのファイルとして実体化する。EmotivPro は本アプリとは独立に
# 実験者が手動操作するため、アプリ側で自動保証できない項目（記録開始・停止・
# エクスポート・Drive アップロード・リジェクトチャンネル）を、記入欄付きの
# チェックリストとして残し、そのまま解析担当者へ提出できるようにする。

import os

from utils.precise_time import format_local

PRE_CHECKS = [
    "PC の日時とタイムゾーンが正しい（下記「セッション情報」の表示と実時刻が一致する）",
    "EmotivPro と本アプリを同じ PC で動かしている",
    "EmotivPro のライセンスが有効である",
    "ヘッドセットの接触状態（コンタクトクオリティ）を確認した",
    "EmotivPro の記録（Record）を開始した ※セッション通し 1 本",
    "本アプリで Participant ID / Eye-drop Condition / 課題パラメータを確認した",
]

POST_CHECKS = [
    "EmotivPro の記録を停止した",
    "EmotivPro から生データをエクスポートした",
    "エクスポートしたファイルが正常に開ける",
    "エクスポートを上記「EEG エクスポートの配置」の名前で eeg/ フォルダへ置いた",
    "所定の Google Drive へアップロードした（behave / eeg / 本チェックリスト）",
    "脳波データと実験ログをタイムスタンプで突合できることを確認した",
]


def _fmt_time(mono_ms, sys_ms):
    return (
        f"{format_local(sys_ms)}（Unixtime(ms) sys={sys_ms} / mono={mono_ms}）"
    )


def write_pre_session(path, info):
    """セッション準備時に、セッション情報＋計測前チェックを書き出す。"""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tz = info.get("timezone") or {}
    lines = [
        f"# セッションチェックリスト — {info.get('base', '')}",
        "",
        "計測前・計測後の確認記録です。記入のうえ、behave / eeg データと一緒に",
        "所定の Google Drive へ提出してください。",
        "",
        "## セッション情報",
        "",
        f"- 参加者 ID: {info.get('participant_id', '')}",
        f"- 目薬条件: {info.get('drop_condition', '')}",
        f"- ファイル名基底: `{info.get('base', '')}`",
        f"- アプリバージョン: {info.get('app_version', '')}",
        f"- 準備時刻: {_fmt_time(info.get('start_unixtime_ms', 0), info.get('start_sys_unixtime_ms', 0))}",
        f"- タイムゾーン: {tz.get('name', '')}（{tz.get('utc_offset', '')}）",
        f"- 行動データ保存先: `{info.get('behave_dir', '')}`",
        f"- EEG 配置先: `{info.get('eeg_dir', '')}`",
        "",
        "## 同期方式",
        "",
        "本アプリは EEG を取得しません（Cortex API 不使用）。EmotivPro と本アプリが",
        "同じ PC の時刻でタイムスタンプを記録し、解析時に突合します。",
        "",
        "- 突合に使う列: `events.csv` / `results.csv` の **`SysUnixTime(ms)` /",
        "  `*Sys(ms)`**（OS 壁時計＝EmotivPro と同じ時計）",
        "- 反応時間の算出: `RT(ms)`（単調時計基準。OS の時刻補正の影響を受けない）",
        "- 両時計のずれは `events.csv` の `clock_check` / `clock_drift` 行で追跡できます",
        "- タイムゾーン変更は `events.csv` の `timezone_change` 行へ記録されます",
        "",
        "## EEG エクスポートの配置",
        "",
        f"EmotivPro からのエクスポートを **`{info.get('eeg_expected_name', '')}.<拡張子>`**",
        "へリネームして、上記 EEG 配置先へ置いてください（behave 側とファイル名の",
        "基底を揃えることで、1 セッション＝1 EEG ファイルとして対応づきます）。",
        "",
        "## 計測前チェック",
        "",
    ]
    lines += [f"- [ ] {item}" for item in PRE_CHECKS]
    lines += [""]
    # 既存セッションのチェックリストを誤って初期化しない。
    with open(path, mode="x", encoding="utf-8") as file:
        file.write("\n".join(lines))
    return path


def append_post_session(path, info):
    """セッション終了時に、実績値＋計測後チェック＋記入欄を追記する。"""
    clock = info.get("clock") or {}
    outcome_label = {
        "completed": "正常終了（全ブロック完了）",
        "aborted": "中断（Abort）",
        "closed": "アプリ終了（課題未完了）",
    }.get(info.get("outcome"), info.get("outcome", "不明"))

    max_drift = clock.get("max_drift_ms")
    warn_count = clock.get("warn_count")
    drift_line = (
        f"- 最大クロックドリフト: {max_drift:+d} ms"
        f"（警告 {warn_count} 件 / 閾値 ±{clock.get('drift_warn_ms')} ms）"
        if max_drift is not None
        else "- 最大クロックドリフト: 記録なし"
    )

    lines = [
        "",
        "## セッション実績（自動記入）",
        "",
        f"- 終了区分: {outcome_label}",
        f"- 終了時刻: {_fmt_time(info.get('end_unixtime_ms', 0), info.get('end_sys_unixtime_ms', 0))}",
        f"- 所要時間: {_format_duration(info.get('duration_s'))}",
        drift_line,
    ]
    if max_drift is not None and warn_count:
        lines.append(
            "  - ドリフト警告が出ています。`events.csv` の `clock_drift` 行を確認し、"
            "解析時は `clock_check` の対応点で補正してください。"
        )
    files = info.get("files") or []
    if files:
        lines += ["- 生成ファイル:"]
        lines += [f"  - `{name}`" for name in files]
    for note in info.get("notes") or []:
        lines.append(f"- 注記: {note}")

    lines += ["", "## 計測後チェック", ""]
    lines += [f"- [ ] {item}" for item in POST_CHECKS]
    lines += [
        "",
        "## 記入欄",
        "",
        "- EmotivPro のセッション名／エクスポートファイル名:",
        "  - ",
        "- リジェクトチャンネル（解析から除外するチャンネル）:",
        "  - ",
        "- 計測中の特記事項（機器トラブル・被験者の様子・中断理由など）:",
        "  - ",
        "- 記入者 / 記入日:",
        "  - ",
        "",
    ]
    with open(path, mode="a", encoding="utf-8") as file:
        file.write("\n".join(lines))
    return path


def _format_duration(duration_s):
    if duration_s is None:
        return "不明"
    total = int(duration_s)
    return f"{total // 3600:d}時間{(total % 3600) // 60:02d}分{total % 60:02d}秒"
