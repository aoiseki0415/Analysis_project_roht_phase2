# Phase 4：脳波解析

脳波解析のPythonスクリプトを配置します。命名形式は `Phase4_No<番号>_<内容>.py` です。追加解析はNo1本体と混在させず、`No1_add`、`No1_sub` の独立スクリプトにします。

成果物と計算済みPSDは、同じNoを使って指定OneDriveと `解析に必要なデータたち/Phase4_脳波解析/` へ保存します。No1の現行スクリプトは `Phase4_No1_FmTheta.py` です。log10 PSD上側3SD除外は実装済みで、60秒平滑化は有限点数の追加基準を設けず、1点以上が有限なら算出する元仕様とします。2026-10-04に全40被験者ペア・80セッションのcacheを確定し、同じ全40ペアの再描画・再集計と成果物検証まで完了しました。No1_addは `Phase4_No1_add_FzTimeFrequencyMap.py` としてNo1本体から分離して実装済みです。

## 事前定義した解析対象

時間変化解析とセット別定量化では、文献調査に基づき次の単一ch×周波数帯を使用します。

- No1 frontal-midline theta（Fmθ）：Fz、4–7 Hz
- No2 occipital alpha：Oz、8–15 Hz
- No3 frontal delta：Fz、1–3 Hz

根拠と解釈上の注意は [`docs/Phase4_解析対象チャンネル文献調査.md`](../../docs/Phase4_解析対象チャンネル文献調査.md) を参照します。FCzとPOzは現行32chに含まれません。

No1は、全32chを1秒Hann窓・1秒移動・256点FFTのWelch法で解析し、4–7 Hz平均の未平滑PSDをHDF5へ一度だけ保存します。Phase 1区間mask後、セッションID・chごとの全Set一括 `log10(PSD)` 平均＋3SDを上側閾値とし、該当ch・時間窓だけをNaNにします。そのデータからFzの60秒平滑化時間変化、製品群別Grand-average、mask後未平滑PSDの定量化・統計、全32chの条件差topographyを作ります。現行の確定仕様は [`docs/Phase4_脳波解析仕様.md`](../../docs/Phase4_脳波解析仕様.md) を唯一の実装正本とします。

No1_addはFzの1–30 Hz線形PSDを用いる追加解析です。No1のシータmaskを流用せず、1–30 Hz平均からセッションID別・全Set一括の専用broadband log10上側3SD時間maskを作り、該当時間の全周波数binをNaNにします。その後、周波数bin別60秒平滑化、各Set100 progress点化、被験者間平均を行い、Eye Drop、Control、`Difference in PSD` の3段Grand-average TFMだけを出力します。正本は [`docs/Phase4_No1_add_FzTimeFrequencyMap仕様.md`](../../docs/Phase4_No1_add_FzTimeFrequencyMap仕様.md) です。

No1_subは `Phase4_No1_sub_FmThetaChange.py` として独立実装します。ローカルのNo1 PSD cacheを読み、各セッションID・各chのSet 1平均を基準にPSD Change（%）へ変換します。Fzの個人時間変化・Grand-average、Set別および全Set統合定量化、全32chの条件差topographyを専用OneDriveルートへ出力します。全Set統合値はSet 1–6の全有限時間窓を直接平均します。Grand-averageは平均線の最大絶対値をy軸の約70%、定量化は0より上：下を約2：1とし、Set名を統計表示より十分上へ離して置きます。ローカル派生cacheは作成せず、ペア109–209はSet 1 baselineが定義できないため除外します。正本は [`docs/Phase4_No1_sub_FmThetaChange仕様.md`](../../docs/Phase4_No1_sub_FmThetaChange仕様.md) です。2026-10-04に本番40ペアを事前検査し、規定どおり109–209を除く39ペアの実行・成果物検証を完了しました。Set 2–6の統計は両側対応ありt検定、補正対象は5比較で固定し、独立再計算により未補正値とFDR-BH値が保存CSVへ完全一致することを確認済みです。No1とNo1_subは現行確定版として扱い、明示的な仕様変更または成果物不具合がない限り再計算しません。

No1_addの実行スクリプトは `Phase4_No1_add_FzTimeFrequencyMap.py` です。3段TFMは絶対PSDに `viridis` の `0–30 µV²/Hz`、差分にゼロ中心の `RdBu_r` の `−20–20 µV²/Hz` を使い、2製品で各カラースケールを共通化します。表示範囲外は色だけを飽和させ、保存数値はクリップしません。

No2とNo3はNo1三解析と同じ実装エンジン・処理順・figure比率を用いる独立エントリポイントです。No2はOz・8–15 Hz、No3はFz・1–3 Hzです。`_sub` は対応する主解析cacheからSet 1基準変化率を作り、`_add` はNo2でOz、No3でFzの1–30 Hz TFMを専用cacheへ保存します。No2_addの表示範囲は絶対PSD `0–20 µV²/Hz`、差分 `−15–15 µV²/Hz`、No3_addはNo1_addと同じ絶対PSD `0–30 µV²/Hz`、差分 `−20–20 µV²/Hz` です。No3_sub定量化の統計表示は通常解析と同じ有意マーク42 pt／n.s. 26 ptと相対位置を使います。No2のEye Drop色はC Cube `#C23B8A`／V Rohto Premium `#E36A8D`、No3は `#8F7300`／`#C29A00`、Controlは共通 `#402B5D` です。

2026-10-04にNo1_addを全40ペア・80セッションへ実行し、80件のFz TFM cache、476件の利用可能Set、既知欠測4 Set、2製品のGrand-average TFM、値・有効N・mask監査表・実行ログを検証しました。figureだけの変更では検証済みcacheを再計算しません。

## No1_addの実行モード

- `--preflight-only`：入力、製品群、ID対応、既知欠測Setだけを検査する
- `--compute-tfm`：セッション別TFM cacheだけを計算・検証する
- `--group-outputs-only`：検証済みcacheから2製品のGrand-average成果物だけを再作成する
- `--all`：cache計算からGrand-average成果物までを一括実行する
- `--force-recompute`：`--compute-tfm` または `--all` と併用し、明示的にcacheを再計算する場合だけ使う

```bash
MPLCONFIGDIR=/tmp/mplconfig-roht .venv/bin/python \
  '解析プログラム/Phase4_脳波解析/Phase4_No1_add_FzTimeFrequencyMap.py' \
  --manifest /secure/path/phase4_manifest.csv \
  --production-batch \
  --all
```

## No1の実行モード

- `--preflight-only`、`--compute-psd`、`--individual-only`、`--group-outputs-only`、`--all` から1つを選択します。
- `--force-recompute` は `--compute-psd` または `--all` と併用し、明示的な再計算決定がある場合だけ使用します。
- `--force-recompute` がない限り、設定hashと入力情報が一致して検証済みのPSD cacheを再利用します。
- `--grand-y-target-fraction` と `--grand-y-basis` は表示検証用の明示的オプションです。本番成果物は標準の `mean_plus_sem` を `0.75` の高さに置く規則を使用し、特例オプションを指定しません。
- 全対象へ同じコード・同じ定数を適用し、既知欠測Set以外のID固有分岐を作りません。

本番manifestはリポジトリ外の非公開CSVを `--manifest` で渡します。実行例は次のとおりです。

```bash
MPLCONFIGDIR=/tmp/mplconfig-roht .venv/bin/python \
  '解析プログラム/Phase4_脳波解析/Phase4_No1_FmTheta.py' \
  --manifest /absolute/path/to/private_manifest.csv \
  --production-batch \
  --preflight-only
```

preflight完了後の本計算では、同じmanifestに `--all` を指定します。入力、cache、OneDriveのデフォルトパスは確定仕様に固定しています。全対象の本番PSD cacheは作成・検証済みで、表示変更時はcacheを再利用します。

## No1実装時の固定事項

- 入力：Phase 1の `brain_activity_eeg` HDF5、256 Hz、V単位、固定32ch順
- PSD：MNE `psd_array_welch`、1秒Hann窓、外側窓を1秒移動、256点FFT、4–7 Hzの4 bin平均、線形µV²/Hz
- Set端：前後128 samplesの反射padding、Set開始・終了を窓中心として評価
- 区間mask：Phase 1のICA学習除外区間と1%以上重なるPSD窓を全32chでNaN化し、時刻・progressは保持
- PSD上側外れ値：Phase 1 mask後、セッションID・ch別に全Setをまとめた `log10(PSD)` の平均＋3SD（`ddof=1`）を超える上側値だけをNaN化。元PSD、閾値、mask、除外数・率を保存
- 閾値監査表：`Sub/tables/Log3SDThresholdExclusion/` にセッションID・Set・ch別のlog平均、標本SD、log／線形閾値、有効窓数、除外窓数・率を保存
- ch mask：ICA学習用ch除外maskはPSDへ適用せず、32chを保持
- 時間変化：各Set内で60秒中心化単純移動平均。NaNは無視し、1点以上が有限なら平均し、窓全体がNaNの場合だけNaN
- 現行非適用：平均参照、ラプラシアン
- cache：全32chの帯域平均PSD時間変化、中心時刻、progress、mask監査情報をHDF5保存
- figure：両mask適用後に60秒平滑化した個人Fzと製品群別Fz Grand-average、両mask適用後の未平滑PSDによる定量化、全32ch差topography
- 個人Fz：平滑化後を `Individual/` 直下、未平滑の閾値除外前後を `Individual/Unsmoothed/BeforeThresholdExclusion/` と `AfterThresholdExclusion/` に保存
- 欠測：個人時間変化は欠測側だけ空白、集団集計・定量化・topographyは対応条件も対称除外

Figureの寸法、フォント、軸名、目盛、Set位置、線幅、色、y上限、統計マーク位置、topographyのmontage・カラースケールはPhase 4仕様書の数値をコード定数としてそのまま実装します。定量化はPhase 3と同様に条件名22 ptと製品名18 ptを分離します。Topographyは6 Set横一列、太い円形頭部輪郭・鼻、8 ptの電極点、等高線なしの滑らかな色面、十分な間隔を空けた太いSet別colorbarで描画し、全Set共通の左右対称かつ切りのよい上限を使います。Phase 2・3を再解釈して別の値を採用しません。

Phase 4の被験者別結果表や日次実行記録はNotionへ作成しません。preflight、本計算、cache検証、出力確認、警告、失敗理由、成果物一覧はOneDriveの `No1_FmTheta/Sub/logs/` と `Sub/tables/` へ保存し、コード・文書の版はGit履歴で追跡します。NotionはPhase 4の概要・確定仕様・文献調査の管理に限定します。
