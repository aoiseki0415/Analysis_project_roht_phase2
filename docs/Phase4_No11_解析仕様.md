# Phase 4 No11・No11_sub：Pz low-alpha解析仕様

更新日：2026-11-13。**現行定義はPz・8–10 Hz（8・9・10 Hzを含む）。No11は絶対PSD、No11_subは各条件自身のSet 1からの変化率。** 本書は方法・Figure・保存構造の現行正本。実行結果は第11節、意思決定の経緯は[専用履歴](history/Phase4_No11_意思決定.md)へ分離する。

旧IAF No11（Fz前後半）は廃止済みの別解析であり、その方法・cache・結果・選別を今回へ流用しない。現行IAFはNo8=Pz／No9=Fz。本書のNo11はIAFではなく**low-alphaの帯域平均パワー**を扱う。

## 1. 目的・今回の範囲

| 項目 | No11 | No11_sub |
|---|---|---|
| 正式stem | `No11_PzLowAlpha` | `No11_sub_PzLowAlphaChange` |
| 代表ch | **Pz** | **Pz** |
| 帯域 | **8、9、10 Hzの3 bin** | 同左 |
| 値 | 帯域平均PSD、µV²/Hz | Set 1平均に対するPSD Change、% |
| 比較 | 製品群別のEye Drop対Control、被験者内対応 | 同左 |
| 出力 | 個人時間変化、Grand-average、Set別・全Set統合定量化 | 同左 |
| 元データ | 検証済みNo10全32ch・8–10 Hz PSD cache | 同じcache |

- 最新の[No10・No10_sub仕様](Phase4_No10_解析仕様.md)の主要解析を継承し、代表chをFzからPzへ変更する。元となる計算・Figure規則は[No1統合仕様](Phase4_No1_共有用解析仕様.md)と同じ。
- 新たな被験者除外・定性的選別は行わない。No10_subの`SpecifiedPairsExcluded`、topography感度分析、IAF選別、他Noの指定除外は継承しない。
- **Topographyは作らない。** 帯域・全32ch入力・条件差定義はNo10と同じで、代表chを変えても全頭mapは重複するため。TFM／No11_addも今回の範囲外。
- No10のcache・Figure・表・除外規則は変更しない。No10_subの除外基準に関する未合意の検討・シミュレーションとも独立して扱う。
- 8–10 Hzは本プロジェクトの操作的なlow-alpha定義。個人別alpha帯やIAFは推定しない。

## 2. 対象・条件対応・欠測

- 基本対象は40被験者ペア・80セッション、Cキューブ／Vロートプレミアム各20ペア。共通対象外、分割EEG、欠測Setの正本は[解析上の注意事項](解析上の注意事項.md)。本書へ個別ID一覧を重複転記しない。
- 実行前にNotionの被験者・セッション対応表と、許可済みGoogle共有資料の匿名ID・製品・点眼回を確認し、manifestおよびcache属性と照合する。100番台／200番台だけでEye Dropを決めない。
- manifestは`first_session_id,second_session_id,drops_session_id,product`を必須列とする。氏名等は取得・保存せず、manifestはOneDriveのSubに保存する。
- 個人時間変化：既知欠測は**欠測側のSetだけ**を非表示。対応条件の実在Setは表示する。
- Grand-average・Set定量化：片条件が既知欠測なら、同じペア・同じSetを**両条件とも**欠測にする。全Set統合も両条件共通の利用可能Setから求める。
- No11はSet 1欠測だけでペア全体を除かない。No11_subはSet 1 baselineが必要なため、既知のSet 1欠測ペアを解析全体から外す。事前想定はNo11 40ペア、sub 39ペアであり、実有効Nは結果表で確認する。
- 想定外のcache不足、条件不一致、Pz欠落、非有限／非正のbaselineは停止・記録する。個人ごとに独自補完・閾値変更・無断除外を行わない。

## 3. 入力cacheと計算の由来

### 3.1 No10 cacheを再利用する理由・検証

No10 cacheの名前にFzが含まれていても、`psd_band_mean`には**全32ch**が保存されている。帯域・1秒窓・mask・時刻はNo11と同一であり、Pz列が既に存在するため、Welchの再計算や同一PSDの複製は不要。

```text
/Users/aoiseki/Desktop/SandBox_ロート案件（データ）/解析に必要なデータたち/
  Phase4_脳波解析/No10_FzLowAlpha/PSDTimeSeries/
    Pair<初回ID>-<2回目ID>_01_ID<初回ID>_FzLowAlpha_AllChannelsPSD.h5
    Pair<初回ID>-<2回目ID>_02_ID<2回目ID>_FzLowAlpha_AllChannelsPSD.h5
```

- 全80 cacheを読み取り専用で使う。No11／No11_subのローカル派生cacheや空のデータフォルダは作らない。
- 読み込み時はNo10のcache guardで、8–10 Hz・実bin`[8,9,10]`、fs、ch名／順、shape、時刻、progress、mask、入力fingerprint、ID／ペア／条件／製品、configuration hashを検証する。
- **元cacheのhashはNo10の生成設定に対するもの。** 生成時のanalysis stem・focus channel・cache configuration versionを含むNo10の設定として照合する。No11/Pzへattrsを書き換えたり、No11のhashを要求して不必要にPSDを再計算したりしない。
- 検証後、`channel_names`の**Pzの名前**から列indexを取得する。Fz列や固定indexの流用を禁止する。No11の解析設定・Pz選択・元cache hashは出力側の記録として保持する。
- 変更前8–11 Hz、No2の8–15 Hz平均、FzだけのTFM、10秒窓IAF用PSDは代用しない。元入力の更新・hash不一致があれば黙って読み進めない。

### 3.2 元PSDの計算仕様（継承・今回は再計算しない）

Phase 1の`brain_activity_eeg`、sample×32chのVをfloat64のµVへ変換（×10⁶）。fs=256 Hzを検証して使用する。追加filter、再参照、Laplacian、ch補間は行わない。

| 引数・項目 | 固定値 |
|---|---|
| 関数 | `mne.time_frequency.psd_array_welch` |
| 入力 | µV、1秒分・全32ch、末尾次元が時間 |
| `sfreq` | 256.0 Hz |
| `fmin`, `fmax` | 8.0, 10.0 Hz |
| `n_fft`, `n_per_seg` | 256, 256 |
| `n_overlap` | 0 |
| `window` | `hann` |
| `average`, `output` | `mean`, `power` |
| `remove_dc`, `verbose` | True, False |
| 外側移動幅 | 256 sample＝1秒 |
| 保存帯域値 | 8・9・10 Hzの算術平均、µV²/Hz |

積分・周波数総和・dB変換はしない。1秒窓には1 Welch segmentが含まれ、後の時間平均とは別処理。

- 各Setの前後を128 sampleずつreflect padding。休憩中のEEGは使わない。
- 窓中心は`0,256,…`。末尾sample `n−1`が含まれなければ追加するため、最後の間隔だけ1秒未満になることがある。
- 相対秒・OriginalTimestampは元の中心sampleから保存する。
- `set_progress=center/(n−1)×100`、`global_progress=(Set−1)×100+set_progress`。
- 実時間で計算してから表示・個人間の位置合わせにprogressを使用する。Set長を揃えるために元EEGを圧縮してPSDを計算しない。

### 3.3 maskの適用

1. 元PSDへ、Phase 1の`ica_training_excluded_mask`と**1%以上**重なる1秒窓のmaskを適用する。全32chをNaNとし、時間を詰めない。maskにも同じreflect paddingを用いた重なり率が保存されている。
2. その後、セッションID×chごとに、利用可能な全Setの有限・正の未平滑8–10 Hz平均PSDをまとめる。
3. `x=log10(PSD)`、`T=mean(x)+3×SD(x,ddof=1)`。`x>T`の上側窓だけを当該chでNaNにする。保存済みのこのmaskを必ず再適用する。
4. 閾値はSet別・条件横断では作らない。下側除外、低PSD足切り、新しい空間QC／被験者除外を加えない。

元PSD、log平均・SD・閾値、線形閾値、mask、Set/ch別有効数・除外数・率はNo10 cacheのまま保持する。ICA学習ch除外maskは監査情報であり、PSD列の削除・NaN化に使わない。Pzにも他chと同じ保存済み品質処理を適用する。

## 4. 時間変化・Set 1変化率

### 4.1 No11の3種類の個人表示

| 表示 | 数値処理 |
|---|---|
| 主図 | Phase 1 mask→8–10 Hz log3SD mask→Set内60秒平滑化 |
| `Unsmoothed/BeforeThresholdExclusion` | Phase 1 mask後・log3SD前、未平滑 |
| `Unsmoothed/AfterThresholdExclusion` | 両mask後、未平滑 |

時間変化は`pd.Series(...).rolling(window=60,center=True,min_periods=1).mean()`を用いる。1秒刻みの**60点**を「60秒平滑化」と呼ぶ。Set末尾の追加点も1点として等重みなので、厳密なtimestamp幅60秒とはわずかに異なる。No1–3／No10と同じ実装を維持する。

- 有限値が1点以上なら平均し、窓全体がNaNならNaN。30点以上などの追加足切りは設けない。
- Set境界をまたがない。端では利用可能範囲だけを平均する。NaNをゼロにせず、時間を前詰めしない。
- 平滑化後にprogressへ対応づける。progress幅で平滑化しない。
- 定量化は主図の平滑化後の値ではなく、**両mask後の未平滑PSD**を使う。

### 4.2 No11_sub

各セッションID・各chについて、両mask後の**Set 1全時間の有限な未平滑PSDの算術平均**を`B`として、

```text
PSD Change(t) = (PSD(t) / B − 1) × 100
```

とする。各条件自身のBを用い、対応条件・Fz・他被験者のBを流用しない。Bは有限かつ正であることを確認する。Pzを代表図・定量化に用いる。

- 個人時間変化は変化率へ変換した後、同じSet内60点中心化平均を適用する。主平滑化PNGだけを保存する。
- 定量化は未平滑変化率。Set 1平均が数値誤差内で0となることを検証する。
- Set 1も図・全Set統合に含める。Set 1を0にするために後続データへ追加補正しない。
- baseline、有限窓数、対象理由、元cache識別子、解析設定はOneDriveの補助CSV・ログに保存し、ローカルへ派生PSD Change cacheを作らない。

## 5. Grand-average・定量化・統計

### 5.1 Grand-average

1. 両mask後・60秒平滑化後の各条件・各SetのPz系列を、`np.linspace(0,100,100,endpoint=False)`の100点へNo1と同じ補間実装で対応づける。Set境界・既知欠測Setをまたいで補間しない。
2. 既知欠測Setを被験者内で両条件同時にNaN化する。
3. 製品群別・条件別に、各progress点の有限な被験者値を等重み平均する。
4. 平均・標本SD（ddof=1）・N・SEM=SD/√Nを保存する。N=1は平均のみでSD/SEMをNaNとする。

No11_subでは**個人別・条件別baseline変換を済ませてから**上記処理を行う。群平均PSDを群平均baselineで割る方式ではない。

### 5.2 被験者ごとの定量値

- **Set別**：当該Set全時間のPzの有限な未平滑PSD／PSD Changeを算術平均する。前半や末尾だけには限定しない。
- **全Set統合**：両条件共通の利用可能Setに属する有限な未平滑窓を連結して平均する。Set平均を単純再平均しない。subもSet 1を含む。
- バーは被験者間平均、点は被験者ごとの定量値、接続線は同じ被験者の2条件。片側欠測ペアは当該比較から両条件とも外す。
- 窓を独立した被験者として検定しない。Set別・全Set統合のNを別々に保存する。

### 5.3 統計

- 共通`paired_statistics.py`、`scipy.stats.ttest_rel`による**両側対応ありt検定**。差の向きはEye Drop−Control。
- N、t、df、未補正p、平均差、差の標本SD、95% CI、Cohen's dzを保存する。
- PNGは未補正p値を表示。CSVは未補正・Bonferroni・Holm・Benjamini–Hochberg FDRを併記する。
- 補正familyは解析・製品ごと。No11は6 Setの6検定、No11_subはSet 2–6の5検定。sub Set 1はBaseline表示で検定しない。
- 全Set統合は1検定で、多重比較補正を行わない。探索的な複数の比較であり、未補正の有意差だけを確証と扱わない。

## 6. 配色（No11・No11_sub共通）

| 条件・製品 | 時間変化・Grand-average | 定量化バー・点 |
|---|---|---|
| Eye Drop (C Cube) | **`#476975`** | **`#7B949D`** |
| Eye Drop (V Rohto Premium) | **`#789BA3`** | **`#A0B8BD`** |
| Control | `#402B5D` | `#66547D` |

利用者確認済みのブルーグレー系。Controlは他解析と共通の深紫、点眼2色はNo11固有。定量化は対応する線色を淡くして、解析・製品の対応を保つ。旧IAF No11の配色やNo10のオリーブ色は使用しない。

## 7. Figure仕様・読み方

共通：Arial、白背景、180 dpi、英語ラベル、上付き²。上・右spine非表示、軸線幅1.5 pt。別フォントへの無言fallbackを認めない。一般時間変化・統計図に参加者タイトルやN説明を追加しない。

### 7.1 個人時間変化・Grand-average

| 要素 | 設定 |
|---|---|
| サイズ | 24×8 inch |
| 横軸 | `Experimental Progress, %`、0–600、50刻み |
| Set区切り | 100–500、`#9E9E9E`破線、1.5 pt |
| Set名 | x=50,150,…,550、axes y=.96、22 pt |
| 軸名／目盛／凡例 | 28／20／20 pt |
| 線 | 3.0 pt、alpha=1、Controlを先に描く |
| 凡例 | 上中央、anchor=(.5,1.18)、2列、枠なし |
| 条件ラベル | `Eye Drop (C Cube)`／`Eye Drop (V Rohto Premium)`、`Control` |
| 余白 | left .08、right .99、top .78、bottom .20、tight保存 |
| No11縦軸 | `PSD (µV²/Hz)` |
| No11_sub縦軸 | `PSD Change, %` |
| 群図の帯 | 平均±SEM、線と同色alpha=.18、境界線なし |

各Setは100 progress幅。実時間の長さはSet・条件・被験者で異なる。横軸100はSet 1終了、200はSet 2終了、以降同様。個人図の2本線は同一被験者の条件比較、群図の2本線は製品群内の被験者間平均。

| 図 | 縦軸規則 |
|---|---|
| No11個人 | 下限0、描画する系列の最大M/.70以上の切りのよい上限 |
| No11群 | 下限0、最大mean+SEMをMとしてM/.75以上。2製品で大きい上限へ統一 |
| No11_sub個人 | 0中心・上下対称、描画系列の最大絶対値が各半軸の約70% |
| No11_sub群 | **平均線**の最大絶対値が各半軸の約70%、上下対称・2製品共通 |

- 未平滑図はその図自身の値を使って上限を決める。過去の95%例外や固定上限は使用しない。
- No11の目盛は3–6個。1,2,2.5,5×10ⁿを候補に5個へ近い間隔を選ぶ。
- subは既存対称軸関数の3–7個候補から5個へ近い間隔。候補1,2,2.5,4,5,10×10ⁿ。
- No11には横グリッドを加えない。subは0に薄い灰色線を引く。
- subの正値は自身のSet 1より増加、負値は減少。2条件の差の方向だけで点眼効果の良否を断定しない。

### 7.2 Set別・全Set統合定量化

- Set別34×9 inch、6独立パネル横一列、共通y軸、全パネルへy目盛数字。全Set統合7.5×9 inch、1パネル。
- 左Eye Drop、右Control。中心±.32、bar幅.42、x範囲±.90、bar alpha=.82、枠`#222222`・1 pt。
- 点サイズ150、alpha=.68、白枠1.2 pt。対応線`#777777`・1.2 pt・alpha=.34。
- jitter±.055、ペア内で同じoffset、seed=4000+Set番号、全Set統合7001。
- 条件名22 pt、Eye Drop直下の括弧付き製品名18 pt、軸名30 pt、目盛23 pt、Set名26 pt。
- Set別余白L .06／R .995／T .94／B .25／wspace .24、全Set版L .20／R .98／T .94／B .25。
- ブラケット黒2.2 pt、capはNo11でaxes高さ.018、subで.02。`n.s.`26 pt・normal。アスタリスク42 pt、No11はbold、subはnormal。すべてArial。
- p<.05=`*`、p<.01=`**`、p<.001=`***`、それ以外=`n.s.`。sub Set 1は`Baseline`であり、検定してn.s.となった意味ではない。

| 要素 | No11 | No11_sub |
|---|---|---|
| M | 表示する個人定量値の最大 | max(個人最大値, 2×abs(min(個人最小値,0))/1.54, 1) |
| 統計線 | 1.13M | 1.15M |
| アスタリスク | 中心1.17Mからaxes高さ.018だけ下へ光学補正 | **bottom anchor 1.08M** |
| n.s. | 中心1.18M | **bottom anchor 1.20M** |
| Set名 | 中心1.29M | 中心1.42M |
| 上限／下限 | 1.37M／0 | 1.54M／−上限÷2 |

No11の実アスタリスク中心は`1.17M−.018×(y上限−y下限)`。n.s.に光学補正は加えない。subのbottom anchorを中心指定へ変更せず、この光学補正も加えない。y目盛は3–6個、0を含む切りのよい等間隔。統合パネルは`All Sets`。縦軸の単位は時間変化と同じ。

## 8. スクリプト・再現

入口は以下。新しいNo11専用入口から既存の帯域／変化率engineを使用し、Pz・固有配色・No11出力先を設定する。No10の指定ペア感度処理を取り込まない。既存No1–10 engineの計算・既定出力を変更しない。

```text
解析プログラム/Phase4_脳波解析/
  Phase4_No11_PzLowAlpha.py
  Phase4_No11_sub_PzLowAlphaChange.py
```

全対象へ同一版・同一固定設定を適用する。cache読込・検証、個人図、群図・定量化を分離し、再描画のためのPSD再計算はしない。

- 絶対PSD：`Phase4_No11_PzLowAlpha.py`、版`20261113_pz_lowalpha_cached_v1`。
- 変化率：`Phase4_No11_sub_PzLowAlphaChange.py`、版`20261113_pz_lowalpha_change_cached_v1`。
- 共通adapter：`phase4_no11_cached_analysis.py`。元No10のcache検証namespaceとNo11描画namespaceを分離する。既存No10やNo1エンジンは編集しない。
- 各entrypointは`--manifest <40ペアCSV> --production-batch --all`で全対象を処理する。`--preflight-only`／`--individual-only`／`--group-outputs-only`で段階別に実行できる。subは`--set-quantification-only`にも対応。
- 全工程の管理：`run_phase4_no11.py --execute --manifest-source-audit <事前照合JSON>`。最新対応表の40ペア・80セッション一致を確認して、preflight→同じentrypointによる少人数試行→全員→独立数値監査を順に実行する。
- 独立監査：`validate_phase4_no11_outputs.py --manifest <CSV> --report <No11/Sub/logs内JSON>`。元EEGのWelch再計算は行わず、保存PSDからPzのmask・変換・統計・群値を再構成する。
- 最終確定：`run_phase4_no11.py --complete-verification --review-manifest <目視・文書・テスト確認JSON>`。全12群図・少なくとも4個人図の実画像確認、数値監査、文書読み戻し、GitHubのcommit SHA一致を確認して完了記録を保存する。
- runtimeはrepository `.venv/bin/python`。実行コマンド・時刻・console・cache SHA・出力hash・失敗履歴はNo11の`Sub/logs/`に保存する。少人数試行は全員処理で現行の群図・表を置き換え、試行のconsoleは過程記録として区別する。

## 9. 保存先・フォルダの読み方

親は許可済みOneDrive `実験本番_本解析/Phase4_脳波解析/`。次の2ルートを既存Noと並列に置く。

```text
No11_PzLowAlpha/
  CCube/                         # VRohtoPremium/も同じ
    Individual/                  # Pz絶対PSD・両mask後・60秒平滑化
      Unsmoothed/
        BeforeThresholdExclusion/ # Phase 1 mask後・log3SD前
        AfterThresholdExclusion/  # 両mask後、未平滑
    GrandAverage/                # 平均±SEM、PNGのみ
    SetQuantification/           # 6 Set別＋全Set統合PNG、統計CSV
  VRohtoPremium/
  Sub/
    tables/
      GrandAverage/
      Log3SDThresholdExclusion/
      SetQuantification/
    logs/
No11_sub_PzLowAlphaChange/
  CCube/                         # VRohtoPremium/も同じ
    Individual/                  # Set 1変化率・60秒平滑化
    GrandAverage/                # 平均±SEM、PNGのみ
    SetQuantification/           # 6 Set別＋全Set統合PNG、統計CSV
  VRohtoPremium/
  Sub/
    tables/
      Set1Baseline/
      GrandAverage/
      SetQuantification/
    logs/
```

- 被験者別の下位フォルダは作らず、個人PNGを並べる。定量化の統計CSV以外の補助表・manifest・ログはSubへ分離する。
- `Topography`、`SpecifiedPairsExcluded`、TFMのフォルダは作らない。
- 個人：`ID<初回>-<2回目>_<stem>_Individual.png`。未平滑は`_Unsmoothed_BeforeThresholdExclusion`／`_Unsmoothed_AfterThresholdExclusion`を追加する。
- 群：`<stem>_GrandAverage_<製品>.png`。
- 定量化：`<stem>_SetQuantification_<製品>.png`／`<stem>_AllSetsQuantification_<製品>.png`。
- 統計CSV・被験者値・群値は用途別suffixで区別する。製品文字列は`CCube`／`VRohtoPremium`。
- `SetQuantification_Statistics`は製品別PNGと同じフォルダ。`AllSetsQuantification_Statistics`と個人`Values`は`Sub/tables/SetQuantification/`、群値は`Sub/tables/GrandAverage/`に保存する（No10と同じ配置）。
- cache原値・maskはNo10ローカルHDF5が正本。No11のSubに元cacheパス・設定hash・検証結果を記録して再現性を確保し、PSDそのものを二重保存しない。

## 10. 記録・検証・完了条件

- NotionのPhase 4親にはNo11／No11_subの独立した概要見出し、各詳細ページには方法・図・保存構造を記載。結果は別節、過程は履歴ページ。日次ログや全被験者結果DBは新設しない。
- GitHubでは本書を両解析の現行統合仕様とし、意思決定・過程はhistoryへ。旧IAF No11と今回のNo11の情報を混在させない。
- 実行範囲、Git版、設定、入力hash、manifest、cache guard、N、mask件数、警告・失敗、成果物一覧・hash、独立数値照合、画像確認はOneDriveのSubに記録する。
- 観察結果と生理的解釈を分ける。値や形状が大きいだけでノイズを確定せず、今回の主要解析へ事後除外を追加しない。

完了前に次を確認する。

1. liveの対象・条件・製品とmanifest、全80 cacheの属性が一致。sourceが現行No10の8/9/10 Hz・全32chであり、Pzを選択している。
2. 元cache・No10成果物・他Noが不変。読込時に元のsource hash検証を通り、別帯域・別条件cacheを拒否する。
3. Phase 1 mask→帯域固有log3SD、Set内60点平均、progress格子、paired欠測を保存値から独立照合する。
4. Pzの未平滑Set値・全Set値、IDごとのbaseline、Set 1平均0、平均／SD／SEM／Nを独立再構成する。
5. 両側対応ありt検定・3補正・family・差の向きをCSVから再計算し、全Set統合とSet別を取り違えていない。
6. 全PNGの名前集合・読込・フォルダ構造を検査。全群図と代表個人図でArial、Pz、軸・単位、色、余白、統計表示を目視する。全件機械検査と抜粋目視を区別する。
7. No11の全40ペア、subのbaseline適格ペアの出力を同じスクリプトで完了。topography・未指示の除外版・旧IAF図が混入していない。
8. Notionを読み戻し、Gitの必要な検証・commit・push・remote一致を確認する。OneDriveローカル同期先への保存とサーバー側同期確認は区別する。

## 11. 実行結果・検証

### 11.1 2026-11-13実行実績

No11自身を上記2 entrypointで全員実行し、**No11 126 PNG、No11_sub 45 PNG、計171 PNG**を保存・読込確認。No11個人40ペア×3種類、sub個人39ペア、各解析の群Grand-average2枚・定量化4枚。80 cache・476実在Setを使用した。新たな被験者選別、topography・TFM、PSD再計算は行っていない。

| 解析／製品 | ペア数 | Set 1→6のpaired N | 全Set統合N | 全Set統合の未補正p |
|---|---:|---|---:|---:|
| No11／Cキューブ | 20 | 20,20,20,20,20,19 | 20 | 0.323629 |
| No11／Vプレ | 20 | 19,19,20,19,20,20 | 20 | 0.665220 |
| sub／Cキューブ | 20 | 20,20,20,20,20,19 | 20 | 0.129777 |
| sub／Vプレ | 19 | 19,18,19,18,19,19 | 19 | 0.570656 |

sub Set 1のNはbaseline有効人数であり、検定Nではない。欠測Setは規定どおり被験者内で対応させた。

### 11.2 観察結果と解釈の限界

- No11絶対PSD：両製品とも各Set・全Set統合の未補正pは.05以上。
- No11_sub：CキューブSet 3は未補正p=.014111、Set 4はp=.008600でEye Drop−Controlが負。Set 3の補正pはBonferroni=.070553、Holm=.056443、BH-FDR=.035277。Set 4は.043001、.043001、.035277。Vプレは全Setで未補正p≥.05。全Set統合も両製品でp≥.05。
- これは探索的な集団内条件比較の観察であり、製品間の差・ノイズの確定・効果の証明を意味しない。小さいbaselineによる変化率拡大や個人の大きな値は主結果に残している。
- sub群図の対称軸は既定の平均線基準で±200%。VプレEye DropはSet 4の5/600点でSEM上端が上限を超える（平均線最大139.26%、平均＋SEM最大239.03%）。数値表のSEMは切り詰めず保持し、平均線の軸規則を今回だけ変更しない。帯全体が常に表示される図ではない。

### 11.3 検証・証跡

- Google匿名共有シート／Notion／manifestの40ペア・80セッション：ID・製品・点眼回の不一致0。
- 独立監査：元cacheの設定・8/9/10 Hz・Pz列・両mask、60点平均、progress、baseline、Set／全Set値、対応ありt検定・3補正、群mean／SD／SEM／Nを再構成し、**17表**と一致。
- repository全テスト**360 passed**（No11関連17件を含む）、新規コード全件Ruff・Git差分checkに合格。最終完了時にも数値コードhash・全PNG hashを確認し、17表を再構成して監査後の改変がないことを検証する。
- 全171 PNGのパス集合・PNG読込・寸法を検査。Arial実体は`/System/Library/Fonts/Supplemental/Arial.ttf`。実画像確認は全12群図と代表個人8図の計20図で、全個人の信号品質を目視判定した意味ではない。
- 全80元cacheのSHA-256と、既存Phase 4成果物・処理データのファイルサイズ／更新時刻一覧が実行前後で不変。元EEGのWelch再計算監査は今回の対象外。
- 実行・検証の正本はNo11 `Sub/logs/No11_ExecutionAndVerification.json`、`No11_IndependentValidation.json`、`No11_DeliveryVerification.json`。後者には最終テスト、実画像、文書・Notion、Git remote SHA確認をまとめる。各解析RunSummaryにも元cacheと対象設定を分けて記録する。
- OneDriveは許可されたローカル同期フォルダへの保存・読戻しを確認。サーバー側の同期完了は独立検証していない。
