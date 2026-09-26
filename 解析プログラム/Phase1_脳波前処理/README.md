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

No2が記録全体への影響が明確な不良チャンネル候補を検出した場合は、フィルタ・トレンド除去後の0 µV中心波形をOneDriveへ保存しますが、処理は停止しません。保守的基準に該当したチャンネルは、利用者承認なしでICA学習・ICA適用対象からだけ自動除外します。不良区間のICA学習用除外と、ICLabelの`eye blink >= 0.80`による成分除去も事前承認なしで実行します。

確定した保存方針では、ICA除外チャンネルをICA・MNEの計算行列からだけ外し、脳活動解析用HDF5は元の32チャンネル順・32列で保存します。ICA除外列は削除・NaN化せず、フィルタ・トレンド除去済み信号を保持します。`ica_channel_excluded_mask`は元順の32要素とし、除外名・理由を付帯させます。瞬き解析用HDF5はFp1・Fp2・平均の3列を維持しつつ、同じICA除外情報を持たせます。

2026年9月22日現在、ICA除外チャンネルを含む元の32チャンネル順への統合、`ica_channel_excluded_mask`、除外理由の付与、保存後検証を実装済みです。

同日、分割対象4 IDの実データ範囲を読み取り確認し、ID 109はSet2～6=`Part2`、ID 120はSet1～5=`Part1`、ID 135はSet1=`Part1`・Set3～6=`Part2`、ID 225はSet1～3=`Part1`・Set5～6=`Part2`として5セットずつ出力できることを確認済みです。対応表は回帰テストで固定されています。

対象IDを省略すると全解析対象を処理するため、代表IDの検証では必ず `--participant-id`または`--first-only`を使います。本番一括処理は、パイロットIDでスクリプト、パラメータ、完了条件を確定した後に行います。確定後は同じGit版と設定を全IDへ適用し、正常完了したIDを理由なく再処理しません。

再現性のため、パイプライン仕様版、乱数シード97、フィルタ・ICA・ICLabel閾値、QC figureスタイル版をメタデータへ保存します。figureとHTMLのレイアウト、配色、軸、単位、解像度、ファイル名はIDによらず固定し、同じコード版を全IDへ適用します。

## 保存先

- 加工済みデータ：`SandBox_ロート案件（データ）/解析に必要なデータたち/Phase1_脳波前処理/No<番号>_<内容>/IDxxx/`
- figure、HTML、表、ログ：指定OneDriveの `実験本番_本解析/Phase1_脳波前処理/No<番号>_<内容>/IDxxx/`

生データ原本には書き込みません。No2の最終データは、セットごとの脳活動解析用EEGと瞬き解析用信号のHDF5です。どちらにも、256 Hzの相対時刻、`OriginalTimestamp`、対応する`results.csv`行動データを含めます。

確認用figureには軸名、単位、色・線種の意味、凡例を記載し、単位がない量は`[a.u.]`と表示します。トレンド除去専用figureは作成しません。ICA前後の全時間帯HTMLは、`QC01_BlinkCheck`=Fp1・Fp2、`QC02_Frontal`=Fz・F3・F4、`QC03_CentralTemporal`=Cz・T7・T8、`QC04_ParietalOccipital`=Pz・O1・O2の順で作成します。256 Hzの全サンプルを保持し、ID内の全Part・全HTMLで初期縦軸を共通化します。各HTML内でもチャンネル間の縦軸を統一し、x軸の表示範囲で自動変更しません。Set開始・終了は縦線とラベルで示します。y軸ボタンで共通スケールを拡大・縮小・初期化できます。広域表示では画面上の各ピクセル内の最小値・最大値を描き、十分に拡大すると元サンプルを時系列順に結ぶ波形へ切り替えます。ドラッグまたは左右矢印キーでx軸移動でき、矢印キーを長押しすると押下中だけ連続移動します。全体表示への復帰、チャンネル切替、カーソル位置の元サンプル値確認を実操作で検証します。10秒PNGは作成しません。瞬き解析用のFp1・Fp2・平均信号は、共通縦軸のセット別PNGとして保存します。

`QC05_ICAExclusionReview`は、Before ICAの全32チャンネルを縦に並べ、ICA学習の除外時間帯を赤帯、ICA学習・適用の除外チャンネルを黄色行と`[ICA除外]`で示すHTMLです。その他の軸操作、共通縦軸、Set境界の仕様はQC01～QC04と同一です。

全時間帯HTMLは、OneDriveプレビューではなく、同期済みのローカルファイルをSafariで直接開きます。Safari検証では、拡大ボタンと波形の左右ドラッグにより表示時間範囲が実際に変化することまで確認します。

各IDのデータ保存後・前処理完了確定前に、ファイル名に`QC01_BlinkCheck`を含むFp1・Fp2だけのHTMLを最大3分確認して瞬き成分除去精度を0～100点で評価します。QC02～QC04は採点に使いません。完全ランダムな10秒区間を飛び飛びに確認し、BeforeでFp1・Fp2に同時に現れる約100 msの瞬き候補がAfterで両方から明瞭に消失・抑制した場合を1点、片側のみまたは部分的な抑制を0.5点、残存または悪化を0点として百分率化します。候補がなければ評価不能とし、推定値を作りません。評価値または評価不能理由をNotionの「ICA処理結果（ID別）」へ記録し、評価後は該当HTMLのSafariタブを閉じるボタンで必ず閉じます。

QC05は除外結果の事後確認用であり、瞬き成分除去精度の採点には使いません。

保存済みICAを変えず、全時間帯HTMLだけを再生成する場合は、`--participant-id <ID> --regenerate-html-only`を指定します。このモードはICAの再学習、成分再判定、HDF5再保存を行いません。

`--output-label`は比較検証用の特別実行で明示された場合だけ使い、通常実行では指定しません。
