# gui/controller_gui.py
# 実験者用コントローラ（Console）。
#
# 本アプリは EEG を取得しない（Emotiv Cortex API 不使用）。EEG は EmotivPro 側で
# 実験者が手動計測・手動エクスポートし、解析時に PC 壁時計のタイムスタンプで突合する。
# したがって Console の責務は次の 4 点になる。
#   1. セッション準備（参加者ID・条件の確定、保存先作成、ファイル名基底の確定、
#      メタ情報とチェックリストの出力、計測前チェックの提示）
#   2. 実験の進行制御（Pause / Resume / Abort）と休憩カウントダウンの表示
#   3. クロックドリフト（単調時計と OS 壁時計のずれ）の監視・警告・記録
#   4. セッション終了時のチェックリスト追記

from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QGroupBox,
    QLineEdit,
    QComboBox,
    QMessageBox,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QIntValidator
from datetime import datetime
import sys
import os
import re
import json

import exp_config
from utils.app_paths import application_root
from utils.clock_monitor import ClockMonitor, DRIFT_EVENT
from utils.event_logger import EventLogger
from utils.precise_time import format_local, now_pair, timezone_info
from utils.session_checklist import (
    PRE_CHECKS,
    append_post_session,
    write_pre_session,
)
from utils.task_logic import format_countdown


class ControllerGUI(QWidget):
    def __init__(self, exp_window=None):
        super().__init__()
        self.exp_window = exp_window  # ← 被験者画面への参照

        self.setWindowTitle("Console")
        self.setup_ui()

        # === セッション状態 ===
        # ファイル名の基底（<ID>_<条件>_<YYYYMMDD_HHMMSS>）。EmotivPro エクスポートも
        # 同じ基底へリネームして eeg/ へ置くことで 1:1 に対応づける。
        self.record_title_base = None
        self.behave_save_dir = None
        self.eeg_save_dir = None
        self.event_logger = None
        self.prepared = False
        self.finalized = False
        self.session_start_pair = None
        self.checklist_path = None
        self.meta_path = None
        self._event_write_failed = False
        self.session_notes = []
        self.session_timezone = None
        self._last_timezone_signature = None

        # 外部ログ出力用関数（GaborCanvasからアクセス可能）
        self.external_logger = self.redirect_log_from_task

        # === クロックドリフト監視 ===
        # mono（反応時間の正）と sys（EmotivPro との突合の正）のずれを 1 秒ごとに
        # 確認し、定期的な対応点（clock_check）と閾値超過の警告（clock_drift）を残す。
        self.clock_monitor = ClockMonitor(
            check_interval_s=exp_config.CLOCK_CHECK_INTERVAL_S,
            drift_warn_ms=exp_config.CLOCK_DRIFT_WARN_MS,
        )
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.update_clock_status)
        self.clock_timer.start(1000)

        self.resize(900, 760)
        self.show_startup_info()

    # === UI ===

    def setup_ui(self):
        layout = QVBoxLayout()

        # 被験者ID入力
        self.participant_id_input = QLineEdit()
        self.participant_id_input.setPlaceholderText("Enter Participant ID")

        id_input_layout = QHBoxLayout()
        id_input_layout.addWidget(QLabel("Participant ID:"))
        id_input_layout.addWidget(self.participant_id_input)
        layout.addLayout(id_input_layout)

        # 目薬条件選択
        self.drop_condition_input = QComboBox()
        self.drop_condition_input.addItems(exp_config.DROP_CONDITION_OPTIONS)

        drop_condition_layout = QHBoxLayout()
        drop_condition_layout.addWidget(QLabel("Eye-drop Condition:"))
        drop_condition_layout.addWidget(self.drop_condition_input)
        layout.addLayout(drop_condition_layout)

        # パラメータ入力（最大傾斜角度・ブロックあたり試行数・ブロック数）
        param_layout = QHBoxLayout()
        self.max_angle_input = QLineEdit()
        self.max_angle_input.setText(str(exp_config.DEFAULT_MAX_TILT_DEG))
        self.max_angle_input.setValidator(QIntValidator(1, 90, self))
        self.trials_per_block_input = QLineEdit()
        self.trials_per_block_input.setText(str(exp_config.DEFAULT_TRIALS_PER_BLOCK))
        self.trials_per_block_input.setValidator(QIntValidator(1, 10000, self))
        self.num_blocks_input = QLineEdit()
        self.num_blocks_input.setText(str(exp_config.DEFAULT_NUM_BLOCKS))
        self.num_blocks_input.setValidator(QIntValidator(1, 20, self))
        self.max_angle_input.editingFinished.connect(self.update_experiment_parameters)
        self.trials_per_block_input.editingFinished.connect(
            self.update_experiment_parameters
        )
        self.num_blocks_input.editingFinished.connect(self.update_experiment_parameters)

        param_layout.addWidget(QLabel("Max Angle (deg):"))
        param_layout.addWidget(self.max_angle_input)
        param_layout.addSpacing(20)
        param_layout.addWidget(QLabel("Trials / Block:"))
        param_layout.addWidget(self.trials_per_block_input)
        param_layout.addSpacing(20)
        param_layout.addWidget(QLabel("Blocks:"))
        param_layout.addWidget(self.num_blocks_input)
        layout.addLayout(param_layout)

        # セッション制御（準備・一時停止・中断）
        self.prepare_button = QPushButton("Prepare session")
        self.pause_resume_button = QPushButton("Pause")
        self.abort_button = QPushButton("Abort")

        session_box = QGroupBox("Session control")
        session_layout = QHBoxLayout()
        session_layout.addWidget(self.prepare_button)
        session_layout.addWidget(self.pause_resume_button)
        session_layout.addWidget(self.abort_button)
        session_box.setLayout(session_layout)
        layout.addWidget(session_box)

        # 時刻・休憩の状態表示
        self.clock_drift_label = QLabel("--")
        self.clock_drift_label.setFont(QFont("Arial", 14))
        self.timezone_label = QLabel("--")
        self.break_countdown_label = QLabel("--:--")
        self.break_countdown_label.setAlignment(Qt.AlignCenter)
        self.break_countdown_label.setFont(QFont("Arial", 16))

        monitor_box = QGroupBox("Clock / Break")
        monitor_layout = QHBoxLayout()
        monitor_layout.addWidget(QLabel("Clock drift:"))
        monitor_layout.addWidget(self.clock_drift_label)
        monitor_layout.addSpacing(20)
        monitor_layout.addWidget(QLabel("Timezone:"))
        monitor_layout.addWidget(self.timezone_label)
        monitor_layout.addStretch(1)
        monitor_layout.addWidget(QLabel("Break remaining:"))
        monitor_layout.addWidget(self.break_countdown_label)
        monitor_box.setLayout(monitor_layout)
        layout.addWidget(monitor_box)

        # 状態表示
        status_box = QGroupBox("State")
        status_layout = QVBoxLayout()
        self.status_label = QLabel("Waiting ...")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setFont(QFont("Arial", 14))
        status_layout.addWidget(self.status_label)
        status_box.setLayout(status_layout)
        layout.addWidget(status_box)

        # 計測前チェック・保存先の案内（Prepare session で内容が確定する）
        guide_box = QGroupBox("Session guide / 計測前チェック")
        guide_layout = QVBoxLayout()
        self.guide_area = QTextEdit()
        self.guide_area.setReadOnly(True)
        guide_layout.addWidget(self.guide_area)
        guide_box.setLayout(guide_layout)
        layout.addWidget(guide_box, stretch=3)

        # ログ/通知表示
        log_box = QGroupBox("Log / Notification")
        log_layout = QVBoxLayout()
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        log_layout.addWidget(self.log_area)
        log_box.setLayout(log_layout)
        layout.addWidget(log_box, stretch=4)

        self.setLayout(layout)

        # 信号とスロットの接続
        self.prepare_button.clicked.connect(self.prepare_session)
        self.pause_resume_button.clicked.connect(self.toggle_pause)
        self.abort_button.clicked.connect(self.handle_abort_clicked)

    def log(self, message):
        self.log_area.append(str(message))

    def show_startup_info(self):
        """起動時に PC の日時・タイムゾーンを提示する（計測前確認の支援）。"""
        tz = timezone_info()
        self.timezone_label.setText(f"{tz['name']} ({tz['utc_offset']})")
        mono_ms, sys_ms = now_pair()
        self.log(f"[App] Gabor task v{exp_config.APP_VERSION}（EEG 取得機能なし）")
        self.log(f"[App] PC 時刻: {format_local(sys_ms)} / {tz['name']} {tz['utc_offset']}")
        self.log("[App] PC の日時・タイムゾーンが正しいことを確認してください。")
        self.guide_area.setPlainText(
            "1. EmotivPro でヘッドセットの接触状態を確認し、記録（Record）を"
            "セッション通し 1 本で開始する\n"
            "2. Participant ID / Eye-drop Condition / 課題パラメータを入力する\n"
            "3. 「Prepare session」を押す（保存先とチェックリストが作成されます）\n"
            "4. 被験者にスペースキーを押してもらい課題を開始する"
        )

    # === セッション準備 ===

    def prepare_session(self):
        """セッションを準備する（実験開始前に実験者が 1 回押す）。

        参加者ID・条件を確定し、保存先の作成、ファイル名基底の確定、イベントログの
        開始、セッションメタとチェックリスト（計測前チェック）の出力までを行う。
        """
        if self.prepared:
            self.log("[Warning] このセッションは既に準備済みです。")
            return False

        participant_id = self.participant_id_input.text().strip()
        if not self._is_valid_participant_id(participant_id):
            self.log(
                "[Error] Participant ID は英数字・'_'・'-' で入力してください。"
            )
            return False
        if not self.update_experiment_parameters():
            self.log("[Error] 課題パラメータを修正してから再度準備してください。")
            return False
        drop_condition = self.get_drop_condition()
        self.session_notes = []
        self._event_write_failed = False

        candidate_start_pair = now_pair()
        session_datetime = datetime.fromtimestamp(candidate_start_pair[1] / 1000.0)
        date_str = session_datetime.strftime("%Y%m%d")
        dirs = self.create_save_directories(participant_id, date_str=date_str)
        if not dirs:
            return False
        self.behave_save_dir, self.eeg_save_dir = dirs

        self.record_title_base = (
            f"{participant_id}_{drop_condition}_"
            f"{session_datetime.strftime('%Y%m%d_%H%M%S')}"
        )
        self.session_start_pair = candidate_start_pair
        self.clock_monitor.start(*self.session_start_pair)
        self.session_timezone = timezone_info()
        self._last_timezone_signature = self._timezone_signature(
            self.session_timezone
        )

        try:
            self.event_logger = EventLogger(
                self.behave_save_dir, base_name=self.record_title_base
            )
        except FileExistsError:
            self.log(
                "[Error] 同じセッション名のイベントログが既に存在します。"
                "既存データを保護するため準備を中止しました。1秒待って再度お試しください。"
            )
            self._clear_failed_prepare()
            return False
        except Exception as e:
            self.log(f"[Error] イベントログを作成できませんでした: {e}")
            self._clear_failed_prepare()
            return False

        if self.exp_window and hasattr(self.exp_window, "canvas"):
            self.exp_window.canvas.file_base = self.record_title_base
            self.exp_window.canvas.save_path = self.behave_save_dir

        metadata_ok = self.write_session_metadata(participant_id, drop_condition)
        checklist_ok = self.write_checklist_pre(participant_id, drop_condition)
        if not metadata_ok or not checklist_ok:
            self.log(
                "[Error] セッションメタ／チェックリストを作成できなかったため、"
                "準備を中止しました。既存ファイルは上書きしていません。"
            )
            self._clear_failed_prepare()
            return False

        self.prepared = True
        self.finalized = False
        self.prepare_button.setText("Prepared")
        self.prepare_button.setEnabled(False)
        self.participant_id_input.setReadOnly(True)
        self.drop_condition_input.setEnabled(False)
        self._set_parameter_inputs_locked(True)
        self.status_label.setText("Prepared")
        self.log(f"[GUI] セッション準備完了: {self.record_title_base}")
        self.show_session_guide()
        return True

    def is_prepared(self):
        return self.prepared

    def reset_session(self):
        """準備状態を解除し、次のセッションを準備できる状態へ戻す。

        被験者画面でリセット（終了画面での Enter）が行われたときに呼ばれる。
        これを行わないと、次のセッションが前セッションのファイル名基底・
        イベントログを再利用してしまい、行動データを上書きする。
        """
        if self.prepared and not self.finalized:
            self.finalize_session(outcome="closed")
        self.prepared = False
        self.finalized = False
        self.record_title_base = None
        self.behave_save_dir = None
        self.eeg_save_dir = None
        self.event_logger = None
        self.session_start_pair = None
        self.checklist_path = None
        self.meta_path = None
        self._event_write_failed = False
        self.session_notes = []
        self.session_timezone = None
        self._last_timezone_signature = None
        self.prepare_button.setText("Prepare session")
        self.prepare_button.setEnabled(True)
        self.participant_id_input.setReadOnly(False)
        self.drop_condition_input.setEnabled(True)
        self._set_parameter_inputs_locked(False)
        self.status_label.setText("Waiting ...")
        self.clear_break_countdown()
        self.log(
            "[GUI] セッションをリセットしました。"
            "次の被験者は Participant ID を入力して Prepare session を押してください。"
        )

    def _clear_failed_prepare(self):
        """準備失敗時の一時状態を解除する（作成済みファイルは保護のため残す）。"""
        if self.exp_window and hasattr(self.exp_window, "canvas"):
            self.exp_window.canvas.file_base = None
        self.record_title_base = None
        self.event_logger = None
        self.session_start_pair = None
        self.checklist_path = None
        self.meta_path = None
        self.session_timezone = None
        self._last_timezone_signature = None

    def create_save_directories(self, participant_id, date_str=None):
        if date_str is None:
            _, sys_ms = now_pair()
            date_str = datetime.fromtimestamp(sys_ms / 1000.0).strftime("%Y%m%d")
        project_root = application_root()
        base_dir = os.path.join(project_root, "data", participant_id, date_str)
        behave_dir = os.path.join(base_dir, "behave")
        # eeg/ はアプリからは書き込まない。EmotivPro からの手動エクスポートを
        # 置くための場所として作成しておく（命名規則は show_session_guide 参照）。
        eeg_dir = os.path.join(base_dir, "eeg")

        try:
            os.makedirs(behave_dir, exist_ok=True)
            os.makedirs(eeg_dir, exist_ok=True)
            self.log(f"[GUI] 保存先を作成しました: {behave_dir}; {eeg_dir}")
            return behave_dir, eeg_dir
        except Exception as e:
            self.log(f"[Error] 保存先を作成できませんでした: {e}")
            return None

    def expected_eeg_basename(self):
        if not self.record_title_base:
            return ""
        return f"{self.record_title_base}{exp_config.EEG_EXPORT_SUFFIX}"

    def show_session_guide(self):
        """計測前チェックと EEG エクスポートの配置ルールを画面へ提示する。"""
        lines = [
            f"セッション: {self.record_title_base}",
            "",
            "■ 計測前チェック",
        ]
        lines += [f"  □ {item}" for item in PRE_CHECKS]
        lines += [
            "",
            "■ EEG エクスポートの配置（計測後）",
            f"  配置先: {self.eeg_save_dir}",
            f"  ファイル名: {self.expected_eeg_basename()}.<拡張子>",
            "  （EmotivPro からのエクスポートを上記の名前にリネームして置く）",
            "",
            "■ 保存済みファイル",
            f"  行動データ: {self.behave_save_dir}",
            f"  チェックリスト: {os.path.basename(self.checklist_path or '')}",
            "",
            "※ 実験終了後、チェックリストへリジェクトチャンネル等を記入し、",
            "  behave / eeg と一緒に Google Drive へアップロードしてください。",
        ]
        self.guide_area.setPlainText("\n".join(lines))

    def write_session_metadata(self, participant_id, drop_condition):
        canvas = getattr(self.exp_window, "canvas", None)
        geometry_cfg = getattr(canvas, "geometry_cfg", None)
        mono_ms, sys_ms = self.session_start_pair
        clock = self.clock_monitor.summary()

        metadata = {
            "app_version": exp_config.APP_VERSION,
            "participant_id": participant_id,
            "drop_condition": drop_condition,
            "date": datetime.fromtimestamp(sys_ms / 1000.0).strftime("%Y%m%d"),
            "start_unixtime_ms": mono_ms,
            "start_sys_unixtime_ms": sys_ms,
            "start_local_time": format_local(sys_ms),
            "timezone": self.session_timezone or timezone_info(),
            "max_tilt_angle": getattr(
                canvas, "max_tilt_angle", exp_config.DEFAULT_MAX_TILT_DEG
            ),
            "trials_per_block": getattr(
                canvas, "trials_per_block", exp_config.DEFAULT_TRIALS_PER_BLOCK
            ),
            "num_blocks": getattr(
                canvas, "num_blocks", exp_config.DEFAULT_NUM_BLOCKS
            ),
            "practice": {
                "min_trials": exp_config.PRACTICE_MIN_TRIALS,
                "threshold_ms": exp_config.PRACTICE_RT_THRESHOLD_MS,
                "window": exp_config.PRACTICE_MA_WINDOW,
            },
            "breaks": {
                "short_s": exp_config.BREAK_SHORT_S,
                "long_s": exp_config.BREAK_LONG_S,
            },
            "clock": {
                "baseline_offset_ms": clock["baseline_offset_ms"],
                "check_interval_s": clock["check_interval_s"],
                "drift_warn_ms": clock["drift_warn_ms"],
            },
            "eeg": {
                "software": "EmotivPro (manual export)",
                "sync_method": "system-clock timestamp matching",
                "expected_export_basename": self.expected_eeg_basename(),
                "note": (
                    "本アプリは EEG を取得しない。突合には *Sys(ms) 列"
                    "（OS 壁時計）を使う。"
                ),
            },
            "calibration": {
                "monitor_width_px": exp_config.MONITOR_WIDTH_PX,
                "monitor_width_mm": exp_config.MONITOR_WIDTH_MM,
                "viewing_distance_mm": exp_config.VIEWING_DISTANCE_MM,
                "patch_size_deg": exp_config.PATCH_SIZE_DEG,
                "spatial_freq_cpd": exp_config.SPATIAL_FREQ_CPD,
                "circle_diameter_mm": exp_config.CIRCLE_DIAMETER_MM,
                "revolution_period_s": exp_config.REVOLUTION_PERIOD_S,
                "geometry": geometry_cfg,
            },
        }

        self.meta_path = os.path.join(
            self.behave_save_dir, f"{self.record_title_base}_meta.json"
        )
        try:
            # 同じ基底名の既存メタ情報を上書きしない。
            with open(self.meta_path, mode="x", encoding="utf-8") as file:
                json.dump(metadata, file, ensure_ascii=False, indent=2)
            self.log(f"[GUI] セッションメタを保存しました: {self.meta_path}")
            return True
        except Exception as e:
            self.log(f"[Error] セッションメタを保存できませんでした: {e}")
            return False

    def write_checklist_pre(self, participant_id, drop_condition):
        mono_ms, sys_ms = self.session_start_pair
        self.checklist_path = os.path.join(
            self.behave_save_dir, f"{self.record_title_base}_checklist.md"
        )
        try:
            write_pre_session(
                self.checklist_path,
                {
                    "base": self.record_title_base,
                    "participant_id": participant_id,
                    "drop_condition": drop_condition,
                    "app_version": exp_config.APP_VERSION,
                    "start_unixtime_ms": mono_ms,
                    "start_sys_unixtime_ms": sys_ms,
                    "timezone": self.session_timezone or timezone_info(),
                    "behave_dir": self.behave_save_dir,
                    "eeg_dir": self.eeg_save_dir,
                    "eeg_expected_name": self.expected_eeg_basename(),
                },
            )
            self.log(f"[GUI] チェックリストを作成しました: {self.checklist_path}")
            return True
        except Exception as e:
            self.checklist_path = None
            self.log(f"[Error] チェックリストを作成できませんでした: {e}")
            return False

    def finalize_session(self, outcome="completed", result_files=None, notes=None):
        """セッション終了時にチェックリストへ実績値と計測後チェックを追記する。"""
        if not self.prepared or self.finalized:
            return False
        self.finalized = True
        end_mono_ms, end_sys_ms = now_pair()
        start_mono_ms = self.session_start_pair[0] if self.session_start_pair else None
        duration_s = (
            (end_mono_ms - start_mono_ms) / 1000.0
            if start_mono_ms is not None
            else None
        )
        files = list(result_files or [])
        for path in (self.meta_path, self.checklist_path):
            if path:
                files.append(os.path.basename(path))
        if self.event_logger:
            files.append(os.path.basename(self.event_logger.path))

        self.status_label.setText(
            "Task Finish" if outcome == "completed" else f"Session end ({outcome})"
        )
        self.clear_break_countdown()

        if not self.checklist_path:
            self.log("[Warning] チェックリストが無いため計測後欄を追記できません。")
            return False
        try:
            append_post_session(
                self.checklist_path,
                {
                    "outcome": outcome,
                    "end_unixtime_ms": end_mono_ms,
                    "end_sys_unixtime_ms": end_sys_ms,
                    "duration_s": duration_s,
                    "clock": self.clock_monitor.summary(),
                    "files": sorted(set(files)),
                    "notes": list(self.session_notes) + list(notes or []),
                },
            )
        except Exception as e:
            self.log(f"[Error] チェックリストへ追記できませんでした: {e}")
            return False

        self.log(f"[GUI] セッション終了（{outcome}）。計測後チェックを追記しました。")
        self.log("[GUI] EmotivPro の記録を停止し、エクスポートしてください。")
        self.log(
            f"[GUI] エクスポートの配置先: {self.eeg_save_dir} / "
            f"ファイル名: {self.expected_eeg_basename()}.<拡張子>"
        )
        return True

    # === クロックドリフト監視 ===

    def update_clock_status(self):
        """1 秒ごとに mono と sys のずれを確認し、表示・記録・警告を行う。"""
        mono_ms, sys_ms = now_pair()
        current_timezone = timezone_info()
        self.timezone_label.setText(
            f"{current_timezone['name']} ({current_timezone['utc_offset']})"
        )

        if not self.prepared:
            self.clock_drift_label.setText("--")
            self.clock_drift_label.setStyleSheet("")
            return

        drift = self.clock_monitor.drift_ms(mono_ms, sys_ms)
        self.clock_drift_label.setText(f"{drift:+d} ms")
        over = abs(drift) >= exp_config.CLOCK_DRIFT_WARN_MS
        self.clock_drift_label.setStyleSheet(
            "color: red; font-weight: bold;" if over else ""
        )
        if self.finalized:
            return

        events = self.clock_monitor.tick(mono_ms, sys_ms)
        for event in events:
            if self.event_logger:
                self._write_monitor_event(
                    event["event"],
                    event["detail"],
                    event["mono_ms"],
                    event["sys_ms"],
                )
            if event["event"] == DRIFT_EVENT:
                self.log(
                    f"[Warning] PC 時刻のずれを検出しました（{event['drift_ms']:+d} ms）。"
                    "スリープ復帰・時刻同期・手動の時刻変更が原因の可能性があります。"
                    "実験は継続しますが、解析時は events.csv の clock_check で補正してください。"
                )

        self._check_timezone_change(current_timezone, mono_ms, sys_ms)

    def _write_monitor_event(self, event, detail, mono_ms, sys_ms):
        """監視イベントを書き込む。失敗しても実験進行は止めない。"""
        try:
            self.event_logger.log(
                event,
                detail=detail,
                unixtime_ms=mono_ms,
                sys_unixtime_ms=sys_ms,
            )
            return True
        except OSError as e:
            if not self._event_write_failed:
                self._event_write_failed = True
                note = f"events.csv の書き込みに失敗: {e}"
                self.session_notes.append(note)
                self.log(f"[Error] イベントログへ書き込めません: {e}")
            return False

    def _check_timezone_change(self, current_timezone, mono_ms, sys_ms):
        """タイムゾーン変更を検知する。

        タイムゾーンだけを変更しても time.time() は変わらないため、クロックドリフト
        監視だけでは検知できない。PDF が同期ずれ要因として明示しているため別途監視する。
        """
        if not self.prepared or self.finalized:
            return
        current_signature = self._timezone_signature(current_timezone)
        previous_signature = self._last_timezone_signature
        if previous_signature is None:
            self._last_timezone_signature = current_signature
            return
        if current_signature == previous_signature:
            return

        previous_name, previous_offset = previous_signature
        current_name, current_offset = current_signature
        detail = (
            f"from={previous_name}/UTC_offset_s={previous_offset},"
            f"to={current_name}/UTC_offset_s={current_offset}"
        )
        if self.event_logger:
            self._write_monitor_event(
                "timezone_change", detail, mono_ms=mono_ms, sys_ms=sys_ms
            )
        note = f"セッション中にタイムゾーン変更を検出: {detail}"
        self.session_notes.append(note)
        self.log(
            f"[Warning] {note}。EmotivPro との突合時にタイムゾーンを確認してください。"
        )
        self._last_timezone_signature = current_signature

    @staticmethod
    def _timezone_signature(info):
        return info.get("name", ""), info.get("utc_offset_s", 0)

    # === 実験進行の制御 ===

    def update_experiment_parameters(self):
        parameters = self._read_experiment_parameters()
        if parameters is None:
            self.log(
                "[Error] 課題パラメータが不正です"
                "（Max Angle: 1–90、Trials / Block: 1–10000、Blocks: 1–20）。"
            )
            return False

        if self.prepared:
            self.log("[Warning] 準備後は課題パラメータを変更できません。")
            return False

        if not self.exp_window:
            return True

        phase = getattr(self.exp_window.canvas, "phase", "idle")
        if phase != self.exp_window.canvas.PHASE_IDLE:
            self.log("[Warning] 実験中はパラメータを変更できません")
            return False

        max_angle, trials_per_block, num_blocks = parameters
        angle_changed = self.exp_window.canvas.max_tilt_angle != max_angle
        self.exp_window.canvas.max_tilt_angle = max_angle
        self.exp_window.canvas.trials_per_block = trials_per_block
        self.exp_window.canvas.num_blocks = num_blocks
        if angle_changed:
            self.exp_window.canvas.init_gabor_patches()
        self.log(
            "[GUI] Parameters updated: "
            f"max_angle={max_angle}, trials_per_block={trials_per_block}, "
            f"num_blocks={num_blocks}"
        )
        return True

    def _read_experiment_parameters(self):
        try:
            values = (
                int(self.max_angle_input.text()),
                int(self.trials_per_block_input.text()),
                int(self.num_blocks_input.text()),
            )
        except ValueError:
            return None
        max_angle, trials_per_block, num_blocks = values
        if not (
            1 <= max_angle <= 90
            and 1 <= trials_per_block <= 10000
            and 1 <= num_blocks <= 20
        ):
            return None
        return values

    def _set_parameter_inputs_locked(self, locked):
        for field in (
            self.max_angle_input,
            self.trials_per_block_input,
            self.num_blocks_input,
        ):
            field.setReadOnly(locked)

    def get_drop_condition(self):
        return self.drop_condition_input.currentText()

    def toggle_pause(self):
        """一時停止/再開のトグル。"""
        canvas = getattr(self.exp_window, "canvas", None) if self.exp_window else None
        if canvas is None:
            return
        if canvas.phase == canvas.PHASE_PAUSED:
            if canvas.resume_experiment():
                self.pause_resume_button.setText("Pause")
        else:
            if canvas.pause_experiment():
                self.pause_resume_button.setText("Resume")
            else:
                self.log("[Warning] 一時停止は練習・ブロック実行中のみ可能です。")

    def handle_abort_clicked(self):
        """実験を中断する（ここまでの行動データを保存）。確認ダイアログ付き。"""
        canvas = getattr(self.exp_window, "canvas", None) if self.exp_window else None
        if canvas is None:
            return
        reply = QMessageBox.question(
            self,
            "実験の中断",
            "実験を中断しますか？ここまでの行動データは保存されます。\n"
            "（EEG は EmotivPro 側で手動停止・エクスポートしてください）",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        if canvas.abort_experiment(reason="manual_abort"):
            self.pause_resume_button.setText("Pause")
            self.clear_break_countdown()
            self.log("[GUI] 実験を中断しました。ここまでのデータを保存します。")
        else:
            self.log("[Warning] 中断できる状態ではありません。")

    def start_break_countdown(self, duration_s):
        """休憩開始時に呼ばれ、残り時間表示を初期化する。"""
        self.update_break_countdown(duration_s)

    def update_break_countdown(self, remaining_s):
        """休憩の残り時間を mm:ss で更新表示する（GaborCanvas が1秒ごとに呼ぶ）。"""
        self.break_countdown_label.setText(format_countdown(remaining_s))

    def clear_break_countdown(self):
        self.break_countdown_label.setText("--:--")

    def redirect_log_from_task(self, text):
        """
        実験タスク（GaborCanvas）からログを受け取って表示するための関数。
        他モジュールからこのGUIにログ出力する用途。
        """
        if not isinstance(text, str):
            return

        if text.startswith("Task Start"):
            self.status_label.setText(text)
            return  # ← ログには出さずに終了

        elif text == "Task Finish":
            self.status_label.setText("Task Finish")
            return

        elif text == "Now Ready":
            self.status_label.setText("Now Ready")

        self.log(text)

    @staticmethod
    def _is_valid_participant_id(participant_id):
        return bool(re.fullmatch(r"[A-Za-z0-9_-]+", participant_id))

    def closeEvent(self, event):
        # Console を閉じたのに被験者画面だけが動き続ける状態を防ぐ。進行中なら
        # 現セグメントを保存して終了し、準備後・開始前なら計測後欄だけを残す。
        canvas = getattr(self.exp_window, "canvas", None) if self.exp_window else None
        if canvas and canvas.phase not in (
            canvas.PHASE_IDLE,
            canvas.PHASE_FINISHED,
        ):
            canvas.abort_experiment(reason="controller_closed", outcome="closed")
        elif self.prepared and not self.finalized:
            self.finalize_session(outcome="closed")
        event.accept()
        app = QApplication.instance()
        if app is not None:
            app.quit()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ControllerGUI()
    window.show()
    sys.exit(app.exec_())
