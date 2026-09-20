# exp_config.py
# ガボール点眼薬実験のパラメータ・画面文言の一元定義。
# 本アプリは EEG を取得しない（Emotiv Cortex API 不使用）ため、認証情報等の
# 秘匿情報は存在しない。すべて git 管理対象。

# --- アプリ情報 ---
# 2.0.0: Cortex API を撤去し、EmotivPro 手動計測＋PC壁時計タイムスタンプ突合方式へ移行。
APP_VERSION = "2.0.0"

# --- ディスプレイ・キャリブレーション（未定項目は None。None時は従来px値でフォールバック） ---
MONITOR_WIDTH_PX = None  # 論理ピクセルで指定（Retina環境では実ピクセルではなく論理ピクセル値を使う）
MONITOR_WIDTH_MM = None
VIEWING_DISTANCE_MM = 570  # 要件書の 57cm
FULLSCREEN = True  # True で被験者画面をフルスクリーン化
# QApplication.screens() の番号。通常、0がメイン（実験者用）、1が第2（被験者用）。
# 指定番号が存在しない場合は0へフォールバックし、起動時にConsoleへ警告を出す。
PARTICIPANT_SCREEN_INDEX = 1
# 正常終了・Abort・アプリ終了時に被験者画面のフルスクリーンを解除する。
EXIT_FULLSCREEN_ON_FINISH = True

# --- リフレッシュレート・描画タイミング ---
# 描画タイマー間隔はモニターのリフレッシュレートから導出する。刺激の移動速度・
# 傾斜速度は下記の実時間ベース算出（円周: REVOLUTION_PERIOD_S、傾斜: TILT_MS_PER_DEG）
# を使うため、REFRESH_RATE_HZ を変えても速度は変わらない（描画の滑らかさのみ変わる）。
REFRESH_RATE_HZ = 60
FRAME_INTERVAL_MS = round(1000 / REFRESH_RATE_HZ)

# --- 刺激（mm/度指定） ---
PATCH_SIZE_DEG = 0.68
SPATIAL_FREQ_CPD = 4.41
CONTRAST = 0.3
BACKGROUND_RGB = (128, 128, 128)
CIRCLE_DIAMETER_MM = 210
REVOLUTION_PERIOD_S = 20.0  # 20秒/周・時計回り
# 傾斜アニメーションの速度は「1度あたり何ミリ秒か」で定義する（実時間ベース）。
# 要件書の「2フレーム/度 ≒ 33ms/度」に対応。リフレッシュレートやフレーム落ちが
# あっても傾斜の到達時間・速度は一定になる。TILT_STEP_DEG_PER_FRAME は旧・
# フレーム依存実装の名残で、現行の時間ベース描画では未使用（後方互換のため残置）。
TILT_MS_PER_DEG = 33.0
TILT_STEP_DEG_PER_FRAME = 0.5  # 【非推奨・未使用】旧フレーム依存実装の係数

# --- フォールバック（キャリブレーション未設定時 = 現行動作維持） ---
FALLBACK_PATCH_DIAMETER_PX = 40
FALLBACK_CYCLES_PER_PATCH = 2.5
FALLBACK_RADIUS_RATIO = 0.3

# --- 参加者条件 ---
DROP_CONDITION_OPTIONS = ["drops", "control"]  # Console上のプルダウン選択肢

# --- 課題構造 ---
DEFAULT_MAX_TILT_DEG = 10
DEFAULT_TRIALS_PER_BLOCK = 320
DEFAULT_NUM_BLOCKS = 6
INTERVAL_SHORT_RANGE_MS = (500, 1500)
INTERVAL_LONG_RANGE_MS = (1500, 3000)
INTERVAL_SHORT_PROB = 0.8
BREAK_SHORT_S = 120  # ブロック間2分
BREAK_LONG_S = 300  # 全体中間5分
LONG_BREAK_AFTER_BLOCK = None  # None なら num_blocks // 2 の直後に長休憩

# --- 時刻同期（EmotivPro との突合） ---
# EEG は EmotivPro 側で手動計測・手動エクスポートし、解析時に PC 壁時計の
# タイムスタンプで突合する。単調時計（反応時間の正）と OS 壁時計（突合の正）の
# ずれを監視し、events.csv に対応点を残す。詳細は utils/clock_monitor.py。
CLOCK_CHECK_INTERVAL_S = 60  # clock_check イベントを残す間隔
CLOCK_DRIFT_WARN_MS = 100  # このずれを超えたら clock_drift を記録し Console へ警告
# EmotivPro エクスポートを eeg/ へ置く際のファイル名サフィックス
# （<ID>_<条件>_<日時> + 本サフィックス + 拡張子）
EEG_EXPORT_SUFFIX = "_eeg"

# --- 練習 ---
PRACTICE_MIN_TRIALS = 30
PRACTICE_RT_THRESHOLD_MS = 1500
PRACTICE_MA_WINDOW = 5
FEEDBACK_DURATION_MS = 500  # ○×の表示時間（要件未規定のためパラメータ化）

# --- 画面文言（文意の区切りで明示改行。N/分数のみテンプレート化） ---
MSG_TASK_START = "課題を開始します。\nスペースキーを押してください。"
MSG_INSTRUCTION = (
    "画面の円周上を、垂直の縞模様が移動します。\n"
    "模様が左右に傾いたら、できる限り素早く\n"
    "スペースキーを押して回答してください。\n\n"
    "それではチュートリアルを行います。\n"
    "スペースキーを押して開始してください。"
)
MSG_PRACTICE_DONE = (
    "お疲れ様でした。それでは本番に移行します。\n"
    "本番では○×のフィードバックはありません。\n"
    "スペースキーを押して1ブロック目を開始してください。"
)
MSG_BLOCK_INTERVAL = (
    "{n}ブロック目が完了しました。\n"
    "ここで{minutes}分間のインターバルを取ります。\n"
    "目薬を使用する条件の場合、目薬を必ず使用してください。"
)
# 休憩明けの被験者向けメッセージ（休憩中はカウントダウンを見せず、経過後に表示）
MSG_BREAK_DONE = "{minutes}分経ちました。\nスペースキーを押して開始してください。"
MSG_ALL_DONE = (
    "これで全てのブロックが完了しました。\n"
    "課題は以上となります。\n"
    "お疲れ様でした。"
)
MSG_PAUSED = "実験を一時停止しています。\nしばらくお待ちください。"
MSG_ABORTED = (
    "実験を中断しました。\n"
    "ここまでのデータを保存しています。\n"
    "お疲れ様でした。"
)

# --- メッセージ画面の配色 ---
MESSAGE_TEXT_COLOR = (0, 0, 0)
MESSAGE_BG_RGB = (255, 255, 255)
MESSAGE_FONT_MIN_PX = 24
MESSAGE_FONT_MAX_PX = 42
MESSAGE_HORIZONTAL_MARGIN_RATIO = 0.08
MESSAGE_VERTICAL_MARGIN_RATIO = 0.08
