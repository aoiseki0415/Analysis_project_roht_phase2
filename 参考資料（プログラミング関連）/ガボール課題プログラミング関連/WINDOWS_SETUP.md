# Windowsで使い始める手順

この方法では、カスタムEXE、BAT、PowerShell、Condaを使いません。
公式Python 3.10とWindowsのコマンドプロンプトだけを使います。

初回セットアップ時は、Pythonパッケージを取得するためインターネット接続が必要です。

## 1. ZIPを展開する

1. 納品されたZIPを右クリックする
2. **「すべて展開」**を押す
3. 書き込み可能な場所へ展開する

推奨例:

```text
C:\Users\<ユーザー名>\Documents\c_gaball_exp1_windows
```

次のファイルが見えることを確認します。

```text
main.py
requirements.txt
settings.json
START_HERE.txt
WINDOWS_SETUP.md
data
docs
gui
tests
utils
```

ZIPの中から直接実行しないでください。`Program Files`など、一般ユーザーが
書き込めない場所にも置かないでください。

## 2. 公式Python 3.10をインストールする

すでにPython 3.10が入っている場合は「3. コマンドプロンプトを開く」へ進みます。

1. Python公式サイトの
   [Python 3.10.11](https://www.python.org/downloads/release/python-31011/)を開く
2. **Windows installer (64-bit)**をダウンロードする
3. ダウンロードした公式インストーラーを起動する
4. **Add python.exe to PATH**へチェックを付ける
5. **Install Now**を押す
6. インストールが終わったら画面を閉じる

Python 3.10.11は、このプロジェクトで動作確認しているPython 3.10系の公式配布版です。
組織PCでインストール許可が必要な場合は、セキュリティ機能を無効にせず、PC管理者へ
依頼してください。

## 3. プロジェクトフォルダでコマンドプロンプトを開く

1. エクスプローラーで、展開後の`main.py`があるフォルダを開く
2. 上部のアドレス欄をクリックする
3. `cmd`と入力してEnterキーを押す

黒いコマンドプロンプトが開きます。行の左側が、実際に展開したフォルダになっている
ことを確認します。

例:

```text
C:\Users\Tanaka\Documents\c_gaball_exp1_windows>
```

次のコマンドでPythonを確認します。

```bat
py -3.10 --version
```

次のように表示されれば正常です。

```text
Python 3.10.11
```

## 4. 初回セットアップを行う

同じコマンドプロンプトへ、次のコマンドを1行ずつ貼り付けて実行します。

```bat
py -3.10 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

最後が次のようになれば合格です。テスト数は更新により変わることがあります。

```text
Ran 85 tests
OK
```

`.venv`はこのアプリ専用のPython環境です。ほかのPythonアプリには影響しません。
Condaのインストールや環境の有効化は不要です。

この初回セットアップは、通常は1回だけ行います。

## 5. EmotivPROを準備する

1. EmotivPROをインストールする
2. EmotivPROへログインする
3. ライセンスが有効であることを確認する
4. ヘッドセットを接続する
5. 短い記録を開始・停止できることを確認する
6. 記録をCSVまたはEDFへ書き出せることを確認する

本アプリはCortex APIを使いません。Client ID、Client Secret、`config.py`は不要です。

## 6. 2画面を設定する

1. Windowsの**「設定」→「システム」→「ディスプレイ」**を開く
2. 表示方法を**「表示画面を拡張する」**にする
3. 実験者が見る画面をメインディスプレイにする
4. **「識別」**を押し、画面1と画面2を確認する

本番では、Consoleを実験者画面、課題を被験者画面へ表示します。

## 7. `settings.json`を設定する

1. `settings.json`を右クリックする
2. **「プログラムから開く」→「メモ帳」**を選ぶ
3. モニターに合わせて数値を入力する
4. 上書き保存する

初期状態:

```json
{
  "FULLSCREEN": true,
  "PARTICIPANT_SCREEN_INDEX": 1,
  "EXIT_FULLSCREEN_ON_FINISH": true,
  "MONITOR_WIDTH_PX": null,
  "MONITOR_WIDTH_MM": null,
  "VIEWING_DISTANCE_MM": 570
}
```

変更例:

```json
{
  "FULLSCREEN": true,
  "PARTICIPANT_SCREEN_INDEX": 1,
  "EXIT_FULLSCREEN_ON_FINISH": true,
  "MONITOR_WIDTH_PX": 1920,
  "MONITOR_WIDTH_MM": 509,
  "VIEWING_DISTANCE_MM": 570
}
```

| 設定名 | 内容 |
|---|---|
| `PARTICIPANT_SCREEN_INDEX` | 被験者画面の番号。通常は`1` |
| `MONITOR_WIDTH_PX` | 被験者用モニターの横幅（Windows上のピクセル数） |
| `MONITOR_WIDTH_MM` | 定規で測った表示部分の横幅（mm） |
| `VIEWING_DISTANCE_MM` | 被験者の眼から画面までの距離（mm） |

`null`のままでも起動しますが、刺激が正しい視角になりません。本番前に必ず実測値を
入力してください。設定に誤りがある場合は、起動時に「設定ファイルエラー」が出ます。

## 8. Windowsの時刻と電源を確認する

1. PCをAC電源へ接続する
2. **「設定」→「時刻と言語」→「日付と時刻」**を開く
3. 日付、時刻、タイムゾーンを確認する
4. 実験開始前に**「今すぐ同期」**を押す
5. 実験中にスリープしない設定にする
6. Windows Updateの再起動予定がないことを確認する

実験開始後は、時刻やタイムゾーンを変更しないでください。

## 9. 1画面で操作テストする

プロジェクトフォルダで開いたコマンドプロンプトから実行します。

```bat
.venv\Scripts\python.exe main.py --single-screen-test
```

- Consoleが左側に表示される
- 被験者画面が右側に表示される
- 本番用の`settings.json`は変更されない

テストしやすい設定:

```text
Participant ID: TEST_SINGLE
Trials / Block: 3
Blocks: 2
```

確認項目:

- [ ] `Prepare session`を押すとStateが`Prepared`になった
- [ ] 被験者画面をクリックするとスペースキーで進められた
- [ ] `Pause`、`Resume`、`Abort`が動いた
- [ ] Consoleの時刻とタイムゾーンが正しかった
- [ ] `data`にテストデータが保存された

## 10. 本番用に起動する

1画面テストを閉じます。2画面を接続した状態で、次を実行します。

```bat
.venv\Scripts\python.exe main.py
```

本番の詳しい順序は
[`docs/実験手順書_EmotivPRO手動記録.md`](docs/実験手順書_EmotivPRO手動記録.md)
を参照してください。

## 11. データの保存場所

データは、`main.py`があるフォルダの`data`へ自動保存されます。

例:

```text
C:\Users\Tanaka\Documents\c_gaball_exp1_windows\data\P001\20260731\
├── behave
└── eeg
```

Consoleとチェックリストにも、そのPC上の実際の保存先が表示されます。開発者PCの
パスは表示されません。ユーザー名、ドライブ、展開先が違っても自動で対応します。

## 2回目以降の起動

毎回行う操作は次の3つだけです。

1. `main.py`があるフォルダをエクスプローラーで開く
2. アドレス欄へ`cmd`と入力してEnterキーを押す
3. 次のコマンドを実行する

```bat
.venv\Scripts\python.exe main.py
```

`venv`の作成や`pip install`を毎回行う必要はありません。

## 困ったとき

### `py`が見つからない

Pythonのインストール後に、開いているコマンドプロンプトをすべて閉じ、手順3から
やり直します。改善しない場合は、Python 3.10.11を再インストールし、
**Add python.exe to PATH**へチェックを付けたか確認します。

### `.venv\Scripts\python.exe`が見つからない

初回セットアップが完了していません。手順4のコマンドを上から実行します。

### `No module named PyQt5`と表示される

次を実行します。

```bat
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### コマンド実行後に`main.py`が見つからない

コマンドプロンプトを閉じ、`main.py`が見えるフォルダでアドレス欄へ`cmd`と入力して
開き直します。

### 設定ファイルエラーが出る

`settings.json`を`settings.example.json`と比較します。分からない場合は、
`settings.example.json`をコピーして`settings.json`を作り直します。

### スペースキーが効かない

被験者画面を一度クリックしてから、スペースキーを押します。

### 課題が違うモニターへ表示される

`settings.json`の`PARTICIPANT_SCREEN_INDEX`を`0`または`1`へ変更し、再起動します。

### `Clock drift`が赤い

実験中に時刻を直さず、表示値と発生時刻を記録します。セッション後に解析担当者へ
伝えてください。

### Pythonの実行自体が組織のセキュリティで止められる

Windowsの保護機能を無効化せず、PC管理者へ公式Python 3.10の実行許可を依頼します。
