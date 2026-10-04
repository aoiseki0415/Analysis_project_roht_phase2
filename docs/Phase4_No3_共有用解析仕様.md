# Phase 4 No3：前頭delta解析 共有用仕様書

## 1. 構成

No3はNo1の確定済み3解析と同じ構造を用いる。変更するのは解析名、主解析帯域、配色、保存先であり、代表チャンネルはNo1と同じFzである。

| 解析 | 内容 | 代表ch | 周波数 |
|---|---|---|---|
| No3 | frontal deltaの絶対PSD | Fz | 1–3 Hz（1・3 Hzを含む3 bin） |
| No3_sub | Set 1基準のdelta PSD Change | Fz | No3 cacheの1–3 Hz平均 |
| No3_add | Fz Time-Frequency Map | Fz | 1–30 Hz、1 Hz刻み |

入力、対象40被験者ペア、条件・製品対応、既知欠測Set、MNE Welch設定、Phase 1区間mask、log10上側3SD除外、平滑化、progress、統計、topography、検証はNo1／No1_sub／No1_addと同一である。

## 2. No3本体

- 全32chへ1秒Hann窓、1秒移動、256点FFT、1 Hz分解能の線形PSDを計算する
- 1、2、3 Hzを算術平均し、単位は `µV²/Hz` とする
- Phase 1区間maskと1%以上重なる窓を全chでNaN化する
- 各セッションID・chで全利用可能Setをまとめ、有限・正の未平滑PSDの `log10` 平均＋3標準偏差を超える上側値だけをNaN化する
- 未平滑・全32chのdelta PSD、時刻、progress、両mask、閾値、除外数・率をNo3専用HDF5へ保存する
- Fzの個人時間変化とGrand-averageだけにSet内60秒中心化単純移動平均を適用する
- 定量化とtopographyはmask後の未平滑PSDを使う
- Set別・全Set統合値を両側対応ありt検定で比較する。主PNGは未補正p、CSVは未補正・Bonferroni・Holm・FDR-BHを保存する
- topographyは全32chの `Eye Drop − Control`、colorbarは `Difference in PSD (µV²/Hz)` とする

## 3. No3_sub

No3の検証済みcacheを読み、セッションID・ch別にSet 1の有限な未平滑PSD平均をbaselineとして次を計算する。

```text
PSD Change = (PSD / Set 1 baseline − 1) × 100
```

変換後にFz時間変化だけをSet内60秒平滑化する。定量化とtopographyは未平滑変化率を使う。Set 1欠測の109–209は解析全体から除外し、Set 1はBaselineとして表示して単独検定を行わない。ローカル派生cacheは作らない。

## 4. No3_add

Fzの1–30 Hz線形PSDをNo3_add専用のセッション別HDF5へ保存する。Phase 1区間mask後、各時間窓の1–30 Hz平均からセッションID別・全Set一括のbroadband `log10`平均＋3SD上側時間maskを作り、該当窓の全周波数binをNaN化する。周波数bin別にSet内60秒平滑化し、Set別100 progress点化後、製品群別Grand-averageを作る。出力はEye Drop、Control、`Difference in PSD = Eye Drop − Control` の縦3段TFMだけとする。

## 5. Figure・配色・保存

- Control：`#402B5D`
- C Cube Eye Drop：`#8F7300`
- V Rohto Premium Eye Drop：`#C29A00`
- 定量化barは上記を基準に可読性を保って淡色化する
- 寸法、Arial、軸名、目盛、線幅、Set位置、y軸占有率、統計位置、topographyはNo1の確定値をそのまま使う
- No3本体のcache：`解析に必要なデータたち/Phase4_脳波解析/No3_FrontalDelta/PSDTimeSeries/`
- No3_add cache：`解析に必要なデータたち/Phase4_脳波解析/No3_add_FzTimeFrequencyMap/TimeFrequencySeries/`
- OneDrive：`Phase4_脳波解析/No3_FrontalDelta/`、`No3_sub_FrontalDeltaChange/`、`No3_add_FzTimeFrequencyMap/`

各主成果物フォルダにはPNGだけを置き、表・統計・監査情報・実行ログは各解析の `Sub/` へ保存する。

## 6. 結果の読み方

- `Individual/`：Fzの60秒平滑化後delta PSD時間変化。Eye DropとControlを同一被験者内で比較する
- `Individual/Unsmoothed/BeforeThresholdExclusion/`：Phase 1区間maskだけを反映した未平滑PSD
- `Individual/Unsmoothed/AfterThresholdExclusion/`：さらにセッションID・ch別のlog10上側3SD除外を反映した未平滑PSD
- `GrandAverage/`：40被験者ペアを製品群別に平均した線。シェードは被験者間SEM
- `SetQuantification/`：各Setおよび全Set統合の未平滑PSD時間平均。線で結ばれた2点が同一被験者で、PNGの統計表示は未補正の両側対応ありt検定
- `Sub/tables/SetQuantification/`：未補正pとBonferroni、Holm、FDR-BH補正結果を含むCSV
- `Topography/`：各chの `Eye Drop − Control`。暖色がEye Dropで高く、寒色がControlで高いことを表す
- No3_sub：Set 1 baselineからの変化率。0%がSet 1水準で、正値は増加、負値は減少を表す
- No3_subの定量化では、統計線をデータ基準値の1.13倍、統計文字を有意時1.17倍・n.s.時1.18倍の位置に置き、通常解析と同じ有意マーク42 pt／n.s. 26 ptを用いる
- No3_add：上段がEye Drop、中段がControl、下段が `Eye Drop − Control` の1–30 Hz TFM

## 7. 全件実行・検証状態（2026-10-04）

- No3本体：40被験者ペア・80セッションを処理し、セッション別cache 80件、PNG 168件を生成
- No3_sub：Set 1欠測の109–209を仕様どおり除外し、39被験者ペア、PNG 86件を生成
- No3_add：セッション別cache 80件、製品群別TFM 2件を生成
- 既知欠測はID109 Set 1、ID120 Set 6、ID225 Set 4、ID135 Set 2。Grand-average、定量化、topographyでは対応条件側の同一Setも欠測として扱う
- 代表cacheでFz、1–3 Hz全bin、256 Hz、`µV²/Hz` を確認し、主PNG・統計CSV・topography・TFMを目視確認した
- 0 byteの出力はなく、No1の既存成果物は保持されている
- 2026-10-04にNo3_subの定量化figureだけ、Phase 2／通常解析と同じ統計マークの大きさ・相対位置へ更新した。数値・検定結果は変更していない
