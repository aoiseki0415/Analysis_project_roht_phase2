# Phase 4 脳波解析仕様

## 1. 文書の位置づけ

本書は、Phase 4 No1本体の解析スクリプトを同じ入力から同じ計算・同じfigureとして再現するための現行正本です。会話や過去メモではなく、本書とNotionのPhase 4詳細ページを実装前に確認します。追加解析 `No1_add：Fz Time-Frequency Map` と `No1_sub：Fmθ PSD Change` は本書へ混在させず、[Phase 4 No1_add：Fz Time-Frequency Map仕様](Phase4_No1_add_FzTimeFrequencyMap仕様.md)および[Phase 4 No1_sub：Fmθ PSD Change仕様](Phase4_No1_sub_FmThetaChange仕様.md)を各解析の正本とします。

Phase 4は、使用した目薬で被験者をCキューブ群とVロートプレミアム群に分け、製品群ごとにEye DropとControlを被験者内比較します。

| No | 指標 | 代表ch | 周波数帯 | 主な解釈 | 状態 |
|---|---|---:|---:|---|---|
| No1 | frontal-midline theta（Fmθ） | Fz | 4–7 Hz（両端を含む） | 認知負荷・認知的努力 | 本書で実装仕様を確定 |
| No1_add | Fz Time-Frequency Map | Fz | 1–30 Hz（1 Hz刻み） | No1を補足する追加解析 | 別仕様書・独立スクリプトで本番40ペア完了 |
| No1_sub | Fmθ PSD Change | Fz（topographyは全32ch） | 4–7 Hz | Set 1基準の相対変化 | 別仕様書・独立スクリプトで本番39ペア完了 |
| No2／No2_sub／No2_add | occipital alpha／PSD Change／Oz TFM | Oz | 8–15 Hz／1–30 Hz | 不注意・マインドワンダリング | No1三解析と同構造で確定 |
| No3／No3_sub／No3_add | frontal delta／PSD Change／Fz TFM | Fz | 1–3 Hz／1–30 Hz | 疲労・眠気 | No1三解析と同構造で確定 |

代表chの文献根拠は[Phase 4 解析対象チャンネル文献調査](Phase4_解析対象チャンネル文献調査.md)を参照します。

## 2. No1の目的と成果物

No1は、Phase 1で作成した連続EEGから全32chの4–7 Hzパワー時間変化を一度だけ計算・保存し、その保存データから次を作成します。

1. Fzの個人時間変化figure
2. Fzの製品群別Grand-average figureと集計表
3. FzのSet別定量化figure、全Set統合figure、統計表
4. 全32chの `Eye Drop − Control` 差を示す個人topography
5. 製品群別Grand-average topography
6. 入力検査、計算、欠測、有効N、出力を追跡する表とログ

試行epochは作りません。Set内の連続EEGを解析します。

## 3. 対象者・条件対応・実行前検査

### 3.1 manifest

Phase 2・3と同じ非公開manifestを使用します。必須列は次の4列です。

```text
first_session_id,second_session_id,drops_session_id,product
```

- `drops_session_id` は2セッションのいずれかでなければなりません。
- Control IDは、2セッションのうち `drops_session_id` ではない方として決定します。
- 製品群と目薬実施回はGoogle Driveの匿名共有スプレッドシートと照合します。
- IDの100番台／200番台だけで条件を推測しません。
- 本番対象は40被験者ペア、80セッション、製品群各20名です。
- ID130・230を含めません。
- 被験者ペア重複、セッションID再利用、対象外ID混入をエラーにします。

### 3.2 入力HDF5の全件preflight

本計算前に、OneDriveへ出力せず全入力を検査します。

- ファイル名：`IDxxx_SetN_brain_activity.h5`
- `participant_id`、`set_number`が対象と一致
- `data_kind == brain_activity_eeg`
- `sampling_frequency_hz == 256`
- `signal_unit == V`
- `signal/data` が `n_samples × 32`
- `signal/channel_names` がPhase 1の固定32ch順と完全一致
- `time/relative_seconds`、`time/OriginalTimestamp`、`qc/ica_training_excluded_mask` の長さが `n_samples` と一致
- `qc/ica_channel_excluded_mask` が32要素
- EEG値が有限値であること
- 既知の欠測Set以外が存在し、既知の欠測Setが誤って存在しないこと

検査不合格時はPSDを計算せず、対象、ファイル、理由をログへ記録して停止します。IDごとの場当たり的な補正は行いません。

## 4. Phase 1入力の読み方

| 内容 | HDF5位置 | 型・単位 | 用途 |
|---|---|---|---|
| EEG | `signal/data` | `n_samples × 32`, float, V | PSD入力 |
| ch名 | `signal/channel_names` | 32要素 | Fz抽出・topography |
| Set内時刻 | `time/relative_seconds` | 秒 | 窓中心・progress |
| 実時刻 | `time/OriginalTimestamp` | 秒 | 出力時刻対応 |
| ICA用区間除外 | `qc/ica_training_excluded_mask` | `n_samples` bool | 1秒PSD窓との重複率を保存し、1%以上重なる窓を解析時に全32chでNaN化 |
| ICA用ch除外 | `qc/ica_channel_excluded_mask` | 32要素bool | 保存のみ。現行PSD除外には使わない |
| ch除外詳細 | `qc/ica_excluded_channel_records_json` | JSON | 監査情報 |
| 区間除外詳細 | `qc/ica_training_exclusions_json` | JSON | 監査情報 |

- `signal/data` をfloat64として読み、`× 1e6`でVからµVへ変換してからPSDを計算します。
- 平均参照、再参照、ラプラシアン、追加フィルタ、追加detrendを行いません。
- Phase 1でEye成分除去済みの脳活動解析用EEGをそのまま使用します。
- 代表figureはFzですが、PSDは全32chで同時に計算します。

## 5. PSD計算の完全仕様

### 5.1 使用関数

`mne.time_frequency.psd_array_welch()` を使用します。時間窓の切り出しはNumPyで行い、各1秒窓に対してWelch PSDを計算します。

```python
psd, freqs = mne.time_frequency.psd_array_welch(
    window_uv.T,
    sfreq=256.0,
    fmin=4.0,
    fmax=7.0,
    n_fft=256,
    n_per_seg=256,
    n_overlap=0,
    window="hann",
    average="mean",
    output="power",
    remove_dc=True,
    verbose=False,
)
```

外側の時間窓を256 samplesずつ移動するため、関数内部では1つの256-sample segmentだけを評価し、`n_overlap=0`とします。窓内平均除去は `remove_dc=True` で明示します。

### 5.2 固定パラメータ

| 項目 | 設定 |
|---|---|
| サンプリング周波数 | 256 Hz |
| 入力単位 | µV |
| 外側窓長 | 256 samples = 1秒 |
| 通常の窓移動 | 256 samples = 1秒 |
| 窓関数 | Hann |
| `n_fft` | 256 |
| `n_per_seg` | 256 |
| 関数内overlap | 0 |
| 周波数分解能 | 1 Hz |
| 対象bin | 4、5、6、7 Hz |
| 帯域代表値 | 4 binの算術平均 |
| PSD単位 | µV²/Hz |
| 対数変換 | PSD出力値は線形値のまま。No1専用の上側外れ値判定に限り `log10(PSD)` を使用 |
| dB変換 | なし |
| 時間平滑化 | cacheはなし。時間変化figureはSet内60秒中心化単純移動平均。NaNを無視し、1点以上が有限なら算出 |
| 区間maskによるNaN化 | 窓内重複率1%以上で全32chのPSDをNaN |
| ch除外 | 現時点ではなし |

現行MNE 1.13の実シグネチャで利用可能な `output="power"` を明示し、パワーPSDを取得します。返された周波数が `[4., 5., 6., 7.]` と一致しない場合はエラーにします。周波数方向は `np.mean(psd, axis=-1)` で平均します。

### 5.3 Set端の反射paddingと窓中心

Setの先頭・末尾までPSDを定義するため、各chのSet信号を前後128 samplesずつ `np.pad(..., mode="reflect")` で延長します。

- 窓中心sampleは `0, 256, 512, ...` とします。
- 最後の中心が元信号の `n_samples - 1` でない場合、`n_samples - 1` を追加します。
- 各中心 `c` に対し、元信号上の `c - 128` から `c + 127` に相当する256 samplesを反射padding後の配列から取得します。
- 最初の窓中心はSet開始、最後の窓中心はSet終了です。
- 通常点の間隔は1秒ですが、最後だけ直前の中心との間隔が1秒未満になることがあります。
- padding部分はPSD計算の文脈だけに使い、保存時刻は元Set内の中心時刻を使います。

### 5.4 窓中心時刻とprogress

- `relative_seconds_center = time/relative_seconds[c]`
- `OriginalTimestamp_center = time/OriginalTimestamp[c]`
- `set_progress_pct = c / (n_samples - 1) × 100`
- `global_progress_pct = (Set番号 - 1) × 100 + set_progress_pct`

Set実時間の違いはprogress軸だけで線形伸縮します。PSDの1秒窓・1秒移動は必ず実時間で計算し、progress変換後に計算しません。

## 6. 区間maskと平滑化

### 6.1 時間平滑化

- ID101–201で15、30、60秒の中心化単純移動平均を比較し、その後の全対象結果も確認したうえで、時間変化をより滑らかに示す設定として60秒を採用しました。
- 1秒刻みPSDに対し60秒の中心化単純移動平均を、Setごとに独立して適用します。Set境界をまたぎません。
- NaNを無視して有限値の算術平均を求めます。窓内に1点以上の有限値があれば算出し、窓全体がNaNの場合だけNaNとします。NaN区間の前詰めや補完はしません。
- 平滑化は実時間で行い、その後にprogress軸へ表示します。Grand-averageは各条件・各Setの平滑化後系列を100点のprogress格子へ対応付けた後、被験者間平均します。
- ローカルHDF5は未平滑PSDを正本とし、平滑化値で上書きしません。定量化とtopographyも未平滑PSDから計算します。

### 6.2 Phase 1区間除外mask

- `ica_training_excluded_mask` と各1秒PSD窓の重なり率を計算し、cacheへ保持します。
- 重なり率が1%以上のPSD窓は、読み出し後の解析値を全32chでNaNにします。
- 元の有限PSDとmask率はcache内に保持し、元EEGやcacheの値自体を上書きしません。
- NaN窓は時間方向へ前詰め、補間、置換せず、時刻とprogressを保持します。
- Set平均、全Set統合平均、topographyは有限PSD窓だけで計算します。
- ID101では全4,008窓中39窓、0.97%が本基準に該当することを確認しました。

### 6.3 No1専用のlog10 PSD上側3SD除外

Phase 1区間maskを適用した後、残存する極端な高PSD値だけを機械的に除外します。

1. 単位は `セッションID × ch` とし、そのIDで利用可能な全Setの有限かつ正の**未平滑4–7 Hz平均PSD**をプールします。Setごとには閾値を作りません。
2. 対応する2セッション、条件、被験者、chを混ぜません。
3. `x = log10(PSD)` とし、`T_log = mean(x) + 3 × SD(x, ddof=1)` を求めます。
4. `x > T_log` の窓だけを上側外れ値とし、そのch・その時間窓だけをNaNにします。下側外れ値は除外しません。
5. 線形PSD上の閾値は `T_linear = 10 ** T_log` として保存します。
6. 時刻、progress、他chは保持し、前詰め、補間、置換を行いません。

元の有限PSD cacheを上書きせず、閾値、除外mask、Set別・ch別の除外数と除外率を別datasetとして保存します。再描画・再集計時も必ず保存済み閾値とmaskを再現し、同じ入力と設定から同じ除外結果になることを検証します。

ID101–201のFzを全Set一括で検証した結果は、ID101が22/3,969窓（0.55%）、ID201が26/4,069窓（0.64%）、合計48/8,038窓（0.60%）でした。この値は方式の妥当性確認であり、ID別に閾値係数を調整する根拠には使用しません。

- 個人時間変化とGrand-average：Phase 1区間mask → 本3SD mask → Set内60秒平滑化
- 定量化とtopography：Phase 1区間mask → 本3SD mask → 未平滑PSDを使用

### 6.4 ICA用ch除外mask

- 最終脳活動HDF5には32chが保持されているため、現行PSDでは全32chを計算します。
- `ica_channel_excluded_mask` がtrueのchも削除・NaN化しません。
- ch maskはICA学習を安定させるための情報であり、脳活動PSDの不使用判定とはみなしません。
- 32ch順を維持し、mask自体は監査情報としてcacheに保持します。

## 7. PSDキャッシュHDF5

### 7.1 保存先と命名

```text
/Users/aoiseki/Desktop/SandBox_ロート案件（データ）/解析に必要なデータたち/
  Phase4_脳波解析/
    No1_FmTheta/
      PSDTimeSeries/
        Pair101-201_01_ID101_FmTheta_AllChannelsPSD.h5
        Pair101-201_02_ID201_FmTheta_AllChannelsPSD.h5
```

同じ被験者の1回目・2回目がファイル名順で連続するよう、`Pair<1回目>-<2回目>_01_ID<1回目>`、`..._02_ID<2回目>` を使います。

### 7.2 HDF5構造

```text
attrs/
  participant_id, pair_id, session_order, condition, product
  source_pipeline, sampling_frequency_hz, input_signal_unit
  psd_unit, psd_method, window_samples, step_samples
  n_fft, n_per_seg, n_overlap, window_function
  fmin_hz, fmax_hz, included_frequencies_hz
  time_smoothing, interval_mask_policy, channel_mask_policy
signal/
  channel_names                       [32]
sets/
  Set1/
    psd_band_mean                     [n_windows, 32], float32, µV²/Hz
    log3sd_outlier_mask               [n_windows, 32], bool
    relative_seconds_center           [n_windows], float64
    OriginalTimestamp_center          [n_windows], float64
    set_progress_pct                  [n_windows], float64
    global_progress_pct               [n_windows], float64
    source_center_sample              [n_windows], int64
    ica_training_mask_fraction        [n_windows], float32
    attrs: source_file, source_n_samples, available
  ...
qc/
  ica_channel_excluded_mask           [32], bool
  ica_excluded_channel_records_json
  source_set_availability             [6], bool
  log3sd_mean_by_channel              [32], float64, log10(µV²/Hz)
  log3sd_sd_by_channel                [32], float64, log10(µV²/Hz)
  log3sd_threshold_log_by_channel     [32], float64, log10(µV²/Hz)
  log3sd_threshold_linear_by_channel  [32], float64, µV²/Hz
  log3sd_excluded_count_by_set_ch     [6, 32], int64
  log3sd_valid_count_by_set_ch        [6, 32], int64
```

- `psd_band_mean`の列順は`signal/channel_names`と完全一致させます。
- `psd_band_mean`はPhase 1区間mask適用前の元の有限PSDを保持し、3SD除外値で上書きしません。
- `log3sd_outlier_mask`は、Phase 1区間mask適用後の有限かつ正のPSDを用いてセッションID・ch別に全Set一括で算出します。
- 欠測Setのgroupは作成せず、`source_set_availability`をfalseにします。
- gzip圧縮、`compression_opts=4`、`shuffle=True`を使用します。
- 保存後に全datasetを読み戻し、shape、単位、ch順、時刻単調増加、progress範囲、有限値を検証します。
- 設定hashと入力ファイルのパス・サイズ・mtimeをログへ残し、設定不一致の既存cacheは再利用しません。

### 7.3 再計算制御

現行の `Phase4_No1_FmTheta.py` は次の独立モードを持ちます。

- `--preflight-only`：入力検査だけ
- `--compute-psd`：PSD cache作成と読み戻し検証
- `--individual-only`：既存cacheから個人figureだけ作成
- `--group-outputs-only`：既存cacheからGrand-average、定量化、統計、topographyを作成
- `--all`：preflight、必要なcache計算、全figure・表・ログ作成
- `--force-recompute`：利用者が明示した場合だけ既存cacheを再計算
- `--grand-y-target-fraction`：Grand-averageの表示専用オーバーライド。標準値は`0.75`で、明示された再描画時だけ変更
- `--grand-y-basis`：Grand-averageのy上限算出対象。標準は`mean_plus_sem`で、明示された再描画時だけ`mean`へ変更

通常は既存cacheの設定hashと完全性が一致すれば再利用します。figureデザイン変更では`--individual-only`または`--group-outputs-only`を使います。

## 8. 共通figureデザイン

| 項目 | 固定値 |
|---|---|
| フォント | Arial |
| PNG解像度 | 180 dpi |
| 軸線幅 | 1.5 pt |
| 上・右spine | 非表示 |
| 軸名 | 28 pt（定量化のy軸のみ30 pt） |
| 目盛数字 | 時間変化20 pt、定量化23 pt |
| 凡例 | 20 pt、枠なし |
| Set名 | 時間変化22 pt、定量化26 pt |
| 時間変化の条件線 | 3.0 pt |
| Set境界 | `#9E9E9E`、破線、1.5 pt |
| 横軸目盛線 | 幅1.5 pt、長さ6 pt |
| 背景 | 白 |
| タイトル | 原則付けない |

すべての軸名・凡例は英語とし、単位を必ず表示します。色だけに依存せず、凡例で条件を明示します。

## 9. 配色

### 9.1 時間変化・Grand-average

| 解析 | Control | Cキューブ Eye Drop | Vロートプレミアム Eye Drop |
|---|---|---|---|
| No1 Fmθ | `#402B5D` | `#A94F2D` | `#D97852` |
| No2 alpha | `#402B5D` | `#C23B8A` | `#E36A8D` |
| No3 delta | `#402B5D` | `#8F7300` | `#C29A00` |

### 9.2 No1定量化

- Control：`#66547D`
- Cキューブ Eye Drop：`#C47A5B`
- Vロートプレミアム Eye Drop：`#E69A7D`

条件と製品の対応は変えず、時間変化線と区別するため明度・彩度だけを変えます。

## 10. 個人時間変化figure

- 1被験者ペア1 PNG。ControlとEye Dropの2線を描きます。
- 条件ラベル：`Control`、`Eye Drop (C Cube)`または`Eye Drop (V Rohto Premium)`
- 欠測Setは線をつながず、該当条件側だけ空白にします。
- figure size：`24 × 8 inch`
- 横軸：`Experimental Progress, %`、範囲0–600、50刻み
- Set境界：100、200、300、400、500
- Set名：50、150、250、350、450、550、axes高さ0.96
- 縦軸：`PSD (µV²/Hz)`、下限0
- 両条件・全Setの有限最大値を `M` とし、y上限は `M / 0.70` 以上となる切りのよい値
- y目盛は0を含む3〜6個。`1, 2, 2.5, 5 × 10^n`の候補から5個に最も近い間隔を選びます。
- Controlを先に、Eye Dropを後に描き、線幅3.0 pt、alpha 1.0とします。
- 凡例：上中央、`bbox_to_anchor=(0.5, 1.18)`、2列、枠なし、20 pt
- margins：left 0.08、right 0.99、top 0.78、bottom 0.20
- 横グリッドなし、180 dpi、`bbox_inches="tight"`
- 標準版は `Individual/` 直下へ保存します。
- `Individual/` 直下の標準版は、Phase 1区間maskとNo1専用3SD maskを適用後、60秒平滑化したFz PSDを描画します。y上限の `M` もこの表示データの2条件・全Setから求めます。
- 60秒平滑化はNaNを無視し、窓内に1点以上の有限値があれば平均し、窓全体がNaNの場合だけNaNとします。前詰め・補間は行いません。
- 閾値除外前の未平滑PSDは `Individual/Unsmoothed/BeforeThresholdExclusion/`、Phase 1区間maskと3SD mask適用後の未平滑PSDは `Individual/Unsmoothed/AfterThresholdExclusion/` に保存します。各figureは自身の表示値から同じ割合規則で自動y軸を決めます。
- y軸固定版は作らず、探索時の `SmoothingComparison/` も本番成果に残しません。

## 11. Grand-average時間変化figure

### 11.1 progress格子と集計

- 各Setの未平滑PSDに60秒中心化単純移動平均を適用した後、`np.linspace(0, 100, 100, endpoint=False)` の100点へ線形対応付けします。
- 補間は各被験者・各条件・各Set内だけで行い、Set間をまたぎません。
- 欠測Setは100点すべてNaNです。既知欠測ペアでは対応条件側も同じSetをNaNにします。
- 各progress点で有限値だけから平均、標本SD（`ddof=1`）、N、`SEM = SD / sqrt(N)`を計算します。
- N=1では平均は保存し、SD・SEMはNaNとします。

### 11.2 figure

- 製品群ごとに1 PNG、figure size `24 × 8 inch`。平均線とSEM帯は60秒平滑化後の個人系列から計算します。
- x軸、Set境界、Set名、文字、線、凡例、余白は個人figureと同じです。
- 平均線3.0 pt、SEM帯は条件色・alpha 0.18・境界線なしです。
- y下限は0です。両条件の `mean + SEM` の有限最大値を `M` とし、y上限は `M / 0.75` 以上となる切りのよい値にします。
- 上記の約75%を本番成果物の標準規則とします。平均線だけを基準にする特例や95%表示は使用しません。
- y目盛は0を含む3〜6個です。
- Cキューブ群とVロートプレミアム群のy軸は、両群の候補上限の大きい方に統一します。
- 凡例へNやSEMの説明文は追加しません。
- progress別mean、SD、SEM、NをCSVへ保存します。

## 12. Set別・全Set統合定量化

### 12.1 被験者値

- Set別値：Phase 1区間maskとNo1専用3SD maskの適用後、そのSetのFzの有限な未平滑PSD窓を時間方向に`np.mean`します。
- 全Set統合値：両条件で共通利用可能なSetのFz PSD窓を全て連結し、時間方向に`np.mean`します。
- Set平均の再平均はせず、PSD窓をプールして時間長を反映します。
- 欠測または対称除外SetはNaNです。時間平滑化値は使用しません。

### 12.2 Set別figure

- 6パネル横一列、`figsize=(34, 9)`、`sharey=True`
- 左Eye Drop、右Control
- bar中心 `[-0.32, 0.32]`、bar幅0.42、x範囲`[-0.90, 0.90]`
- bar alpha 0.82、枠`#222222`・1.0 pt
- dot size 150、alpha 0.68、白枠1.2 pt
- 対応線 `#777777`・1.2 pt・alpha 0.34
- jitterは両条件で同一offset、最大±0.055、固定seed `4000 + Set番号`
- x条件名22 pt、製品名18 pt、y目盛23 pt、y軸名30 pt、Set名26 pt
- x軸は `Eye Drop` と `Control` を22 ptで同じ高さに置き、Eye Dropの直下だけへ括弧付き製品名を18 ptで独立表示します。製品名を条件名と同じtick labelへ結合しません。
- 全6パネルにy目盛数字を表示します。
- margins：left 0.06、right 0.995、top 0.94、bottom 0.25、wspace 0.24
- 上・右spine非表示、グリッドなし、180 dpi

### 12.3 統計表示とy軸

全パネルの有限な被験者定量値の最大値を `M` とします。

- 統計ブラケット `1.13M`
- `*`中心 `1.17M`
- `n.s.`中心 `1.18M`
- Set名中心 `1.29M`
- y上限 `1.37M`
- ブラケットは黒・2.2 pt・縦capはaxes高さ0.018
- `n.s.`は26 pt、Arial、normal
- `*`、`**`、`***`は42 pt、Arial、bold
- `p < 0.05`=`*`、`p < 0.01`=`**`、`p < 0.001`=`***`、その他=`n.s.`
- y下限0、y目盛は0を含む3〜6個です。

### 12.4 全Set統合figure

- 1パネル、`figsize=(7.5, 9)`
- bar、dot、対応線、統計位置、文字、色はSet別と同じです。
- 表示名は `All Sets`、jitter seedは7001です。
- margins：left 0.20、right 0.98、top 0.94、bottom 0.25

## 13. 統計

- `scipy.stats.ttest_rel()`による両側対応ありt検定
- 各Setで両条件が有限の被験者だけを使用
- 差は `Eye Drop − Control`
- N、t、自由度、未補正p、平均差、差のSD、95% CI、Cohen's dzを保存
- 主PNGは未補正p値の記号を表示
- 6 SetのCSVには未補正、Bonferroni、Holm、Benjamini–Hochberg FDRのp値を保存
- 全Set統合は1検定なので多重比較補正なし
- 共通 `解析プログラム/paired_statistics.py` を再利用

## 14. Topography

### 14.1 値の作成

各被験者ペア・Set・chで、Phase 1区間maskとNo1専用3SD maskを適用した後、有限な未平滑Set内PSD窓を時間方向に算術平均し、`Eye Dropのch別Set平均 − Controlのch別Set平均`を計算します。32chすべてで同じ計算を行います。欠測Setは計算せず、補間、空間平滑化、平均参照、ラプラシアンを追加しません。

### 14.2 描画関数と座標

- `mne.channels.make_standard_montage("colin27_1020")`
- `mne.create_info(channel_names, sfreq=256, ch_types="eeg")`
- `info.set_montage(montage, match_case=False, on_missing="raise")`
- `mne.viz.plot_topomap()`
- cmap `RdBu_r`、0中心、`vlim=(-V, V)`
- `sensors="k."`、`names=False`、`contours=0`、`extrapolate="head"`
- 補間は `image_interp="cubic"`、`border="mean"`、`res=256`
- 10-20法の電極位置、補間面、頭部輪郭を同じ座標系で描くため、sphereは `(0, 0, 0, 0.095 m)` に固定
- 現行32chが32/32対応することをpreflightで再確認
- 頭部は太さ4.0 ptの濃色円形輪郭と鼻を表示し、耳輪郭は非表示
- 電極位置は8.0 ptの濃色点で表示し、ch名は表示しない
- 等高線を重ねず、滑らかな補間色面だけを表示

### 14.3 個人topography

- 1被験者ペア1 PNG、6 Set横一列、`figsize=(36, 6.5)`、180 dpi
- Set title 24 pt、Arial、pad 16
- 全6 Set・全32chの最大絶対差を `M` とし、`M / 0.85` 以上の切りのよい最小値を `V` とします。候補係数は `1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10 × 10ⁿ` とします。これにより、最大差が色軸の約85%以下に位置します。
- 同一被験者の6 Setで共通スケール、被験者間では変更可
- 欠測Setは中央へ `Missing` を22 ptで表示
- 各Setの右横に十分な間隔を空け、太さを確保した同一スケールのcolorbarを1本ずつ置きます（`fraction=0.08`、`pad=0.10`、`aspect=12`）。
- colorbar tickは `−V, 0, V`、label `Difference in PSD (µV²/Hz)`・28 pt、tick 24 pt。条件差の表記に `Δ` は使用しない
- figure titleなし

### 14.4 Grand-average topography

- 製品群ごとに1 PNG、6 Set横一列
- 各Setで有限な被験者差をchごとに平均
- 既知欠測ペアは該当Setから除外
- `V`は、その製品群の全Set・全chの群平均差の最大絶対値 `M` から、個人版と同じ `M / 0.85` と切りのよい値で決める
- 同一製品群の6 Setで共通スケール
- Setごとの有効Nを表へ保存
- figure size、title、輪郭、電極点、補間面、colorbar、文字は個人版と同じ
- 統計mask、有意電極、欠測補間は現時点で重ねない

## 15. 欠測Setの完全な扱い

| 欠測セッション | 欠測Set | 対応セッション |
|---|---:|---|
| ID109 | Set 1 | ID209 |
| ID120 | Set 6 | ID220 |
| ID135 | Set 2 | ID235 |
| ID225 | Set 4 | ID125 |

- PSD cache：欠測セッションの該当Setは作らず、対応側は作ります。
- 個人時間変化：欠測側だけ空白、対応側は描画し、欠測を線で接続しません。
- Grand-average：該当ペアの両条件をそのSetでNaN化します。
- Set別定量化：該当ペアの両条件をNaNとし、dot・bar・検定から除外します。
- 全Set統合：両条件で共通利用可能な5 Setだけをプールします。
- 個人topography：該当Setは `Missing` とします。
- Grand-average topography：該当Setではそのペアを除外します。
- 欠測を前詰め、時間補間、Set間補間しません。

## 16. OneDrive成果物・表・ログ

```text
実験本番_本解析/
  Phase4_脳波解析/
    No1_FmTheta/
      CCube/
        Individual/
          Unsmoothed/
            BeforeThresholdExclusion/
            AfterThresholdExclusion/
        GrandAverage/
        SetQuantification/
        Topography/
          Individual/
          GrandAverage/
      VRohtoPremium/
        Individual/
          Unsmoothed/
            BeforeThresholdExclusion/
            AfterThresholdExclusion/
        GrandAverage/
        SetQuantification/
        Topography/
          Individual/
          GrandAverage/
      Sub/
        tables/
          GrandAverage/
          Log3SDThresholdExclusion/
          SetQuantification/
          Topography/
        logs/
```

- `Individual/`：3SD mask適用後・60秒平滑化後の被験者ペア別Fz時間変化・自動y軸PNGだけ
- `Individual/Unsmoothed/BeforeThresholdExclusion/`：3SD閾値除外前の未平滑Fz時間変化
- `Individual/Unsmoothed/AfterThresholdExclusion/`：3SD閾値除外後の未平滑Fz時間変化
- `GrandAverage/`：60秒平滑化後の製品群別Fz平均±SEM PNGだけ
- `SetQuantification/`：Set別PNG、全Set統合PNG、統計CSV
- `Topography/Individual/`：被験者ペアごとの6 Set topography PNG
- `Topography/GrandAverage/`：製品群別6 Set topography PNG
- `Sub/tables/Log3SDThresholdExclusion/`：セッションID・Set・ch別のlog平均、標本SD、log閾値、線形閾値、有効窓数、除外窓数、除外率
- `Sub/tables/`：上記閾値記録に加え、progress別集計、被験者別Set平均、統計詳細、topography値・N
- `Sub/logs/`：preflight、cache hash、実行モード、入力・出力、警告、失敗理由

主成果物フォルダへJSONや補助CSVを混在させません。

## 17. 命名規則

- 個人時間変化：`ID101-201_No1_FmTheta_Individual.png`
- 個人時間変化・閾値除外前：`ID101-201_No1_FmTheta_Individual_Unsmoothed_BeforeThresholdExclusion.png`
- 個人時間変化・閾値除外後：`ID101-201_No1_FmTheta_Individual_Unsmoothed_AfterThresholdExclusion.png`
- Grand-average：`No1_FmTheta_GrandAverage_CCube.png`
- Set別定量化：`No1_FmTheta_SetQuantification_CCube.png`
- 全Set統合：`No1_FmTheta_AllSetsQuantification_CCube.png`
- 個人topography：`ID101-201_No1_FmTheta_Topography.png`
- 群topography：`No1_FmTheta_Topography_GrandAverage_CCube.png`
- 統計：`No1_FmTheta_SetQuantification_Statistics_CCube.csv`
- 3SD閾値記録：`No1_FmTheta_Log3SDThresholdExclusion_ID101-201.csv`（pilot）／`No1_FmTheta_Log3SDThresholdExclusion_AllParticipants.csv`（全対象）

Vロートプレミアム群は `VRohtoPremium` を使い、探索用の `Pattern`、`Test`、`New` 等は本番名へ入れません。

## 18. 記録先

Phase 4親ページにはNo1／No1_sub／No1_add、No2／No2_sub／No2_add、No3／No3_sub／No3_addの概要だけを独立見出しで置きます。各解析は専用詳細ページ、専用スクリプト、専用cache、専用OneDriveルートで管理し、相互に混在させません。

Phase 4の被験者別結果表と日次解析記録はNotionへ作成しません。解析実行時は、対象範囲、製品群、利用可能Set、欠測Set、cache作成・検証、個人figure、topography、警告、失敗理由、集団結果の有効N、統計、成果物名をOneDriveの `Sub/logs/` と `Sub/tables/` のCSVへ保存します。観察結果と解釈を分け、コード・文書の変更履歴はGitで管理します。

## 19. 実装と完了条件

### 19.1 実装前

- README、本書、運用ルール、解析上の注意事項、フォルダ管理、Notion Phase 4全ページを確認
- manifestとGoogle Driveの条件対応を照合
- 全入力preflightに合格

### 19.2 実装

- 全IDへ同じPythonコード・同じ定数を適用
- ID固有処理は本書の既知欠測Setだけ
- 計算関数、cache I/O、progress、統計、figure、topographyを関数分離
- 固定seed、固定色、固定figure定数をコード定数として一元管理

### 19.3 完了

- PSD cacheを読み戻してshape・時刻・ch・単位・有限性を検証
- セッションID・ch別の全Set一括3SD閾値、線形閾値、mask、除外数・率を再計算し、cacheと一致することを検証
- 欠測Setの個人／集団処理を検証
- figureの軸、目盛り、色、線幅、文字、凡例、ファイル名を検証
- Grand-averageのSEM・Nと定量化の対応NをCSVから再計算して一致確認
- topographyの差の向きが `Eye Drop − Control` であることを確認
- OneDriveのfigure・表・実行ログと、ローカルcacheを更新して読み戻し確認
- Git変更時は検証、commit、push、remote一致を確認し、実行ログへcommit番号を記録

## 20. 現時点の状態と未確定事項

- No1専用log10 PSD上側3SD除外は実装済み。2026-10-04に全40被験者ペア・80セッションを白紙から同一スクリプトで再計算して80件のcacheを確定した。60秒平滑化は有限点数の追加基準を設けず、1点以上が有限なら算出する元仕様へ戻し、保存済みcacheを再利用して全40ペアを再描画・再集計した。既知欠測4 Set、個人figure各40組、製品群別Grand-average・定量化・topography、監査表、実行ログを検証済みであり、No1は現行確定版として固定する
- No1_addは独立仕様書・独立スクリプトで本番40ペア・80セッションの解析と成果物検証を完了し、現行確定版として固定した
- No2・No3はNo1三解析を派生元とする差分仕様を確定し、代表ch、帯域、配色、名称、保存先以外の処理をNo1から変更しない

未確定事項を暗黙実装しません。変更時は本書、Notion、コード、テストを同時更新します。

最終更新：2026年10月4日
