# Phase 4 No4・No5：Fz序盤PSD Change｜解析仕様

## 状態と目的

2026-11-08にNo4・No5を同じ共通エンジンで全対象に実行し、図と数値表を指定OneDriveへ保存した。本書はその実装済み仕様である。No1_sub／No3_subの確定済み成果物を変更せず、同じSet 1基準変化率を使い、各Set序盤に限定した点眼条件差を探索する。Vロートプレミアムで点眼直後の前頭低周波パワーが相対的に低いかを見て、同じ定義でCキューブも比較する。疲労・眠気の改善や点眼の因果効果を、この指標だけで断定しない。

| 解析 | 代表ch | 帯域 | 入力（読み取り専用） | OneDriveルート |
|---|---|---|---|---|
| No4 | Fz | 4–7 Hz（7 Hzを含む） | ローカル `Phase4_脳波解析/No1_FmTheta/PSDTimeSeries/` | `Phase4_脳波解析/No4_FzThetaEarlyChange/` |
| No5 | Fz | 1–3 Hz（3 Hzを含む） | ローカル `Phase4_脳波解析/No3_FrontalDelta/PSDTimeSeries/` | `Phase4_脳波解析/No5_FzDeltaEarlyChange/` |

新しいWelch PSDやローカル派生cacheは作らない。既存HDF5の元PSD、Phase 1区間mask、セッションID・ch別の全Set一括log10上側3SD mask、時刻、progress、設定hashを検証して再利用する。No1_add／No3_addの1–30 Hz TFM cacheは帯域別No4・No5定量値の入力には使わない。

## 計算の順序

1. 非公開manifestの `first_session_id,second_session_id,drops_session_id,product` で被験者ペア・Eye Drop／Control・使用製品を確定する。100番台／200番台だけで条件を推定しない。
2. No4はNo1、No5はNo3のcacheからFzの未平滑・線形PSD（µV²/Hz）を読み、既存仕様のPhase 1区間maskとlog10上側3SD maskを適用する。時刻は前詰めせず、除外窓をNaNとする。チャンネル除外maskによる追加除外はしない。
3. 各セッションID・Fzについて、mask後のSet 1にある有限PSDの平均をbaselineとする。baselineが有限かつ正であることを検証する。
4. 各1秒PSD窓を `PSD Change = (PSD / baseline - 1) × 100` に変換する。条件間・被験者間でbaselineを共用しない。変換は平滑化前に行う。
5. 個人の全時間変化figureは、変化率をSetごとに実時間60秒の中心化単純移動平均にした後、Setをまたがず0–100% progressへ対応付けて描く。NaNを無視し、平滑化窓の全値がNaNの場合だけ出力もNaNとする。1ペアの2条件を1枚に描く。
6. Grand-averageは、個人の平滑化後系列を各Setの100 progress点へ対応付けてから、製品群・条件・Set・progress点ごとに被験者間平均し、平均±SEMと有効Nを求める。
7. 序盤定量化は、**平滑化前**のPSD Changeを各Set内で時間平均する。保存済み`set_progress_pct`で、前半は `0 ≤ progress < 50`、最初の4分の1は `0 ≤ progress < 25`、比較用の全Setは `0 ≤ progress ≤ 100` とする。各範囲の有限な1秒窓の算術平均を、被験者・条件・Set別の代表値とする。3種類を同じデータから計算し、progressを正規化してから窓を切り出さない。
8. Set 1の全Set版は定義上ほぼ0%となる一方、Set 1の前半・最初の4分の1は全Set平均からの偏差なので0%とは限らない。これらを「点眼直後の効果」と自動的に解釈しない。
9. 追加の**セット境界定量化**は、同じ未平滑・mask後のPSD Changeを用い、隣接する5境界（Set 1→2～5→6）を調べる。50%版は前Setの `50 ≤ progress ≤ 100` と次Setの `0 ≤ progress < 50`、25%版は前Setの `75 ≤ progress ≤ 100` と次Setの `0 ≤ progress < 25` の有限1秒窓を、それぞれ時間平均する。各条件の値を「次Set序盤平均 − 前Set終盤平均」（単位はpercentage point、pp）とする。さらに同一被験者内で `Eye Drop − Control` の境界変化差を求める。Setをまたぐ平滑化や時間軸の前詰めはしない。

## 欠測、比較、外れ値

- Set 1欠測の109–209ペアはbaselineが定義できないためNo4・No5全体から除外する。その他の既知欠測Setは、個人figureでは欠測した条件だけを空白にし、Grand-averageと定量化では対応条件側も同じSetを除外する。NaNを0や隣接Setで置換しない。
- CキューブとVロートプレミアムを分け、各群内でEye DropとControlを被験者内対応で比較する。各定量化範囲・Setについて、両条件が有効なペアだけを集計しNを記録する。
- セット境界では、前後2 Setが両条件で利用可能な被験者ペアだけを採用する。一方に欠測Setがあれば、その境界は両条件ともNaNとして集計しない。有限窓が片側に存在しない場合も境界値をNaNとする。製品×境界×窓幅ごとに対応ありN、条件別平均・SD、被験者内差の平均を保存する。
- 全員・全有効Setの結果を主表示として残し、主結果には追加の外れ値被験者除外をしない。Vロートプレミアム群だけに、目視で懸念が挙がったNo4の135–235、No5の101–201をペアの両条件から外す**事後・探索的な感度分析**を追加した。これは一般的な外れ値判定規則ではなく、個人値の生理的・ノイズ由来も確定しない。主結果・感度分析とも推測統計と統計マークは付けない。
- No1_sub／No3_subのtopography感度分析に用いた全32chの判定基準を、Fz単一chのNo4・No5に自動流用しない。

## Figureと補助QC

- `Individual/`：Fzの全Set（0–600%）をつなげたPSD Change時間変化。1被験者ペアにつきEye DropとControlを同一図へ描く。
- `GrandAverage/`：製品群別の全時間変化、平均±SEM。Set別Nを記録する。
- `SetQuantification/`：全Set、前半、最初の4分の1の3定義をファイル名で区別した6 Set横並び比較。被験者の対応する2点とバーを描く。確定前の統計マークは付けない。
- `BetweenSetQuantification/`：前Set終盤→次Set序盤の50%版・25%版を別PNGとし、5境界を横並びに表示する。バーは条件内の被験者間平均、点・結線は被験者内対応。縦軸は `Transition in PSD Change (pp)`。推測統計と有意記号は付けない。
- `SensitivityAnalysis/`：空。今回の指定ペア除外版は比較しやすいよう、Vロートプレミアム群の既存 `SetQuantification/` と `BetweenSetQuantification/` に `ExcludePair...` を付けて主結果と並置する。
- Fzの個人1–30 Hz TFMは既存No1_add／No3_addで**出力されていない**。保存済みTFM cacheから将来個人QC図を追加することは可能だが、No4・No5の帯域定量化とは別物である。今回のNo4・No5では個人TFMを生成していない。
- 図の基本様式（Arial、英語の軸・凡例、Set境界、文字サイズ、線幅）はNo1_sub／No3_subの確定仕様を継承する。個人・Grand-averageは24×8 inch、180 dpi、線幅3.0 pt、Set名22 pt、軸名28 pt、目盛20 pt、Grand-averageは平均±SEM。Grand-averageは2製品で共通の対称y軸とし、平均線の最大絶対値が約70%の位置に来る規則を継承する。SEMとSet名の重なりを避けるためSet名に薄い白背景を付ける。
- 条件色はNo1～No3の点眼色との重複を避ける。No4の点眼はCキューブ `#2679A8`、Vロートプレミアム `#3AA4B8`、No5はそれぞれ `#347C62`、`#66A86B`。Controlは既定 `#402B5D`。定量化のバー・点はNo4が `#5A9FC3`／`#70B7C3`、No5が `#60A184`／`#87BC8B`、Controlは `#66547D`。定量化は34×9 inch、180 dpi、バー幅0.42、点サイズ150、軸名30 pt、目盛23 pt、Set名26 pt、横軸条件名22 pt、製品名18 pt。ペア点を薄い線で結び、各ペアの点は再現可能な固定シードのジッターで左右へ散らす。
- y軸は0を含み、既存No1_subの `_quantification_layout` に従って表示値全体から下限・上限・3～6個の目盛りを決める（下側は上限の約半分の広さであり、厳密な対称軸ではない）。感度分析図では除外後の値でこの設定を再計算する。図のタイトルは定量化範囲を `Full Set`、`First 50% of Each Set`、`First 25% of Each Set` で区別する。Set境界は100%ごとの灰色破線。定量化に推測統計・有意記号は今回付けない。
- セット境界図は30×9 inch、180 dpi、5パネルで共通y軸、Arial、既存のバー幅・点・結線・ジッター・製品色を継承する。パネル名は `Set 1 → 2` など。y軸は2条件の被験者値から上記レイアウト規則で決め、全5境界に共通とする。

## OneDriveフォルダ・結果の読み方

各Noで製品群を先に分け、同じ構造にする。`Individual/`、`GrandAverage/`、`SetQuantification/`、`BetweenSetQuantification/` はPNGのみ。主結果の図は変更しない。`SetQuantification/` には定義別の3図、`BetweenSetQuantification/` には50%版・25%版の2図を各製品群で保存する。個人別Set×範囲の数値と有効窓数、製品別平均・SD・paired N、Set 1基準PSD、Grand-averageの100点別平均・SD・SEM・Nは `Sub/tables/`、セット境界のペア別値・製品別集計は `Sub/tables/BetweenSetQuantification/`、実行記録は `Sub/logs/` に保存する。主結果に被験者追加除外はない。指定ペア除外感度分析のVロートプレミアム群だけに各NoでSet別3 PNG・境界別2 PNGを同じ図フォルダへ追加し、除外後の群集計2 CSVと実行JSONを `Sub/` へ追加した。`SensitivityAnalysis/` と `Sub/tables/OutlierReview/` は空のまま。

```text
Phase4_脳波解析/
  No4_FzThetaEarlyChange/
    CCube/{Individual,GrandAverage,SetQuantification,BetweenSetQuantification,SensitivityAnalysis}/
    VRohtoPremium/{Individual,GrandAverage,SetQuantification,BetweenSetQuantification,SensitivityAnalysis}/
    Sub/tables/{Set1Baseline,SetQuantification,BetweenSetQuantification,GrandAverage,OutlierReview}/
    Sub/logs/
  No5_FzDeltaEarlyChange/
    CCube/{Individual,GrandAverage,SetQuantification,BetweenSetQuantification,SensitivityAnalysis}/
    VRohtoPremium/{Individual,GrandAverage,SetQuantification,BetweenSetQuantification,SensitivityAnalysis}/
    Sub/tables/{Set1Baseline,SetQuantification,BetweenSetQuantification,GrandAverage,OutlierReview}/
    Sub/logs/
```

## 実行・検証記録

実行入口は `解析プログラム/Phase4_脳波解析/Phase4_No4_FzThetaEarlyChange.py` と `Phase4_No5_FzDeltaEarlyChange.py`。両者は `phase4_early_fz_change.py` を共有し、全被験者を同じコードのループで処理する。非公開manifestを `--manifest` に指定する。全成果物の再実行は `--production-batch --all`、既存figureを変更せずセット境界のみ追加・更新する場合は `--production-batch --transition-only` を使う。指定ペア除外図だけを保存済みペア別定量値から再生成する場合は `--production-batch --excluded-pair-sensitivity-only` を使い、このモードだけmanifestは不要。指定ペアは共通スクリプト内でNo別に固定し、任意の個人・閾値を引数から指定しない。主解析モードは入力監査と既存No1_sub／No3_subの全Set定量値再現を先に行う。感度分析モードも保存済みペア別値の件数・重複・ペア完全性と全Set値の再現を検証する。

実行前に入力cacheのID・条件・帯域bin・256 Hz・窓長/ステップ256 samples・log10上側3SDの適用範囲・設定hash・Fz列・既知欠測を照合した。40ペアのうちSet 1欠測の109–209のみを除き39ペア（Cキューブ20、Vロートプレミアム19）を実行した。Set 6の120–220、Set 2の135–235、Set 4の125–225は、群集計と定量化で対応する2条件を同じSetから除外した。各Noで個人PNG39枚、製品別Grand-average PNG2枚、製品×3範囲の定量化PNG6枚、計47枚を読戻し確認した。Set 1全Set版の個人平均は数値誤差内で0%。全39ペア×6 Setの全Set定量値はNo1_sub／No3_subの保存CSVと一致した。追加の外れ値除外や推測統計は実施していない。

解釈上の保留点：この段階の図は探索的であり、製品効果の統計的有意性は未評価。目立つ個人値や帯域の変化が生理的由来かアーチファクトかも本解析だけでは確定しない。実行ログの `Sub/logs/No4_FzThetaEarlyChange_RunSummary.json` とNo5の対応ファイルに、方法・対象数・欠測・出力件数・入力先を記録した。

### 追加実行：隣接Set境界の50%・25%定量化

2026-11-08に上記39ペアの保存済みPSDから、No4・No5を同じ共通スクリプトの `--transition-only` で実行した。各Noで製品群×2窓幅のPNG4枚、ペア別CSV（39ペア×5境界×2窓幅=390行）、群集計CSV（2製品×5境界×2窓幅=20行）と実行ログを追加した。前後2 Setを両条件で対応づけられるNはCキューブ19–20、Vロートプレミアム18–19。以前の `Individual/`・`GrandAverage/`・`SetQuantification/` の成果物とローカルPSD cacheは変更していない。

群平均の `Eye Drop − Control` 境界変化差は、VロートプレミアムのSet 2→3でNo4シータが50%版−7.17 pp／25%版−2.19 pp、No5デルタが50%版−18.83 pp／25%版−27.21 ppだった。ただし他の境界では符号が揃わず、個人差も大きい。Cキューブでも境界によって正負が混在した。この探索図だけでは製品効果や点眼時点の即時効果は結論できない。セット境界を点眼時刻と同一視しない。この時点の主結果には追加の外れ値被験者除外と推測統計を適用していない。

### 追加実行：Vロートプレミアム群の指定ペア除外感度分析

2026-11-08に、No4では135–235、No5では101–201が図上で外れ値的に見えたという事前の個別指摘を受け、**Vロートプレミアム群のみ**で各1ペアをEye Drop・Controlの両条件から除く事後感度分析を追加した。Cキューブ、主結果、Individual、Grand-average、ローカルPSD cache、保存済みペア別値は変更していない。これはデータ駆動の一般除外閾値ではなく、特定ペアを外した場合に結果がどれだけ変わるかを示す探索的比較である。

各Noの `Sub/tables/SetQuantification/*_PairSetWindowValues.csv` と `Sub/tables/BetweenSetQuantification/*_PairSetTransitionValues.csv` を読み、入力の39ペア（Cキューブ20、Vロートプレミアム19）とペア×Set×窓の完全性、重複なし、No1_sub／No3_subの全Set値との一致を検証した。該当ペアを両条件から除いて、VロートプレミアムのSet別3定義と境界別2定義を被験者内対応で再集計した。PSD・PSD Change・境界のペア別値を再計算していない。縦軸の上下限・目盛りは、それぞれの除外後の全パネル値で `_quantification_layout` を再計算した。

各NoのVロートプレミアム `SetQuantification/` に `ExcludePair135-235` または `ExcludePair101-201` 付きのPNGを3枚、`BetweenSetQuantification/` に2枚追加した。対応する群平均・SD・paired NのCSVをそれぞれの `Sub/tables/` の同名サブフォルダへ1枚ずつ、入力ファイルのSHA-256・適用ペア・各SetのN・出力件数を `Sub/logs/*_ExcludedPairSensitivityRunSummary.json` へ保存した。通常の無印PNGは残した。除外後のVロートプレミアム候補は19→18ペア、既知欠測のためSet別Nは17–18、境界別Nも17–18。推測統計・有意記号は追加していない。図の変化を製品効果やアーチファクト確定の証拠とは扱わない。
