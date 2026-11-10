# Phase 4 No8–11：Pz・Fzのセット別／前後半別IAF

更新日：2026-11-10。**現行方式を実装し、40被験者ペア・80セッションを実行・検証済み。** 本書をNo8–11の現行仕様の正本とする。旧方式の実行実績・採用率は流用せず、以下の結果は新方式から算出した。

## 1. 目的と解析の対応

課題進行に伴うアルファ帯の局所ピーク周波数を、同一被験者のEye DropとControlで比較する。パワーの大きさではなくピーク位置（Hz）を扱い、元のPSDも併記する。

| No | ch | 1セッションの推定単位 | OneDriveルート |
|---|---|---|---|
| No8 | Pz | 各Set全体、6値 | `No8_PzSetwiseIAF/` |
| No9 | Pz | 各Set前半・後半、12値 | `No9_PzHalfSetIAF/` |
| No10 | Fz | 各Set全体、6値 | `No10_FzSetwiseIAF/` |
| No11 | Fz | 各Set前半・後半、12値 | `No11_FzHalfSetIAF/` |

各Noで**1被験者ペア1枚の3パネルPNG**を作り、製品別に整理する。Grand-average、定量化バー、統計検定、topography、Set 1基準変化率、連続progress上のIAF時間変化は作らない。PzとFzで計算・採用条件を変えない。

## 2. 入力・対象者・欠測

1. 実行前にREADME、運用ルール、Python環境、本書、解析上の注意事項、Notionの現行方針・解析ストーリーを確認する。
2. 現行対象は40被験者ペア・80セッション。共通の対象外、既知の4欠測Setは[解析上の注意事項](解析上の注意事項.md)に従う。新たな被験者除外はしない。No4–7やtopographyの事後感度分析除外は流用しない。
3. 非公開manifestの `first_session_id,second_session_id,drops_session_id,product` を許可された被験者対応資料と照合する。IDの100番台／200番台から点眼条件を推測しない。参加者別対応表・値をGitや共有仕様へ転記しない。
4. 入力はPhase 1のセット別「脳活動解析用」HDF5。確定済みのフィルタ・トレンド除去・ICA処理後EEGと不良時間maskを読み取り専用で使う。瞬き成分の復元信号、No1–7の帯域平均PSD cacheは使わない。追加フィルタ・再参照・再ICAはしない。
5. `fs=256 Hz`、等間隔sample、時刻、Set番号、Pz/Fz列、単位を照合する。時間窓と前後半の境界はPhase 1の `time/relative_seconds`（sample番号/256）に基づく。これはNo1–7と同じsample clockであり、各間隔が1/256秒であることを検証する。`OriginalTimestamp`は無線計測由来の間隔揺れを含むため、有限・厳密単調増加・信号との行数一致を確認して出典情報として保持し、等間隔と仮定したり再サンプリングしたりしない。異なるfsを256 Hzとみなさない。入力がVならµVへ変換し、PSDをµV²/Hzへ統一する。二重変換しない。
6. Phase 1でICA学習から除外されたchも、最終入力に信号が保持されていれば使う。ただし通常chと同じICA成分除去が適用されたとは扱わず、QCへ記録する。利用不能chは理由付きNaNとし、別chで代替しない。
7. 欠測Setは当該条件だけ未描画。対応条件が存在すれば描く。個人図のみなのでpaired ORによる追加欠測化はしない。Set 1欠測でもペア全体は除外しない。NaNを0 Hz、10 Hz、隣接値で補完しない。

## 3. 推定区間とWelch内部窓

**IAFの推定区間**はSet全体またはSet前後半。**Welch内部のsegment**はその中の10秒窓。区間内の有効periodogramを平均して1本のPSDを作り、1つのIAFを求める。10秒ごとのIAFを平均する方法ではない。

### 3.1 区間の定義

- No8・10：Setの開始から終了までを対象とする。冒頭60秒だけではない。
- No9・11：不良区間を除く前の**元のSet実時間**の50%位置で分割する。試行数や有効時間の半分ではない。
- sample支持区間を `[0,N/fs)` とし、境界を `N/(2*fs)` に置く。前半は境界未満、後半は境界以上のsample。等間隔入力の分割indexは `ceil(N/2)`。奇数sampleの前後半差は1 sample以内で、重複・取り落としなし。実時刻との一致を検証する。
- 前半をa（0–50%）、後半をb（50–100%）と呼び、順序は `1a,1b,2a,2b,...,6a,6b`。
- 各推定区間の先頭から10秒窓を5秒間隔で置く。**後半は後半の先頭を新しい起点**にする。全Setの窓を単に前後半へ分類する方法とは異なる。
- Set境界・前後半境界を越える窓、末尾の不完全窓、paddingは使わない。末尾の未使用長も記録する。「区間全体を対象にしたWelch推定」は全sampleが必ず採用されるという意味ではない。

### 3.2 PSDのパラメータ

| 項目 | 設定 | 理由・意味 |
|---|---|---|
| 計算法 | 有効な修正periodogramの算術平均 | Welch平均PSDを不良窓を除いて計算 |
| 関数 | `scipy.signal.periodogram`を各有効窓へ適用 | 不良sampleを含む窓だけを除ける |
| `fs` | 256 Hz、入力属性から検証 | 時間・周波数軸の整合 |
| 窓長 | 10秒＝2560 samples | 実測長からFFT bin間隔0.1 Hz |
| 窓形状 | `get_window('hann',2560,fftbins=True)` | periodic Hannを明示 |
| 窓間隔 | 5秒＝1280 samples | 50% overlap |
| `nfft` | 2560、zero paddingなし | 0.1 Hz bin |
| `detrend` | `'constant'` | 各窓の平均を除く |
| PSD | `return_onesided=True, scaling='density'` | 片側密度、µV²/Hz |
| 数値精度 | EEGをfloat64へ変換してからV→µV換算、計算・保存もfloat64 | 単位換算時の不要なfloat32丸めを避ける |
| 平均 | 線形PSDの算術平均 | median、log平均、IAF値の平均ではない |
| 保存周波数 | 1.0–40.0 Hz、0.1 Hz刻み、両端含む391 bins | 描画・帯域端の判定・再利用 |
| 描画周波数 | 1.0–30.0 Hz、両端含む | 指定のスペクトル表示 |
| ピーク探索 | 8.0–15.0 Hz、両端含む | 本解析のalpha定義 |

不良窓がない場合、同じ明示Hann窓を渡した `scipy.signal.welch(fs=256,nperseg=2560,noverlap=1280,nfft=2560,detrend='constant',scaling='density',return_onesided=True,average='mean')` と一致することをテストする。全PSDを計算後に1–40 Hzへ切り出す。

0.1 Hzは**bin間隔**であり、生理的ピークを0.1 Hz精度で識別できる保証ではない。10秒はこの間隔を得る設計判断であり、IAFに唯一の標準窓長があるという主張ではない。Hann・50% overlapの参照：[SciPy Welch](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.welch.html)。

### 3.3 Phase 1不良区間

Phase 1の不良時間maskに**1 sampleでも**重なる10秒窓は全体を不採用。対象chに非有限sampleがある窓も除く。元の時間位置を保ち、不良区間を詰めて連結しない。NaN入り全区間を通常のWelchへ渡すだけで自動除外されるとは想定しない。

有効窓が1つ以上なら計算する。有効窓数、unique coverage（有効窓の時間区間の和集合）、元区間に対する割合を記録するが、最低60秒・6窓・35秒・有効率の追加足切りはしない。有効窓0ならPSD・IAFはNaNとし、短時間／全窓不良などの理由を分ける。PSDが作れても局所ピークがなければIAFだけNaN。

No1–7の帯域平均PSD時系列へ行うlog10上側3SD除外は追加しない。時間方向のPSD外れ値除外と、平均スペクトル上のピーク探索を混同しない。

## 4. IAF：平均PSDの局所ピーク

1. 推定区間内の有効periodogramを**周波数binごとに先に平均**する。
2. 1–40 Hzの線形平均PSDへ `scipy.signal.find_peaks` を適用。`height, prominence, distance, width, threshold` 等の採否制約は渡さない。
3. 局所最大から8–15 Hzの候補を残す。8.0・15.0 Hzも7.9・15.1 Hzの隣接binとの比較で局所最大なら候補となる。
4. 元の平均PSDが最高の候補を選ぶ。同高なら低周波数側。平坦な頂部は固定版SciPyの規則（平坦部中央、偶数長は低index側）に従う。
5. 0.1 Hz gridで出力し、放物線補間やGaussian fittingはしない。局所最大がなければ理由付きNaN。単調曲線の帯域端を無条件に選ぶ `argmax(PSD[8–15 Hz])` にはしない。

**1/f背景除去、log変換、Savitzky–Golay平滑化、z値、ピークの顕著さによる足切り、旧複数峰80%フラグは使わない。** 旧処理を初期値として残さず、新しい計算契約で実装する。

微小な局所峰も採用され得る探索的指標である。NaNを減らす方針は全値の生理的妥当性を保証しない。PSD、候補峰数、選択峰PSD、有効窓量を確認する。1/f、ノイズ、多峰間の切替の影響は残り、注意・眠気・製品効果の直接証明とはしない。

## 5. Figureの確定設計

**左：Eye DropのPSD、中央：ControlのPSD、右：両条件のIAF推移。** 左・中央は条件内でSet間比較するため独立y軸。見かけの高さをそのまま条件間のパワー差と解釈しない。6本／12本とも同じ3パネル構成。承認済みプレビューは合成データであり実データの解析結果ではない。

### 5.1 全体

| 項目 | 確定値 |
|---|---|
| 画像 | 白背景PNG、27×10 inch、180 dpi、4860×1800 px |
| 配置 | 1行3列、各軸 `set_box_aspect(1)` |
| 余白 | left=.052, right=.985, bottom=.19, top=.88, wspace=.30 |
| 保存 | キャンバス寸法を保持。`bbox_inches='tight'`で別寸法化しない |
| フォント | 全文字Arial。見つからなければ停止し、黙って代替しない |
| 軸ラベル | 28 pt、labelpad=14 |
| 目盛 | 20 pt、tick長6・幅1.5 pt |
| 軸線 | 1.5 pt、上・右spineなし |
| 各タイトル | 26 pt、pad=20 |
| タイトル文言 | 左 `Eye Drop (C Cube)`／`Eye Drop (V Rohto Premium)`、中央 `Control`、右 `Pz — Alpha Peak Frequency`／Fz版 |
| 全体タイトル | 参加者名・N・統計・製品効果の注記を追加しない |

### 5.2 PSDパネル（左・中央）

| 項目 | 確定値 |
|---|---|
| x軸 | `Frequency (Hz)`、1–30、ticks=1,5,10,15,20,25,30 |
| y軸 | `PSD (µV²/Hz)`、線形、下限0 |
| y上限 | **当該パネル**の全6／12本の1–30 Hz内の有限PSD最大値 `M/0.80`。最高点を軸高80%へ。alphaだけでMを求めない |
| y目盛 | `MaxNLocator(nbins=5,steps=[1,2,2.5,5,10])`を基準に、範囲内3–6ラベル・キリのよい間隔。上限自体を丸める必要なし。桁あふれ防止に`ScalarFormatter(powerlimits=(-3,4),useOffset=False)`を用い、必要な場合だけ指数の倍率表示。線形軸・データ値・単位は変えない |
| PSD線 | 2.5 pt実線、alpha=1。描画用周波数平滑化なし |
| alpha境界 | x=8と15、`#888888`、点線1.5 pt、帯域シェードなし |
| 凡例 | 右上、枠なし、18 pt、labelspacing=.30、handlelength=1.7、columnspacing=.8 |
| 6本 | `Set 1`〜`Set 6`、凡例1列 |
| 12本 | `Set 1a, Set 1b,...,Set 6b`、凡例2列（左1a〜6a、右1b〜6b） |
| 12本の説明 | 図下部(0.5,.035)、中央17 pt：`a: first half (0–50%)` と `b: second half (50–100%)` を縦棒で区切って表示 |

各条件の基本色からHLSのhue・saturationを保持し、時系列順 `i=0..K−1`（K=6/12）のlightnessを `0.80−0.58*i/(K−1)` とする。透明度ではなく、**明→暗の濃淡**を明確に変える。欠測があっても色順は詰めない。凡例は6／12区間を固定表示し、欠測ラベルに `unavailable` を添える。

全PSDが利用不能ならy=0–1を仮表示し `No usable PSD` と明記する。M=0も0–1表示としゼロPSDと明記する。値を捏造しない。

### 5.3 IAFパネル（右）

| 項目 | 確定値 |
|---|---|
| y軸 | `IAF (Hz)`、7.5–15.5固定、ticks=8〜15（1 Hz間隔） |
| 6値のx軸 | `Set`、位置・ラベル1〜6、範囲.75–6.25 |
| 12値のx軸 | `Set / Half`、位置1〜12、ラベル1a,1b,...,6a,6b、範囲.75–12.25 |
| 線・点 | 条件ごとの基本色、線3 pt、丸印10 pt、白edge 1 pt |
| 凡例 | `Eye Drop (製品名)`と`Control`、右上、枠なし、17 pt、handlelength=2 |
| 接続 | 隣接する有限のSet／前後半値を結ぶ。NaNをまたぐ線は描かず、孤立した有限点は表示 |

### 5.4 配色

| No | Cキューブ Eye Drop | Vロートプレミアム Eye Drop | Control |
|---|---|---|---|
| No8 | `#2456A6` | `#5689CF` | `#402B5D` |
| No9 | `#23734B` | `#53A078` | `#402B5D` |
| No10 | `#A63D46` | `#CF7278` | `#402B5D` |
| No11 | `#79543A` | `#AC8058` | `#402B5D` |

Controlは従来の深い紫。点眼の基本色はNo8–11間で重複させない。PSD濃淡系列とIAF線の基本色で製品を取り違えない。

## 6. 保存構造と再利用

### 6.1 ローカル（生成済み）

許可された `SandBox_ロート案件（データ）/解析に必要なデータたち/` のみを使用する。

```text
Phase4_脳波解析/No8-11_PzFzIAF/SpectralSegments/
  Pair<初回ID>-<2回目ID>_01_ID<初回ID>_PzFz_IAFSpectra.h5
  Pair<初回ID>-<2回目ID>_02_ID<2回目ID>_PzFz_IAFSpectra.h5
```

同じ人の2セッションをファイル名順で隣接させる。Pz/Fzを共通HDF5へ保存し、全Set・前後半各窓gridを識別する。新schemaは `phase4-iaf-localpeak-2026-11-10-v2`。旧cacheは自動移行・読み替えしない。必須保存項目：

- 周波数軸、ch、単位、fs、元Set長、全Set／前半／後半の境界sample・時刻。
- 窓の元sample開始・終了、有効mask、除外理由、線形periodogram、平均PSD。
- 候補・有効窓数、unique coverage秒・割合、末尾未使用長、ICA学習除外chフラグ。
- ピーク候補周波数・PSD、選択IAF、推定不能理由。旧peak z・SG残差は生成しない。
- 入力hash、全計算設定hash、schema・コード版、条件・製品照合情報。

同一sample範囲・処理の窓は共用可能だが、全Setgridから後半gridへの暗黙流用は禁止。計算・IAF推定・描画を分離し、図だけの変更は新schemaの適合cacheから再描画する。EEGの再読込・PSD再計算をしない。計算設定hashと描画設定・コード版の出典情報は分け、描画のみの変更で計算cacheを無効化しない。計算設定／入力不一致cacheを黙って利用しない。

### 6.2 OneDrive

許可された `実験本番_本解析/Phase4_脳波解析/` 配下に並列配置する。

```text
No8_PzSetwiseIAF/
  CCube/Individual/
  VRohtoPremium/Individual/
  Sub/tables/
  Sub/logs/
No9_PzHalfSetIAF/       （同じ構造）
No10_FzSetwiseIAF/     （同じ構造）
No11_FzHalfSetIAF/     （同じ構造）
```

主PNG：`Pair<初回ID>-<2回目ID>_No<番号>_<ch>_<SetwiseIAFまたはHalfSetIAF>_ThreePanel.png`。Individual直下にPNGのみを並べ、個人フォルダやCSV/JSONは置かない。各Noで製品別20枚・計40枚、4解析合計160枚を保存・読戻し確認済み。

- `Sub/tables/`：`ParticipantManifest.csv`、`No<番号>_IAF_Estimates.csv`（推定単位別IAF・候補峰数・選択峰PSD・有効窓量・理由・境界・ICAフラグ）、`No<番号>_PeakAvailability.csv`（製品・条件・算出状態別件数）。Set別6／前後半12行を各セッションで保ち、既知欠測も理由付き行を残す。全対象の行数は480／960。
- `Sub/logs/`：照合、実行範囲、hash、出力件数、cache利用、警告、検証、未完了事項。清掃監査は解析結果と区別する。
- スペクトルQCは主3パネルへ統合。旧 `Sub/QualityCheck/`、時間窓例示図、GrandAverage等は作らない。
- Notionは方法・概要・判断の置き場。参加者別DBは新設せず、集計した実行結果だけを記載する。

## 7. 旧方式と新実装の切り分け

新実装前に旧本番成果物・合成プレビュー・旧IAF cacheを清掃し、空の保存先から開始した。清掃監査ログはNo8のSub/logsへ保持し、現在は新方式の図・数値表・80 cacheがある。清掃経緯は履歴文書へ分離する。成果物確認はローカル同期フォルダに対するものであり、OneDriveサーバー同期完了の独立検証とは区別する。

旧6スクリプト・旧テストは内容を変えず `解析プログラム（過去版いらなくなったやつ）/Phase4_No8-11_IAF_20261109_廃止/` へ退避済みで、現行入口・通常test収集対象から外した。過去版は参照専用で再実行しない。旧コマンドを本番手順にしない。

現行コードは `解析プログラム/Phase4_脳波解析/phase4_iaf.py`（計算・cache・実行）と `phase4_iaf_figures.py`（描画）。全員に同じコード・設定を適用する。4つの入口 `Phase4_No8_PzSetwiseIAF.py`, `Phase4_No9_PzHalfSetIAF.py`, `Phase4_No10_FzSetwiseIAF.py`, `Phase4_No11_FzHalfSetIAF.py` も同じ共通engineを呼ぶ。旧ピーク/QC/60秒時間変化は混入させていない。

実行モードは `--preflight-only`（入力の読取検証のみ）、`--compute-only`（cache・数値表・ログ）、`--figures-only`（適合cacheから再描画）、`--all`（全工程）。`--manifest`は必須で、本番全員では`--production-batch`を付ける。共通engineの`--analysis 8 9 10 11`で対象Noを指定でき、省略時は全4解析。固定Python環境を使い、出力先fallback・個人別コード変更をしない。

```sh
MPLCONFIGDIR=/tmp/mplconfig-roht .venv/bin/python 解析プログラム/Phase4_脳波解析/phase4_iaf.py --manifest <非公開manifest.csv> --production-batch --all
```

`<非公開manifest.csv>`は実ファイルに置き換える。実行済み対応表は各Noの`Sub/tables/ParticipantManifest.csv`に保存される。図のみでは`--all`を`--figures-only`へ置き換える。cacheがない／入力SHA・計算設定・schema・条件情報が一致しない場合は停止し、勝手に再計算・読替えしない。入力の出典照合ではファイルhashと時刻を読むが、描画のためにEEGの数値解析やPSD再計算はしない。

廃止理由と議論経緯は[旧方式と再設計記録](history/Phase4_No8-11_旧方式と再設計記録.md)へ分離した。旧採用率・旧完了状態は現行結果ではない。Notionは[現行共通仕様](https://app.notion.com/p/413161f2809781bdb65bcac9202d7126)と[廃止記録](https://app.notion.com/p/414161f2809781e0954fd060e7aafb63)を別ページで管理し、Phase 4親ページには各Noの概要のみを置く。

## 8. 実装・実行時の検証

1. manifest、40ペア、既知欠測、ch/fs/単位/Phase 1 maskを照合。
2. 全Set／前後半境界、奇数sample、後半独立grid、境界非横断、不良1 sample窓の除外、欠損非連結を検証。
3. 合成正弦波・既知PSD・単位・0.1 Hz軸・Welch一致・有効1窓の計算・0窓NaNを検証。
4. 8/15 Hz端、帯域外峰、単調・完全平坦PSD、多峰・同高・plateauの選択を検証。旧z/SG/coverage等が一切有効になっていないことを確認。
5. 6／12値が全区間平均PSDから作られ、窓別IAF平均でないことを確認。
6. HDF5のschema/hash/形状・値の読戻し、旧版拒否、図のみでcache hash不変を検証。
7. PNG件数・寸法・全画像デコード。図を開き、6／12線と凡例、濃淡、色、Arial、文字の重なり、独立y上限80%、IAF軸、欠測を確認。
8. 全員同一コード・設定、表と図、警告・制限、Notion/Git/OneDriveの状態を照合。commit・push・remote検証後に報告。

## 9. 新方式の実行結果と限界

2026-11-10、40ペア（各製品20）・80セッションを同じengineで実行。入力476 Set、共通HDF5 80件、PNG160枚。既知欠測を含む固定行数を維持した。

| No | 予定推定数 | 算出できたIAF | 元Set欠測 | 有効10秒窓0 |
|---|---:|---:|---:|---:|
| No8：Pz・Set全体 | 480 | 473 | 4 | 3 |
| No9：Pz・前後半 | 960 | 943 | 8 | 9 |
| No10：Fz・Set全体 | 480 | 473 | 4 | 3 |
| No11：Fz・前後半 | 960 | 943 | 8 | 9 |

有効PSDがあって局所ピークだけ見つからなかった区間は今回は0。算出不能区間は原Phase 1不良時間maskがすべての候補10秒窓へ重なったもので、z値や有効率の追加足切りによる欠損ではない。全Setと後半は独立した窓起点を使うため、全Setと前後半の有効窓の有無は単純な包含関係にならない。欠測理由・対象区間・有効窓量は非公開CSVで確認できる。

PzのICA学習除外chフラグは元Set単位で12件（前後半表では24行）、Fzは0。方針どおり信号を保持したが、該当Pzを通常のICA成分除去済みchと同一視しない。

検証では全体199テストが成功（新IAF数値・cache43、描画25を含む）。独立監査で476入力SHA、247,314件の窓×ch採否、2,856平均PSDとピーク、2,880 CSV行を照合した。原EEGから2,832実窓のperiodogramを再計算して保存値と一致（最大絶対差0）。各PNGは4860×1800で全件読戻しし、4解析・両製品・既知欠測を含む代表10画像を目視確認した。すべての画像を目視したという意味ではない。No8の全40人を`--figures-only`で再描画し、80 cacheのhash不変・数値表一致を確認した。他のPhase 4成果物・中間データ1,665ファイルのサイズ・更新時刻も不変。

これは**算出・再現性の確認**であり、アルファ成分の正確な検出率や製品効果を意味しない。低周波／高周波の大きなノイズが残る例、弱いalpha峰・多峰間の切替はあり得る。左・中央は独立y軸のため高さを条件間で直接比較しない。PSDと右パネルを併せて探索的に読む。今回、新たな被験者除外・追加ノイズ除去・群平均・統計検定はしていない。
