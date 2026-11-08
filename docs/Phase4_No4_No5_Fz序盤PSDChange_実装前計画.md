# Phase 4 No4・No5：Fz序盤PSD Change｜実装前計画

## 状態と目的

本書は実装前の探索計画であり、No4・No5のコード、計算結果、統計的結論はまだ存在しない。No1_sub／No3_subの確定済み成果物を変更せず、同じSet 1基準変化率を使い、各Set序盤に限定した点眼条件差を調べる。Vロートプレミアムで点眼直後の前頭低周波パワーが相対的に低いかを探索し、同じ定義でCキューブも比較する。疲労・眠気の改善や点眼の因果効果を、この指標だけで断定しない。

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
- 全員・全有効Setの結果を主表示として残す。外れ値の探索は個人時系列、Set別値、元の絶対PSD、Fz TFMを照らして原因と影響を記録し、除外対象・基準・除外前後Nを明示した別の感度分析として扱う。除外後だけを主要結果へすり替えない。**除外閾値と統計表示は未確定**であり、実装時に都合のよい基準を暗黙に追加しない。
- No1_sub／No3_subのtopography感度分析に用いた全32chの判定基準を、Fz単一chのNo4・No5に自動流用しない。

## 予定するfigureと補助QC

- `Individual/`：Fzの全Set（0–600%）をつなげたPSD Change時間変化。1被験者ペアにつきEye DropとControlを同一図へ描く。
- `GrandAverage/`：製品群別の全時間変化、平均±SEM。Set別Nを記録する。
- `SetQuantification/`：全Set、前半、最初の4分の1の3定義をファイル名で区別した6 Set横並び比較。被験者の対応する2点とバーを描く。確定前の統計マークは付けない。
- `SensitivityAnalysis/`：外れ値除外を実際に採用して試す場合だけ、除外前の主表示と分離して保存する。
- Fzの個人1–30 Hz TFMは既存No1_add／No3_addで**出力されていない**。保存済みTFM cacheから個人QC図を後で追加することは可能だが、No4・No5の帯域定量化とは別物であり、必要性・表示法・保存先を実装前に確認する。現時点では個人TFMを生成したとは記録しない。
- 図の基本様式（Arial、英語の軸・凡例、条件色、Set境界、文字サイズ、線幅）はNo1_sub／No3_subの確定仕様を継承する。No4はNo1のtheta色、No5はNo3のdelta色、Controlは共通 `#402B5D` を使う。序盤範囲の表示、軸上限、統計表示の細部は試作図で確認してから確定する。

## OneDriveフォルダ（空で先行準備）

各Noで製品群を先に分け、同じ構造にする。`Individual/` と `GrandAverage/` はPNGのみ、`SetQuantification/` は定義別PNGと必要な統計CSV、数値表と実行記録は `Sub/` に置く。フォルダ作成は解析実行や結果生成を意味しない。

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

## 実装前の確認事項

実装前にREADME・運用ルール・解析上の注意事項・本書・Notionの対応ページを再確認する。入力cacheの設定hash／単位／Fz列／既知欠測と条件manifestをpreflightで照合する。全Set・前半・最初の4分の1について有限窓数とpaired Nを残し、Set 1全Set版の平均が数値誤差内で0%であること、No1_sub／No3_subの全Set値を再現することを検証する。今回の作業では解析スクリプトを作成・変更せず、計算・figure出力も行わない。
