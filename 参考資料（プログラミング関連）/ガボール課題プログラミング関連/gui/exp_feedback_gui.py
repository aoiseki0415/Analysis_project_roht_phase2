# ================================
# 実験課題B - PyQt5 GUI 概要
# ================================
# このスクリプトは、ガボールパッチ刺激を用いた視覚課題のPyQt5によるGUI実装です。
# 本アプリは EEG を取得しません（Emotiv Cortex API 不使用）。EEG は EmotivPro 側で
# 実験者が手動計測・手動エクスポートし、解析時に PC 壁時計のタイムスタンプで突合
# します。したがってここでの責務は「刺激提示」と「行動ログに正確な時刻を残すこと」です。
#
# 主なクラス／関数とその説明：
#
# - GaborCanvas(QWidget):
#     刺激描画用のキャンバスウィジェット。円周上のガボールパッチを描画し、傾斜アニメーション・
#     反応処理・刺激間遅延・練習/本番ブロック/休憩の進行（フェーズ状態機械）を管理します。
#     - init_gabor_patches(): 指定範囲の角度に対するガボール画像を事前生成
#     - create_gabor(orientation_deg): 指定角度のガボールパッチ画像を生成（背景透明化に対応）
#     - paintEvent(): フレーム更新ごとに刺激またはメッセージ画面を描画
#     - keyPressEvent(): フェーズごとのスペース/エンターキー入力をディスパッチ
#     - start_practice() / start_block(n): 練習・本番ブロックの初期化と開始
#     - end_current_segment(label): 練習/ブロック共通の終了処理（保存・イベントログ）
#     - start_break() / on_break_finished(): ブロック間・中間休憩の管理
#     - finish_experiment(): 実験全体の終了処理
#     - schedule_next_tilt(): 刺激表示タイミングのスケジューリング（500–1500msの割合8割、1500–3000msの割合2割）
#     - trigger_tilt(): 実際に傾斜刺激を開始する処理
#     - save_results(label): 実験結果をCSVとして保存
#
# - ExperimentWindow(QWidget):
#     実験用メインウィンドウ。キャンバスを表示。
#     - start_experiment(): ウィンドウのraise/focusのみを行う（進行はGaborCanvasのフェーズ状態機械が担う）。
#
# - main 部分:
#     PyQt5アプリケーションを実行。ウィンドウを表示し、イベントループを開始します。

import sys
import random
import csv
import os
from functools import partial
from PyQt5.QtCore import Qt, QTimer, QPointF, QRectF
from PyQt5.QtGui import QPainter, QPixmap, QImage, QColor
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QLabel,
    QSpacerItem,
    QSizePolicy,
)
import numpy as np

import exp_config
from utils.display_calibration import resolve_geometry
from utils.event_logger import EventLogger
from utils.message_layout import message_font_size_px
from utils.precise_time import now_pair, unixtime_s, unixtime_ms as now_unixtime_ms
from utils.task_logic import (
    break_duration_s,
    gabor_position,
    practice_should_end,
    sample_interval_ms,
    tilt_display_angle,
)


class GaborCanvas(QWidget):
    # === フェーズ定数 ===
    PHASE_IDLE = "idle"
    PHASE_INSTRUCTION = "instruction"
    PHASE_PRACTICE = "practice"
    PHASE_PRACTICE_DONE = "practice_done"
    PHASE_BLOCK = "block_running"
    PHASE_BREAK_REST = "break_rest"
    PHASE_BREAK_READY = "break_ready"
    PHASE_PAUSED = "paused"
    PHASE_FINISHED = "finished"

    # メッセージ画面（塗りつぶし色をMESSAGE_BG_RGBにするフェーズ）
    MESSAGE_PHASES = {
        PHASE_IDLE,
        PHASE_INSTRUCTION,
        PHASE_PRACTICE_DONE,
        PHASE_BREAK_REST,
        PHASE_BREAK_READY,
        PHASE_PAUSED,
        PHASE_FINISHED,
    }

    def __init__(
        self,
        parent=None,
        patch_diameter=40,
        max_tilt_angle=10,
        total_trials=30,
        num_blocks=None,
        external_logger=None,
        save_dir=None,
        controller_window=None,
    ):
        super().__init__(parent)
        self.setMinimumSize(800, 800)
        self.external_logger = external_logger
        self.controller_window = controller_window

        # === パラメータ設定 ===
        self.geometry_cfg = resolve_geometry(exp_config)
        self.center = QPointF(self.width() / 2, self.height() / 2)
        self.radius = 250
        self.frame_interval = exp_config.FRAME_INTERVAL_MS
        self.patch_diameter = self.geometry_cfg["patch_diameter_px"]
        self.deg_per_frame = self.geometry_cfg["deg_per_frame"]
        self.motion_phase_deg = 0.0  # 円周上の初期位置（ブロック/練習開始時に再設定予定）
        self.motion_start_time = None  # 円周移動の起点時刻（練習/ブロック開始時に設定）
        self.max_tilt_angle = max_tilt_angle
        self.trials_per_block = total_trials
        self.num_blocks = (
            num_blocks if num_blocks is not None else exp_config.DEFAULT_NUM_BLOCKS
        )
        self.save_path = save_dir or "data/behav"
        # behave ファイル名の基底。EmotivPro エクスポートと同じ
        # <ID>_<条件>_<YYYYMMDD_HHMMSS> を ControllerGUI.prepare_session から
        # 受け取る（None 時は Unixtime(ms) 付き命名にフォールバック）。
        self.file_base = None

        self.setFocusPolicy(Qt.StrongFocus)
        self.setFocus()

        # === 状態変数 ===
        self.frame_count = 0
        self.trial_active = False
        self.trial_responded = False
        self.tilt_pending = False
        self.target_tilt_angle = 0
        self.display_tilt_angle = 0
        self.is_animating_tilt = False
        self.trial_count = 0
        self.tilt_onset_time = 0  # mono 時計（反応時間の正）
        self.tilt_onset_sys_time = 0  # OS 壁時計（EEG 突合の正）
        self.onset_position = (0, 0.0, 0.0)  # (角度deg, x, y)
        self.show_gabor = False

        # === フェーズ状態機械 ===
        self.phase = self.PHASE_IDLE
        self.current_block = 0
        self.event_logger = None
        self.pending_draw_start_log = False
        self.practice_rts = []  # 練習フェーズの正答RTリスト

        # === セグメント・ポーズ・休憩の状態 ===
        self.current_segment_label = None  # 進行中セグメント（"practice"/"block1"..）
        self._prepause_phase = None  # ポーズ直前のフェーズ（Resume 時に戻す）
        self._break_remaining_s = 0  # 休憩の残り秒数
        self._break_minutes = 0  # 休憩明けメッセージ用の分数
        self._completion_message = exp_config.MSG_ALL_DONE
        self.saved_files = []  # 保存した行動データファイル名（チェックリスト用）
        self.data_write_errors = []  # チェックリストへ残す書き込みエラー
        self._event_write_error_reported = False
        self._pending_result_batches = []  # 一時的な失敗時に終了前の再試行へ回す

        # === ログ保存用 ===
        self.results = []  # 各試行の記録を格納するリスト

        # === ガボール画像生成 ===
        self.gabor_patches = {}
        self.init_gabor_patches()

        # === タイマー設定 ===
        self.timer = QTimer(self)
        # デフォルトのCoarseTimerはOSの都合で発火間隔が最大5%程度ずれる。
        # 円周移動が20秒/周と低速で1フレームあたりの移動量が小さいため、
        # このずれが動きのカクつきとして目立ちやすい。PreciseTimerで抑える。
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.timeout.connect(self.update)

        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.send_task_time_update)
        self.start_time = None  # ← 課題開始時の時刻を保持

        self.tilt_timer = QTimer(self)
        self.tilt_timer.setSingleShot(True)
        self.tilt_timer.timeout.connect(self.trigger_tilt)

        # 休憩は 1 秒ごとに残り時間を刻み、実験者側にカウントダウンを表示する。
        self.break_tick_timer = QTimer(self)
        self.break_tick_timer.timeout.connect(self._on_break_tick)

        # === メッセージ表示用 ===
        self.msg_label = QLabel("", self)
        self.msg_label.setStyleSheet(
            f"color: rgb{exp_config.MESSAGE_TEXT_COLOR}; "
            "background-color: transparent;"
        )
        self.msg_label.setAlignment(Qt.AlignCenter)
        self.msg_label.setWordWrap(True)
        self.msg_label.hide()

        # === ○×フィードバック表示用 ===
        self.feedback_label = QLabel("", self)
        self.feedback_label.setStyleSheet(
            "color: black; font-size: 80px; background-color: transparent;"
        )
        self.feedback_label.setAlignment(Qt.AlignCenter)
        self.feedback_label.hide()

        self._layout_overlay_labels()

        # === 起動時表示 ===
        self.show_message(exp_config.MSG_TASK_START)

    def resizeEvent(self, event):
        self.center = QPointF(self.width() / 2, self.height() / 2)  # 中心位置を更新
        self._layout_overlay_labels()
        super().resizeEvent(event)

    def _layout_overlay_labels(self):
        horizontal_margin = round(
            self.width() * exp_config.MESSAGE_HORIZONTAL_MARGIN_RATIO
        )
        vertical_margin = round(
            self.height() * exp_config.MESSAGE_VERTICAL_MARGIN_RATIO
        )
        content_width = max(1, self.width() - horizontal_margin * 2)
        content_height = max(1, self.height() - vertical_margin * 2)
        self.msg_label.setGeometry(
            horizontal_margin,
            vertical_margin,
            content_width,
            content_height,
        )
        message_font = self.msg_label.font()
        message_font.setPixelSize(
            message_font_size_px(
                content_width,
                content_height,
                self.msg_label.text(),
                min_px=exp_config.MESSAGE_FONT_MIN_PX,
                max_px=exp_config.MESSAGE_FONT_MAX_PX,
            )
        )
        self.msg_label.setFont(message_font)
        self.feedback_label.setGeometry(0, 0, self.width(), self.height())

    def show_message(self, text):
        self.msg_label.setText(text)
        self._layout_overlay_labels()
        self.msg_label.show()
        self.update()

    def hide_message(self):
        self.msg_label.hide()
        self.update()

    def _record_data_write_error(self, message):
        if message not in self.data_write_errors:
            self.data_write_errors.append(message)
        if self.external_logger:
            self.external_logger(f"[Error] {message}")
        else:
            print(f"[Error] {message}")

    def _log_event(
        self, event, detail="", unixtime_ms=None, sys_unixtime_ms=None
    ):
        """イベントを書き込む。I/O 失敗時も課題進行を止めない。"""
        if not self.event_logger:
            return False
        try:
            self.event_logger.log(
                event,
                detail=detail,
                unixtime_ms=unixtime_ms,
                sys_unixtime_ms=sys_unixtime_ms,
            )
            return True
        except OSError as exc:
            if not self._event_write_error_reported:
                self._event_write_error_reported = True
                self._record_data_write_error(
                    f"events.csv の書き込みに失敗しました"
                    f"（最初に失敗したイベント: {event}）: {exc}"
                )
            return False

    def _report_tilt_onset(self, block, trial, target, mono_ms, sys_ms):
        """描画イベント終了後にオンセットを保存し、描画を I/O で遅らせない。"""
        self._log_event(
            "tilt_onset",
            detail=f"block={block},trial={trial},target={target}",
            unixtime_ms=mono_ms,
            sys_unixtime_ms=sys_ms,
        )
        message = f"Trial {trial} - 傾斜開始: 目標角度 {target}°"
        if self.external_logger:
            self.external_logger(message)
        else:
            print(message)

    def _report_gabor_draw_start(self, block, mono_ms, sys_ms):
        self._log_event(
            "gabor_draw_start",
            detail=f"block={block}",
            unixtime_ms=mono_ms,
            sys_unixtime_ms=sys_ms,
        )

    def show_feedback(self, is_ok):
        self.feedback_label.setText("○" if is_ok else "×")
        self.feedback_label.show()
        QTimer.singleShot(exp_config.FEEDBACK_DURATION_MS, self.feedback_label.hide)

    def init_gabor_patches(self):
        self.gabor_patches = {}
        for angle in range(-self.max_tilt_angle, self.max_tilt_angle + 1):
            self.gabor_patches[angle] = self.create_gabor(angle)

    def create_gabor(self, orientation_deg):
        size = self.patch_diameter
        image = QImage(size, size, QImage.Format_ARGB32)
        image.fill(QColor(0, 0, 0, 0))

        center = size / 2
        freq = self.geometry_cfg["cycles_per_patch"] / size
        contrast = exp_config.CONTRAST
        mean_lum = exp_config.BACKGROUND_RGB[0]
        amp = mean_lum * contrast
        sigma = size / 4
        edge_width = 0
        angle_rad = np.deg2rad(orientation_deg)

        for y in range(size):
            for x in range(size):
                xp = x - center
                yp = y - center
                r = np.sqrt(xp**2 + yp**2)

                if r >= size / 2:
                    mask = 0
                elif r > (size / 2 - edge_width):
                    mask = 0.5 * (
                        1 + np.cos(np.pi * (r - (size / 2 - edge_width)) / edge_width)
                    )
                else:
                    mask = 1

                x_rot = xp * np.cos(angle_rad) + yp * np.sin(angle_rad)
                grating = np.cos(2 * np.pi * freq * x_rot)
                gauss = np.exp(-(xp**2 + yp**2) / (2 * sigma**2))
                intensity = mean_lum + amp * grating * gauss
                intensity = np.clip(intensity, 0, 255)
                val = int(intensity * mask)
                image.setPixelColor(x, y, QColor(val, val, val, int(255 * mask)))

        return QPixmap.fromImage(image)

    def current_radius(self):
        radius_px = self.geometry_cfg["radius_px"]
        if radius_px is None:
            return min(self.width(), self.height()) * exp_config.FALLBACK_RADIUS_RATIO
        return radius_px

    def current_motion_angle(self):
        # QTimer/paintEventの発火間隔はOSスケジューリングにより揺らぐため、
        # frame_count（描画回数）ではなく経過時間から角度を直接算出する。
        # こうすることで、フレームが遅延・スキップしても位置が実時間から
        # ずれず、「止まって後で飛ぶ」ようなカクつきが生じない。
        if self.motion_start_time is None:
            elapsed_s = 0.0
        else:
            elapsed_s = unixtime_s() - self.motion_start_time
        degrees_per_second = 360.0 / exp_config.REVOLUTION_PERIOD_S
        return (self.motion_phase_deg + elapsed_s * degrees_per_second) % 360

    def current_gabor_position(self):
        angle = self.current_motion_angle()
        x, y = gabor_position(
            self.center.x(), self.center.y(), self.current_radius(), angle
        )
        return angle, x, y

    def paintEvent(self, event):
        self.center = QPointF(self.width() / 2, self.height() / 2)
        self.radius = self.current_radius()
        painter = QPainter(self)
        # 円周移動は20秒/周と低速で1フレームの移動量が1〜2px程度しかないため、
        # 整数ピクセルへスナップして描画すると階段状のカクつきが目立つ。
        # QRectF始点＋SmoothPixmapTransformでサブピクセル単位の滑らかな
        # 位置決めにする。
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        if self.phase in self.MESSAGE_PHASES:
            painter.fillRect(self.rect(), QColor(*exp_config.MESSAGE_BG_RGB))
        else:
            painter.fillRect(self.rect(), QColor(*exp_config.BACKGROUND_RGB))

        draw_started_this_frame = False
        draw_start_pair = None
        if self.pending_draw_start_log and self.show_gabor:
            draw_start_pair = now_pair()
            draw_started_this_frame = True
            self.pending_draw_start_log = False

        if not self.show_gabor:
            return

        angle_deg, patch_x, patch_y = self.current_gabor_position()
        tilt_started_this_frame = False
        if self.tilt_pending and self.phase in (
            self.PHASE_PRACTICE,
            self.PHASE_BLOCK,
        ):
            # QTimer の発火時刻ではなく、最初の傾斜フレームを描く時刻を刺激
            # オンセットとする。タイマー発火から描画までの 1 フレーム前後のずれを
            # Sys 時刻へ混入させないため。
            self.trial_count += 1
            self.tilt_onset_time, self.tilt_onset_sys_time = now_pair()
            self.onset_position = (angle_deg, patch_x, patch_y)
            self.tilt_pending = False
            self.trial_active = True
            self.trial_responded = False
            self.is_animating_tilt = True
            self.display_tilt_angle = 0
            tilt_started_this_frame = True

        if self.trial_active and self.is_animating_tilt:
            # 傾斜角は経過時間から直接算出する（実時間ベース）。1度あたり
            # TILT_MS_PER_DEG ミリ秒かけて目標角へ到達させることで、リフレッシュ
            # レートやフレーム落ちに依存せず傾斜の速度・到達時間を一定に保つ。
            elapsed_ms = now_unixtime_ms() - self.tilt_onset_time
            self.display_tilt_angle = tilt_display_angle(
                elapsed_ms, self.target_tilt_angle, exp_config.TILT_MS_PER_DEG
            )
            if abs(self.display_tilt_angle) >= abs(self.target_tilt_angle):
                self.is_animating_tilt = False
                self.display_tilt_angle = self.target_tilt_angle
        elif not self.trial_active:
            self.display_tilt_angle = 0

        rounded_angle = round(self.display_tilt_angle)
        # ガボール画像は整数角度で事前生成している。オンセットフレームが 0°へ
        # 丸められると「時刻だけ開始して見た目はまだ垂直」になるため、開始後は
        # 最小 1°の傾斜を描画する。
        if self.trial_active and rounded_angle == 0 and self.target_tilt_angle != 0:
            rounded_angle = 1 if self.target_tilt_angle > 0 else -1
        rounded_angle = np.clip(
            rounded_angle, -self.max_tilt_angle, self.max_tilt_angle
        )
        patch = self.gabor_patches.get(rounded_angle, self.gabor_patches.get(0))

        if patch:
            target_rect = QRectF(
                patch_x - self.patch_diameter / 2,
                patch_y - self.patch_diameter / 2,
                self.patch_diameter,
                self.patch_diameter,
            )
            painter.drawPixmap(target_rect, patch, QRectF(patch.rect()))

        if tilt_started_this_frame:
            QTimer.singleShot(
                0,
                partial(
                    self._report_tilt_onset,
                    self.current_block,
                    self.trial_count,
                    self.target_tilt_angle,
                    self.tilt_onset_time,
                    self.tilt_onset_sys_time,
                ),
            )
        if draw_started_this_frame:
            draw_mono_ms, draw_sys_ms = draw_start_pair
            QTimer.singleShot(
                0,
                partial(
                    self._report_gabor_draw_start,
                    self.current_block,
                    draw_mono_ms,
                    draw_sys_ms,
                ),
            )

        self.frame_count += 1

    def keyPressEvent(self, event):
        if self.phase == self.PHASE_IDLE:
            if event.key() != Qt.Key_Space:
                return

            if self.parent() and hasattr(self.parent(), "get_experiment_parameters"):
                max_angle, trial_count, num_blocks = (
                    self.parent().get_experiment_parameters()
                )
                self.max_tilt_angle = max_angle
                self.trials_per_block = trial_count
                self.num_blocks = num_blocks
                self.init_gabor_patches()  # 傾き変更後は再生成

                if self.external_logger:
                    self.external_logger(
                        f"最大傾斜角度：{self.max_tilt_angle}; "
                        f"トライアル数：{self.trials_per_block}; "
                        f"ブロック数：{self.num_blocks}"
                    )

            if not self._acquire_session():
                return

            detail = (
                f"blocks={self.num_blocks},trials_per_block={self.trials_per_block}"
            )
            self._log_event("experiment_start", detail=detail)

            self.phase = self.PHASE_INSTRUCTION
            self.show_message(exp_config.MSG_INSTRUCTION)

            self.start_time = unixtime_s()
            self.status_timer.start(1000)
            return

        if self.phase == self.PHASE_INSTRUCTION:
            if event.key() == Qt.Key_Space:
                self.start_practice()
            return

        if self.phase in (self.PHASE_PRACTICE, self.PHASE_BLOCK):
            if event.key() == Qt.Key_Space:
                self.handle_response_keypress()
            return

        if self.phase == self.PHASE_PRACTICE_DONE:
            if event.key() == Qt.Key_Space:
                self.start_block(1)
            return

        if self.phase in (self.PHASE_BREAK_REST, self.PHASE_PAUSED):
            # 休憩中・一時停止中はキー入力を無視（進行は自動 / Console 操作）
            return

        if self.phase == self.PHASE_BREAK_READY:
            if event.key() == Qt.Key_Space:
                self.start_block(self.current_block + 1)
            return

        if self.phase == self.PHASE_FINISHED:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                self.reset_for_new_session()
                self.setFocus()  # ← フォーカス取り直し
            return

    def _acquire_session(self):
        """課題開始前に保存先・ファイル名基底・イベントロガーを確定する。

        Console 接続時は「セッション準備（Prepare session）」が済んでいることを
        必須とする（保存先とファイル名基底、計測前チェックの提示がここで確定するため）。
        Console 未接続（GUI単体起動）時は従来どおり自前でイベントロガーを作る。
        """
        controller = self.controller_window
        if controller is None:
            self.event_logger = EventLogger(self.save_path, base_name=self.file_base)
            return True

        if not controller.is_prepared():
            if self.external_logger:
                self.external_logger(
                    "[Warning] 課題を開始できません。"
                    "Console で Participant ID を入力し「Prepare session」を押してください。"
                )
            return False

        self.save_path = controller.behave_save_dir
        self.file_base = controller.record_title_base
        self.event_logger = controller.event_logger
        return True

    def handle_response_keypress(self):
        current_time, current_sys_time = now_pair()
        phase_label = "practice" if self.phase == self.PHASE_PRACTICE else "main"

        if self.trial_active and not self.trial_responded:
            reaction_time = current_time - self.tilt_onset_time
            if self.external_logger:
                self.external_logger(
                    f"Trial {self.trial_count} Correct - 反応時間: {reaction_time}ms"
                )
            else:
                print(
                    f"Trial {self.trial_count} Correct - 反応時間: {reaction_time}ms"
                )

            onset_angle, onset_x, onset_y = self.onset_position
            press_angle, press_x, press_y = self.current_gabor_position()
            self.results.append(
                [
                    self.trial_count,
                    self.tilt_onset_time,
                    self.tilt_onset_sys_time,
                    current_time,
                    current_sys_time,
                    reaction_time,
                    "correct",
                    self.current_block,
                    phase_label,
                    self.target_tilt_angle,
                    onset_angle,
                    onset_x,
                    onset_y,
                    press_angle,
                    press_x,
                    press_y,
                ]
            )
            self.trial_responded = True
            self.trial_active = False
            self.is_animating_tilt = False
            self.display_tilt_angle = 0

            if self.phase == self.PHASE_PRACTICE:
                self.practice_rts.append(reaction_time)
                self.show_feedback(reaction_time <= exp_config.PRACTICE_RT_THRESHOLD_MS)
                if practice_should_end(
                    self.practice_rts,
                    exp_config.PRACTICE_MIN_TRIALS,
                    exp_config.PRACTICE_RT_THRESHOLD_MS,
                    exp_config.PRACTICE_MA_WINDOW,
                ):
                    self.end_current_segment(
                        "practice",
                        segment_end_ms=current_time,
                        segment_end_sys_ms=current_sys_time,
                    )
                    self.show_message(exp_config.MSG_PRACTICE_DONE)
                    self.phase = self.PHASE_PRACTICE_DONE
                else:
                    self.schedule_next_tilt()
            else:  # PHASE_BLOCK
                if self.trial_count >= self.trials_per_block:
                    self.end_current_segment(
                        f"block{self.current_block}",
                        segment_end_ms=current_time,
                        segment_end_sys_ms=current_sys_time,
                    )
                    if self.current_block < self.num_blocks:
                        self.start_break()
                    else:
                        self.finish_experiment()
                else:
                    self.schedule_next_tilt()
        elif not self.trial_active:
            if self.external_logger:
                self.external_logger(
                    f"Trial {self.trial_count} Mistouch - 傾斜なしでキーが押されました。"
                )
            else:
                print(
                    f"Trial {self.trial_count} Mistouch - 傾斜なしでキーが押されました。"
                )

            press_angle, press_x, press_y = self.current_gabor_position()
            self.results.append(
                [
                    self.trial_count,
                    "",
                    "",
                    current_time,
                    current_sys_time,
                    "",
                    "mistouch",
                    self.current_block,
                    phase_label,
                    self.target_tilt_angle,
                    "",
                    "",
                    "",
                    press_angle,
                    press_x,
                    press_y,
                ]
            )
            if self.phase == self.PHASE_PRACTICE:
                self.show_feedback(False)

    def start_practice(self):
        self.current_segment_label = "practice"
        self._start_practice_body()

    def _start_practice_body(self):
        self.hide_message()
        self.phase = self.PHASE_PRACTICE
        self.current_block = 0
        self.trial_count = 0
        self.practice_rts = []
        self.motion_phase_deg = random.uniform(0, 360)
        self.motion_start_time = unixtime_s()
        self.frame_count = 0
        self.results = []
        self.show_gabor = True
        self.pending_draw_start_log = True
        self.timer.start(self.frame_interval)
        self._log_event("practice_start")
        self.schedule_next_tilt()

    def start_block(self, n):
        self.current_segment_label = f"block{n}"
        self._start_block_body(n)

    def _start_block_body(self, n):
        self.hide_message()
        self.phase = self.PHASE_BLOCK
        self.current_block = n
        self.trial_count = 0
        self.motion_phase_deg = random.uniform(0, 360)
        self.motion_start_time = unixtime_s()
        self.frame_count = 0
        self.results = []
        self.show_gabor = True
        self.pending_draw_start_log = True
        self.timer.start(self.frame_interval)
        self._log_event("block_start", detail=str(n))
        if self.external_logger:
            self.external_logger(f"Block {n} start")
        self.schedule_next_tilt()

    def end_current_segment(self, label, segment_end_ms=None, segment_end_sys_ms=None):
        """練習/ブロック共通の終了処理（self.phase が切り替わる前に呼ぶこと）。"""
        if segment_end_ms is None or segment_end_sys_ms is None:
            segment_end_ms, segment_end_sys_ms = now_pair()
        self.tilt_timer.stop()
        self.timer.stop()
        self.show_gabor = False
        self.save_results(label)
        event_name = (
            "practice_end" if self.phase == self.PHASE_PRACTICE else "block_end"
        )
        if self.event_logger:
            self._log_event(
                event_name,
                detail=str(self.current_block),
                unixtime_ms=segment_end_ms,
                sys_unixtime_ms=segment_end_sys_ms,
            )
            # 実験全体の終端も events.csv に残す（EEG 側は EmotivPro の 1 本の
            # 記録なので、解析時はこの時刻で区間を切り出す）。
            if (
                self.phase == self.PHASE_BLOCK
                and self.current_block >= self.num_blocks
            ):
                self._log_event(
                    "experiment_end",
                    unixtime_ms=segment_end_ms,
                    sys_unixtime_ms=segment_end_sys_ms,
                )

    def start_break(self):
        duration_s = break_duration_s(
            self.current_block,
            self.num_blocks,
            exp_config.BREAK_SHORT_S,
            exp_config.BREAK_LONG_S,
            exp_config.LONG_BREAK_AFTER_BLOCK,
        )
        self._break_remaining_s = duration_s
        self._break_minutes = duration_s // 60
        self.show_message(
            exp_config.MSG_BLOCK_INTERVAL.format(
                n=self.current_block, minutes=self._break_minutes
            )
        )
        self.phase = self.PHASE_BREAK_REST
        self._log_event(
            "break_start",
            detail=f"after_block={self.current_block},duration_s={duration_s}",
        )
        # 実験者側に休憩の残り時間をカウントダウン表示する。
        if self.controller_window and hasattr(
            self.controller_window, "start_break_countdown"
        ):
            self.controller_window.start_break_countdown(duration_s)
        self.break_tick_timer.start(1000)

    def _on_break_tick(self):
        self._break_remaining_s -= 1
        if self.controller_window and hasattr(
            self.controller_window, "update_break_countdown"
        ):
            self.controller_window.update_break_countdown(
                max(0, self._break_remaining_s)
            )
        if self._break_remaining_s <= 0:
            self.break_tick_timer.stop()
            self.on_break_finished()

    def on_break_finished(self):
        self._log_event("break_end")
        if self.controller_window and hasattr(
            self.controller_window, "clear_break_countdown"
        ):
            self.controller_window.clear_break_countdown()
        # 被験者側は休憩中カウントダウンを見せず、経過後に「x分経ちました…」を表示。
        self.show_message(
            exp_config.MSG_BREAK_DONE.format(minutes=self._break_minutes)
        )
        self.phase = self.PHASE_BREAK_READY

    def finish_experiment(self):
        self._completion_message = exp_config.MSG_ALL_DONE
        self._complete_experiment(outcome="completed")

    def _complete_experiment(self, outcome="completed"):
        self.status_timer.stop()
        self.break_tick_timer.stop()
        self.show_message(self._completion_message)
        self.phase = self.PHASE_FINISHED
        self._notify_session_end(outcome)
        if (
            exp_config.EXIT_FULLSCREEN_ON_FINISH
            and self.window().isFullScreen()
        ):
            self.window().showNormal()
        self.window().setWindowFlag(Qt.WindowStaysOnTopHint, False)
        self.window().show()

    def _notify_session_end(self, outcome):
        """セッション終了を Console へ通知する（チェックリストの計測後欄を追記）。"""
        self._retry_pending_result_saves()
        if not self.controller_window or not hasattr(
            self.controller_window, "finalize_session"
        ):
            return
        self.controller_window.finalize_session(
            outcome=outcome,
            result_files=list(self.saved_files),
            notes=list(self.data_write_errors),
        )

    # === ポーズ / 再開 / 中断（Console から操作） ===
    def pause_experiment(self):
        """一時停止する。練習・ブロック進行中のみ有効。"""
        if self.phase not in (self.PHASE_PRACTICE, self.PHASE_BLOCK):
            return False
        self._prepause_phase = self.phase
        self.tilt_timer.stop()
        self.timer.stop()
        # 進行中の試行を破棄する。
        discarded_trial = self.trial_count if self.trial_active else None
        if self.trial_active and self.trial_count > 0:
            # 本番ブロックの完了判定は trial_count を使うため、破棄した試行を
            # 数えたままにすると results.csv の正答試行が設定数より 1 件減る。
            self.trial_count -= 1
        self.trial_active = False
        self.tilt_pending = False
        self.is_animating_tilt = False
        self.trial_responded = True
        self.display_tilt_angle = 0
        # 円周位置を凍結し、Resume 時に同じ位置から動き出せるようにする。
        self.motion_phase_deg = self.current_motion_angle()
        self.motion_start_time = None
        self.show_gabor = False
        pause_detail = self.current_segment_label or ""
        if discarded_trial is not None:
            pause_detail += f",discarded_trial={discarded_trial}"
        self._log_event("pause", detail=pause_detail)
        self.phase = self.PHASE_PAUSED
        self.show_message(exp_config.MSG_PAUSED)
        if self.external_logger:
            self.external_logger("[GUI] 実験を一時停止しました。")
        return True

    def resume_experiment(self):
        """一時停止から再開する。"""
        if self.phase != self.PHASE_PAUSED:
            return False
        target_phase = self._prepause_phase or self.PHASE_BLOCK
        self._prepause_phase = None
        self._log_event("resume", detail=self.current_segment_label or "")
        self.phase = target_phase
        self.hide_message()
        self.show_gabor = True
        # motion_phase_deg は Pause 時の角度を維持したまま、起点時刻だけ更新する。
        self.motion_start_time = unixtime_s()
        self.timer.start(self.frame_interval)
        self.schedule_next_tilt()
        if self.external_logger:
            self.external_logger("[GUI] 実験を再開しました。")
        return True

    def abort_experiment(self, reason="", outcome="aborted"):
        """実験を中断し、そこまでの行動データを保存して終了する。"""
        if self.phase in (self.PHASE_IDLE, self.PHASE_FINISHED):
            return False
        self.tilt_timer.stop()
        self.timer.stop()
        self.status_timer.stop()
        self.break_tick_timer.stop()
        self.trial_active = False
        self.tilt_pending = False
        self.is_animating_tilt = False
        self.show_gabor = False
        abort_ms, abort_sys_ms = now_pair()
        # 進行中セグメントの行動データを保存（練習中は current_block=0）。
        seg = self.current_segment_label or (
            "practice"
            if self.phase == self.PHASE_PRACTICE
            else f"block{self.current_block}"
        )
        self.save_results(f"aborted_{seg}")
        if self.event_logger:
            self._log_event(
                "abort",
                detail=reason or seg,
                unixtime_ms=abort_ms,
                sys_unixtime_ms=abort_sys_ms,
            )
            self._log_event(
                "experiment_end",
                detail=outcome,
                unixtime_ms=abort_ms,
                sys_unixtime_ms=abort_sys_ms,
            )
        if self.controller_window and hasattr(
            self.controller_window, "clear_break_countdown"
        ):
            self.controller_window.clear_break_countdown()
        self._completion_message = exp_config.MSG_ABORTED
        if self.external_logger:
            self.external_logger(
                "[GUI] 実験を中断しました。ここまでのデータを保存します。"
            )
        self._complete_experiment(outcome=outcome)
        return True

    def send_task_time_update(self):
        if self.start_time is not None:
            elapsed = int(unixtime_s() - self.start_time)
            if self.external_logger:
                self.external_logger(f"Task Start {elapsed}s")

    def schedule_next_tilt(self):
        self.trial_responded = False
        self.trial_active = False
        self.tilt_pending = False
        self.display_tilt_angle = 0

        delay = sample_interval_ms(
            random,
            exp_config.INTERVAL_SHORT_RANGE_MS,
            exp_config.INTERVAL_LONG_RANGE_MS,
            exp_config.INTERVAL_SHORT_PROB,
        )
        self.tilt_timer.start(delay)

    def trigger_tilt(self):
        if (
            self.phase not in (self.PHASE_PRACTICE, self.PHASE_BLOCK)
            or not self.show_gabor
        ):
            return

        self.target_tilt_angle = random.choice(
            [-self.max_tilt_angle, self.max_tilt_angle]
        )
        self.tilt_pending = True
        self.is_animating_tilt = False
        self.display_tilt_angle = 0
        # 実際のオンセット時刻は、次の paintEvent で最初の傾斜画像を描く直前に取る。
        self.update()

    def save_results(self, label):
        """セグメント（label）の行動データを CSV 保存する。

        ファイル名は EmotivPro エクスポートと同じ基底を使い
        ``<ID>_<条件>_<日時>_<セグメント>_results.csv`` とする。基底が無い場合のみ
        Unixtime(ms) 付き命名にフォールバックする。

        時刻列は mono（``*(ms)``）と sys（``*Sys(ms)``）の併記。反応時間は mono の
        差分、EEG との突合は sys を使う。
        """
        if not self.results:
            return None
        rows = list(self.results)
        self.results = []
        filename = self._result_filename(label)
        if self._write_result_rows(filename, rows):
            return filename

        # 次セグメントを継続できるよう、未保存行をラベルとともにメモリへ退避する。
        # セッション終了時に 1 回再試行し、それでも失敗した場合はチェックリストへ残す。
        self._pending_result_batches.append(
            {"label": label, "filename": filename, "rows": rows}
        )
        return None

    def _result_filename(self, label):
        if self.file_base:
            return os.path.join(
                self.save_path, f"{self.file_base}_{label}_results.csv"
            )
        return os.path.join(
            self.save_path, f"gabor_results_{label}_{now_unixtime_ms()}.csv"
        )

    def _write_result_rows(self, filename, rows):
        try:
            os.makedirs(self.save_path, exist_ok=True)
            # 既存の実験データを上書きしない。基底名衝突も書き込み失敗として
            # Console とチェックリストへ明示する。
            with open(filename, mode="x", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow(
                    [
                        "Trial",
                        "TiltOnset(ms)",
                        "TiltOnsetSys(ms)",
                        "KeyPress(ms)",
                        "KeyPressSys(ms)",
                        "RT(ms)",
                        "ResponseType",
                        "Block",
                        "Phase",
                        "TargetAngle(deg)",
                        "OnsetPosAngle(deg)",
                        "OnsetPosX(px)",
                        "OnsetPosY(px)",
                        "PressPosAngle(deg)",
                        "PressPosX(px)",
                        "PressPosY(px)",
                    ]
                )
                writer.writerows(rows)
        except (OSError, csv.Error) as exc:
            self._record_data_write_error(
                f"行動結果 CSV を保存できませんでした"
                f"（{os.path.basename(filename)}）: {exc}"
            )
            return False

        self.saved_files.append(os.path.basename(filename))
        if self.external_logger:
            self.external_logger(f"[GUI] 結果を {filename} に保存しました。")
        else:
            print(f"結果を {filename} に保存しました。")
        return True

    def _retry_pending_result_saves(self):
        if not self._pending_result_batches:
            return
        pending = self._pending_result_batches
        self._pending_result_batches = []
        for batch in pending:
            if not self._write_result_rows(batch["filename"], batch["rows"]):
                self._pending_result_batches.append(batch)
        if self._pending_result_batches:
            labels = ", ".join(batch["label"] for batch in self._pending_result_batches)
            self._record_data_write_error(
                f"終了時の再試行後も未保存の行動結果があります: {labels}"
            )

    def reset_for_new_session(self):
        self.results = []
        self.saved_files = []
        self.data_write_errors = []
        self._event_write_error_reported = False
        self._pending_result_batches = []
        self.frame_count = 0
        self.trial_active = False
        self.trial_responded = False
        self.tilt_pending = False
        self.target_tilt_angle = 0
        self.display_tilt_angle = 0
        self.is_animating_tilt = False
        self.trial_count = 0
        self.tilt_onset_time = 0
        self.tilt_onset_sys_time = 0
        self.onset_position = (0, 0.0, 0.0)
        self.practice_rts = []
        self.show_gabor = False
        self.pending_draw_start_log = False
        self.tilt_timer.stop()
        self.break_tick_timer.stop()
        self.status_timer.stop()
        self.current_block = 0
        self.current_segment_label = None
        self._prepause_phase = None
        self._completion_message = exp_config.MSG_ALL_DONE
        self.event_logger = None
        self.file_base = None
        self.phase = self.PHASE_IDLE
        # Console 側も準備状態を解除する（解除しないと次のセッションが前セッションの
        # ファイル名基底・イベントログを再利用し、行動データを上書きしてしまう）。
        if self.controller_window and hasattr(self.controller_window, "reset_session"):
            self.controller_window.reset_session()
        elif self.controller_window and hasattr(
            self.controller_window, "clear_break_countdown"
        ):
            self.controller_window.clear_break_countdown()
        self.show_message(exp_config.MSG_TASK_START)


class ExperimentWindow(QWidget):
    def __init__(
        self,
        trials_per_block=10,
        num_blocks=exp_config.DEFAULT_NUM_BLOCKS,
        external_logger=None,
        max_angle_input=10,
        save_dir=None,
        controller_window=None,
    ):
        super().__init__()
        self.setWindowTitle("実験課題B - PyQt版")
        self.trials_per_block = trials_per_block
        self.num_blocks = num_blocks
        self.max_angle_input = max_angle_input
        self.controller_window = controller_window

        self.canvas = GaborCanvas(
            max_tilt_angle=max_angle_input or 10,
            total_trials=self.trials_per_block,
            num_blocks=self.num_blocks,
            external_logger=external_logger,
            save_dir=save_dir,
            controller_window=self.controller_window,
        )

        layout = QVBoxLayout()
        layout.addSpacerItem(
            QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding)
        )
        layout.addWidget(self.canvas, alignment=Qt.AlignHCenter | Qt.AlignVCenter)
        layout.addSpacerItem(
            QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding)
        )

        self.setLayout(layout)

    def start_experiment(self):
        """ウィンドウを前面に出してフォーカスする。進行はcanvasのフェーズ状態機械が担う。"""
        self.show()
        self.raise_()
        self.activateWindow()

    def get_experiment_parameters(self):
        if self.controller_window:
            try:
                max_angle = int(self.controller_window.max_angle_input.text())
                trial_count = int(
                    self.controller_window.trials_per_block_input.text()
                )
                num_blocks = int(self.controller_window.num_blocks_input.text())
                return max_angle, trial_count, num_blocks
            except ValueError:
                pass
        return (
            self.canvas.max_tilt_angle,
            self.canvas.trials_per_block,
            self.canvas.num_blocks,
        )  # fallback

    def closeEvent(self, event):
        # 被験者画面だけが閉じられた場合も、進行中データとチェックリストを残して
        # アプリ全体を終了する。
        if self.canvas.phase not in (
            self.canvas.PHASE_IDLE,
            self.canvas.PHASE_FINISHED,
        ):
            self.canvas.abort_experiment(
                reason="participant_window_closed", outcome="closed"
            )
        elif (
            self.controller_window
            and self.controller_window.is_prepared()
            and not self.controller_window.finalized
        ):
            self.controller_window.finalize_session(outcome="closed")
        event.accept()
        app = QApplication.instance()
        if app is not None:
            app.quit()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ExperimentWindow(trials_per_block=80)
    window.show()
    sys.exit(app.exec_())
