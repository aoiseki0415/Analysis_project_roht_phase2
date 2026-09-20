# gabor_task（ガボール視覚課題・刺激提示アプリ）

ガボールパッチを使った視覚反応課題を提示し、行動データ（反応時間・イベント）を
高精度なタイムスタンプ付きで記録する PyQt5 アプリケーションです。練習フェーズ・
本番複数ブロック運用・休憩管理を備えます
（要件定義: `docs/20260709_gabor-drops-experiment_requirements.md`）。

**本アプリは脳波（EEG）を取得しません（Emotiv Cortex API 不使用）。**
EEG は EmotivPro 側で実験者が手動で計測・エクスポートし、解析時に本アプリの
行動ログと**PC の壁時計タイムスタンプで突合**します
（移行の要件定義: `docs/20260731_cortex-removal-emotivpro-sync_requirements.md`）。

## 同期方式（重要）

EmotivPro と本アプリは、いずれも**同じ PC のローカル時刻**でタイムスタンプを
記録します。解析時は両者のタイムスタンプを突き合わせてイベントを対応づけます。

- 突合に使う列: `events.csv` の `SysUnixTime(ms)`、`results.csv` の `*Sys(ms)`
  （OS の壁時計＝EmotivPro が使うのと同じ時計）
- 反応時間 `RT(ms)`: 単調時計（`utils/precise_time.py`）基準。Windows の壁時計の
  分解能（約 15.6ms）による量子化と、セッション中の時刻補正の影響を受けません
- 2 つの時計のずれは、`events.csv` の `clock_check`（既定 60 秒ごと）と
  `clock_drift`（既定 ±100ms 超で記録・Console へ警告）で追跡できます。
  Console には常時 `Clock drift` が表示されます。タイムゾーンだけの変更は
  Unix 時刻の差に現れないため、別途 `timezone_change` として記録・警告します

**ずれの原因になるもの**（PDF「Emotiv脳波計測・データ同期 引継ぎ資料」より）:
PC の時刻変更、タイムゾーン変更、スリープ復帰、複数 PC 間の時刻差。
**EmotivPro と本アプリは同じ PC で動かしてください。**

## 必要環境

- 納品先Windows: Windows 11、公式Python 3.10、EmotivPRO、Emotivヘッドセット
- 開発環境: Python 3.10

Cortex API の Client ID / Secretと`config.py`は**不要**です。本アプリは
EMOTIV Launcher / Cortex Serviceを起動・操作しません。ただし、EmotivPRO自体の
インストールやログインにEMOTIV Launcherが使われる場合は、EMOTIV側の手順に従います。

## セットアップ

### 納品先Windows（Conda・カスタムEXE・BAT不要）

公式Python 3.10とコマンドプロンプトを使用します。

1. ZIPを右クリックし、「すべて展開」する
2. Python 3.10.11の公式Windows版をインストールする
3. `main.py`があるフォルダのアドレス欄へ`cmd`と入力する
4. 次を1行ずつ実行する

```bat
py -3.10 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

5. `settings.json`へモニター幅・視距離・表示先を入力する

詳細は[`WINDOWS_SETUP.md`](WINDOWS_SETUP.md)を参照してください。

### ソースコードから実行する場合

**macOS / Linux**

```bash
python3.10 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`data/`以下の実験データはGit管理対象外です。

コードはWindows / macOS共通です。Windowsではプロジェクト専用の`.venv`を使うため、
ほかのPythonアプリへ影響しません。

### モニターキャリブレーションの設定（実験前に必須）

被験者画面を表示する実機モニターで以下を実測します。納品先Windowsでは
`settings.json`、ソース実行では`exp_config.py`に設定します。
未設定（`None`のまま）だと刺激サイズ・円周半径がpx固定値のフォールバックで
描画され、視角ベースの正確なサイズにならないため、**本番実験の前に必ず設定する**。

- `FULLSCREEN`: 被験者画面をフルスクリーン表示する。本番既定値は`True`
- `PARTICIPANT_SCREEN_INDEX`: 被験者画面を出すモニター番号。通常は、実験者用の
  メインモニターが`0`、第2モニターが`1`
- `EXIT_FULLSCREEN_ON_FINISH`: 正常終了・Abort後に自動でウィンドウ表示へ戻す。
  本番既定値は`True`
- `MONITOR_WIDTH_PX`: 被験者画面の論理ピクセル幅（macOS Retina / Windows拡大表示
  ともに、実ピクセルではなくOSが報告する論理ピクセル値を使う）
- `MONITOR_WIDTH_MM`: モニターの物理幅（mm）
- `VIEWING_DISTANCE_MM`: 視距離（mm）。デフォルトは要件書記載の57cm

Windowsの「設定」→「システム」→「ディスプレイ」で表示方法を「拡張」にする。
Windowsの「識別」番号とアプリの画面番号が一致しない場合があるため、実際の
表示先を見て確認すること。
実験者ConsoleはWindowsのメインモニターへ配置される。指定番号が存在しない
1画面環境では、被験者画面も`screen[0]`へフォールバックする。

### PCの時刻設定（実験前に必須）

同期は PC の時刻そのものに依存します。実験前に必ず確認してください。

- 日付・時刻・タイムゾーンが正しいこと（起動時にConsoleへ表示される）
- 実験中に PC がスリープしない設定になっていること
- 実験中に時刻・タイムゾーンを変更しないこと

## 起動

ソース実行:

```bash
python main.py
```

納品先Windowsでは、プロジェクトフォルダのコマンドプロンプトで実行します。

```bat
.venv\Scripts\python.exe main.py
```

ヘッドセットなしでも起動でき、課題フロー（練習・ブロック進行・休憩・
行動データ出力）をそのまま確認できます。動作確認の際は Console の
`Trials / Block` と `Blocks` を小さい値（例: 3 と 2）にしてください。

### 1画面だけで動作確認する

納品先Windowsでは次を実行します。

```bat
.venv\Scripts\python.exe main.py --single-screen-test
```

macOS / Linuxのソース実行では次のオプションを付けます。

```bash
python main.py --single-screen-test
```

このモードは操作確認専用で、`settings.json`や`exp_config.py`の本番設定は
変更されません。本番では被験者用モニターを接続し、`--single-screen-test`を
付けずに起動してください。

## 本番での操作手順

当日の詳細なチェック項目、異常時対応、EEGエクスポート手順は
[`docs/実験手順書_EmotivPRO手動記録.md`](docs/実験手順書_EmotivPRO手動記録.md)
を使用してください。以下は全体の要約です。

**重要**: スペースキー入力（課題の進行・被験者の反応）は、**被験者画面が
アクティブ（最前面でフォーカスがある状態）のときだけ**受け付けられる。
実験者がConsoleをクリック・操作するとフォーカスがConsole側へ移るため、
その後は**必ず被験者画面を一度クリックしてアクティブに戻してから**課題を
進めること。被験者画面がアクティブでないままだと、スペースキーを押しても
画面が進まず、被験者の反応も記録されない。

1. PC の日時・タイムゾーンが正しいことを確認する
2. EmotivPro を起動し、ヘッドセットを被験者に装着してコンタクト品質を整える
3. **EmotivPro の記録（Record）を開始する。記録はセッション通し 1 本**
   （練習・全ブロックを 1 本に含める。区間の切り出しは `events.csv` の時刻で行う）
4. 本アプリを起動する（前節「起動」のコマンド）
5. Console で Participant ID・Eye-drop Condition（目薬条件）・最大傾斜角度・
   ブロックあたり試行数・ブロック数を入力する
6. **`Prepare session` を押す**。保存先の作成、ファイル名の確定、セッションメタと
   チェックリストの出力が行われ、「Session guide / 計測前チェック」欄に
   計測前チェックと EEG エクスポートの配置ルールが表示される
7. 被験者画面を一度クリックしてアクティブにし、スペースキーを押す（説明文が表示される）
8. スペースキーで練習フェーズへ進む。ガボールパッチの傾きを検出したら
   スペースキーで反応する（○×フィードバックあり）。最低30試行かつ直近5試行の
   平均反応時間が1500ms以下になると練習終了
9. スペースキーで本番1ブロック目を開始する（以降フィードバックなし）
10. 各ブロック終了ごとに休憩（通常2分、中間ブロック後は5分）が入る。休憩中は
    被験者画面にカウントダウンを出さず、Console に残り時間を mm:ss 表示する。
    経過後に被験者画面へ「x分経ちました…」が出るので、スペースキーで次ブロックへ進む
11. 全ブロック終了で終了メッセージが表示される
12. **EmotivPro の記録を停止し、生データをエクスポートする**
13. エクスポートを `data/<ID>/<日付>/eeg/` へ **`<base>_eeg.<拡張子>`** の名前で置く
14. `<base>_checklist.md` にリジェクトチャンネル等を記入し、behave / eeg と
    一緒に所定の Google Drive へアップロードする

進行中はいつでも Console から操作できる:

- `Pause` / `Resume`: 一時停止と再開（円周上の位置を維持して再開する）
- `Abort`: 中断。そこまでの行動データを保存して終了する
  （EEG は EmotivPro 側で手動停止・エクスポートする）

Console のボタンを操作した後は、被験者画面を一度クリックしてアクティブに
戻すこと（アクティブでないとスペースキーが効かない）。

## 出力ファイル

behave の各ファイルと EmotivPro エクスポートは、同じ基底名
`<Participant ID>_<条件>_<YYYYMMDD_HHMMSS>`（以下 `<base>`）を共有する。

保存先は、実行中のプロジェクトフォルダを基準に自動生成される。Consoleや
チェックリストに表示される絶対パスは固定値ではなく、相手PCでZIPを展開した
ドライブ・ユーザー名・フォルダに合わせた実際のパスになる。

```text
data/<Participant ID>/<YYYYMMDD>/
├── behave/
│   ├── <base>_meta.json                      # セッション設定・時計情報・キャリブレーション
│   ├── <base>_checklist.md                   # 計測前/計測後チェック（記入して提出する）
│   ├── <base>_events.csv                     # 実験/練習/ブロック/休憩/時計監視のイベントログ
│   ├── <base>_practice_results.csv           # 練習フェーズの試行結果
│   ├── <base>_block<N>_results.csv           # 各本番ブロックの試行結果
│   └── <base>_aborted_<segment>_results.csv  # 中断時、そこまでの試行結果
└── eeg/
    └── <base>_eeg.<拡張子>                    # EmotivPro からの手動エクスポート（実験者が配置）
```

### `results.csv` の列

```text
Trial, TiltOnset(ms), TiltOnsetSys(ms), KeyPress(ms), KeyPressSys(ms), RT(ms),
ResponseType, Block, Phase, TargetAngle(deg),
OnsetPosAngle(deg), OnsetPosX(px), OnsetPosY(px),
PressPosAngle(deg), PressPosX(px), PressPosY(px)
```

- `*(ms)` は単調時計、`*Sys(ms)` は OS 壁時計。**EEG との突合には `*Sys(ms)` を使う**
- `RT(ms)` は単調時計の差分（`KeyPress(ms) - TiltOnset(ms)`）
- `TiltOnset*` はタイマー発火時ではなく、最初の傾斜画像を描く直前に取得する
- `ResponseType` は `correct`（傾斜への反応）または `mistouch`（傾斜なしでの押下）

### `events.csv` の列とイベント

```text
UnixTime(ms), SysUnixTime(ms), Event, Detail
```

`experiment_start` / `practice_start` / `practice_end` / `block_start` /
`block_end` / `gabor_draw_start` / `tilt_onset` / `break_start` / `break_end` /
`pause` / `resume` / `abort` / `experiment_end` / `clock_check` / `clock_drift` /
`timezone_change`

### 旧バージョン（Cortex 版）のデータとの違い

2025-09-29 / 2025-10-15 に取得したデータは、本バージョンと列構成が異なる。
解析側では列名で分岐すること。

- 旧: `results.csv` に `*Sys(ms)` 列が無く、`events.csv` は
  `UnixTime(ms), Event, Detail` の 3 列
- 旧: EEG は `eeg/` にセグメント別レコードとして自動エクスポートされ、
  EEG 内に Cortex マーカーが埋め込まれていた
- 新: EEG は EmotivPro からの手動エクスポート 1 本。マーカーは無く、
  突合は `*Sys(ms)` で行う

## 配布用パッケージの作成（他PCへ渡す場合）

`data/` シンボリックリンクや開発環境を除いたクリーンな zip を作るスクリプトを
用意している。

```bash
bash scripts/package_for_distribution.sh
```

`dist/c_gaball_exp1_<timestamp>.zip` が作成される。除外されるもの: `data`
（空フォルダに置き換え）、`.git`・`__pycache__`・`.DS_Store`・`.venv`等。

## テスト

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -v
```

## 注意

- **EmotivPro の記録開始・停止・エクスポートは実験者の手動操作**であり、
  本アプリは関与しない。開始忘れ・停止忘れを防ぐため、チェックリストを使うこと
- 過去の検証での同期精度は概ね ±10ms（保証値ではなく参考値）。案件ごとに
  同期精度を確認すること
- EmotivPro エクスポート CSV の `Timestamp` 列の仕様（単位・UTC/ローカル）は
  実機で確認して確定すること（突合スクリプトの実装に直結する）
- 無反応試行のタイムアウトはありません
- 実験前に少数試行で、行動CSV・イベントログ・EmotivPro エクスポートの3つが
  タイムスタンプで対応づくことを確認してください
