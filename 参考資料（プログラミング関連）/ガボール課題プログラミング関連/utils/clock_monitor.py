# utils/clock_monitor.py
# 単調時計（mono）と OS 壁時計（sys）のずれ＝クロックドリフトの監視（PyQt5非依存）。
#
# 背景: Cortex API の injectMarker による厳密同期を廃止し、EmotivPro との同期を
# 「双方が同じ PC のローカル時刻でタイムスタンプを記録し、解析時に突合する」方式へ
# 変更した。このため行動ログの絶対時刻の正確さが同期精度そのものになる。
# utils/precise_time.py の mono 時計は起動時に壁時計を 1 回アンカーする設計のため、
# セッション中の NTP 補正・手動の時刻変更・スリープ復帰には追従しない。
# 本モジュールはその差を定期的に記録（clock_check）し、閾値を超えたら警告
# （clock_drift）することで、事後補正と異常検知を可能にする。
#
# 時刻は一切内部で取得せず、呼び出し側から (mono_ms, sys_ms) を受け取る純粋な
# 状態機械として実装する（テスト容易性のため）。

CHECK_EVENT = "clock_check"
DRIFT_EVENT = "clock_drift"


class ClockMonitor:
    """mono と sys のオフセットを監視し、記録すべきイベントを返す。

    使い方（呼び出し側は 1 秒ごとに tick するだけでよい）::

        monitor = ClockMonitor(check_interval_s=60, drift_warn_ms=100)
        monitor.start(*now_pair())          # セッション準備時に基準を取る
        for event in monitor.tick(*now_pair()):
            event_logger.log(event["event"], event["detail"],
                             unixtime_ms=event["mono_ms"],
                             sys_unixtime_ms=event["sys_ms"])
    """

    def __init__(self, check_interval_s=60, drift_warn_ms=100):
        self.check_interval_ms = int(check_interval_s * 1000)
        self.drift_warn_ms = int(drift_warn_ms)
        self._baseline_offset_ms = None
        self._last_check_mono_ms = None
        self._last_warn_drift_ms = None
        self._last_offset_ms = None
        self._max_drift_ms = 0
        self._warn_count = 0

    # --- 基準の設定 ---

    def start(self, mono_ms, sys_ms):
        """基準オフセットを取り直し、監視状態をリセットする。

        セッション準備（Prepare session）時に呼ぶ。アンカー直後のオフセットは
        ほぼ 0 だが、アプリ起動から準備までに時間が空くこともあるため明示的に取る。
        """
        self._baseline_offset_ms = sys_ms - mono_ms
        self._last_check_mono_ms = mono_ms
        self._last_warn_drift_ms = None
        self._last_offset_ms = self._baseline_offset_ms
        self._max_drift_ms = 0
        self._warn_count = 0
        return self._baseline_offset_ms

    @property
    def started(self):
        return self._baseline_offset_ms is not None

    # --- 監視 ---

    def drift_ms(self, mono_ms, sys_ms):
        """基準オフセットからのずれ（ms・符号付き）を返す。未開始なら 0。"""
        if self._baseline_offset_ms is None:
            return 0
        return (sys_ms - mono_ms) - self._baseline_offset_ms

    def tick(self, mono_ms, sys_ms):
        """監視を 1 回進め、記録すべきイベントのリストを返す。

        戻り値の各要素は ``{"event", "detail", "mono_ms", "sys_ms", "drift_ms"}``。
        初回 tick は基準の設定のみを行い、イベントを返さない。
        """
        if self._baseline_offset_ms is None:
            self.start(mono_ms, sys_ms)
            return []

        offset_ms = sys_ms - mono_ms
        drift = offset_ms - self._baseline_offset_ms
        self._last_offset_ms = offset_ms
        if abs(drift) > abs(self._max_drift_ms):
            self._max_drift_ms = drift

        events = []
        detail = f"offset_ms={offset_ms},drift_ms={drift}"

        # 刺激イベントが無い区間（休憩中など）にも時刻の対応点を残す。
        if mono_ms - self._last_check_mono_ms >= self.check_interval_ms:
            self._last_check_mono_ms = mono_ms
            events.append(self._make(CHECK_EVENT, detail, mono_ms, sys_ms, drift))

        # 閾値超過で警告。以後は前回警告時からさらに閾値以上変化した場合のみ再警告し、
        # 同程度のずれが続く間ログが氾濫しないようにする。
        if abs(drift) >= self.drift_warn_ms and (
            self._last_warn_drift_ms is None
            or abs(drift - self._last_warn_drift_ms) >= self.drift_warn_ms
        ):
            self._last_warn_drift_ms = drift
            self._warn_count += 1
            events.append(self._make(DRIFT_EVENT, detail, mono_ms, sys_ms, drift))

        return events

    @staticmethod
    def _make(event, detail, mono_ms, sys_ms, drift):
        return {
            "event": event,
            "detail": detail,
            "mono_ms": mono_ms,
            "sys_ms": sys_ms,
            "drift_ms": drift,
        }

    # --- 実績（セッションメタ・チェックリスト用） ---

    def summary(self):
        return {
            "baseline_offset_ms": self._baseline_offset_ms,
            "last_offset_ms": self._last_offset_ms,
            "max_drift_ms": self._max_drift_ms,
            "warn_count": self._warn_count,
            "check_interval_s": self.check_interval_ms / 1000,
            "drift_warn_ms": self.drift_warn_ms,
        }
