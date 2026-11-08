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

## 欠測、比較、外れ値

- Set 1欠測の109–209ペアはbaselineが定義できないためNo4・No5全体から除外する。その他の既知欠測Setは、個人figureでは欠測した条件だけを空白にし、Grand-averageと定量化では対応条件側も同じSetを除外する。NaNを0や隣接Setで置換しない。
- CキューブとVロートプレミアムを分け、各群内でEye DropとControlを被験者内対応で比較する。各定量化範囲・Setについて、両条件が有効なペアだけを集計しNを記録する。
- 全員・全有効Setの結果を主表示として残し、今回のNo4・No5では追加の外れ値被験者除外をしない。外れ値感度分析と推測統計の基準・表示は未確定で、今回の図には統計マークを付けない。将来実施する場合は主要結果と分け、除外基準・対象・前後Nを明示する。
- No1_sub／No3_subのtopography感度分析に用いた全32chの判定基準を、Fz単一chのNo4・No5に自動流用しない。

## Figureと補助QC

- `Individual/`：Fzの全Set（0–600%）をつなげたPSD Change時間変化。1被験者ペアにつきEye DropとControlを同一図へ描く。
- `GrandAverage/`：製品群別の全時間変化、平均±SEM。Set別Nを記録する。
- `SetQuantification/`：全Set、前半、最初の4分の1の3定義をファイル名で区別した6 Set横並び比較。被験者の対応する2点とバーを描く。確定前の統計マークは付けない。
- `SensitivityAnalysis/`：今回空。後に外れ値除外を実際に試す場合だけ主表示と分離して保存する。
- Fzの個人1–30 Hz TFMは既存No1_add／No3_addで**出力されていない**。保存済みTFM cacheから将来個人QC図を追加することは可能だが、No4・No5の帯域定量化とは別物である。今回のNo4・No5では個人TFMを生成していない。
- 図の基本様式（Arial、英語の軸・凡例、Set境界、文字サイズ、線幅）はNo1_sub／No3_subの確定仕様を継承する。個人・Grand-averageは24×8 inch、180 dpi、線幅3.0 pt、Set名22 pt、軸名28 pt、目盛20 pt、Grand-averageは平均±SEM。Grand-averageは2製品で共通の対称y軸とし、平均線の最大絶対値が約70%の位置に来る規則を継承する。SEMとSet名の重なりを避けるためSet名に薄い白背景を付ける。
- 条件色はNo1～No3の点眼色との重複を避ける。No4の点眼はCキューブ `#2679A8`、Vロートプレミアム `#3AA4B8`、No5はそれぞれ `#347C62`、`#66A86B`。Controlは既定 `#402B5D`。定量化のバー・点はNo4が `#5A9FC3`／`#70B7C3`、No5が `#60A184`／`#87BC8B`、Controlは `#66547D`。定量化は34×9 inch、180 dpi、バー幅0.42、点サイズ150、軸名30 pt、目盛23 pt、Set名26 pt、横軸条件名22 pt、製品名18 pt。ペア点を薄い線で結び、各ペアの点は再現可能な固定シードのジッターで左右へ散らす。
- y軸は0中心の対称範囲とし、既存No1_subの目盛り規則を利用する。図のタイトルは定量化範囲を `Full Set`、`First 50% of Each Set`、`First 25% of Each Set` で区別する。Set境界は100%ごとの灰色破線。定量化に推測統計・有意記号は今回付けない。

## OneDriveフォルダ・結果の読み方

各Noで製品群を先に分け、同じ構造にする。`Individual/`、`GrandAverage/`、`SetQuantification/` はPNGのみ。`SetQuantification/` には定義別の3図を保存する。個人別Set×範囲の数値と有効窓数、製品別平均・SD・paired N、Set 1基準PSD、Grand-averageの100点別平均・SD・SEM・Nは `Sub/tables/`、実行記録は `Sub/logs/` に保存する。`SensitivityAnalysis/` と `Sub/tables/OutlierReview/` は空であり、今回の主要結果に被験者追加除外はない。

```text
Phase4_脳波解析/
  No4_FzThetaEarlyChange/
    CCube/{Individual,GrandAverage,SetQuantification,SensitivityAnalysis}/
    VRohtoPremium/{Individual,GrandAverage,SetQuantification,SensitivityAnalysis}/
    Sub/tables/{Set1Baseline,SetQuantification,GrandAverage,OutlierReview}/
    Sub/logs/
  No5_FzDeltaEarlyChange/
    CCube/{Individual,GrandAverage,SetQuantification,SensitivityAnalysis}/
    VRohtoPremium/{Individual,GrandAverage,SetQuantification,SensitivityAnalysis}/
    Sub/tables/{Set1Baseline,SetQuantification,GrandAverage,OutlierReview}/
    Sub/logs/
```

## 実行・検証記録

実行入口は `解析プログラム/Phase4_脳波解析/Phase4_No4_FzThetaEarlyChange.py` と `Phase4_No5_FzDeltaEarlyChange.py`。両者は `phase4_early_fz_change.py` を共有し、全被験者を同じコードのループで処理する。非公開manifestを `--manifest` に指定し、`--production-batch --all` で実行する。個別にパラメータや除外対象を変更しない。

実行前に入力cacheのID・条件・帯域bin・256 Hz・窓長/ステップ256 samples・log10上側3SDの適用範囲・設定hash・Fz列・既知欠測を照合した。40ペアのうちSet 1欠測の109–209のみを除き39ペア（Cキューブ20、Vロートプレミアム19）を実行した。Set 6の120–220、Set 2の135–235、Set 4の125–225は、群集計と定量化で対応する2条件を同じSetから除外した。各Noで個人PNG39枚、製品別Grand-average PNG2枚、製品×3範囲の定量化PNG6枚、計47枚を読戻し確認した。Set 1全Set版の個人平均は数値誤差内で0%。全39ペア×6 Setの全Set定量値はNo1_sub／No3_subの保存CSVと一致した。追加の外れ値除外や推測統計は実施していない。

解釈上の保留点：この段階の図は探索的であり、製品効果の統計的有意性は未評価。目立つ個人値や帯域の変化が生理的由来かアーチファクトかも本解析だけでは確定しない。実行ログの `Sub/logs/No4_FzThetaEarlyChange_RunSummary.json` とNo5の対応ファイルに、方法・対象数・欠測・出力件数・入力先を記録した。
