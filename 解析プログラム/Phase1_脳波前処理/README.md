# Phase 1：脳波前処理（確定版）

このフォルダには全IDへ同一条件を適用する現行本番スクリプトだけを置きます。過去の比較スクリプトは `解析プログラム（過去版いらなくなったやつ）/Phase1_脳波前処理/` にあり、本番解析では使用しません。

## 実行前の必読順

1. ルート `README.md`
2. `docs/運用ルール.md`
3. `docs/解析上の注意事項.md`
4. `docs/Phase1_脳波前処理仕様.md`
5. Notion「解析ストーリー / フェーズ1：脳波前処理」の現行本文とID別テーブル

## 現行スクリプト

- `Phase1_No1_InputAuditAndSynchronization.py`：入力監査、`OriginalTimestamp`と行動側`*Sys(ms)`の同期、セット境界の確定
- `Phase1_No2_AutomatedPreProcessing.py`：フィルタ、detrend、ICA学習専用のチャンネル・区間除外、extended Infomax、ICLabel、セット分割、HDF5とQC成果物の保存
- `phase1_pipeline.py`：No1とNo2の共通実装

## 確定パラメータ

| 項目 | 設定 |
|---|---:|
| ASR BurstCriterion相当 | 20 |
| 絶対振幅 | 400 µV（前後1秒を含めてICA学習から除外） |
| flatline | 5秒 |
| RANSAC相関閾値 | 0.75 |
| RANSAC候補時間率 | 40% |
| RANSAC自動除外時間率 | 60% |
| ICLabel Eye blink | 0.80以上だけ除去 |
| ICA | extended Infomax、乱数シード97、最大1000反復 |

絶対振幅400 µVは現時点の確定値です。後日、利用者から変更指示があった場合だけ、仕様・コード・テストを同時に改訂します。

## 実行

```bash
MPLCONFIGDIR=/tmp/mplconfig-roht .venv/bin/python \
  '解析プログラム/Phase1_脳波前処理/Phase1_No1_InputAuditAndSynchronization.py' \
  --participant-id 101

MPLCONFIGDIR=/tmp/mplconfig-roht .venv/bin/python \
  '解析プログラム/Phase1_脳波前処理/Phase1_No2_AutomatedPreProcessing.py' \
  --participant-id 101
```

IDを省略すると全対象を処理します。代表IDの確認では必ず `--participant-id` または `--first-only` を使います。通常実行は比較ラベルを受け付けず、ローカル解析データを必ず保存します。

## 出力とQC

- ローカル：`解析に必要なデータたち/Phase1_脳波前処理/No<番号>_<内容>/IDxxx/`
- OneDrive：`実験本番_本解析/Phase1_脳波前処理/No<番号>_<内容>/IDxxx/`
- `QC01_BlinkCheck`：Fp1・Fp2のICA前後を表示する全時間HTML
- `QC05_ICAExclusionReview`：Before ICAの全32ch、ICA学習除外区間、ICA学習除外chを表示するHTML
- 除去ICごとのtopomap、PSD、時系列、ICLabel確率
- セット別の脳活動解析用EEG HDF5と瞬き解析用HDF5

QC02～QC04のICA前後HTMLとトレンド除去専用figureは作成しません。

保存後、完了確定前に次を実施します。

1. `QC01_BlinkCheck`だけを開き、最大3分で全時間を重複なく高速走査する。
2. BeforeのFp1・Fp2に同期する短時間の尖りまたは丘状波形を瞬き候補とし、Afterで両方から明瞭に消失・抑制された割合を0～100点で目視概算する。
3. 除去した各ICのtopomap PNGを見てFp1・Fp2の空間的バランスを評価する。除去IC全体で左右が補完されている場合も問題なしとする。
4. Notionに精度、空間的バランス（良好／一部偏り／片側偏重）、簡潔な所見を記録する。
5. 確認後はHTMLタブを必ず閉じる。

空間的バランスはQC記録であり、IC除去条件に追加しません。除去はICLabel `eye blink >= 0.80` だけで自動実行し、途中承認を求めません。

## 分割記録

| ID | 使用セット | 元取得区間 |
|---|---|---|
| 109 | Set2～6 | Part2 |
| 120 | Set1～5 | Part1 |
| 135 | Set1 / Set3～6 | Part1 / Part2 |
| 225 | Set1～3 / Set5～6 | Part1 / Part2 |

空白を補間せず、Partごとにフィルタ・detrendを行い、ID共通のICAモデルを各Partに適用します。上表の対応は回帰テストで固定しています。
