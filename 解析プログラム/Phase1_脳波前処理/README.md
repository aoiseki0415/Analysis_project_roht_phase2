# Phase 1：脳波前処理

脳波前処理のPythonスクリプトです。実行前にルート`README.md`、`docs/運用ルール.md`、`docs/解析上の注意事項.md`、`docs/Phase1_脳波前処理仕様.md`、Notionの「解析ストーリー」配下を確認します。

## スクリプト

- `Phase1_No1_InputAuditAndSynchronization.py`：入力監査、`OriginalTimestamp`と行動側の`*Sys(ms)`の同期、セット境界の決定
- `Phase1_No2_AutomatedPreProcessing.py`：フィルタ、detrend、不良チャンネル候補検出、ICA学習用区間除外、extended Infomax、ICLabel、セット分割、HDF5とQC成果物の保存
- `phase1_pipeline.py`：No1とNo2の共通実装

## 実行順序

```bash
MPLCONFIGDIR=/tmp/mplconfig-roht .venv/bin/python \
  '解析プログラム/Phase1_脳波前処理/Phase1_No1_InputAuditAndSynchronization.py' \
  --participant-id 101

MPLCONFIGDIR=/tmp/mplconfig-roht .venv/bin/python \
  '解析プログラム/Phase1_脳波前処理/Phase1_No2_AutomatedPreProcessing.py' \
  --participant-id 101
```

No2が不良チャンネル候補を検出した場合は、利用者の決定まで停止します。承認後は `--approved-bad-channel <CH>`、残す場合は `--retained-bad-channel <CH>` を候補ごとに指定します。対象IDを省略すると全解析対象を処理するため、代表IDの検証では必ず `--participant-id`または`--first-only`を使います。

## 保存先

- 加工済みデータ：`SandBox_ロート案件（データ）/解析に必要なデータたち/Phase1_脳波前処理/No<番号>_<内容>/IDxxx/`
- figure、HTML、表、ログ：指定OneDriveの `実験本番_本解析/Phase1_脳波前処理/No<番号>_<内容>/IDxxx/`

生データ原本には書き込みません。No2の最終データは、セットごとの脳活動解析用EEGと瞬き解析用信号のHDF5です。どちらにも、256 Hzの相対時刻、`OriginalTimestamp`、対応する`results.csv`行動データを含めます。
