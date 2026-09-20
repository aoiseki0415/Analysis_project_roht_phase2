# utils/event_logger.py
# ブロック開始/終了・実験全体開始/終了・クロック監視など、試行単位に紐づかない
# イベントを記録するロガー（PyQt5非依存）。
#
# 時刻は mono（反応時間・イベント間隔の正）と sys（EmotivPro との突合の正）を
# 併記する。詳細は utils/precise_time.py を参照。

import csv
import os

from utils.precise_time import now_pair


class EventLogger:
    """2 系統の Unixtime(ms) 付きイベントを CSV に逐次追記するロガー。"""

    HEADER = ["UnixTime(ms)", "SysUnixTime(ms)", "Event", "Detail"]

    def __init__(self, save_dir, base_name=None):
        """``base_name`` を渡すと ``<base_name>_events.csv`` に保存する。

        behave の各ファイルと EmotivPro エクスポートは同じ基底
        ``<ID>_<条件>_<YYYYMMDD_HHMMSS>`` を共有する。``None`` の場合は
        Unixtime(ms) 付きの名前にフォールバックする（コントローラ未接続時など）。
        """
        os.makedirs(save_dir, exist_ok=True)
        if base_name:
            filename = f"{base_name}_events.csv"
        else:
            filename = f"gabor_events_{now_pair()[0]}.csv"
        self._path = os.path.join(save_dir, filename)
        # 実験データは上書きしない。同じ基底名が既に存在する場合は
        # FileExistsError を呼び出し側へ返し、新しいセッションの開始を止める。
        with open(self._path, mode="x", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(self.HEADER)

    @property
    def path(self):
        return self._path

    def log(self, event, detail="", unixtime_ms=None, sys_unixtime_ms=None):
        """イベントを 1 行追記する。

        時刻は「両方省略（その場で取得）」か「両方指定」のいずれかとする。
        片方だけを指定すると 2 系統の時計の対応が崩れ、事後補正ができなくなるため
        ValueError とする。
        """
        if (unixtime_ms is None) != (sys_unixtime_ms is None):
            raise ValueError(
                "unixtime_ms と sys_unixtime_ms は対で指定すること"
                "（片方のみの指定は 2 系統の時計の対応を壊す）"
            )
        if unixtime_ms is None:
            unixtime_ms, sys_unixtime_ms = now_pair()
        with open(self._path, mode="a", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow([unixtime_ms, sys_unixtime_ms, event, detail])
