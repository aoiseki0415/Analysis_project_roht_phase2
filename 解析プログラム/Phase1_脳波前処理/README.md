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

No2が記録全体への影響が明確な不良チャンネル候補を検出した場合は、フィルタ・トレンド除去後の0 µV中心波形をOneDriveへ保存しますが、処理は停止しません。チャンネル単位で事前に明示的な除去承認がある候補だけを `--approved-bad-channel <CH>` で指定して除去します。確認後に保持すると決まった候補は `--retained-bad-channel <CH>` で指定します。どちらも指定されない候補は「除去承認なしで保持」と記録し、保持したまま後続処理を継続します。候補が複数ある場合は各オプションをチャンネルごとに繰り返します。不良区間のICA学習用除外と、ICLabelの`eye blink >= 0.80`による成分除去は事前承認なしで実行します。

確定した保存方針では、承認済み除去チャンネルをICA・MNEの計算中だけ除外し、脳活動解析用HDF5は元の32チャンネル順・32列へ戻します。除去済み列は全行`NaN`、`channel_available_mask`は元順の32要素とし、除去名・理由・承認記録を付帯させます。瞬き解析用HDF5はFp1・Fp2・平均の3列を維持しつつ、同じ利用可否情報と除去記録を持たせます。`NaN`列をICA・MNEへ入力しません。

> **実装保留**：2026年9月21日時点では、この固定32列保存方針のコード変更は利用者指示により未実施です。実装・テスト完了前にPhase 1 No2を再実行しません。

対象IDを省略すると全解析対象を処理するため、代表IDの検証では必ず `--participant-id`または`--first-only`を使います。本番一括処理は、パイロットIDでスクリプト、パラメータ、完了条件を確定した後に行います。確定後は同じGit版と設定を全IDへ適用し、正常完了したIDを理由なく再処理しません。

## 保存先

- 加工済みデータ：`SandBox_ロート案件（データ）/解析に必要なデータたち/Phase1_脳波前処理/No<番号>_<内容>/IDxxx/`
- figure、HTML、表、ログ：指定OneDriveの `実験本番_本解析/Phase1_脳波前処理/No<番号>_<内容>/IDxxx/`

生データ原本には書き込みません。No2の最終データは、セットごとの脳活動解析用EEGと瞬き解析用信号のHDF5です。どちらにも、256 Hzの相対時刻、`OriginalTimestamp`、対応する`results.csv`行動データを含めます。

確認用figureには軸名、単位、色・線種の意味、凡例を記載し、単位がない量は`[a.u.]`と表示します。複数チャンネルを上下表示する場合は縦軸スケールを統一します。ICA前後の全時間帯HTMLは、Fp1・Fp2・FzのICA前後について256 Hzの全サンプルを保持し、3チャンネルで共通の縦軸を使います。広域表示では画面上の各ピクセル内の最小値・最大値を描き、十分に拡大すると元サンプルを時系列順に結ぶ波形へ切り替えます。拡大・縮小、x軸移動、全体表示への復帰、チャンネル切替、カーソル位置の元サンプル値確認を実操作で検証します。10秒PNGは作成しません。瞬き解析用のFp1・Fp2・平均信号は、共通縦軸のセット別PNGとして保存します。

全時間帯HTMLは、OneDriveプレビューではなく、同期済みのローカルファイルをSafariで直接開きます。Safari検証では、拡大ボタンと波形の左右ドラッグにより表示時間範囲が実際に変化することまで確認します。

保存済みICAを変えず、全時間帯HTMLだけを再生成する場合は、`--participant-id <ID> --regenerate-html-only`を指定します。このモードはICAの再学習、成分再判定、HDF5再保存を行いません。
