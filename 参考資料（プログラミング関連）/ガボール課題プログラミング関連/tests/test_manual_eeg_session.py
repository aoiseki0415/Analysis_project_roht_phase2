import csv
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt5.QtCore import QEvent, Qt
    from PyQt5.QtGui import QKeyEvent
    from PyQt5.QtWidgets import QApplication

    import exp_config
    from gui.controller_gui import ControllerGUI
    from gui.exp_feedback_gui import ExperimentWindow, GaborCanvas
except ImportError:
    QApplication = None
    ControllerGUI = None
    ExperimentWindow = None
    GaborCanvas = None


class FakeCanvas:
    PHASE_IDLE = "idle"
    PHASE_FINISHED = "finished"

    def __init__(self):
        self.phase = self.PHASE_IDLE
        self.max_tilt_angle = 10
        self.trials_per_block = 320
        self.num_blocks = 6
        self.geometry_cfg = {"source": "test"}
        self.file_base = None
        self.save_path = None
        self.patch_refresh_count = 0

    def init_gabor_patches(self):
        self.patch_refresh_count += 1


@unittest.skipIf(QApplication is None, "PyQt5 is not installed")
class ManualEegSessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.behave_dir = os.path.join(self._tmp.name, "behave")
        self.eeg_dir = os.path.join(self._tmp.name, "eeg")
        os.makedirs(self.behave_dir)
        os.makedirs(self.eeg_dir)
        self.canvas = FakeCanvas()
        self.controller = ControllerGUI(
            exp_window=SimpleNamespace(canvas=self.canvas)
        )
        self.controller.create_save_directories = lambda _participant_id, **_kwargs: (
            self.behave_dir,
            self.eeg_dir,
        )

    def tearDown(self):
        self.controller.clock_timer.stop()
        self.controller.prepared = False
        self.controller.deleteLater()
        self.app.processEvents()
        self._tmp.cleanup()

    def test_prepare_validates_and_locks_task_parameters(self):
        self.controller.participant_id_input.setText("P01")
        self.controller.max_angle_input.setText("12")
        self.controller.trials_per_block_input.setText("40")
        self.controller.num_blocks_input.setText("3")

        self.assertTrue(self.controller.prepare_session())
        self.assertEqual(12, self.canvas.max_tilt_angle)
        self.assertEqual(40, self.canvas.trials_per_block)
        self.assertEqual(3, self.canvas.num_blocks)
        self.assertTrue(self.controller.max_angle_input.isReadOnly())
        self.assertTrue(self.controller.trials_per_block_input.isReadOnly())
        self.assertTrue(self.controller.num_blocks_input.isReadOnly())

        with open(self.controller.meta_path, encoding="utf-8") as file:
            metadata = json.load(file)
        self.assertEqual(12, metadata["max_tilt_angle"])
        self.assertEqual(40, metadata["trials_per_block"])
        self.assertEqual(3, metadata["num_blocks"])

    def test_prepare_rejects_invalid_task_parameters(self):
        self.controller.participant_id_input.setText("P01")
        self.controller.max_angle_input.setText("")
        self.assertFalse(self.controller.prepare_session())
        self.assertFalse(self.controller.is_prepared())
        self.assertEqual([], os.listdir(self.behave_dir))

    def test_timezone_change_is_logged_even_without_clock_drift(self):
        self.controller.participant_id_input.setText("P01")
        self.assertTrue(self.controller.prepare_session())
        old_name, old_offset = self.controller._last_timezone_signature
        changed = {
            "name": f"{old_name}_changed",
            "utc_offset_s": old_offset + 3600,
            "utc_offset": "UTC+00:00",
        }

        self.controller._check_timezone_change(changed, 1000, 1000)

        with open(
            self.controller.event_logger.path, newline="", encoding="utf-8"
        ) as file:
            rows = list(csv.reader(file))
        self.assertEqual("timezone_change", rows[-1][2])
        self.assertTrue(
            any("タイムゾーン変更" in note for note in self.controller.session_notes)
        )

    def test_save_directories_follow_the_current_project_location(self):
        self.controller.create_save_directories = (
            ControllerGUI.create_save_directories.__get__(self.controller)
        )
        with mock.patch(
            "gui.controller_gui.application_root", return_value=self._tmp.name
        ):
            behave_dir, eeg_dir = self.controller.create_save_directories(
                "P99", date_str="20260731"
            )

        expected_base = os.path.join(self._tmp.name, "data", "P99", "20260731")
        self.assertEqual(os.path.join(expected_base, "behave"), behave_dir)
        self.assertEqual(os.path.join(expected_base, "eeg"), eeg_dir)
        self.assertIn(behave_dir, self.controller.log_area.toPlainText())
        self.assertIn(eeg_dir, self.controller.log_area.toPlainText())


@unittest.skipIf(QApplication is None, "PyQt5 is not installed")
class ResultWriteFailureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_result_write_failure_is_retained_without_raising(self):
        with tempfile.TemporaryDirectory() as directory:
            blocking_path = os.path.join(directory, "not-a-directory")
            with open(blocking_path, mode="w", encoding="utf-8") as file:
                file.write("block directory creation")
            messages = []
            canvas = GaborCanvas(
                max_tilt_angle=1,
                total_trials=1,
                num_blocks=1,
                external_logger=messages.append,
                save_dir=blocking_path,
            )
            canvas.file_base = "P01_drops_20260731_153636"
            canvas.results = [[0] * 16]

            self.assertIsNone(canvas.save_results("practice"))
            self.assertEqual([], canvas.results)
            self.assertEqual(1, len(canvas._pending_result_batches))
            self.assertTrue(canvas.data_write_errors)
            self.assertTrue(any(message.startswith("[Error]") for message in messages))

            os.remove(blocking_path)
            os.makedirs(blocking_path)
            canvas._retry_pending_result_saves()
            self.assertEqual([], canvas._pending_result_batches)
            self.assertTrue(
                os.path.exists(
                    os.path.join(
                        blocking_path,
                        "P01_drops_20260731_153636_practice_results.csv",
                    )
                )
            )
            canvas.deleteLater()
            self.app.processEvents()


@unittest.skipIf(QApplication is None, "PyQt5 is not installed")
class ParticipantMessagePresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_instruction_uses_margins_line_breaks_and_responsive_font(self):
        canvas = GaborCanvas()
        canvas.resize(800, 800)
        canvas.show_message(exp_config.MSG_INSTRUCTION)
        self.app.processEvents()

        instruction_size = canvas.msg_label.font().pixelSize()
        self.assertIn("\n", canvas.msg_label.text())
        self.assertGreater(canvas.msg_label.geometry().x(), 0)
        self.assertLess(canvas.msg_label.width(), canvas.width())
        self.assertGreaterEqual(instruction_size, exp_config.MESSAGE_FONT_MIN_PX)
        self.assertLessEqual(instruction_size, exp_config.MESSAGE_FONT_MAX_PX)

        canvas.show_message(exp_config.MSG_TASK_START)
        self.app.processEvents()
        self.assertGreaterEqual(canvas.msg_label.font().pixelSize(), instruction_size)

        canvas.deleteLater()
        self.app.processEvents()


@unittest.skipIf(QApplication is None, "PyQt5 is not installed")
class ManualEegFlowIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.behave_dir = os.path.join(self._tmp.name, "behave")
        self.eeg_dir = os.path.join(self._tmp.name, "eeg")
        os.makedirs(self.behave_dir)
        os.makedirs(self.eeg_dir)
        self.controller = ControllerGUI()
        self.experiment = ExperimentWindow(
            trials_per_block=1,
            num_blocks=2,
            external_logger=self.controller.redirect_log_from_task,
            max_angle_input=2,
            controller_window=self.controller,
        )
        self.controller.exp_window = self.experiment
        self.controller.create_save_directories = lambda _participant_id, **_kwargs: (
            self.behave_dir,
            self.eeg_dir,
        )
        self.controller.participant_id_input.setText("P01")
        self.controller.max_angle_input.setText("2")
        self.controller.trials_per_block_input.setText("1")
        self.controller.num_blocks_input.setText("2")
        self.assertTrue(self.controller.prepare_session())
        self.experiment.show()
        self.app.processEvents()

    def tearDown(self):
        canvas = self.experiment.canvas
        for timer in (
            canvas.timer,
            canvas.status_timer,
            canvas.tilt_timer,
            canvas.break_tick_timer,
            self.controller.clock_timer,
        ):
            timer.stop()
        self.controller.prepared = False
        self.experiment.deleteLater()
        self.controller.deleteLater()
        self.app.processEvents()
        self._tmp.cleanup()

    def press_space(self):
        event = QKeyEvent(QEvent.KeyPress, Qt.Key_Space, Qt.NoModifier)
        self.experiment.canvas.keyPressEvent(event)

    def answer_current_trial(self):
        canvas = self.experiment.canvas
        canvas.tilt_timer.stop()
        canvas.trigger_tilt()
        self.assertTrue(canvas.tilt_pending)
        self.assertFalse(canvas.trial_active)
        canvas.repaint()
        self.app.processEvents()
        self.assertFalse(canvas.tilt_pending)
        self.assertTrue(canvas.trial_active)
        self.press_space()

    def test_complete_flow_writes_all_manual_sync_artifacts(self):
        canvas = self.experiment.canvas
        with mock.patch.object(exp_config, "PRACTICE_MIN_TRIALS", 1), mock.patch.object(
            exp_config, "PRACTICE_RT_THRESHOLD_MS", 10_000
        ):
            self.press_space()  # idle -> instruction
            self.press_space()  # instruction -> practice
            self.answer_current_trial()
            self.assertEqual(canvas.PHASE_PRACTICE_DONE, canvas.phase)

            self.press_space()  # block 1
            self.answer_current_trial()
            self.assertEqual(canvas.PHASE_BREAK_REST, canvas.phase)
            canvas.break_tick_timer.stop()
            canvas.on_break_finished()
            self.press_space()  # block 2
            self.answer_current_trial()

        self.assertEqual(canvas.PHASE_FINISHED, canvas.phase)
        self.assertTrue(self.controller.finalized)
        self.assertEqual(
            3,
            len(
                [
                    name
                    for name in os.listdir(self.behave_dir)
                    if name.endswith("_results.csv")
                ]
            ),
        )
        result_onsets = set()
        for name in os.listdir(self.behave_dir):
            if not name.endswith("_results.csv"):
                continue
            with open(
                os.path.join(self.behave_dir, name),
                newline="",
                encoding="utf-8",
            ) as file:
                rows = list(csv.reader(file))
            self.assertEqual("TiltOnsetSys(ms)", rows[0][2])
            result_onsets.update((row[1], row[2]) for row in rows[1:])

        with open(
            self.controller.event_logger.path, newline="", encoding="utf-8"
        ) as file:
            event_rows = list(csv.reader(file))[1:]
        event_names = [row[2] for row in event_rows]
        for expected in (
            "experiment_start",
            "practice_start",
            "practice_end",
            "block_start",
            "block_end",
            "break_start",
            "break_end",
            "experiment_end",
        ):
            self.assertIn(expected, event_names)
        event_onsets = {
            (row[0], row[1]) for row in event_rows if row[2] == "tilt_onset"
        }
        self.assertEqual(result_onsets, event_onsets)
        with open(self.controller.checklist_path, encoding="utf-8") as file:
            checklist = file.read()
        self.assertIn("## セッション実績（自動記入）", checklist)
        self.assertIn("正常終了（全ブロック完了）", checklist)

        canvas.reset_for_new_session()
        self.assertFalse(self.controller.is_prepared())
        self.assertEqual(canvas.PHASE_IDLE, canvas.phase)
        self.assertFalse(self.controller.max_angle_input.isReadOnly())

    def test_pause_resume_and_abort_finish_without_eeg_gate(self):
        canvas = self.experiment.canvas
        self.press_space()
        self.press_space()
        canvas.tilt_timer.stop()
        canvas.trigger_tilt()
        canvas.repaint()
        self.app.processEvents()
        self.assertEqual(1, canvas.trial_count)
        self.assertTrue(canvas.trial_active)
        self.assertTrue(canvas.pause_experiment())
        self.assertEqual(canvas.PHASE_PAUSED, canvas.phase)
        self.assertEqual(0, canvas.trial_count)
        self.assertTrue(canvas.resume_experiment())
        self.assertEqual(canvas.PHASE_PRACTICE, canvas.phase)
        self.answer_current_trial()
        self.assertTrue(canvas.abort_experiment(reason="test_abort"))
        self.assertEqual(canvas.PHASE_FINISHED, canvas.phase)
        self.assertTrue(self.controller.finalized)

        with open(
            self.controller.event_logger.path, newline="", encoding="utf-8"
        ) as file:
            event_names = [row[2] for row in list(csv.reader(file))[1:]]
        for expected in ("pause", "resume", "abort", "experiment_end"):
            self.assertIn(expected, event_names)
        self.assertTrue(
            any(
                name.endswith("_aborted_practice_results.csv")
                for name in os.listdir(self.behave_dir)
            )
        )


if __name__ == "__main__":
    unittest.main()
