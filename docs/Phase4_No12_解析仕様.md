# Phase 4 No12・No12_sub：前頭〜中央10電極ROI low-alpha解析仕様

文書更新日：2026-11-16（10電極改訂）。**現行の確定方法**は、F3・Fz・F4・FC5・FC1・FC2・FC6・C3・Cz・C4の8–10 Hz帯域平均PSDへch別品質maskを適用し、時点ごとに有効chを等重み平均する方式。本書はNo12本体とNo12_subを統合した実装・共有用の正本である。**10電極版の全員再実行・独立数値監査・全PNG機械確認・全群図を含む19枚の目視・511テストを完了。Git公開は別の完了ゲートで確認する。** 結果・検証は第11節、議論・意思決定の過程は[専用履歴](history/Phase4_No12_意思決定.md)へ分離する。旧5電極の方法・実績は[履歴専用保存版](history/Phase4_No12_旧5電極仕様結果_20261116.md)に隔離し、10電極の方法・結果・検証へ流用しない。

対応Notion：[No12詳細・共通方法](https://app.notion.com/p/41a161f2809781ffb693daa055c63777)、[No12_sub詳細](https://app.notion.com/p/41a161f2809781559af0e8d1b4d6de02)、[意思決定履歴](https://app.notion.com/p/41a161f280978192a3bef4d9a266e342)。親はPhase 4ページ。

## 1. 目的・対象・範囲

| 項目 | No12 | No12_sub |
|---|---|---|
| 正式stem | `No12_FrontalROILowAlpha` | `No12_sub_FrontalROILowAlphaChange` |
| ROI | **F3・Fz・F4・FC5・FC1・FC2・FC6・C3・Cz・C4（10電極）** | 同左 |
| 帯域 | **8・9・10 Hzの3 bin（両端込み）** | 同左 |
| 値 | 帯域平均後・ch平均後PSD、µV²/Hz | ROI自身のSet 1平均からのPSD Change、% |
| 比較 | 製品別のEye Drop対Control、被験者内対応 | 同左 |
| 出力 | 個人時間変化、Grand-average、Set別・全Set統合定量化 | 同左 |
| 入力 | 現行No10の全32ch・8–10 Hz PSD cache | 同じcache |

- Fz単極／旧5電極から左右のFC列と中央C列まで広げた**前頭〜中央ROI**の探索解析。F列3ch、FC列4ch、C列3chで、**F7・F8は含めない**。既存stemの`FrontalROI`は保存先の互換名であり、解剖学的に前頭だけを測る意味ではない。8–10 Hzは本プロジェクトの操作的定義であり、個人別alpha帯やIAFを推定しない。
- 電極選定はNo10_sub・Vプレのtopographyを参考にした事後的な探索決定。完成済みtopography値のch平均は候補比較だけであり、本解析のROI値ではない。今回の結果を独立した確認的検証・前頭特異性の証明としない。
- FCz・F1・F2は今回の記録32chに存在しないため含めず、欠けた電極を補間・推定してROIへ加えない。
- [No10仕様](Phase4_No10_解析仕様.md)・[No11仕様](Phase4_No11_解析仕様.md)の最新計算・図・保存方式を継承する。新規部分は**品質処理後・平滑化前のch間平均**と、そのROI平均を基準にするsub変換である。
- **Topography・TFMは生成しない。** 同じ全32ch low-alphaのmapはNo10と重複し、ROI値自体は1系列である。既存map、個人図、他Noの成果物は変更しない。
- 初回は追加の定性的被験者除外なし。他Noの被験者除外、topographyのペア×ch×Set除外、IAF選別を持ち込まない。将来のROIの信号品質確認後に追加版を検討できるが、今回はその対象・結果を先回りして作らない。

## 2. 対象・条件対応・欠測

- 基本対象40ペア・80セッション、2製品各20ペア。共通対象外、既知4欠測Set、分割記録は[解析上の注意事項](解析上の注意事項.md)を正本とし、個別ID一覧を本書へ複製しない。
- 実行直前にNotionの対応表・注意事項と許可済みGoogle資料を照合する。manifestの`first_session_id,second_session_id,drops_session_id,product`とcache属性を照合し、IDの100／200番台だけでEye Dropを決めない。
- 個人図は既知欠測の条件・Setだけを非表示とし、対応条件の実在Setは表示する。
- Grand-average・Set定量化は、片条件が既知欠測のSetを同じペアの両条件から外す。全Set統合も両条件共通の利用可能Setを用いる。欠測をゼロや他Setで補わず、時刻を詰めない。
- No12はSet 1欠測だけでペア全体を除かない。No12_subは各条件のROI Set 1 baselineが必要なので、既知Set 1欠測ペアは両条件・全Setを対象外とする。
- 10電極版で確認した対象はNo12 40ペア／sub 39ペア。実対象・Set別の実有効Nは第11節と生成表へ記録する。想定外の入力不足・電極欠落・条件不一致・計算不能baselineは停止・記録し、無断補完や個人別規則を追加しない。

## 3. 入力cacheとPSDの由来

### 3.1 読み取り専用再利用と設定の識別

```text
/Users/aoiseki/Desktop/SandBox_ロート案件（データ）/解析に必要なデータたち/
  Phase4_脳波解析/No10_FzLowAlpha/PSDTimeSeries/
    Pair<初回ID>-<2回目ID>_01_ID<初回ID>_FzLowAlpha_AllChannelsPSD.h5
    Pair<初回ID>-<2回目ID>_02_ID<2回目ID>_FzLowAlpha_AllChannelsPSD.h5
```

- ファイル名にFzが含まれていても`sets/SetN/psd_band_mean`は全32ch・窓×chの未平滑原値である。ROI10chを`channel_names`の名前で選ぶ。固定indexやFz単列の代用を禁止する。
- 全80 cacheをNo10生成設定のcache guardで検証する。8–10 Hz・実bin`[8,9,10]`、fs、名前／順、shape、時刻・progress、mask、入力fingerprint、ID／条件／製品、configuration hashが必要。
- **元cache hashは生成時のNo10設定に対して検証する。** No12の解析名やROI名を元attrsへ書き戻さず、No12 hashの不一致を理由にPSDを再計算しない。No12出力の設定hashにはROI・平均順序・描画・出力設定を含め、source hashと区別する。
- 旧8–11 Hz、No2の8–15 Hz平均、TFM、IAF用PSDを代用しない。元の値・mask・sourceは書き換えない。
- No12／subの新しいローカルcacheや空のデータフォルダは作らない。計算済みPSDを二重保存せず、由来・ROI品質・baseline・集計・実行証跡を専用OneDriveのSubへ保存する。

### 3.2 元PSDの計算仕様（今回再計算しない）

Phase 1の`brain_activity_eeg`、sample×32ch・Vをfloat64のµVへ変換（×10⁶）した入力。fs=256 Hzを検証している。追加filter、再参照、Laplacian、ch補間はない。

| 項目 | 固定仕様 |
|---|---|
| 関数 | `mne.time_frequency.psd_array_welch` |
| 入力 | 1秒分の全32ch・µV、末尾次元が時間 |
| `sfreq` | 256.0 Hz |
| `fmin`, `fmax` | 8.0, 10.0 Hz |
| `n_fft`, `n_per_seg`, `n_overlap` | 256, 256, 0 |
| `window`, `average`, `output` | `hann`, `mean`, `power` |
| `remove_dc`, `verbose` | True, False |
| 外側移動幅 | 256 sample＝1秒 |
| 帯域値 | 8・9・10 Hzの算術平均、µV²/Hz |

積分・総和・dB化はしない。各1秒窓内は1 Welch segmentで、後のROI平均・時間平均とは別工程。Set両端は128 sampleずつreflect paddingし、休憩中のEEGは使わない。窓中心は`0,256,…`、末尾sample`n−1`が未収録なら追加するため、最後の間隔だけ1秒未満になり得る。

相対秒・OriginalTimestampは中心sample由来。`set_progress=center/(n−1)×100`、`global_progress=(Set−1)×100+set_progress`。実時間上でPSDを計算した後に表示位置を換算し、progress軸へ圧縮したEEGからPSDを求めない。全chは同じ中心時刻・progressを共有する。

### 3.3 前処理区間除外を考慮したPSDの使用

1. Phase 1の`ica_training_excluded_mask`と**1%以上重なる1秒PSD窓**を、全chでNaNとして解析から外す。maskにも同じreflect paddingを適用した重なり率を使う。
2. その後、各セッションID×chについて、利用可能な全Setの有限・正の未平滑8–10 Hz PSDをプールする。`x=log10(PSD)`、`T=mean(x)+3×SD(x,ddof=1)`、`x>T`の上側窓だけをそのchでNaNにする。
3. **保存済みのPhase 1区間maskと帯域固有log3SD maskを再適用してからROIを計算する。** 元cacheにmask前PSDが残っていることは、不良区間を今回の解析へ含める意味ではない。

log3SDはSetごとでもROI平均後でもなく、条件を混ぜないID・chごとの全Set基準。下側足切り、空間外れ値mask、追加ch除外は導入しない。ICA学習用ch除外maskは監査情報であり、PSDのch削除には使わない。前処理の区間除外を考慮しながらPSD時間変化を扱う従来方針を維持する。

## 4. ROI平均・変化率・平滑化の順序

### 4.1 ch平均

各時刻tの両mask後の有限ch集合を`V(t)`、要素数を`n(t)`とする。

```text
ROI_PSD(t) = sum(PSD_ch(t), ch in V(t)) / n(t)    if n(t) >= 1
ROI_PSD(t) = NaN                                 if n(t) == 0
```

- 10chすべて有限なら10ch算術平均、1–9chだけ有限ならそのchだけの等重み平均。NaNを0にして常に10で割らない。
- 「最低3ch」「常に全10ch」などの新しいquorumは設けない。chの欠測を別時刻・近傍chで補間しない。
- **ch別log3SD除外→ch平均→平滑化**の順を固定する。先にch別平滑化して平均する方式とは、NaNがある場合に一致しない。
- `BeforeThresholdExclusion`はPhase 1 mask後・log3SD前の各chを平均、`AfterThresholdExclusion`は両mask後の各chを平均する。どちらも未平滑。

### 4.2 No12_subのbaseline

各セッションIDの両mask後・ch平均後のROIについて、**Set 1全時間の有限な未平滑ROI値の算術平均**を`B_ROI`とする。

```text
PSD Change(t) = (ROI_PSD(t) / B_ROI − 1) × 100
```

- 先にch平均してからbaselineと変化率を求める。**各chをSet 1比へ変換してから平均する方法ではない。** chごとのbaselineの平均や、群平均baselineを代用しない。
- Eye Drop／Controlそれぞれ自身のBを使い、有限・正を検証する。小さい正baselineだけを理由に新たに除外しない。
- Set 1未平滑変化率の平均が数値誤差内で0であることを確認する。Set 1も個人・群図・全Set統合に含める。
- baseline、有効窓数、除外理由、source識別子はSubに記録し、別のローカル変化率cacheは作らない。

### 4.3 時間変化用の平滑化

No12はROI絶対PSD、subは変化率へ変換したROIを、各Set内で`pd.Series(...).rolling(window=60,center=True,min_periods=1).mean()`により平滑化する。

- 1秒PSD gridの**60点**を「60秒平滑化」と呼ぶ既存方式。Set末尾追加点も等重み1点なので、厳密なtimestamp幅60秒とは区別する。
- NaNを除いて平均し、1点以上有限なら算出、窓全体NaNならNaN。廃止した30点以上の条件を戻さない。
- Set境界をまたがず、端は利用可能範囲だけ。中心がNaNでも近隣に有限値があれば描画値は得られる。欠測を元PSDへ書き戻して補ったことにはならない。
- 平滑化後にprogress上へ表示・位置合わせする。**定量化には平滑化前のROI値**を使う。

### 4.4 ROI品質監査と限界

時点ごとの有効ch数0–10と構成を保存する。構成maskは固定順`[F3,Fz,F4,FC5,FC1,FC2,FC6,C3,Cz,C4]`に対応し、bit 0–9を同順で記録する。全10chが有効ならbitmask=1023。256以上も失わない整数型（uint16以上）を使い、旧5bitの監査と混在させない。Setごとに各有効ch数の窓数・率、chごとの残存率、全欠測窓数を集計する。閾値前／後を混同しない。

chが欠けるとROIの構成・相対重みが時間的に変わる。平均化はノイズの消失や信号品質を保証せず、1chの大きな残存値や複数chに共通するノイズも影響し得る。比率変化は小baselineで拡大し得る。今回はこれらを記録・解釈上の注意とし、結果を見て閾値や採用chを個別変更しない。

## 5. Grand-average・定量化・統計

### 5.1 Grand-average

各条件・Setの平滑化後ROI系列を、既存No10／No11と同じ補間関数で`np.linspace(0,100,100,endpoint=False)`の100点へ対応づける。Set境界・既知欠測Setをまたいで補間しない。既知欠測は両条件同時に外し、製品別・条件別・各progress点の有限被験者を等重み平均する。平均、標本SD（ddof=1）、N、SEM=SD/√Nを保存し、N=1は平均のみ、SD／SEMはNaN。

subは個人・条件別ROIのbaseline変換を済ませてから集計する。群PSDを群baselineで割らない。各Setの100点化は描画・群位置合わせ用で、定量化には用いない。

### 5.2 被験者別定量値

- Set別：当該Set全時間の有限な**未平滑ROI PSD／PSD Change**を算術平均。
- 全Set統合：両条件共通の利用可能Setに属する有限な未平滑窓を連結して平均。Set平均を単純再平均しない。subもSet 1を含む。
- ROI有効ch数にかかわらず、有限な各時点のROI値を等重み平均する。10chが有効な時刻を10倍重く扱わない。ch×時間を一括平均する方法とは区別する。
- バーは被験者間平均、点は被験者の定量値、細線は同じ被験者の条件対応。片条件の定量値が非有限なら、その比較は両条件とも除く。時間窓や電極を独立被験者として扱わない。

### 5.3 統計と表示

- 共通`paired_statistics.py`の`scipy.stats.ttest_rel`、**両側対応ありt検定**。差方向Eye Drop−Control。
- N、t、df、未補正p、平均差、差の標本SD、95% CI、Cohen's dzを保存。
- 主PNGは未補正p。CSVは未補正・Bonferroni・Holm・Benjamini–Hochberg FDRを併記。
- familyは解析×製品ごと。No12は6 Setの6検定、subはSet 2–6の5検定。sub Set 1は`Baseline`表示で検定しない。
- 全Set統合は1検定で補正しない。探索的な複数比較であり、未補正pや図の方向だけを製品効果の確証としない。

## 6. 配色（No12・No12_sub共通）

| 条件 | 時間変化・Grand-average線 | 定量化バー・点 |
|---|---|---|
| Control | `#402B5D` | `#66547D` |
| Eye Drop (C Cube) | **`#4B4B4B`** | **`#787878`** |
| Eye Drop (V Rohto Premium) | **`#909090`** | **`#B0B0B0`** |

利用者承認済みのチャコール／ミディアムグレー。Controlは他解析と共通の深紫、点眼色はNo12固有。定量化は線色より淡くし、同じ製品・解析の対応を保つ。実画像で白背景上の識別性を確認する。

## 7. Figure仕様・読み方

共通：Arial、白背景、180 dpi、英語ラベル、上付き²。上・右spineなし、軸線1.5 pt。別フォントへ黙ってfallbackしない。参加者タイトル・N説明は追加しない。

### 7.1 個人時間変化・Grand-average

| 要素 | No10／No11と同じ固定値 |
|---|---|
| サイズ | 24×8 inch |
| 横軸 | `Experimental Progress, %`、0–600、50刻み |
| Set境界 | 100–500、`#9E9E9E`破線、1.5 pt |
| Set名 | x=50,150,…,550、axes y=.96、22 pt |
| 軸名／目盛／凡例 | 28／20／20 pt |
| 線 | 3.0 pt、alpha=1、Controlを先に描く |
| 凡例 | 上中央、anchor=(.5,1.18)、2列、枠なし |
| 条件ラベル | `Eye Drop (C Cube)`／`Eye Drop (V Rohto Premium)`、`Control` |
| 余白 | left .08／right .99／top .78／bottom .20、tight保存 |
| 縦軸 | No12 `PSD (µV²/Hz)`、sub `PSD Change, %` |
| 群SEM帯 | 線と同色、alpha=.18、境界線なし |

2条件の線はいずれも10chのROI系列。Setはそれぞれ100 progress幅であり、実時間長は被験者・Set・条件で異なる。個人図は同じ人の2条件、群図は製品別の被験者間平均。

| 図 | y軸規則 |
|---|---|
| No12個人 | 下限0、描画系列最大M/.70以上の切りのよい上限 |
| No12群 | 下限0、最大mean+SEMをMとしてM/.75以上。2製品共通 |
| sub個人 | 0中心上下対称、描画系列最大絶対値が半軸の約70% |
| sub群 | **平均線**の最大絶対値が半軸の約70%、上下対称・2製品共通 |

未平滑図の上限はその図自身のROI値から計算。95%例外・固定上限は使わない。No12目盛は3–6個、候補1,2,2.5,5×10ⁿから5個に近い間隔。subは既存対称軸関数の3–7個候補から5個に近い間隔、候補1,2,2.5,4,5,10×10ⁿ。No12に横グリッドは加えず、subは0に薄灰線。sub群のSEMが軸外なら保存値をclipせず、その事実を記録する。

### 7.2 Set別・全Set統合定量化

- Set別34×9 inch、6パネル横一列、共通y軸、全パネルにy目盛。全Set統合7.5×9 inch、1パネル。
- 左Eye Drop／右Control。中心±.32、bar幅.42、x範囲±.90、bar alpha=.82、枠`#222222`・1 pt。
- 点サイズ150、alpha=.68、白枠1.2 pt。対応線`#777777`・1.2 pt・alpha=.34。
- jitter±.055、ペア内同offset、seed=4000+Set番号／全Set版7001。
- 条件名22 pt、Eye Drop直下の括弧付き製品名18 pt、軸名30 pt、目盛23 pt、Set名26 pt。
- Set別余白L .06／R .995／T .94／B .25／wspace .24。全Set版L .20／R .98／T .94／B .25。
- ブラケット黒2.2 pt、capはNo12でaxes高さ.018、subで.02。n.s.26 pt・normal、アスタリスク42 pt（No12 bold／sub normal）、Arial。
- p<.05=`*`、p<.01=`**`、p<.001=`***`、それ以外`n.s.`。sub Set 1は`Baseline`で、非有意の意味ではない。

| 要素 | No12 | No12_sub |
|---|---|---|
| M | 表示する個人定量値の最大 | max(個人最大値, 2×abs(min(個人最小値,0))/1.54, 1) |
| 黒線 | 1.13M | 1.15M |
| アスタリスク | 中心1.17Mからaxes高さ.018下へ光学補正 | **bottom anchor 1.08M** |
| n.s. | 中心1.18M | **bottom anchor 1.20M** |
| Set名 | 中心1.29M | 中心1.42M |
| 上限／下限 | 1.37M／0 | 1.54M／−上限÷2 |

No12の実アスタリスク中心は`1.17M−.018×(y上限−y下限)`。n.s.へ光学補正を加えず、subのbottom anchorを中心指定へ読み替えない。定量化目盛は3–6個、0を含む切りのよい等間隔。統合パネルは`All Sets`、縦軸単位は時間変化と同じ。

## 8. スクリプト・再現・将来の追加除外

入口は`解析プログラム/Phase4_脳波解析/Phase4_No12_FrontalROILowAlpha.py`と`Phase4_No12_sub_FrontalROILowAlphaChange.py`。共通helper `phase4_no12_cached_analysis.py`でROI処理を行い、No10生成設定の検証namespaceとNo12出力設定を分離する。既存No1–11の計算・出力を変更しない。

- cache検証・ROI計算、個人図、群集計・定量化・統計を工程別に実行可能にする。図調整だけで元PSDを再計算しない。
- 各入口は`--manifest <CSV> --production-batch`と、`--preflight-only`／`--individual-only`／`--group-outputs-only`／`--all`を使う。subの`--set-quantification-only`は既存の限定モードで、Set別6パネルPNGだけを対象にし、全工程の代用にしない。
- 一括管理は`run_phase4_no12.py --execute --manifest-source-audit <当日の対応表照合JSON>`。**完了済み旧5電極版から10電極版へ移行する今回だけ**、`--execute --replace-five-channel-version --manifest-source-audit <当日の対応表照合JSON>`を用いる。新しいlive照合JSONを先に検証し、旧実行記録が`completed`かつ旧5電極の完全一致であることを確認してから、旧非PNGを履歴へ分離する。完了版の暗黙の上書きや、10電極完了版へのこの移行flagの再使用は拒否する。出力フォルダの事前準備は同runnerの`--prepare-only`。同じ実装のpreflight→少人数試行→本番全員→独立監査を実行する。
- 独立照合は`validate_phase4_no12_outputs.py --manifest <CSV> --report <No12/Sub/logs内JSON>`。最終の画像・文書・Notion・テスト・Git照合をまとめた後、runnerの`--complete-verification --review-manifest <確認JSON>`で引渡し記録を確定する。数値実行成功とGit公開確認を別段階として扱う。
- 実装版は本体`20261116_frontocentral_roi10_lowalpha_cached_v2`、sub `20261116_frontocentral_roi10_lowalpha_change_cached_v2`。仮想1系列の内部名は`FrontalROI`。出力設定hashにはROI・演算順序・配色と、実装helper／継承するNo1本体・sub／No11描画helperのsource SHAを記録し、元No10 cacheの設定hashとは分ける。
- 全対象へ同じ版・同じ固定パラメータを適用する。少人数試行の後も個人専用の変更を残さず、全員を同じentrypointから処理する。
- runtimeはrepositoryの`.venv/bin/python`。実装・実行前に[Python環境](Python環境.md)を確認する。コマンド・版・source hash・出力hash・警告・失敗・再実行理由はSubへ記録する。
- 初回は追加除外なし。既存No10／No11／topographyの指定集合を読んで自動適用しない。後日、ROIの信号品質に基づく新しい指定が確定した場合だけ、主結果・個人図を保持して追加版を実装する。
- 将来の指定版はGrandAverage直下に識別suffix付きPNG、定量化は`SetQuantification/SpecifiedPairsExcluded/`。追加版の数値・軸・統計は残存ペアから再計算し、採否・理由を分離記録する。**今回このフォルダ・追加図は生成しない。**

## 9. 保存先・フォルダの読み方

親は許可済みOneDrive `実験本番_本解析/Phase4_脳波解析/`。No10／No11と並列に置き、No11の主要版構造へROI監査だけを追加する。

```text
No12_FrontalROILowAlpha/
  CCube/                          # VRohtoPremium/も同じ
    Individual/
      Unsmoothed/
        BeforeThresholdExclusion/ # Phase 1後・log3SD前のROI、未平滑
        AfterThresholdExclusion/  # 両mask後のROI、未平滑
    GrandAverage/                 # 両mask後ROI・60点平滑化、平均±SEM
    SetQuantification/            # Set別・AllSets PNG＋Set別統計CSV
  VRohtoPremium/
  Sub/
    tables/
      GrandAverage/
      Log3SDThresholdExclusion/
      ROIQuality/
      SetQuantification/
    logs/
    history/Pilot/                # 少人数試行CSVのみ、元のtables相対パスを保持
No12_sub_FrontalROILowAlphaChange/
  CCube/                          # VRohtoPremium/も同じ
    Individual/                   # ROI Set 1変化率・60点平滑化
    GrandAverage/
    SetQuantification/
  VRohtoPremium/
  Sub/
    tables/
      Set1Baseline/
      GrandAverage/
      ROIQuality/
      SetQuantification/
    logs/
    history/Pilot/                # 少人数試行CSVのみ、元のtables相対パスを保持
```

- 個人ごとの下位フォルダは作らずPNGを直接並べる。Individual・GrandAverageはPNGだけ。Topography・TFM・固定軸・平滑化比較フォルダは作らない。
- 個人名：`ID<初回>-<2回目>_<stem>_Individual.png`。未平滑版は`_Unsmoothed_BeforeThresholdExclusion`／`_Unsmoothed_AfterThresholdExclusion`を追加。
- 群名：`<stem>_GrandAverage_<製品>.png`。定量化：`<stem>_SetQuantification_<製品>.png`／`<stem>_AllSetsQuantification_<製品>.png`。製品は`CCube`／`VRohtoPremium`。
- **Set別統計CSVは製品別SetQuantification直下**。全Set統合統計CSV・被験者定量値は`Sub/tables/SetQuantification/`、群値は`Sub/tables/GrandAverage/`。No10／No11の細部を維持する。
- ROI品質のCSVは`Sub/tables/ROIQuality/`、baselineはsubの`Sub/tables/Set1Baseline/`。補助表はデータ生成の由来・再現監査用であり、新しいPSD正本ではない。
- ROI監査は`<stem>_ROIWindowQuality_<scope>.csv`に閾値前後の有効ch数・10bit構成mask・中心時刻／sample・progress、`ROISetQuality`に0–10chの窓数・率、`ROIChannelCoverage`にch別残存率を記録する。本体の全員scopeは`AllParticipants`（80セッション）、subは`AllAnalysablePairs`（baseline適格78セッション）。元cache検査は両方とも全80件が対象。絶対PSDの`Log3SDThresholdExclusion/`は元10chの閾値監査であり、新しいROI用log3SD閾値を作らない。
- manifest・source照合・実行設定・警告・独立監査・実画像確認・成果物hashはSubに保存する。新しいローカル派生cacheは作らない。
- 少人数試行scopeの監査CSVは、本番の全員scope表と混在させず、各Noの`Sub/history/Pilot/<元のtables相対パス>`へhashを照合して移管する。対象はrunnerが特定した試行CSVのみ。旧5電極の非PNG表・ログ・旧Pilotは、元の相対階層を保って`Sub/history/BeforeROI10_20261116/<元の相対パス>`へhash付きで隔離する（旧Pilotはその下の`Sub/history/Pilot/`）。この移管で空いた通常`Sub/history/Pilot/`には10電極版の試行CSVだけを置く。新しいlive照合JSONは新世代の入力として保持する。本番PNGは履歴へ複製・事前削除せず、同名の10電極版へ上書きする。元No10 cache・他Noは変更しない。

## 10. 記録・検証・完了条件

NotionはPhase 4親のNo12／No12_sub概要、専用子ページの詳細方法・別節の結果、さらに分離した意思決定履歴として管理する。日次ログや全被験者結果DBを新設しない。GitHubは本書を現行統合仕様、historyを議論・旧判断とする。実数Nや検証済み件数は実行後だけ追記し、旧5電極No12やNo10／No11の過去実績を現行10電極版へ転記しない。

1. live対象・条件・製品・manifestと全80 source cacheの属性・設定・source fingerprintを照合。
2. 10chの実在・名前・時刻一致、Phase 1 maskとch別log3SD再適用を確認。元cache・他解析の不変を検証。
3. 独立処理で有効ch平均を再構成。1–10ch平均・全NaN・構成mask・n(t)・閾値前後・Set率の整合を検証。
4. ROI自身のSet 1平均、変換順序、baseline有効性、Set 1平均0を確認。ch別変化率平均に誤置換していないことを合成例でもテスト。
5. 未平滑Set／AllSets値、paired欠測、60点平滑化後100点化、群mean／SD／SEM／Nを独立照合。
6. 対応ありt検定・差方向・補正family・統計CSVを独立再計算。
7. 全PNGの命名・件数・読込・寸法・保存階層を機械検査。全群図と代表個人図を実画像で確認し、Arial・色・ラベル・ROI・軸比率・統計表示・重なりを評価。全件機械確認と抜粋目視を区別。
8. 未指示の除外版・topography・TFM・別No成果物の混入なし。元cache・他No成果物の不変を確認。
9. Notionを読み戻し、対象明示stage、検証、commit、push、remote SHA一致を確認して完了。OneDriveローカル保存とサーバー同期は別の確認として扱う。

## 11. 実行結果・検証（現行10電極版）

### 11.1 実行範囲・保存状態（2026-11-16）

10電極版の正常終了runは**16:35:05–16:35:44 JST**。同一runner・入口でpreflight、少人数試行、No12本体／subの全員処理、独立数値監査を順に実行し、全工程終了コード0。`No12_ExecutionAndVerification.json`の数値実行完了時の状態は`numerical_execution_and_output_audit_passed`、`No12_IndependentValidation.json`は`passed`。その後の引渡しゲート通過時に前者を`completed`へ更新する。元EEGのWelch再計算や新しいPSD cacheは作っていない。

| 項目 | 10電極版の確認結果 |
|---|---|
| 入力 | No10の80 HDF5・476実在Setを読み取り専用で使用。8/9/10 Hz・10ch実在・mask・時刻・由来を確認 |
| No12 | 全40ペア、126 PNG＝個人3種×40＋Grand-average2＋定量化4 |
| No12_sub | baseline適格39ペア（Cキューブ20／Vプレ19）、45 PNG＝個人39＋Grand-average2＋定量化4 |
| 総PNG | **171枚**。全件の名前集合・読込・寸法・指定保存先を機械確認 |
| 追加除外 | なし。既知Set欠測とsub baseline要件のみ |
| 旧世代分離 | 旧5電極の非PNG50件を`BeforeROI10_20261116`へhash確認付きで分離。旧PNGは同名の10電極版へ上書き |
| 新世代試行 | 10電極の試行専用CSV7件を通常`Sub/history/Pilot/`へ分離。本番全員scopeの表・図は10電極版 |

1回目は本番描画後の検証console書込みで`TimeoutError: [Errno 60]`となった。数値不一致による失敗ではない。runnerのログ保存をバッファ後の一括書込み・読戻しへ変更し、失敗runを`Sub/logs/attempts/20261116T163505/`へ分離してから全員処理を再実行した。失敗の工程と現行の正常終了結果を混在させない。

### 11.2 対応のある有効N

Set別は両条件の定量値が揃うペア数、全Set統合は両条件共通の利用可能Setを持つペア数。全6 Set完備数ではない。Grand-averageのprogress点別Nは別CSVへ保存する。

| 解析 | 製品 | Set 1→6のpaired N | 全Set統合N |
|---|---|---|---:|
| No12 | Cキューブ | 20・20・20・20・20・19 | 20 |
| No12 | Vプレ | 19・19・20・19・20・20 | 20 |
| No12_sub | Cキューブ | 20・20・20・20・20・19 | 20 |
| No12_sub | Vプレ | 19・18・19・18・19・19 | 19 |

sub Set 1はbaseline有効人数で、t検定を実施したNではない。既知欠測は両条件対応で維持した。

### 11.3 有効ch構成と欠測

両mask後の全80セッション・**315,166 PSD窓**について確認した。窓数割合であり、厳密な実時間割合・被験者除外率ではない。

| 有効ch数 | 窓数 | 全窓比 |
|---:|---:|---:|
| 0 | 20,785 | 6.59494% |
| 1 | 75 | 0.02380% |
| 2 | 64 | 0.02031% |
| 3 | 40 | 0.01269% |
| 4 | 58 | 0.01840% |
| 5 | 50 | 0.01586% |
| 6 | 65 | 0.02062% |
| 7 | 102 | 0.03236% |
| 8 | 185 | 0.05870% |
| 9 | 629 | 0.19958% |
| 10 | 293,113 | 93.00274% |

有限ROIは294,381窓。そのうち全10ch有効が99.56927%、1–9ch平均は1,268窓・0.43073%。10bit構成（全有効1023）、時点別有効数・Set集計・ch別残存率を保存した。構成変動が少ないことは、残存ノイズ不存在やROIの生理的妥当性の保証ではない。

### 11.4 観察結果・統計と解釈の限界

以下は被験者ごとの**全Set統合の未平滑ROI定量値**の被験者間平均±SEM。平滑化後のGrand-average線の時間平均ではない。

| 解析・製品 | Eye Drop平均±SEM | Control平均±SEM | Eye Drop−Control平均差 | 未補正p |
|---|---:|---:|---:|---:|
| No12・Cキューブ（µV²/Hz） | 10.22584 ± 3.92819 | 7.69028 ± 2.41543 | +2.53557 | 0.13468 |
| No12・Vプレ（µV²/Hz） | 9.18617 ± 2.46893 | 9.54901 ± 2.53168 | −0.36284 | 0.72414 |
| sub・Cキューブ（%） | 20.14524 ± 6.73158 | 41.74055 ± 10.15218 | −21.59531 pp | 0.04004 |
| sub・Vプレ（%） | 30.53381 ± 6.03582 | 42.44546 ± 14.61112 | −11.91164 pp | 0.36617 |

- Set別の未補正p<.05は**sub・CキューブSet 4のみ**。Eye Drop 22.95292 ± 8.22736%、Control 63.49041 ± 16.59795%、差−40.53749 pp、N=20、p=.02722。Bonferroni／Holm p=.13609、BH-FDR p=.10795で、3種補正後は非有意。
- 全Set統合のsub・Cキューブはp=.04004。これはSet別familyとは別の1検定であり、現行仕様どおり多重比較補正なし。その他の全Set統合、その他のSet検定は未補正でもp≥.05。sub Set 1は検定しない。
- Vプレの効果、条件同等性、効果不存在をこれだけで確定しない。topographyを参照した事後ROI選定・未補正比較を含む探索であり、独立した確認的検証ではない。
- 旧5電極版の値は履歴専用。本表に混在させない。参考topography値のch平均とも、演算順序・採否が異なるので一致を要求しない。
- Phase 1の要確認記録はsource監査へ残し、今回のROIへ追加除外を自動転用しなかった。数値検証はノイズがないことを診断したものではない。

### 11.5 独立検証・保護範囲

- 80 source cacheからPhase 1 mask→ch別log3SD→有限ch平均→ROI baseline→平滑化→群値／未平滑定量化／統計を独立再構成し、**24 CSV**と一致。ROI有効数・bit構成、Set 1平均0、対応ありt検定、3種補正も確認した。元EEGからWelchを再計算した監査ではない。
- 本体の時点品質315,166行・Set品質476行・ch品質4,760行、subの時点品質308,630行・Set品質465行・ch品質4,650行を確認した。旧5chのmask幅・値を流用していない。
- 全171 PNGの機械確認に加え、**全12群PNG＋代表個人7 PNG＝19枚**を実画像で確認した。4群時間変化図、8定量化図に加え、両製品の個人・既知欠測・閾値前後・subの代表例を確認。全個人の信号品質を目視診断した意味ではない。
- No12 Grand-averageは両製品共通**0–30 µV²/Hz、目盛0・10・20・30**、subは両製品共通**−200〜200%、100刻み**。平均線・SEM帯の切れなし。10電極の表示値から再設定した軸であり、旧5電極subの±150を固定継承していない。
- 定量化はsub CキューブSet 4・All Setsのアスタリスク、Set 1の`Baseline`、統計線・Set名・条件名／製品名の位置とサイズを確認し、重なりなし。Arialの実体は`/System/Library/Fonts/Supplemental/Arial.ttf`。配色・単位・目盛・凡例も確認した。
- **pytest 511 passed、91.47秒、Ruff成功。** 4 warningsは他の既存sensitivity空集合テスト由来で、今回の数値不一致や本番失敗ではない。別担当の独立コードレビューでも仕様・実装の一致を確認した。
- 元80 cacheのSHA-256と、他Noを含む保護対象**2,763ファイル**のSHA-256が前後一致。No10／No11、他解析、原データは不変。No12本体／sub以外へ今回の出力整理・削除を拡張していない。
- 保存・読戻しは許可済みOneDriveローカル同期フォルダで確認した。**OneDriveサーバー側同期完了は独立確認していない。**

### 11.6 証跡・最終公開確認

- `Sub/logs/ROI10SourceAudit.json`／`ManifestSourceAudit.json`：live条件・製品・採否・manifest照合。
- `No12_ROI10Replacement.json`：旧非PNG50件・SHA-256・旧PNGの置換前識別・新旧ROI。
- `No12_ExecutionAndVerification.json`：正常終了runのコマンド・時刻・console・source／出力／保護hash・試行分離。失敗runは`attempts/`へ分離。
- `No12_IndependentValidation.json`：24表の独立照合、ROI構成、Set別N、全PNG検査。
- `No12_Pytest.xml`／`No12_ReviewManifest.json`／`No12_DeliveryVerification.json`：最終試験、19画像・文書・Notionの確認、数値再照合・保護hash・Git公開SHAの引渡し証跡。
- 各Noの`<stem>_RunSummary.json`：実行版・対象・設定・source・出力。数値正本は現行Sub表と製品別SetQuantification統計CSV。
- 最終テスト・画像・Notion読戻し・Git commit／push／remote一致は引渡し確認へ記録する。**数値実行成功だけをGit公開やクラウド同期完了の根拠としない。**
