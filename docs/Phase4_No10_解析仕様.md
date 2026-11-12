# Phase 4 No10・No10_sub：Fz low-alpha解析仕様

更新日：2026-11-12。**現行帯域は8–10 Hz（両端込み）。全対象の再計算、subの指定ペア除外追加版、独立数値監査と画像確認を完了。方法は第1〜11節、最新実績は第12節、旧実績・過程はhistoryに分離する。**

本書は現行仕様。議論・準備の経緯は[設計決定記録](history/Phase4_No10_設計決定記録_20261112.md)へ分離する。既存No1–9の仕様・コード・結果は変更しない。

対応Notion：[No10詳細・共通設計](https://app.notion.com/p/416161f2809781738442d82aa8c4357f)、[No10_sub詳細](https://app.notion.com/p/416161f2809781a7bc00ebe3c680f340)、[設計決定・準備記録](https://app.notion.com/p/416161f2809781839c12d8d54b6af35e)。親はPhase 4ページ。

## 1. 目的・解析単位

| 項目 | No10 | No10_sub |
|---|---|---|
| 解析名 | Fz low-alpha絶対PSD | Fz low-alpha PSD Change |
| 正式stem | `No10_FzLowAlpha` | `No10_sub_FzLowAlphaChange` |
| 帯域 | **8、9、10 Hzの3 binを含む** | 同左 |
| 代表ch | **Fz** | **Fz** |
| 値 | 帯域内PSDの算術平均、µV²/Hz | 各ID・ch自身のSet 1平均に対する変化率、% |
| 比較 | 製品群別に同じ被験者のEye DropとControl | 同左 |
| 出力 | 個人時間変化、Grand-average、Set別・全Set統合定量化、個人・群topography | 同左 |

low-alpha 8–10 Hzは今回の操作的定義であり、普遍的な帯域定義と断定しない。IAFや個人別帯域の推定はしない。No10_add／TFMは今回の範囲外。帯域変更前の実績は[旧実績保存版](history/Phase4_No10_旧帯域実行結果_20261112.md)へ分離し、現行結果として使用しない。

旧IAF No10は既にNo9へ改番済み。**新No10はlow-alphaパワーであり、旧No10のFz IAFではない。** 現行IAFは[No8・No9仕様](Phase4_No8_No9_共有用解析仕様.md)のみ。

## 2. 引き継ぐ仕様と参照元

- 最新の[No1統合仕様](Phase4_No1_共有用解析仕様.md)の本体・subを基準とし、[No2](Phase4_No2_共有用解析仕様.md)・[No3](Phase4_No3_共有用解析仕様.md)の帯域変更方式と整合させる。
- 変更点は帯域、代表ch、解析名・保存先・cache識別子、点眼色と、subの指定ペア除外感度分析。計算・欠測・統計・描画の基本構造は維持する。
- No1の一時的な95% y軸、廃止済み30点平滑化足切り、固定y軸、探索用図は継承しない。
- No1–3のtopography感度分析、No2のOz/Pz補助除外、No4–7の指定ペア除外、No8–9のIAF選別は継承しない。
- 不明点は現行No1–3の正本と実装を照合し、未解決の矛盾があれば勝手に選ばず停止する。以下の平滑化点数・描画anchor等は既存実装を詳記したもので、No1–3の数値計算やデザインを変更しない。過去の実績や除外率をNo10の結果として転記しない。

## 3. 入力・対象・欠測

- Phase 1確定済み `IDxxx_SetN_brain_activity.h5` を読み取り専用入力とする。`data_kind=brain_activity_eeg`、32chの名前・順、Set番号、時刻、単位、fsを検証する。
- `signal/data` はsample×32chのV。float64でµVへ変換（×10⁶）してからPSD計算する。**PSD計算・保存は全32ch**、Fzだけを時間変化と定量化の代表に使う。
- 実測・保存fsが256 Hzであることを検証する。256でない入力を黙って256として扱わない。追加のfilter、再参照、Laplacian、ch補間は行わない。
- 許可済み被験者リストとPhase 1入力対応から40ペア・80セッション、2製品各20ペアを基準にする。IDの100/200番台だけでEye Dropを決めない。ペア、製品、点眼回、セッション条件のmanifestを照合・保存する。
- 既知の4欠測Set、共通対象外、分割記録の正本は[解析上の注意事項](解析上の注意事項.md)。本書に個人ID一覧を重複保存しない。
- 個人時間変化：欠測条件のSetだけ線を描かず、対応する条件の実在Setは描く。
- Grand-average・Set定量化・topography：片条件が既知欠測なら**同じペア・同じSetを両条件から外す**。全Set統合値も両条件共通の利用可能Setを使用する。
- No10はSet 1欠測だけで被験者全体を除かない。No10_subはSet 1 baselineが必要なので、既知Set 1欠測ペアは全体を対象外とする。今回の実使用Nは第12節に記載する。
- 想定外の入力不足、ch不一致、非有限入力、計算不能baselineはpreflightで停止・記録し、個人別の独自除外や補完を追加しない。
- 主結果は追加の被験者選別を行わない。No10_subの追加版だけに[注意事項の確定除外集合](解析上の注意事項.md#phase-4-no10_sub指定ペア除外追加版2026-11-12確定)を適用する。第6.4節で対象成果物と除外単位を定義する。

## 4. No10：PSD計算と品質mask

### 4.1 1秒窓・1秒移動

No1–3と同じ `mne.time_frequency.psd_array_welch` を使う。全被験者へ以下の固定値を適用する。

| 引数・項目 | 固定値 |
|---|---|
| 入力 | 1秒分のµV信号、末尾次元が時間。全32ch |
| `sfreq` | 256.0 Hz |
| `fmin`, `fmax` | **8.0, 10.0 Hz** |
| `n_fft`, `n_per_seg` | 256, 256 |
| `n_overlap` | 0 |
| `window` | `hann` |
| `average`, `output` | `mean`, `power` |
| `remove_dc`, `verbose` | True, False |
| 外側の移動幅 | 256 sample＝1秒 |
| 周波数bin確認 | `[8., 9., 10.]` と完全一致 |
| 帯域値 | 3 binを算術平均。積分・総和・dB化はしない |

1秒窓内は1 Welch segment。複数時間窓のPSDを後で平均する処理と、Welch内部の平均は混同しない。

- Setの信号両端に128 sampleずつreflect padding。休憩時間のEEGは入力しない。
- 窓中心sampleは `0, 256, ...`。末尾sample `n−1` が含まれなければ追加するため、最後だけ間隔が1秒未満になる場合がある。
- 相対時刻・OriginalTimestampは中心sampleの値を保持する。
- `set_progress = center / (n−1) × 100`、`global_progress = (Set−1) × 100 + set_progress`。
- 計算は実時間・元sampleで行い、progressは表示・被験者間位置合わせ用。異なるchも同じ時刻・progress列を使う。

### 4.2 区間除外とlog3SD

1. Phase 1 `ica_training_excluded_mask` と1秒PSD窓の重なり率を求める。maskにも同じreflectを適用する。
2. 重なり率 **1%以上** の窓は解析時に全32chをNaNにする。時刻を詰めない。
3. その後、**セッションID×chごと**に利用可能な全Setの有限・正の未平滑8–10 Hz平均PSDをまとめる。
4. `x=log10(PSD)`、`T=mean(x)+3×SD(x, ddof=1)`。`x>T` の窓だけ、そのchでNaNにする。Set別閾値、下側閾値、条件間で共通の閾値は使わない。
5. 元PSDを上書きせず、log平均・SD・T・10^T・mask・Set/ch別の有効数／除外数／率を保持する。再描画でも両maskを必ず適用する。

No1のtheta、No2の8–15 Hz、変更前のNo10帯域で算出した閾値・maskを転用しない。ICA学習用 `ica_channel_excluded_mask` は監査用に保存するが、PSDでのch除外には使わず32chを保持する。PSD計算・主結果へ新たな低PSD足切り、被験者除外、空間外れ値除外は設けない。subの事後感度分析は保存cacheに影響しない別工程とする。

### 4.3 時間変化と定量化の分岐

- 時間変化：両mask適用後 → **Set内の1秒刻みPSDに60点の中心化単純移動平均** → progress表示。既存No1–3と同じく、`pd.Series(...).rolling(window=60, center=True, min_periods=1).mean()` を使う。
- これは1秒刻みを基準にした「60秒平滑化」であり、progress幅による平滑化ではない。ただしSet末尾の追加PSD点だけ間隔が1秒未満となるため、厳密にtimestampで60秒を切り出す方式とは区別する。末尾も既存実装どおり1点として等重みで扱う。
- 平滑化窓の有限値を等重み平均。1点以上なら計算し、全NaNのみNaN。30点以上の条件は復活させない。Set境界はまたがず、端は利用可能範囲で平均する。
- 定量化・topography：両mask適用後の**未平滑PSD**を使用する。
- `BeforeThresholdExclusion` はPhase 1区間mask適用後・log3SD前、`AfterThresholdExclusion` は両mask適用後。どちらも未平滑。
- 欠測Setの穴は保つ。NaNをゼロにせず、窓の時刻を前詰めしない。

## 5. No10_sub：Set 1基準の変化率

No10専用cacheだけを読み取り専用で使用し、Welchを再計算しない。

1. 元PSDへPhase 1区間maskとNo10専用log3SD maskを適用する。
2. **IDごと・chごと**にSet 1全時間の有限な未平滑PSDの算術平均を `B` とする。
3. `PSD Change(t) = (PSD(t) / B − 1) × 100`。各条件自身のBを使い、対応条件・他chのBを流用しない。
4. Bが有限かつ正であることを検証。既知Set 1欠測以外の異常は黙って除外しない。
5. 個人時間変化：変化率へ変換後にNo10と同じ60秒平滑化。Grand-averageはその後にprogress位置合わせ。
6. Set定量化・topography：**未平滑の変化率**を使用する。Set 1も表示・全Set統合に含め、Set 1平均は数値誤差内で0になることを検証する。

独立したローカルPSD Change cacheは作らない。再現に必要なbaseline、有効窓数、対象理由、計算設定、No10入力cache識別子はOneDriveの補助表・ログに残す。

## 6. Grand-average・定量化・統計・topography

### 6.1 Grand-average

- 各条件・各Setの平滑化後系列を `np.linspace(0,100,100,endpoint=False)` の100点へ、No1の同じ補間実装で対応づける。Set間を連続補間しない。
- 既知欠測Setは両条件の100点をNaN。製品群別・条件別に各progress点の有限被験者を等重みで平均する。
- 平均・標本SD（ddof=1）・N・SEM=SD/√Nを保存。N=1なら平均のみ、SD/SEMはNaN。SEMはSDではない。

### 6.2 定量化

- Set別：Fzの当該Set全時間の有限な未平滑値の算術平均。全時間を使い、前半／最後80試行等へ限定しない。
- 全Set統合：両条件共通で使えるSetの有限な未平滑窓を連結して平均。Set平均の単純再平均ではない。
- バーは被験者間平均、点は被験者値、対応線は同じ被験者の2条件。利用可能なペアだけで比較する。
- `paired_statistics.py` の `scipy.stats.ttest_rel`、**両側対応ありt検定**。差の向きはEye Drop−Control。
- N、t、df、未補正p、平均差、差のSD、95% CI、Cohen’s dzを保存する。
- PNGは未補正p。CSVは未補正、Bonferroni、Holm、BH-FDRを保存。補正familyは製品ごと・解析ごと。
- No10は6 Set、No10_subはSet 1をBaselineとして検定せずSet 2–6の5検定。全Set統合は1検定なので補正しない。探索的解析として未補正の限界を明記する。

### 6.3 Topography

- 全32chそれぞれに上記Set定量化を行い、同じ被験者内の **Eye Drop−Control** を計算する。
- 個人は6 Set横並び、Grand-averageは被験者別差を製品群内で等重み平均する。画像同士を平均しない。
- No10の単位はµV²/Hz。No10_subは変化率同士の差で、数値的にはpercentage points（図は既存と同じ `%` 表記）。
- 既知欠測は両条件対応で除外。既存No1–3の群topography実装では、**当該Setの条件差が全32chで有限なペア**を群平均に使用し、Setごとの `Valid_N` を保存する。chごとに異なる母集団を黙って混ぜない。
- 実行監査ではch別の有限ペア数も照合し、全32ch共通Nとの一致／不一致を記録する。部分的に非有限なchがある場合は、上記のSet単位採用に及ぼす影響を別記する。補足分析の事後的ch除外は流用しない。

### 6.4 No10_subのみ：指定ペア除外の追加感度分析

- 主結果を保持し、`SpecifiedPairsExcluded` と識別する追加版を両製品で作る。対象の正本は[解析上の注意事項](解析上の注意事項.md#phase-4-no10_sub指定ペア除外追加版2026-11-12確定)。Vロートプレミアム2ペア、Cキューブ1ペアを指定する。
- 除外するのは**指定ペアのEye Drop／Control両条件・全Set**。片条件・一部Setだけの除外ではない。既知欠測とbaseline要件を適用後、指定集合を群集計から外す。
- 追加対象はFzの **Grand-average、Set別定量化、全Set統合定量化** と対応する数値表・統計・実行記録だけ。この追加除外によってNo10本体、subの個人図、主結果、topography、元PSD・mask・baselineは変更しない。帯域変更ではこれらも8–10 Hzで再計算・再生成する。感度版topographyは作らない。
- 保存済み現行帯域cacheから通常のsub値を作り、対象集合だけを絞って同じ平均・SEM・対応ありt検定を再計算する。補正familyは追加版・製品ごとにSet 2–6の5検定、全Set統合は未補正の1検定。Set 1を全Set統合へ含める。
- 縦軸・統計配置は除外後の値から第8節の同じ比率で再計算する。Grand-averageは追加版の両製品で共通軸とし、主結果の大きな上限を固定流用しない。
- 選定理由は**帯域変更前の結果で持続的に大きな変化率を観察した利用者指定**。事後・探索的な感度分析であり、ノイズと確定した除外や一般的な品質閾値ではない。主結果と並べて影響を確認し、追加版のみで製品効果を確定しない。
- 対象集合・理由、除外前後のペア数、Set別／全Set統合の実有効N、元cache識別子をSubへ記録する。対象者をmanifestから削除したり、再描画のたびに結果を見て再選別したりしない。

## 7. 配色（No10・No10_sub共通）

| 条件・製品 | 時間変化・Grand-average線 | 定量化バー・点 |
|---|---|---|
| Control | `#402B5D` | `#66547D` |
| Eye Drop (C Cube) | `#637B22` | `#8B9D58` |
| Eye Drop (V Rohto Premium) | `#91A63D` | `#ACBC6E` |

既存のorange／pink／yellow、blue／cyan、青緑、赤、brown系と区別するオリーブ系。4つの新規hexは既存解析設定と重複させない。Controlは意図的な共通色。定量化は対応する線色を淡くし、同じ解析・製品の関係を保持する。描画した両製品・両解析の図で識別性を確認した。topographyは条件色ではなく共通の発散色 `RdBu_r`。

## 8. Figure仕様

全図Arial、白背景、180 dpi、英語ラベル。正規表記の上付き²を用い、別フォントへ黙ってfallbackしない。上・右spine非表示、軸線幅1.5。一般時間変化・統計図に参加者タイトルやN説明を加えない。

### 8.1 時間変化

| 要素 | 設定 |
|---|---|
| サイズ | 24×8 inch |
| 横軸 | `Experimental Progress, %`、0–600、50刻み |
| Set区切り | 100–500、`#9E9E9E`破線1.5 pt |
| Set名 | x=50,150,…,550、axes y=0.96、22 pt |
| 軸名／目盛／凡例 | 28／20／20 pt |
| 条件線 | 3.0 pt、alpha=1、Controlを先に描画 |
| 凡例 | 上中央、anchor=(0.5,1.18)、2列、枠なし、製品名付きEye Drop |
| 余白 | left .08、right .99、top .78、bottom .20、tight保存 |
| No10 yラベル | `PSD (µV²/Hz)` |
| No10_sub yラベル | `PSD Change, %` |
| SEM帯 | 同色alpha=.18、境界線なし、Grand-averageのみ |

縦軸は**描画に使う系列**から決める。未平滑図はその図自身の値を使う。

- No10個人：下限0、最大値M/0.70以上の切りのよい上限。
- No10群：下限0、最大の平均+SEMをMとしてM/0.75以上。2製品の大きい上限へ統一。95%例外を使わない。
- No10_sub個人：0中心・上下対称。最大絶対値が正負各半軸の約70%に来る上限。
- No10_sub群：**平均線の**最大絶対値を基準に同じ70%・上下対称。2製品で共通軸。SEM帯を基準にはしない。
- No10の目盛は3–6個、候補1,2,2.5,5×10ⁿから5個に最も近い間隔を選ぶ。subは既存の対称軸関数をそのまま使い、3–7個の候補から5個に最も近い間隔を選ぶ（通常は5個）。subの目盛候補は1,2,2.5,4,5,10×10ⁿ。No10は横グリッドなし、subだけ0の薄い灰色線。

### 8.2 定量化

- Set別34×9 inch・6パネル横一列・共通y軸、全パネルにy目盛数字。全Set統合7.5×9 inch・1パネル。
- 左Eye Drop、右Control。中心±.32、bar幅.42、x範囲±.90。bar alpha=.82、枠#222222・1 pt。
- 点サイズ150、alpha=.68、白枠1.2 pt。対応線#777777・1.2 pt・alpha=.34。
- jitter±.055、ペア内で同じoffset、seed=4000+Set番号、全Set統合7001。
- 条件名22 pt、Eye Drop直下の括弧付き製品名18 pt、軸名30 pt、目盛23 pt、Set名26 pt。
- Set別余白L .06／R .995／T .94／B .25／wspace .24。全Set版L .20／R .98／T .94／B .25。
- ブラケット黒2.2 pt。capはNo10でaxes高さ.018、subでaxes高さ.02。`n.s.`は両解析とも26 pt・normal。アスタリスクは両解析とも42 ptだが、No10はbold、subは既存No1_sub–No3_subと同じnormal。すべてArial。
- p<.05=`*`、p<.01=`**`、p<.001=`***`、それ以外=`n.s.`。Set 1基準検定不能をn.s.と偽装せずBaseline表示。

| 位置・軸 | No10 | No10_sub |
|---|---|---|
| M | 表示する個人定量値の最大値 | max(個人最大値, 2×abs(min(個人最小値,0))/1.54, 1) |
| 黒線 | 1.13M | 1.15M |
| アスタリスク | 基準中心1.17Mからaxes高さ.018だけ下へ光学補正 | **bottom anchor 1.08M** |
| n.s. | 中心1.18M | **bottom anchor 1.20M** |
| Set名 | 中心1.29M | 中心1.42M |
| 上限／下限 | 1.37M／0 | 1.54M／−上限÷2 |

No10は既存共通 `add_significance_bracket` の光学補正まで継承するため、実際のアスタリスク中心は `1.17M − .018×(y上限−y下限)`。`n.s.`へこの補正は加えない。subはNo1_sub〜No3_sub確定実装のbottom anchorをそのまま継承し、中心指定へ読み替えず、この光学補正も加えない。定量化のy目盛は両解析とも3–6個、0を含む切りのよい等間隔。全Set版の表示名はAll Sets。

### 8.3 Topography

- 36×6.5 inch、6 Set横一列。各図内の全Setで同じ対称カラースケール。個人ごと・製品群ごとには可変。
- 全Set・chの最大絶対差をMとし、V≥M/.85を満たす最小の切りのよい値。候補1,1.5,2,2.5,3,4,5,6,8,10×10ⁿ。範囲−V〜+V、目盛−V,0,+V。
- MNE montage=`colin27_1020`、sphere=(0,0,0,.095)、`plot_topomap`：cmap=RdBu_r、sensors=k.、名前なし、contours=0、extrapolate=head、image_interp=cubic、border=mean、res=256。
- 頭円・鼻4 pt、耳なし、電極点8、Set名24 pt／pad16、Missing表示22 pt。空間補間は描画用で数値平均・統計を変更しない。
- colorbar fraction=.08、pad=.10、aspect=12、数字24 pt。
- No10ラベル `Difference in PSD (µV²/Hz)` は28 pt、subラベル `Difference in PSD Change, %` は20 pt。Δへ省略しない。
- chごとの有意記号は追加しない。sub Set 1は0のBaseline map。

## 9. スクリプト・中間データ・再現手順

### 9.1 スクリプトと識別版

```text
解析プログラム/Phase4_脳波解析/
  Phase4_No10_FzLowAlpha.py
  Phase4_No10_sub_FzLowAlphaChange.py
  phase4_no10_cache_guard.py
  phase4_no10_sub_sensitivity.py
  validate_phase4_no10_outputs.py
  run_phase4_no10_band_revision.py
```

No2／No3と同じ `phase4_band_variant_config.py` 経由で検証済みNo1／No1_sub engineを使用する。mainは `configure_band_engine`、subは `configure_change_engine` でNo10固有の帯域・代表ch・保存先・色を設定する。全被験者は同一コード・設定でループ処理する。No10固有設定の変更が他Noのdefault・出力先を変えないことを別プロセスのテストで確認する。既存No1–3 engineそのものは今回変更しない。

| 識別子 | 値 |
|---|---|
| No10 script version | `20261112_lowalpha_8to10_v2` |
| No10 cache configuration version | `20261112_lowalpha_8to10_cache_v2` |
| No10_sub script version | `20261112_lowalpha_8to10_change_v2` |

No10はPSD計算・保存、cache検証、個人図、Grand-average、定量化、topographyを独立実行できる。No10_subはcache読込から開始し、各出力工程を分離する。以下のCLIは再現手順であり、本番完了を示す実行記録ではない。

| モード | No10 | No10_sub |
|---|---|---|
| `--preflight-only` | manifest・Phase 1入力検査のみ | cache・条件対応・Set 1 baseline検査のみ |
| `--compute-psd` | cache計算・保存・読み戻し検証のみ | なし |
| `--individual-only` | cacheから3種の個人時間変化と個人topography | cacheから個人時間変化と個人topography |
| `--group-outputs-only` | Grand-average・定量化・統計・群topography | 同左＋本番全対象なら指定ペア除外追加版 |
| `--set-quantification-only` | なし | 主結果の定量化・統計だけ |
| `--sensitivity-only` | なし | 指定ペア除外のGrand-average・Set／全Set定量化・統計だけ |
| `--all` | preflight→必要なcache計算→全出力 | preflight→主結果全出力＋本番全対象なら指定ペア除外追加版（PSD再計算なし） |

本番では40ペアの同じmanifestと `--production-batch` を使う。subもmanifestから対象を手で削らず、仕様化されたSet 1欠測除外と、追加出力だけの指定ペア除外を実装内で適用する。manifestは以下の必須4列を持ち、氏名を含めず、Gitへ保存しない。

```text
first_session_id,second_session_id,drops_session_id,product
```

```sh
no10_repo='/Users/aoiseki/GitHub/Analysis_project_roht_phase2'
no10_manifest='/Users/aoiseki/Library/CloudStorage/OneDrive-個人用/デスクトップ/SandBoxプロジェクト/ロート製薬フェーズ2 2026.5/実験本番_本解析/Phase4_脳波解析/No10_FzLowAlpha/Sub/tables/ParticipantManifest.csv'
no10_main="$no10_repo/解析プログラム/Phase4_脳波解析/Phase4_No10_FzLowAlpha.py"
no10_sub="$no10_repo/解析プログラム/Phase4_脳波解析/Phase4_No10_sub_FzLowAlphaChange.py"

"$no10_repo/.venv/bin/python" "$no10_main" --manifest "$no10_manifest" --production-batch --preflight-only
"$no10_repo/.venv/bin/python" "$no10_main" --manifest "$no10_manifest" --production-batch --compute-psd
"$no10_repo/.venv/bin/python" "$no10_main" --manifest "$no10_manifest" --production-batch --individual-only
"$no10_repo/.venv/bin/python" "$no10_main" --manifest "$no10_manifest" --production-batch --group-outputs-only
"$no10_repo/.venv/bin/python" "$no10_sub" --manifest "$no10_manifest" --production-batch --all
```

No10の計算から全出力までは、3つの生成モードの代わりに `--all` でも実行できる。同じ作業で両方を重複実行しない。既定input・cache・outputは許可済みの固定先を使い、他の保存先へfallbackしない。`--force-recompute` は不具合または合意済み計算変更時だけ使用し、図の調整では使わない。Grand-averageは既定の `--grand-y-target-fraction 0.75 --grand-y-basis mean_plus_sem` を変更しない。

subの全対象 `--all`／`--group-outputs-only` は、baseline適格な39ペアの主結果に続けて感度版を自動生成する。少数ペアpilotではこの自動追加を省略する。感度版だけを再描画する場合は、同じ40ペアmanifestと `--production-batch --sensitivity-only` を指定し、cache・ID・製品・確定除外集合を再検証する。`--set-quantification-only` は主定量化だけであり、感度版も更新したい場合に代用しない。

### 9.2 キャッシュ

```text
/Users/aoiseki/Desktop/SandBox_ロート案件（データ）/解析に必要なデータたち/
  Phase4_脳波解析/No10_FzLowAlpha/PSDTimeSeries/
    Pair<初回ID>-<2回目ID>_01_ID<初回ID>_FzLowAlpha_AllChannelsPSD.h5
    Pair<初回ID>-<2回目ID>_02_ID<2回目ID>_FzLowAlpha_AllChannelsPSD.h5
```

- No1と同じHDF5構造（[No1仕様第7節](Phase4_No1_共有用解析仕様.md#7-psdキャッシュhdf5)）。未平滑・mask前の `sets/SetN/psd_band_mean` が原値正本。32ch、float32、窓×ch。
- `log3sd_outlier_mask`、`ica_training_mask_fraction`、各中心時刻（float64）、Set/global progress、中心sample、ch名、ch mask、Set availability、QC閾値・数を保存する。
- attrsには `script_version`、帯域8–10・実bin、fs、単位、ID/ペア/条件/製品、PSDパラメータ、mask方針、`configuration_hash`、`input_fingerprints_json`、作成時刻を保存する。Set datasetはgzip4・shuffleを用いる。
- 専用のschema名・analysis stem・cache versionを独立attrsとして保存する方式ではない。**analysis stem・focus channel・cache configuration version・全計算設定と入力fingerprintを設定hashの生成内容に含める**。script versionは生成時の履歴として独立attrsに保存し、互換性判定はcache configuration versionを含むhashで行う。描画だけのscript version変更でPSD再計算を要求しない。
- No2の8–15 Hzや変更前No10の帯域平均cacheから8–10 Hzを逆算できない。No10はPhase 1から現行3 binのPSDと専用log3SDを再計算する。FzのみのTFM cacheやIAFの10秒窓・0.1 Hz PSDも使用しない。
- 読み戻してshape・時刻・progress・ch順・設定・mask再現を検証。No10専用cache guardで8–10 Hzの全bin・設定hashの再計算一致・入力ファイルのサイズ／mtime・manifestのID／ペア／条件／製品を確認し、別帯域・旧数値設定・入力変更・条件不一致のcacheでは停止する。旧cacheを現行として再利用しない。図だけの調整でPSDを再計算しない。
- No10_sub用のローカルデータフォルダは作らない。

### 9.3 今回の帯域置換・実行監査

- `run_phase4_no10_band_revision.py` は今回の置換専用ラッパー。解析手法を別実装せず、同じ本番main／subスクリプトを40ペアmanifestで呼ぶ。
- Googleの匿名化ID・製品・点眼回／セッション条件を照合し、照合済みmanifestのSHA-256を固定する。全80セッション入力をpreflightしてから更新を始める。
- 旧CSV・JSON・LOGは各Noの `Sub/history/Before8to10Hz_20261112/` へ元相対パスで保存し、コピーhashを確認する。旧実行ログは現行logsから履歴へ移す。旧PNGは現行図へ置換し、表示用の旧版は残さない。
- mainの `--all --force-recompute` → subの `--all` →独立監査を実行する。cache 80件のhash更新、全260 PNGの再生成、他Noの出力・cacheのパス／サイズ／mtime不変を検査する。これらの件数は予定値であり、完了実績は第12節による。
- 独立監査は保存PSD・mask・baseline・定量・統計・GA・topographyを再構成する。さらに各実在Setの先頭／中央／末尾の1秒窓・全32chを元EEGからSciPy Welchで再計算し、8・9・10 Hz平均と保存値を照合する。全窓の元EEG再計算ではなく抜粋検証である。
- コマンド・Git commit・時刻・終了コード・成果物hash・警告／失敗・数値検証は `Sub/logs/` へ保存する。数値監査と実画像確認は別の完了項目にする。OneDriveローカル同期フォルダへの保存を、サーバー側同期完了と同一視しない。
- 数値監査・画像確認・文書更新とGit pushの後、同じ実行管理スクリプトの `--complete-verification --review-manifest <確認記録JSON>` で、解析を再実行せず目視対象PNGのhash、保護対象の不変、manifestのhash、GitのHEADとremoteの一致を最終照合し、`DeliveryVerification_20261112_8to10Hz.json` と実行記録の完了状態を保存する。

## 10. OneDrive構造・結果の見方

親は許可済み `実験本番_本解析/Phase4_脳波解析/`。その下に既存Noと並列に配置する。**以下は確定した出力構造。実生成件数・検証実績は第12節を参照する。**

```text
No10_FzLowAlpha/
  CCube/                         # VRohtoPremium/も同じ構造
    Individual/                  # 両mask後・60秒平滑化の2条件線
      Unsmoothed/
        BeforeThresholdExclusion/ # Phase 1 mask後、log3SD前
        AfterThresholdExclusion/  # 両mask後
    GrandAverage/                # 平均±SEM
    SetQuantification/           # Set別・全Set統合PNGと統計CSV
    Topography/
      Individual/                # ペアごとのEye Drop−Control
      GrandAverage/              # 被験者別差の群平均
  VRohtoPremium/
  Sub/
    tables/{GrandAverage,Log3SDThresholdExclusion,SetQuantification,Topography}/
    logs/
No10_sub_FzLowAlphaChange/
  CCube/                         # VRohtoPremium/も同じ構造
    Individual/                  # Set 1変化率・60秒平滑化
    GrandAverage/                # 主結果＋SpecifiedPairsExcluded PNG
    SetQuantification/           # 主結果PNG・統計CSV
      SpecifiedPairsExcluded/    # 追加版Set別・全Set統合PNG・統計CSV
    Topography/{Individual,GrandAverage}/
  VRohtoPremium/
  Sub/
    tables/{Set1Baseline,GrandAverage,SetQuantification,Topography}/
    logs/
```

- `{A,B}` は2つの独立フォルダを示す省略表記。被験者別フォルダは作らない。
- 図フォルダはPNGだけ（定量化の統計CSVは例外）。補助表・manifest・実行記録はSubへ。
- 個人命名：`ID<初回>-<2回目>_<stem>_Individual.png`、未平滑版は `_Unsmoothed_BeforeThresholdExclusion`／`_Unsmoothed_AfterThresholdExclusion` を追加。
- 群図：`<stem>_GrandAverage_<製品群>.png`。定量化：`<stem>_SetQuantification_<製品群>.png`／`<stem>_AllSetsQuantification_<製品群>.png`。
- 頭皮図：`ID<初回>-<2回目>_<stem>_Topography.png`／`<stem>_Topography_GrandAverage_<製品群>.png`。
- 統計CSV：`<stem>_SetQuantification_Statistics_<製品群>.csv` 等、No1と同じ用途別接尾辞。製品群文字列はCCube／VRohtoPremium。
- sub追加Grand-averageは同じGrandAverage直下に `<stem>_GrandAverage_<製品群>_SpecifiedPairsExcluded.png`。追加定量化PNG・統計CSVは `SetQuantification/SpecifiedPairsExcluded/` へ置き、ファイル名にも `_SpecifiedPairsExcluded` を付ける。補助CSVも対応するSub/tables内で同じsuffixを用い、主結果を上書きしない。
- 帯域変更後は現行ルートのPSD・PNG・数値表を新帯域の成果物へ置換する。旧帯域の図を現行結果に残さず、旧版の方法・実績はhistoryへ分離する。移行・再計算・置換の対象と完了はSub/logsで監査し、既存No1–9や原EEGへ範囲を広げない。
- No10_sub時間変化の正値は自身のSet 1より高い方向。topographyの正値はEye Dropの値／変化率がControlより高い方向で、効果の良否を自動的に意味しない。

## 11. 記録と完了条件

- Notion Phase 4親はNo10とNo10_subの概要、子ページは方法・図・保存構造。準備状況と解析結果を分ける。被験者別結果表・日次ログは新設しない。
- GitHubは本書をNo10本体＋subの唯一の現行仕様とし、意思決定過程はhistoryへ。仕様変更はNotionと同時更新する。
- 実行時の対象範囲・入力hash・N・mask件数・警告・失敗・成果物一覧・検証は各NoのSub/logs・Sub/tablesへ。観察と解釈は分ける。
- 今回は明示的な開始指示に基づきNo10・No10_subの実装と全対象実行を行う。既存No1–9の成果物は変更しない。本番結果が未確認の段階で完了を記載せず、実行後に方法とは分離して実績を記録する。

実装・実行時には少なくとも以下を検証する。

1. 全対象manifestのID・条件・製品・既知欠測とPhase 1入力が一致する。
2. fs、µV変換、3 bin（8・9・10 Hz）、全32ch、padding・端点・1秒移動・progressが独立計算と一致する。旧帯域cacheの誤使用を拒否する。
3. Phase 1 mask→帯域固有log3SD、Setを跨ぐ閾値と跨がない平滑化、保存後のmask再現が一致する。
4. subのID/ch別baseline、Set 1平均0、paired欠測、全Set統合、統計family・差方向が一致する。
5. 個人・群topography数値がch別未平滑定量差と一致する。Fz値も同じ定量値と照合する。
6. 全図の命名・読込・成果物場所を確認し、全群図と代表個人図でArial、色、ラベル、軸比率、統計anchorを目視する。目視対象と全件機械確認を区別して記録する。
7. 既存No1–9と原本が不変。実行後のみ結果・実数N・検証成否を追記する。
8. sub追加版で指定集合だけを両条件・全Setから除き、主結果・個人・topographyを保持したことを照合する。追加の平均／SEM・Set／全Set統合値・対応あり統計・3補正・N・縦軸を独立検証し、実画像も確認する。

## 12. 現行8–10 Hzの実行結果・検証

### 12.1 実行・保存

2026-11-12、実装commit `42e182eae82f76e082ddd10d9aa24bdea2dfe005` で再実行した。No10は18:40〜18:48 JST、subは18:48〜18:49、独立監査は18:49に完了し、全工程の終了コードは0。計算・数値監査consoleにwarning／errorの該当行はなかった。

| 項目 | 現行8–10 Hzの確認結果 |
|---|---|
| 条件対応 | Googleの被験者・当日記録と40ペア・80セッションを照合、製品別20ペアずつ、齟齬0 |
| No10 cache | 全32chの80 HDF5をPhase 1入力から再計算。476実在Set、既知欠測4 Set。全80件のhashが旧cacheから更新 |
| No10 PNG | 168枚＝個人時間変化120枚（平滑化・未平滑閾値前・未平滑閾値後各40）、個人topography40枚、群図8枚 |
| No10_sub主結果 | baseline適格39ペア（Cキューブ20、Vプレ19）。個人時間変化39枚、個人topography39枚、群図8枚 |
| No10_sub追加版 | Cキューブ19・Vプレ17ペア。各製品でGrand-average・Set別・全Set統合の3枚、計6枚を追加 |
| PNG合計 | No10 168枚＋sub 92枚＝260枚。すべて現行帯域で再生成、旧帯域PNGは現行結果に残さない |
| 旧版の保存 | 旧CSV・JSON・LOG計30件を各Subの `history/Before8to10Hz_20261112/` へ保存し、コピーのhashを照合。旧実績は[履歴専用文書](history/Phase4_No10_旧帯域実行結果_20261112.md)へ分離 |

追加の指定ペア除外はsubの群時間変化・定量化だけに適用した。主結果の39ペア、個人図、topographyは保持し、大きな変化率を示す個人図も主結果から自動削除していない。帯域変更そのものでは、これらも8–10 Hzへ更新している。

### 12.2 対応のある有効N

Set別は定量化の両条件有限ペア数。全Set統合は対応する有効Setを持つペア数であり、全6 Set完備数ではない。Grand-averageのprogress点別Nは別途CSVに保存する。

| 解析・集合 | 製品 | Set 1→6のN | 全Set統合N |
|---|---|---|---:|
| No10主結果 | Cキューブ | 20・20・20・20・20・19 | 20 |
| No10主結果 | Vプレ | 19・19・20・19・20・20 | 20 |
| sub主結果 | Cキューブ | 20・20・20・20・20・19 | 20 |
| sub主結果 | Vプレ | 19・18・19・18・19・19 | 19 |
| sub指定ペア除外追加版 | Cキューブ | 19・19・19・19・19・19 | 19 |
| sub指定ペア除外追加版 | Vプレ | 17・16・17・16・17・17 | 17 |

subのSet 1はbaseline確認用で、t検定は行わない。指定対象そのものは[注意事項](解析上の注意事項.md#phase-4-no10_sub指定ペア除外追加版2026-11-12確定)を正本とする。

### 12.3 maskと検証

- 全315,166 PSD窓のうち、Phase 1 maskによる除外は20,568窓（6.526%）。Phase 1 mask後の有限・正値9,427,136 window×ch要素のうち、帯域固有log3SDによる追加除外は16,472要素（0.1747%）。前者は窓、後者は窓×chであり、被験者除外率や厳密な実時間割合ではない。
- 全80 cacheのversion・8/9/10 Hz・入力・条件対応・時刻・maskを検証。各実在Setの先頭／中央／末尾、計1,428窓×32chを元EEGから独立SciPy Welchで再計算し、保存PSDとmaskを照合した（PSD許容差 `rtol=2e-6, atol=1e-7`）。元EEG全窓の二重計算ではない。
- 保存cacheからbaseline、未平滑定量値、平均／SEM、対応ありt検定、3種補正、topographyを独立再構成し、29数値CSVを照合（`rtol=atol=1e-8`）。baselineは2,496行、追加版の採否表39行も照合した。
- 本体／sub×製品の4群で、群topographyの全32ch共通Nとch別Nの差は0。既定の全ch有限判定による追加のN減少はなかった。
- 全333テストとRuffは合格。全260 PNGの名前集合・読込・再生成を検証した。
- 目視は**全群図22枚＋代表個人図4枚＝26枚**。既知欠測、未平滑閾値前／後、指定除外ペアの個人図保持も確認。Arial、軸・単位、配色、凡例、Set・統計文字、切れや重なりに修正必須の問題はなかった。全260枚を目視したという意味ではない。Arialの解決先は `/System/Library/Fonts/Supplemental/Arial.ttf`。
- 保護対象（既存No1–9の結果と処理済みデータ）1,977件のpath・size・mtime_nsは実行前後で一致。別監査でも既存結果1,410ファイルの更新時刻に今回実行以降の変更はなかった。全保護ファイルの内容hash照合とは区別する。

### 12.4 観察結果と解釈の限界

対応あり・両側t検定の未補正p<0.05は、sub主結果のCキューブSet 4だけだった（N=20、Eye Drop−Control平均差−37.836 percentage points、t=−2.199、p=0.04049）。このSetはBonferroni／Holm p=0.20245、BH-FDR p=0.17211で、補正後は有意でない。指定ペア除外追加版では同SetがN=19、平均差−28.826 percentage points、未補正p=0.07854となった。他のSet比較と全Set統合は未補正でもp≥0.05。いずれの集合でも補正後p<0.05のSetはなかった。

| 全Set統合の未補正p | Cキューブ | Vプレ |
|---|---:|---:|
| No10主結果 | 0.1377 | 0.8459 |
| sub主結果 | 0.0703 | 0.3562 |
| sub指定ペア除外追加版 | 0.1353 | 0.6034 |

指定ペア除外は変更前の所見に基づく事後・探索的分析で、ノイズを確定した除外でも、Vプレの効果を証明する解析でもない。有意でない結果も効果不存在の証明ではない。大きな値、波形の形状、生理的解釈の妥当性は数値実装の一致とは別の問題として扱う。

### 12.5 証跡と確認範囲

- No10 `Sub/logs/BandRevision_20261112_8to10Hz.json`：入力・条件照合、実行コマンド／commit／時刻、旧版保存、cache更新、PNG再生成、保護対象。
- No10 `Sub/logs/ValidationSummary_20261112_8to10Hz.json`：独立数値監査、N、各CSV照合、画像読込、元EEG抜粋検証。
- sub `Sub/logs/No10_sub_FzLowAlphaChange_RunSummary.json`／`No10_sub_FzLowAlphaChange_SpecifiedPairsExcluded_RunSummary.json`：主結果と追加版を分離した対象・設定・出力記録。
- 数値正本は各 `Sub/tables/` と定量化フォルダの統計CSV。図や丸めた本文から数値を再取得しない。
- 保存・読戻しは許可済みOneDriveローカル同期先で確認した。サーバー側への同期完了は独立確認していない。Git公開と最終引渡しの確認は第9.3節の締め工程で記録する。
