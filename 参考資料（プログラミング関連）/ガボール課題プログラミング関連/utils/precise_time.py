# utils/precise_time.py
# 高精度 Unixtime ユーティリティ（PyQt5非依存）。
#
# 本アプリは 2 系統の時計を併記して記録する。用途（＝どちらが正か）が異なる。
#
#   mono : unixtime_s() / unixtime_ms()
#          import 時に壁時計を time.perf_counter() へ 1 回アンカーし、以降は
#          perf_counter（全OSで µs 精度・単調増加）のオフセットで算出する。
#          Windows の Python 3.10 では time.time() の分解能が約 15.6ms しかなく、
#          反応時間が 15.6ms 刻みに量子化されるため、**反応時間・イベント間隔の正**
#          としてこちらを使う。
#
#   sys  : sys_unixtime_ms()
#          OS の壁時計（time.time()）そのもの。EmotivPro が EEG に付ける
#          タイムスタンプと同一の時計であるため、**EEG との突合の正**として使う。
#
# 両者は起動直後にはほぼ一致するが、セッション中に OS の時刻同期（NTP）・手動の
# 時刻変更・スリープ復帰が起きると mono 側は追従しないため差（ドリフト）が生じる。
# この差は utils/clock_monitor.py で監視・記録し、解析時に事後補正できるようにする。
# 記録系はすべて now_pair() で両者を対にして取得すること。

import time
from datetime import datetime


def _calibrate():
    """壁時計の tick 境界を捕まえて (wall, perf) のアンカー対を返す。

    time.time() の値が変わった瞬間を最大 0.2 秒間ポーリングすることで、
    アンカー誤差を「壁時計の分解能（Windows で約 15.6ms）」ではなく
    「perf_counter 1 読み分（µs オーダー）」に抑える。macOS/Linux では
    壁時計自体が µs 精度のため、ループは即座に終了する。
    """
    t0 = time.time()
    deadline = time.perf_counter() + 0.2
    while time.perf_counter() < deadline:
        t1 = time.time()
        if t1 != t0:
            return t1, time.perf_counter()
    return time.time(), time.perf_counter()


_ANCHOR_WALL_S, _ANCHOR_PERF_S = _calibrate()


def unixtime_s():
    """mono 時計の現在時刻（Unixtime 秒・float）を µs 精度で返す。"""
    return _ANCHOR_WALL_S + (time.perf_counter() - _ANCHOR_PERF_S)


def unixtime_ms():
    """mono 時計の現在時刻（Unixtime ミリ秒・int）を返す。

    反応時間・イベント間隔など「セッション内の相対時刻」はすべて本関数を基準にする。
    """
    return int(unixtime_s() * 1000)


def sys_unixtime_ms():
    """OS の壁時計の現在時刻（Unixtime ミリ秒・int）を返す。

    EmotivPro のタイムスタンプと突き合わせる際はこちらを使う。
    """
    return int(time.time() * 1000)


def now_pair():
    """(mono_ms, sys_ms) を可能な限り同一瞬間に取得して返す。

    記録系（行動データ・イベントログ）の時刻取得は必ず本関数を使い、
    2 系統の時計を対で残すこと（片方だけを記録すると事後補正ができなくなる）。
    """
    mono_ms = unixtime_ms()
    sys_ms = sys_unixtime_ms()
    return mono_ms, sys_ms


def timezone_info():
    """実行 PC のタイムゾーン情報を返す。

    PDF の計測前確認「PC の日時とタイムゾーンが正しいこと」を、セッションメタと
    チェックリストに残すために使う。
    """
    # Unix 系ではプロセス起動後の OS / TZ 環境変更を反映させる。Windows には
    # tzset が無いため、標準ライブラリが返す現在値をそのまま使う。
    if hasattr(time, "tzset"):
        time.tzset()
    is_dst = time.localtime().tm_isdst > 0
    offset_s = -(time.altzone if is_dst else time.timezone)
    name = time.tzname[1] if is_dst and len(time.tzname) > 1 else time.tzname[0]
    sign = "+" if offset_s >= 0 else "-"
    total_min = abs(offset_s) // 60
    return {
        "name": name,
        "utc_offset_s": offset_s,
        "utc_offset": f"UTC{sign}{total_min // 60:02d}:{total_min % 60:02d}",
    }


def format_local(unixtime_ms_value):
    """Unixtime(ms) を人間可読なローカル時刻文字列へ変換する。"""
    dt = datetime.fromtimestamp(unixtime_ms_value / 1000.0)
    return dt.strftime("%Y-%m-%d %H:%M:%S.") + f"{dt.microsecond // 1000:03d}"
