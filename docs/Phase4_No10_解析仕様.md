# Phase 4 No10・No10_sub：Fz low-alpha解析仕様

更新日：2026-11-12。**設計確定・空フォルダ準備段階。スクリプト未実装、解析未実行、結果なし。**

本書は現行仕様。議論・準備の経緯は[設計決定記録](history/Phase4_No10_設計決定記録_20261112.md)へ分離する。既存No1–9の仕様・コード・結果は変更しない。

対応Notion：[No10詳細・共通設計](https://app.notion.com/p/416161f2809781738442d82aa8c4357f)、[No10_sub詳細](https://app.notion.com/p/416161f2809781a7bc00ebe3c680f340)、[設計決定・準備記録](https://app.notion.com/p/416161f2809781839c12d8d54b6af35e)。親はPhase 4ページ。

## 1. 目的・解析単位

| 項目 | No10 | No10_sub |
|---|---|---|
| 解析名 | Fz low-alpha絶対PSD | Fz low-alpha PSD Change |
| 正式stem | `No10_FzLowAlpha` | `No10_sub_FzLowAlphaChange` |
| 帯域 | **8、9、10、11 Hzの4 binを含む** | 同左 |
| 代表ch | **Fz** | **Fz** |
| 値 | 帯域内PSDの算術平均、µV²/Hz | 各ID・ch自身のSet 1平均に対する変化率、% |
| 比較 | 製品群別に同じ被験者のEye DropとControl | 同左 |
| 出力 | 個人時間変化、Grand-average、Set別・全Set統合定量化、個人・群topography | 同左 |

low-alpha 8–11 Hzは今回の操作的定義であり、普遍的な帯域定義と断定しない。IAFや個人別帯域の推定はしない。No10_add／TFMは今回の範囲外。

旧IAF No10は既にNo9へ改番済み。**新No10はlow-alphaパワーであり、旧No10のFz IAFではない。** 現行IAFは[No8・No9仕様](Phase4_No8_No9_共有用解析仕様.md)のみ。

## 2. 引き継ぐ仕様と参照元

- 最新の[No1統合仕様](Phase4_No1_共有用解析仕様.md)の本体・subを基準とし、[No2](Phase4_No2_共有用解析仕様.md)・[No3](Phase4_No3_共有用解析仕様.md)の帯域変更方式と整合させる。
- 変更点は帯域、代表ch、解析名・保存先・cache識別子、点眼色。計算・欠測・統計・描画の基本構造は維持する。
- No1の一時的な95% y軸、廃止済み30点平滑化足切り、固定y軸、探索用図は継承しない。
- No1–3のtopography感度分析、No2のOz/Pz補助除外、No4–7の指定ペア除外、No8–9のIAF選別は継承しない。
- 不明点は現行No1–3の正本と実装を照合し、矛盾があれば勝手に選ばず停止する。過去の実績や除外率をNo10の結果として転記しない。

## 3. 入力・対象・欠測

- Phase 1確定済み `IDxxx_SetN_brain_activity.h5` を読み取り専用入力とする。`DataKind=brain_activity_eeg`、32chの名前・順、Set番号、時刻、単位、fsを検証する。
- `signal/data` はsample×32chのV。float64でµVへ変換（×10⁶）してからPSD計算する。**PSD計算・保存は全32ch**、Fzだけを時間変化と定量化の代表に使う。
- 実測・保存fsが256 Hzであることを検証する。256でない入力を黙って256として扱わない。追加のfilter、再参照、Laplacian、ch補間は行わない。
- 許可済み被験者リストとPhase 1入力対応から40ペア・80セッション、2製品各20ペアを基準にする。IDの100/200番台だけでEye Dropを決めない。ペア、製品、点眼回、セッション条件のmanifestを照合・保存する。
- 既知の4欠測Set、共通対象外、分割記録の正本は[解析上の注意事項](解析上の注意事項.md)。本書に個人ID一覧を重複保存しない。
- 個人時間変化：欠測条件のSetだけ線を描かず、対応する条件の実在Setは描く。
- Grand-average・Set定量化・topography：片条件が既知欠測なら**同じペア・同じSetを両条件から外す**。全Set統合値も両条件共通の利用可能Setを使用する。
- No10はSet 1欠測だけで被験者全体を除かない。No10_subはSet 1 baselineが必要なので、既知Set 1欠測ペアは全体を対象外とする（現行対応なら39ペアが予定母集団）。実使用Nは実行時に別途確認する。
- 想定外の入力不足、ch不一致、非有限入力、計算不能baselineはpreflightで停止・記録し、個人別の独自除外や補完を追加しない。

## 4. No10：PSD計算と品質mask

### 4.1 1秒窓・1秒移動

No1–3と同じ `mne.time_frequency.psd_array_welch` を使う。以下は仕様であり、この段階では実装・実行しない。

| 引数・項目 | 固定値 |
|---|---|
| 入力 | 1秒分のµV信号、末尾次元が時間。全32ch |
| `sfreq` | 256.0 Hz |
| `fmin`, `fmax` | **8.0, 11.0 Hz** |
| `n_fft`, `n_per_seg` | 256, 256 |
| `n_overlap` | 0 |
| `window` | `hann` |
| `average`, `output` | `mean`, `power` |
| `remove_dc`, `verbose` | True, False |
| 外側の移動幅 | 256 sample＝1秒 |
| 周波数bin確認 | `[8., 9., 10., 11.]` と完全一致 |
| 帯域値 | 4 binを算術平均。積分・総和・dB化はしない |

1秒窓内は1 Welch segment。複数時間窓のPSDを後で平均する処理と、Welch内部の平均は混同しない。

- Setの信号両端に128 sampleずつreflect padding。休憩時間のEEGは入力しない。
- 窓中心sampleは `0, 256, ...`。末尾sample `n−1` が含まれなければ追加するため、最後だけ間隔が1秒未満になる場合がある。
- 相対時刻・OriginalTimestampは中心sampleの値を保持する。
- `set_progress = center / (n−1) × 100`、`global_progress = (Set−1) × 100 + set_progress`。
- 計算は実時間・元sampleで行い、progressは表示・被験者間位置合わせ用。異なるchも同じ時刻・progress列を使う。

### 4.2 区間除外とlog3SD

1. Phase 1 `ica_training_excluded_mask` と1秒PSD窓の重なり率を求める。maskにも同じreflectを適用する。
2. 重なり率 **1%以上** の窓は解析時に全32chをNaNにする。時刻を詰めない。
3. その後、**セッションID×chごと**に利用可能な全Setの有限・正の未平滑8–11 Hz平均PSDをまとめる。
4. `x=log10(PSD)`、`T=mean(x)+3×SD(x, ddof=1)`。`x>T` の窓だけ、そのchでNaNにする。Set別閾値、下側閾値、条件間で共通の閾値は使わない。
5. 元PSDを上書きせず、log平均・SD・T・10^T・mask・Set/ch別の有効数／除外数／率を保持する。再描画でも両maskを必ず適用する。

No1のthetaやNo2の8–15 Hzで算出した閾値・maskを転用しない。ICA学習用 `ica_channel_excluded_mask` は監査用に保存するが、PSDでのch除外には使わず32chを保持する。新たな低PSD足切り、被験者除外、空間外れ値除外は設けない。

### 4.3 時間変化と定量化の分岐

- 時間変化：両mask適用後 → **Set内・実時間60秒中心化単純移動平均** → progress表示。
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
- 既知欠測は両条件対応で除外。Set/chごとのNを保存する。補足分析の事後的ch除外は流用しない。

## 7. 配色（No10・No10_sub共通）

| 条件・製品 | 時間変化・Grand-average線 | 定量化バー・点 |
|---|---|---|
| Control | `#402B5D` | `#66547D` |
| Eye Drop (C Cube) | `#637B22` | `#8B9D58` |
| Eye Drop (V Rohto Premium) | `#91A63D` | `#ACBC6E` |

既存のorange／pink／yellow、blue／cyan、青緑、赤、brown系と区別するオリーブ系。4つの新規hexは既存解析設定と重複させない。Controlは意図的な共通色。定量化は対応する線色を淡くし、同じ解析・製品の関係を保持する。実装後の描画で識別性を確認する。topographyは条件色ではなく共通の発散色 `RdBu_r`。

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
- 目盛は3–6個、候補1,2,2.5,5×10ⁿから設定。No10は横グリッドなし、subだけ0の薄い灰色線。

### 8.2 定量化

- Set別34×9 inch・6パネル横一列・共通y軸、全パネルにy目盛数字。全Set統合7.5×9 inch・1パネル。
- 左Eye Drop、右Control。中心±.32、bar幅.42、x範囲±.90。bar alpha=.82、枠#222222・1 pt。
- 点サイズ150、alpha=.68、白枠1.2 pt。対応線#777777・1.2 pt・alpha=.34。
- jitter±.055、ペア内で同じoffset、seed=4000+Set番号、全Set統合7001。
- 条件名22 pt、Eye Drop直下の括弧付き製品名18 pt、軸名30 pt、目盛23 pt、Set名26 pt。
- Set別余白L .06／R .995／T .94／B .25／wspace .24。全Set版L .20／R .98／T .94／B .25。
- ブラケット黒2.2 pt、cap=axes高さ.018。`n.s.`26 pt normal、アスタリスク42 pt bold、すべてArial。
- p<.05=`*`、p<.01=`**`、p<.001=`***`、それ以外=`n.s.`。Set 1基準検定不能をn.s.と偽装せずBaseline表示。

| 位置・軸 | No10 | No10_sub |
|---|---|---|
| M | 表示する個人定量値の最大値 | max(個人最大値, 2×abs(min(個人最小値,0))/1.54, 1) |
| 黒線 | 1.13M | 1.15M |
| アスタリスク | 中心1.17M | **bottom anchor 1.08M** |
| n.s. | 中心1.18M | **bottom anchor 1.20M** |
| Set名 | 中心1.29M | 中心1.42M |
| 上限／下限 | 1.37M／0 | 1.54M／−上限÷2 |

subの文字位置はNo1_sub〜No3_sub確定実装のanchorをそのまま継承し、中心指定へ読み替えない。y目盛3–6個、0を含む切りのよい等間隔。全Set版の表示名はAll Sets。

### 8.3 Topography

- 36×6.5 inch、6 Set横一列。各図内の全Setで同じ対称カラースケール。個人ごと・製品群ごとには可変。
- 全Set・chの最大絶対差をMとし、V≥M/.85を満たす最小の切りのよい値。候補1,1.5,2,2.5,3,4,5,6,8,10×10ⁿ。範囲−V〜+V、目盛−V,0,+V。
- MNE montage=`colin27_1020`、sphere=(0,0,0,.095)、`plot_topomap`：cmap=RdBu_r、sensors=k.、名前なし、contours=0、extrapolate=head、image_interp=cubic、border=mean、res=256。
- 頭円・鼻4 pt、耳なし、電極点8、Set名24 pt／pad16、Missing表示22 pt。空間補間は描画用で数値平均・統計を変更しない。
- colorbar fraction=.08、pad=.10、aspect=12、数字24 pt。
- No10ラベル `Difference in PSD (µV²/Hz)` は28 pt、subラベル `Difference in PSD Change, %` は20 pt。Δへ省略しない。
- chごとの有意記号は追加しない。sub Set 1は0のBaseline map。

## 9. スクリプト・中間データの設計

### 9.1 スクリプト（予定・まだ作らない）

```text
解析プログラム/Phase4_脳波解析/
  Phase4_No10_FzLowAlpha.py
  Phase4_No10_sub_FzLowAlphaChange.py
```

No2／No3と同じ `phase4_band_variant_config.py` 経由で検証済みNo1／No1_sub engineを使用する設計。全被験者は同一コード・設定でループ処理する。No10固有設定の変更が他Noのdefault・出力先を変えないことをテストする。

No10はPSD計算・保存、cache検証、個人図、Grand-average、定量化、topographyを独立実行可能にする。No10_subはcache読込から開始し、各出力工程を分離する。未実装なので、存在しないCLIの実行コマンドは掲載しない。

### 9.2 キャッシュ（保存先準備のみ）

```text
/Users/aoiseki/Desktop/SandBox_ロート案件（データ）/解析に必要なデータたち/
  Phase4_脳波解析/No10_FzLowAlpha/PSDTimeSeries/
    Pair<初回ID>-<2回目ID>_01_ID<初回ID>_FzLowAlpha_AllChannelsPSD.h5
    Pair<初回ID>-<2回目ID>_02_ID<2回目ID>_FzLowAlpha_AllChannelsPSD.h5
```

- No1と同じHDF5構造（[No1仕様第7節](Phase4_No1_共有用解析仕様.md#7-psdキャッシュhdf5)）。未平滑・mask前の `sets/SetN/psd_band_mean` が原値正本。32ch、float32、窓×ch。
- `log3sd_outlier_mask`、`ica_training_mask_fraction`、各中心時刻（float64）、Set/global progress、中心sample、ch名、ch mask、Set availability、QC閾値・数を保存する。
- attrsはNo10専用schema/version、帯域8–11・実bin、fs、単位、ID/ペア/条件/製品、PSDパラメータ、mask方針を明示。gzip4・shuffle、設定hash・入力パス/サイズ/mtimeも記録する。
- No2の8–15 Hz帯域平均cacheから8–11 Hzを逆算できない。No10はPhase 1から新規計算する。FzのみのTFM cacheやIAFの10秒窓・0.1 Hz PSDも使用しない。
- 読み戻してshape・時刻・progress・ch順・設定・mask再現を検証。別帯域・別設定cacheなら停止する。図だけの調整でPSDを再計算しない。
- No10_sub用のローカルデータフォルダは作らない。

## 10. OneDrive構造・結果の見方

親は許可済み `実験本番_本解析/Phase4_脳波解析/`。その下に既存Noと並列に追加する。**現在は空フォルダだけ。以下のPNG／CSVは将来の出力予定。**

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
    GrandAverage/
    SetQuantification/
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
- No10_sub時間変化の正値は自身のSet 1より高い方向。topographyの正値はEye Dropの値／変化率がControlより高い方向で、効果の良否を自動的に意味しない。

## 11. 記録と今後の完了条件

- Notion Phase 4親はNo10とNo10_subの概要、子ページは方法・図・保存構造。準備状況と解析結果を分ける。被験者別結果表・日次ログは新設しない。
- GitHubは本書をNo10本体＋subの唯一の現行仕様とし、意思決定過程はhistoryへ。仕様変更はNotionと同時更新する。
- 実行時の対象範囲・入力hash・N・mask件数・警告・失敗・成果物一覧・検証は各NoのSub/logs・Sub/tablesへ。観察と解釈は分ける。
- 今回の範囲は文書と空フォルダ。解析結果の推測、スクリプト作成、cache作成、figure描画、既存成果物の変更をしない。

将来の実装・実行時には少なくとも以下を検証する。

1. 全対象manifestのID・条件・製品・既知欠測とPhase 1入力が一致する。
2. fs、µV変換、4 bin、全32ch、padding・端点・1秒移動・progressが独立計算と一致する。
3. Phase 1 mask→帯域固有log3SD、Setを跨ぐ閾値と跨がない平滑化、保存後のmask再現が一致する。
4. subのID/ch別baseline、Set 1平均0、paired欠測、全Set統合、統計family・差方向が一致する。
5. 個人・群topography数値がch別未平滑定量差と一致する。Fz値も同じ定量値と照合する。
6. 全図のArial、色、ラベル、軸比率、統計anchor、成果物場所を実画像で確認する。
7. 既存No1–9と原本が不変。実行後のみ結果・実数N・検証成否を追記する。
