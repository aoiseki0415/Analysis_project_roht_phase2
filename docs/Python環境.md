# Python環境

## 1. 採用方針

本解析は、プロジェクト専用のPython環境で実行します。

- Python：3.14.7
- 環境管理：uv 0.12.17
- 仮想環境：リポジトリ直下の `.venv/`
- 依存関係定義：`pyproject.toml`
- 解決済み依存関係：`uv.lock`

OS付属の `/usr/bin/python3`（Python 3.9.6）へパッケージを追加しません。`.venv/`、`.tools/`、キャッシュはGit管理対象外です。

## 2. 主なライブラリ

| 目的 | ライブラリ |
|---|---|
| 数値計算・信号処理 | NumPy、SciPy |
| 表・CSV・Excel・Parquet | pandas、openpyxl、PyArrow |
| 統計・機械学習 | statsmodels、scikit-learn |
| 可視化 | Matplotlib、Seaborn |
| 対話的解析 | JupyterLab、IPython kernel |
| EEGの読み込み・前処理・解析 | MNE-Python |
| ICA成分の自動分類 | MNE-ICALabel、ONNX Runtime |
| ICAアルゴリズム | MNE extended Infomax、python-picard |
| 不良区間・センサーの補助評価 | autoreject |
| テスト・静的検査 | pytest、Ruff |

正確な導入版は `uv.lock` で固定します。依存関係を変更するときは、互換性テスト後に `pyproject.toml` と `uv.lock` を同時に更新します。

## 3. EEGLABとの対応

PythonではMNE-PythonをEEG解析の中核にします。EEGLABと完全に同一のソフトウェアではありませんが、本案件で必要になる次の機能を備えています。

| EEGLABで行っていた処理 | Python環境での主な手段 |
|---|---|
| `.set` / `.fdt` データの読み込み | `mne.io.read_raw_eeglab()` |
| 連続EEGのフィルタ・再参照・チャンネル処理 | MNE `Raw` API |
| ICA | `mne.preprocessing.ICA` のextended InfomaxまたはPicard |
| ICLabel | `mne_icalabel.label_components()` |
| 瞬き・眼球・筋活動などの成分候補分類 | ICLabelのラベルと確率を利用 |
| 不良センサー・区間の補助評価 | MNEおよびautoreject |

ICLabelは、extended Infomax、平均基準、1–100 HzにフィルタしたEEGを前提として学習されています。本解析の正式な前処理では、過去のMATLAB処理と実データを確認したうえで条件を確定します。自動ラベルだけで除去成分を決めず、成分波形、頭皮分布、スペクトル、EOGとの関係も確認します。

本案件は試行ごとのepochingを脳活動の主解析にしない方針です。autorejectは主にEpochsを対象とするため、必要な場面だけ補助的に使用し、連続解析へ機械的には適用しません。

## 4. Codexによる実行

作業ディレクトリをリポジトリルートにして、次を使用します。

```bash
.venv/bin/python 解析プログラム/verify_environment.py
.venv/bin/python 解析プログラム/<解析スクリプト>.py
```

依存関係の同期、テスト、品質検査にはリポジトリ内のuvを使用します。

```bash
.tools/uv/uv sync --frozen
.tools/uv/uv run pytest -q
.tools/uv/uv run ruff check pyproject.toml 解析プログラム tests
```

Codexは、これらの作成・実行・検証について通常の承認を求めません。解析スクリプトは `解析プログラム/` に置き、解析結果は指定されたOneDriveの `実験本番_本解析` またはその配下だけへ保存します。

## 5. 新しい環境での復元

uvが存在しない場合は、公式インストーラーを確認したうえで、リポジトリ内の `.tools/uv/` へ配置します。その後、Pythonと全依存関係をロックファイルから復元します。

```bash
curl -LsSf https://astral.sh/uv/install.sh -o /tmp/uv-install.sh
UV_UNMANAGED_INSTALL="$PWD/.tools/uv" sh /tmp/uv-install.sh
UV_CACHE_DIR="$PWD/.tools/uv-cache" \
UV_PYTHON_INSTALL_DIR="$PWD/.tools/python" \
"$PWD/.tools/uv/uv" sync --frozen
```

復元後は、次の検証をすべて成功させます。

```bash
MPLCONFIGDIR="$PWD/.tools/matplotlib" .venv/bin/python 解析プログラム/verify_environment.py
.tools/uv/uv run pytest -q
.tools/uv/uv run ruff check pyproject.toml 解析プログラム tests
```

`verify_environment.py` は外部データやOneDriveへ書き込まず、合成データを使って数値計算、連続EEG処理、extended Infomax ICA、ICLabel分類を確認します。

## 6. 変更時の注意

- Pythonのminor版や主要ライブラリを更新する場合、MNE、MNE-ICALabel、SciPy、ONNX Runtimeの対応状況を公式情報で確認します。
- `uv.lock` を手編集しません。
- `.venv/`、`.tools/`、Jupyterのキャッシュ、解析結果をcommitしません。
- 実データでの検証前に、入力形式、チャンネル名、サンプリング周波数、参照、イベント構造を確認します。
- Python環境の変更も解析再現性に影響するため、検証、commit、push、Notion記録まで同じ作業内で完了します。
