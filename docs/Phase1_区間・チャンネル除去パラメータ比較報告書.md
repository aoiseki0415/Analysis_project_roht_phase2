# Phase 1 区間除去・チャンネル除去パラメータ比較報告書

作成日：2026年9月26日

対象：ID101、Part1、Set1～6

## 1. 目的

ICA学習前の区間除去・チャンネル除去について、初期設定、中間型、極端型の3パターンを比較した。パターン間で変更したのは、ASR、絶対振幅、flatline、RANSAC相関、候補時間率、自動除外時間率の6項目である。その他のフィルタ、ICA、ICLabel設定は共通とした。

## 2. 区間除去のパラメータ設定

「中間型」「極端型」が「初期設定と同じ」の項目は、表中で「同じ」と記載した。

| パラメータ | 設定内容 | 初期設定 | 中間型 | 極端型 | 外部フィードバックと判断 | 公式情報 |
|---|---|---:|---:|---:|---|---|
| ASR BurstCriterion | 急激な多チャンネル変動を異常とする閾値。小さいほど厳しい | 20 | 20 | 15 | 15を比較候補としたが、20が公式の保守的既定値 | [EEGLAB clean_rawdata](https://eeglab.org/plugins/clean_rawdata/) |
| ASR判定窓 | ASR判定の時間窓 | 0.5秒 | 同じ | 同じ | 変更不要 | [EEGLAB詳細資料](https://eeglab.org/plugins/clean_rawdata/Documentation.html) |
| ASR窓の重なり | 隣接するASR窓の重複率 | 50% | 同じ | 同じ | 変更不要 | [EEGLAB詳細資料](https://eeglab.org/plugins/clean_rawdata/Documentation.html) |
| ASR基準データ選択 | 正常状態の基準共分散を推定する窓 | log RMS robust zが全chで−3.5～3.5。不足時は良好な最低20窓または全体の10% | 同じ | 同じ | プロジェクト独自の停止回避策として維持 | 完全一致する公式規定なし |
| 最終区間判定窓 | 除外区間を最終判定する窓長 | 1.0秒 | 同じ | 同じ | 変更不要 | [EEGLAB詳細資料](https://eeglab.org/plugins/clean_rawdata/Documentation.html) |
| 最終判定窓の重なり | 最終判定窓の重複率 | 66% | 同じ | 同じ | 変更不要 | [EEGLAB詳細資料](https://eeglab.org/plugins/clean_rawdata/Documentation.html) |
| RMS許容範囲 | 各窓・各chのlog RMSを異常とする範囲 | robust zが−3.5未満または7超 | 同じ | 同じ | EEGLAB由来の範囲として維持 | [EEGLAB詳細資料](https://eeglab.org/plugins/clean_rawdata/Documentation.html) |
| WindowCriterion | 異常ch比率が何%を超えた窓を除外するか | 25%超 | 同じ | 同じ | 32chでは9ch以上が異常の窓を除外 | [EEGLAB詳細資料](https://eeglab.org/plugins/clean_rawdata/Documentation.html) |
| 絶対振幅基準 | 基準以上の振幅を含む区間を強制的に除外 | 500 µV | 400 µV | 200 µV | 200 µVでは瞬き成分まで過剰に除外する懸念がある | プロジェクト独自追加 |
| 絶対振幅区間の前後余白 | 振幅超過区間の前後に追加する除外時間 | 前後1秒 | 同じ | 同じ | フィルタ影響と周辺アーチファクトを含めるため維持 | 公式規定なし |
| 適用先 | 検出区間を実際に除外するデータ | ICA学習用データのみ | 同じ | 同じ | 最終EEGでは全時間を保持し、除外maskを保存 | 本研究の運用方針 |

## 3. チャンネル除去のパラメータ設定

| パラメータ | 設定内容 | 初期設定 | 中間型 | 極端型 | 外部フィードバックと判断 | 公式情報 |
|---|---|---:|---:|---:|---|---|
| フラットライン時間 | 完全に同じ値が継続したchを除外する時間 | 30秒 | 5秒 | 5秒 | 5秒はEEGLAB既定値であり採用根拠が明確 | [EEGLAB clean_rawdata](https://eeglab.org/plugins/clean_rawdata/) |
| 高周波・低周波の分離境界 | ラインノイズ評価とRANSAC予測の帯域境界 | 45 Hz | 同じ | 同じ | 現行コードに合わせて45 Hzで統一 | 45 Hzの直接規定なし |
| ラインノイズ探索閾値 | 高周波RMSによる候補判定 | robust zが4超 | 同じ | 同じ | 候補抽出用として維持 | [EEGLAB clean_rawdata](https://eeglab.org/plugins/clean_rawdata/) |
| ラインノイズ自動除外閾値 | ラインノイズだけで自動除外する閾値 | robust zが6以上 | 同じ | 同じ | 4超を候補、6以上を自動除外とする保守的な独自基準 | 6の公式規定なし |
| RANSAC前処理 | チャンネル予測前に残す周波数帯 | 45 Hzローパス | 同じ | 同じ | 低周波部分で予測する考え方を維持 | [PREP原著](https://pmc.ncbi.nlm.nih.gov/articles/PMC4471356/) |
| RANSAC判定窓 | 予測と相関評価を行う窓長 | 5秒 | 同じ | 同じ | PREPの約4秒と近く、維持可能 | [PREP原著](https://pmc.ncbi.nlm.nih.gov/articles/PMC4471356/) |
| RANSAC反復数 | 予測を繰り返す回数 | 50回 | 同じ | 同じ | 変更不要 | [Autoreject RANSAC](https://autoreject.github.io/stable/generated/autoreject.Ransac.html) |
| RANSAC予測ch割合 | 1回の予測に使うch割合 | 25% | 同じ | 同じ | 変更不要 | [Autoreject RANSAC](https://autoreject.github.io/stable/generated/autoreject.Ransac.html)、[PREP原著](https://pmc.ncbi.nlm.nih.gov/articles/PMC4471356/) |
| RANSAC相関閾値 | 予測波形と実測波形の相関閾値 | 0.80未満 | 0.75未満 | 0.75未満 | 0.75は公式値との整合性が高い | [Autoreject RANSAC](https://autoreject.github.io/stable/generated/autoreject.Ransac.html)、[PREP原著](https://pmc.ncbi.nlm.nih.gov/articles/PMC4471356/) |
| RANSAC探索時間率 | 相関閾値を下回った窓が何%以上なら候補とするか | 50%以上 | 40%以上 | 40%以上 | 40%はAutoreject・PREPと一致 | [Autoreject RANSAC](https://autoreject.github.io/stable/generated/autoreject.Ransac.html)、[PREP原著](https://pmc.ncbi.nlm.nih.gov/articles/PMC4471356/) |
| RANSAC自動除外時間率 | RANSAC単独で自動除外する時間割合 | 80%以上 | 60%以上 | 60%以上 | 60%は比較候補。公式の直接基準はない | 公式規定なし |
| 複数検出器の一致 | 何種類の検出器が一致すれば自動除外するか | 2種類以上 | 同じ | 同じ | 保守的な独自統合ルールとして維持 | 公式規定なし |
| 適用先 | 異常chを実際に除外するデータ | ICA学習・ICA適用のみ | 同じ | 同じ | 最終EEGでは元の32chを保持し、除外maskと理由を保存 | 本研究の運用方針 |

## 4. ID101での比較結果

| パターン | ICA学習除外区間 | ICA学習除外ch | 除去IC | 瞬き成分除去の目視精度 | 端的な結果 |
|---|---|---|---|---:|---|
| 初期設定 | 70区間、188.227秒 | PO9 | IC0、IC5、IC13 | 85 | 区間除去は最少。瞬き成分は概ね除去されたが、一部残存を確認 |
| 中間型 | 74区間、227.052秒 | PO9 | IC0、IC5、IC13 | 92 | 区間除去の増加は小さく、目視上は3案で最も良好 |
| 極端型 | 376区間、1267.998秒 | PO9 | IC0、IC5 | 88 | 200 µV基準により瞬き成分を含む区間まで大幅に除外。過剰除去の懸念が強い |

注：チャンネル除去はいずれもICA学習・ICA適用に限定され、最終EEGではPO9を含む32チャンネルを保持する。瞬き成分除去の精度は、Fp1・Fp2のICA前後HTMLを目視確認した評価値である。

## 5. 所感

中間型は、初期設定からの区間除去増加を約39秒に抑えながら、瞬き成分の除去が最も良好に見えた。極端型は除外時間が約1268秒まで増加し、ICAの結果も中間型を上回らなかった。以上より、**中間型が区間除去量と瞬き除去精度のバランスに最も優れ、現時点の採用候補として妥当**と判断する。

## 6. スクリプトの配置と読み方

### 6.1 Google Driveのフォルダ構造

共有・確認用のコピーは、許可されたGoogle Driveフォルダ内の`スクリプト/`をルートとし、次の名前と構造で配置する。Pythonファイル名と相対的な配置は変更しない。ドキュメントは別の場所で管理するため、この構造には含めない。

```text
マイドライブ/
└── SandBox関連/
    └── ロート製薬PJ フェーズ2 2026.5~/
        └── 実験本解析_Codex共有用/
            └── スクリプト/
                └── Phase1_脳波前処理/
                    ├── Phase1_No1_InputAuditAndSynchronization.py
                    ├── Phase1_No2_AutomatedPreProcessing.py
                    ├── phase1_pipeline.py
                    └── パラメータ比較/
                        ├── Phase1_No2_Pattern1_Initial.py
                        ├── Phase1_No2_Pattern2_Intermediate.py
                        └── Phase1_No2_Pattern3_Extreme.py
```

Google Drive版は共有・確認用のコピーであり、最新版の正本はGitHubリポジトリとする。スクリプトを更新するときはGitHub側を更新し、検証・commit・push後に必要なPythonファイルだけをGoogle Driveへコピーする。ドキュメント、生データ、加工済みEEG、OneDriveの品質確認HTML・figure、HDF5、実行ログ、`.venv/`、`.tools/`、キャッシュは`スクリプト/`へ入れない。

### 6.2 GitHub上の正本

Phase 1の前処理スクリプトの正本は、リポジトリ内の次のフォルダにある。

```text
解析プログラム/Phase1_脳波前処理/
```

### 6.3 最初に確認するファイル

処理全体の入口は、次のファイルである。

```text
解析プログラム/Phase1_脳波前処理/Phase1_No2_AutomatedPreProcessing.py
```

このファイルは、対象IDとパラメータパターンを受け取り、共通処理を呼び出す。実際のフィルタ、区間除去、チャンネル除去、ICA、ICLabel、QC出力は、次の共通実装にまとめられている。

```text
解析プログラム/Phase1_脳波前処理/phase1_pipeline.py
```

`phase1_pipeline.py`では、冒頭の`PARAMETER_PROFILES`に3パターンの値が定義されている。処理内容を確認する場合は、主に次の関数を追う。

| 確認内容 | 関数・定義 |
|---|---|
| 3パターンの設定値 | `PARAMETER_PROFILES` |
| 使用パターンの切替 | `apply_parameter_profile()` |
| フラットライン検出 | `detect_flatlines()` |
| ICA用除外chの決定 | `select_ica_channel_exclusion_candidates()` |
| 絶対振幅による区間検出 | `absolute_amplitude_intervals()` |
| 参加者単位の前処理全体 | `preprocess_participant()` |

### 6.4 3パターンの専用スクリプト

比較用の入口は、次のフォルダに分けている。

```text
解析プログラム/Phase1_脳波前処理/パラメータ比較/
```

| パターン | 実行するファイル |
|---|---|
| 初期設定 | `Phase1_No2_Pattern1_Initial.py` |
| 中間型 | `Phase1_No2_Pattern2_Intermediate.py` |
| 極端型 | `Phase1_No2_Pattern3_Extreme.py` |

各専用スクリプトは、使用するパラメータ名、OneDriveの出力フォルダ名、ローカル加工済みデータを保存しない比較モードを固定している。処理本体を3重に複製せず、すべて同じ`Phase1_No2_AutomatedPreProcessing.py`と`phase1_pipeline.py`を使用する。

### 6.5 出力結果の確認先

比較結果は、指定OneDriveの次の場所に保存される。

```text
実験本番_本解析/
  Phase1_脳波前処理/
    No2_AutomatedPreProcessing/
      ID101_Pattern1_Initial/
      ID101_Pattern2_Intermediate/
      ID101_Pattern3_Extreme/
```

各フォルダでは、主に次のファイルを確認する。

| 確認内容 | ファイル名 |
|---|---|
| 区間除去・ch除去の全体確認 | `ID101_Part1_QC05_ICAExclusionReview_BeforeICA.html` |
| Fp1・Fp2のICA前後確認 | `ID101_Part1_QC01_BlinkCheck_ICA_before_after.html` |
| 区間除去の一覧 | `ID101_ICA_training_excluded_intervals.csv` |
| ICA学習除外ch | `ID101_ICA_channel_exclusions.json` |
| 除去ICとICLabel確率 | `ID101_ICLabel_probabilities.csv` |
| 実行結果の要約 | `ID101_QC_summary.json` |
| 実行ログ | `ID101_run.log` |

## 7. 参照資料

- [Notion：区間除去とch除去のパラメータ設定に関する議論](https://app.notion.com/p/3e7161f2809781ae8cc5c79c765e0ec7)
- [Phase 1 脳波前処理仕様](Phase1_脳波前処理仕様.md)
- [EEGLAB clean_rawdata plugin](https://eeglab.org/plugins/clean_rawdata/)
- [EEGLAB clean_rawdata詳細資料](https://eeglab.org/plugins/clean_rawdata/Documentation.html)
- [Autoreject RANSAC API](https://autoreject.github.io/stable/generated/autoreject.Ransac.html)
- [PREP pipeline原著](https://pmc.ncbi.nlm.nih.gov/articles/PMC4471356/)
