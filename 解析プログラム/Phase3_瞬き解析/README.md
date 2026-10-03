# Phase 3：瞬き解析

瞬き解析のPythonスクリプトを配置します。命名形式は `Phase3_No<番号>_<内容>.py` です。

現行の確定仕様は [Phase 3 瞬き解析仕様](../../docs/Phase3_瞬き解析仕様.md) です。実装・実行前に必ず確認します。

## No1：瞬き検出・Blink Rate解析

- 入力はPhase 1のセット別 `IDxxx_SetN_blink_signal.h5`
- 主解析信号の表示名は `Eye Blink Component Signal`。計算は「ICAでICへ分解 → ICLabel eye blink確率0.80以上のICを選択 → そのICのチャンネル別寄与をセンサー空間へ戻す（ICA前EEG−除去後EEGと同値）→ 使用可能なFp1・Fp2を時点ごとに平均 → Phase 3で1–10 Hzゼロ位相フィルタ」の順で行う。通常はFp1・Fp2平均だが、一方がICA学習除外なら残るFp信号を主解析列とする。ID124・209はFp2補助列が全SetでNaNのため主解析列の実体はFp1のみだが、他IDと同じ処理を行う。Phase 1 HDF5の `Fp1_Fp2_mean` はフィルタ前までの結果で、Fp1・Fp2単独はセット別検出数の補助QCのみ
- 検出用フィルタは1–10 Hz、ピーク検出は `scipy.signal.find_peaks`
- Peak height基準は設けず、同一セッションの使用可能な全セットからprominenceの中央値・MADを求め、`中央値 + 12 × 1.4826 × MAD`を全セットへ共通適用する。係数12は文献推奨値ではなく、8／10／12の探索比較と係数10による初回全対象出力の過剰検出確認を踏まえて選んだ固定値
- パーセンタイル閾値は、IDごとに上位一定割合を選んで抽出割合と総数を似通わせ、実際のID差・条件差を弱めるおそれがあるため使用しない
- 同一瞬きの重複検出を避ける安全条件としてminimum peak distanceを100 ms、瞬きらしい時間幅を保つ形状条件としてpeak widthを20–320 msに固定する
- 検出確認HTMLはセッションIDごとにMAD方式の1ファイルを作り、同じResetスケールの横長PNGも作る
- 全候補prominenceの分布とMAD閾値線を、横軸0–500 µV・縦軸対数のPNGとしてセッションIDごとに作り、500 µV超の候補数も図中へ記す
- Blink Rate時間変化は60秒中心化窓、1秒刻み、端点は実際の窓長で補正する。さらにセット内だけで15秒中心化単純移動平均を適用し、その後0〜600へ変換する
- セット別定量値は検出総数をセット実時間（分）で割る。移動窓値の時間平均は使用しない
- Cキューブ群とVロートプレミアム群を分け、各群でEye Drop対Controlを被験者内比較
- 主要Grand-average・セット別定量化は全使用可能データで作成して保持する。追加版として、ID233 ControlのSet 1〜3で瞬き成分が十分に抽出されていないという事後確認に基づき、Vロートプレミアム群だけID133–233の両条件のSet 1〜3を群集計から外す。個人結果、瞬き検出結果、主要版、Set 4〜6は変更しない
- 個人時間変化、製品群別Grand-average、6パネルセット別定量化を同じNo1の一括実行で出力する。Grand-averageはセット内0〜100%の100点固定グリッドへ、セット境界を越えずに補間して被験者間集計する。セット別定量化は個人ペア図ではなく、条件内の被験者間平均バー・被験者値ドット・被験者内対応線を示す製品群別図とする
- 欠測セットは補完しない。ID 109 Set 1、ID 120 Set 6、ID 135 Set 2、ID 225 Set 4を欠測として扱う
- Blink Rate線・SEM帯のPhase 3専用色はControl `#402B5D`、C Cube `#168C80`、V Rohto Premium `#2A91B3`。セット別定量化は同じ条件対応の明度・彩度違いとして、Control `#66547D`、C Cube `#4CA79E`、V Rohto Premium `#62AFC6`を使う
- 個人Blink Rate図は0始まりで、2条件の線の最大値が縦軸上限の約70%となる5 blinks/min刻みの上限を使う。Grand-averageは各進捗位置の標本SD（`ddof=1`）を有効人数Nの平方根で割ったSEMを用いて平均±SEMを描き、`平均 + SEM` の最大値が縦軸上限の約75%となる5 blinks/min刻みの上限を製品群ごとに使う。Grand-average右下のN・shade説明は表示しない
- 指定OneDriveの `Phase3_瞬き解析/No1_BlinkRate/` 直下で `CCube/`、`VRohtoPremium/`、`Sub/` に分け、各製品群内を `Individual/`、`GrandAverage/`、`SetQuantification/`、`QualityCheck/` に分ける。HTML・横長PNGは `QualityCheck/BlinkDetection/`、prominence分布PNGは `QualityCheck/ProminenceDistribution/` に保存する。検出確認の凡例は `Eye Blink Component Signal`、縦軸は `Amplitude (µV)` とする。検出成果物は `Pair<1回目>-<2回目>_01_ID<1回目>`、`..._02_ID<2回目>` の接頭辞で並べ、表・ログはNo1直下の `Sub/` へ分離する
- Vロートプレミアム群の追加figureと対応CSVには `ExcludePair133-233_Sets1-3` を付け、通常版と混同・上書きしない
- Phase 3ではローカルデスクトップへ新しい中間データを保存しない
- FigureのSet名・軸名・目盛・凡例はPhase 2と同等の大きさとする。セット別定量化の被験者ドットは固定seedのランダム左右ジッターを加え、同一被験者の2条件を同じoffsetの線で結ぶ
- Notionは親ページを確定事項の要約、子ページを詳細手法とする。結果は1行1被験者ペアの統合表とし、行ページ内へ2セッションのQCと、セッション・Set別の平均信号／Fp1／Fp2検出数、セット時間、Blink Rate、閾値、欠測・備考を記録する。共通SetのEye Drop／Control総検出数の大きい方÷小さい方が2倍以上なら `条件間瞬き数バランス=要確認` とし、除外判定には使わない
- 各セッションの目視QCは最大3分。HTMLのx軸を個々のスパイクが見える幅まで拡大し、先頭から末尾まで表示窓を連続的に送って全使用時間を確認する。Reset全景だけの確認は禁止し、終了後はHTMLを閉じる

実行スクリプトは `Phase3_No1_BlinkRate.py` です。被験者ペアは、条件表で確認した1回目ID・2回目ID・目薬ありID・製品を明示します。

```bash
MPLCONFIGDIR=/tmp/mplconfig-roht .venv/bin/python \
  '解析プログラム/Phase3_瞬き解析/Phase3_No1_BlinkRate.py' \
  --participant '101:201:101:VRohtoPremium'
```

複数被験者は `--participant` を繰り返すか、`first_session_id`、`second_session_id`、`drops_session_id`、`product` の4列を持つ非公開manifestを `--manifest` で指定します。ID番号帯から条件を推測しません。

本番一括実行前は、同じ非公開manifestに `--production-batch --preflight-only` を付けます。40ペア・80セッション、製品群各20名、重複・対象外ID、既知の欠測Set、HDF5構造、主解析列の有限性を出力なしで全件検査します。合格後、`--preflight-only` だけを外した同一コマンドで、全個人結果からGrand-averageとセット別定量化まで一括作成します。

既存の個人・検出結果を保持したまま群集計だけを再作成する場合は、同じ40ペアmanifestを使って次を実行します。

```bash
MPLCONFIGDIR=/tmp/mplconfig-roht .venv/bin/python \
  '解析プログラム/Phase3_瞬き解析/Phase3_No1_BlinkRate.py' \
  --manifest /path/to/private_manifest.csv \
  --production-batch --group-outputs-only
```

## MAD係数の比較実行

正式実行の既定値は係数12に固定します。係数比較を再開する場合だけ `--prominence-mad-multiplier` と `--comparison-label` を明示し、正式成果物を上書きせず `No1_BlinkRate_ParameterComparison/<label>/` へ分離します。過去の比較結果は [MAD係数比較記録](../../docs/Phase3_MAD係数比較.md) に履歴として残します。

## 実装・実行の完了条件

1. ルートREADME、運用ルール、解析上の注意事項、Phase 3仕様、NotionのPhase 3ページを確認する
2. 全対象を同一コードと固定パラメータのループで処理する
3. パイロットIDで入力、検出、欠測、HTML操作、figure、CSV・JSON、Notion記録を検証する
4. OneDrive成果物とNotionの読み戻しまで確認する
5. 許可済みの通常工程では利用者承認を求めない
