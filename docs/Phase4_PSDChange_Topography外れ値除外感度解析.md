# Phase 4 PSD Change topography：条件別・双方向外れ値除外感度解析

## 結論

No1_sub～No3_subのGrand-average topographyで見られた単一chの局所的な突出は、一部の被験者ペア×ch×Setの外れ値が算術平均を引っ張ったことが主要因の一つと判断した。そこで、Eye DropとControlを別々に評価し、Set 1絶対PSD高値、持続的上昇、絶対PSD低値を伴う持続的低下を除外する追加感度解析を確定した。

除外後は外れ値による局所支配が概ね縮小した。ただし、事前仮説どおりの領域特異性が証明されたとは扱わず、特にNo2のVロートプレミアムは残存する空間構造に注意する。

## 問題

No1 Fmθ、No2後頭alpha、No3前頭deltaのPSD Change Grand-average topographyに、次の問題があった。

- 単一chまたはごく近傍だけが極端に着色される
- 隣接ch間で色が急に反転し、解剖学的に連続した勾配と読みにくい
- 事前に着目した前頭または後頭の領域特異性を評価しにくい

Topographyは被験者ペア間の算術平均である。そのため、一部の被験者の一部chに極端値があると、集団に共通した分布でなくてもGrand-averageに強く現れる。

## 外れ値の原因

確認された外れ方は、大きく次の3種類である。

1. **Set 1から絶対PSDが過大**
   - baseline自体が同一chの他セッションや近傍電極より著しく大きい。
   - そのchのSet 1基準は妥当でないため、後続SetのPSD Changeも信頼しにくい。
2. **Set 1後の持続的な上昇**
   - 短いスパイクではなく、Setの相当部分で高値が連続する。
   - 長時間の高値はセッション全体の分布自体を押し上げるため、時間点単位の上側3SD除外後にも残りうる。
3. **信号減衰を疑う持続的な低下**
   - Set 1に比べて低下が長く続き、絶対PSDも同一chの他セッションおよび近傍電極より極端に低い。
   - 負方向のPSD Changeだけでは生理的低下と区別できないため、絶対PSD低値を必須の裏付けとした。

入力cacheにはPhase 1区間maskと、セッションID×ch別・全Set一括の `log10(PSD)` 上側3SD maskが適用済みである。本感度解析は、それでも残るbaseline異常と持続異常を補完する。

## 除外対象の特定方法

### 共通原則

- No1は4～7 Hz、No2は8～15 Hz、No3は1～3 Hzの保存済み未平滑PSD cacheを使い、Welch PSDは再計算しない。
- Eye DropとControlを必ず別々に判定する。
- 片条件で該当した場合、同一被験者ペア×ch×Setを両条件から除外する（paired OR）。
- 除外を別ch、別Set、被験者全体へは自動拡張しない。例外はSet 1絶対PSD高値で、同一ペア×chのSet 2～6を除外する。
- 絶対PSDと比率は正に歪むため、`log10`後に中央値と `1.4826×MAD` によるrobust zを計算する。
- PSD ChangeはセッションID・chごとに `(PSD / Set 1有限値平均 − 1) × 100`、条件差は `Eye Drop − Control` とする。

### 確定閾値

| 経路 | 除外条件 |
|---|---|
| Set 1絶対PSD高値 | Set 1絶対PSDの `log10` robust z `> 4.5`、同じchの全セッション中央値の2.5倍以上、近傍4電極中央値の2.0倍以上をすべて満たす |
| 持続的上昇：中央傾向 | 60秒非重複blockのSet 1比の中央値 `>= 2.5`、その `log10` robust z `> 3.5`、2倍以上block率 `>= 50%`、かつ2block以上連続 |
| 持続的上昇：上側占有 | 60秒block比75パーセンタイル `>= 3.0`、その `log10` robust z `> 3.5`、2倍以上block率 `>= 40%`、かつ2block以上連続 |
| 持続的上昇：空間裏付け | block比中央値 `>= 2.5`、2倍以上block率 `>= 50%`、かつ2block以上連続に加え、Set絶対PSDが同じch中央値の2.5倍以上かつ近傍4電極中央値の2.0倍以上 |
| 絶対PSD低値を伴う持続的低下 | block比中央値 `<= 0.30`、0.5倍以下block率 `>= 60%`、かつ2block以上連続、Set絶対PSDの `log10` robust z `< −4.0`、同じch中央値の0.35倍以下、近傍4電極中央値の0.45倍以下をすべて満たす |

## 除外結果

- No1 Fmθ：155 / 6,144セル（2.523%）
- No2後頭alpha：182 / 6,144セル（2.962%）
- No3前頭delta：173 / 6,144セル（2.816%）
- 合計：510 / 18,432セル（2.767%）
- Set×chの最小有効N：15

分母はSet 2～6で条件差が有限な被験者ペア×ch×Setセル数であり、元から欠測したセルは新規除外数へ含めない。paired OR適用後、製品群×Set×chごとに残った有限ペアでGrand-averageを再計算した。

## Grand-average topographyの評価

| 解析 | 製品 | 除外後の定性評価 |
|---|---|---|
| No1 Fmθ | Cキューブ | 主要な孤立ピークは縮小し、残存分布は概ね広く連続的。 |
| No1 Fmθ | Vロートプレミアム | 後半Setの正方向は広域分布で、支配的な孤立chは認めない。 |
| No2後頭alpha | Cキューブ | 負方向は広域で、初期図の局所極端値は縮小。 |
| No2後頭alpha | Vロートプレミアム | 大きな孤立極端値は縮小したが、頭部周縁の赤青交代が残り、6図中で最も慎重な解釈が必要。 |
| No3前頭delta | Cキューブ | Set 4 F4の単独支配は縮小。局所構造は残るが、特定の一人・一chの極端値支配ではない。 |
| No3前頭delta | Vロートプレミアム | 後半Setは前方正・後方負の広い勾配で、単一ch極端値ではない。 |

本感度解析により局所外れ値のGrand-averageへの支配は改善したが、エビデンスは領域特異性の証明ではない。外れ値除外後の追加topographyは、主要解析を置き換える図ではなく、結果の頑健性と残存リスクを確認する補助結果とする。

## 成果物と監査記録

- 実装：`解析プログラム/Phase4_脳波解析/Phase4_PSDChangeConditionwiseBidirectionalOutlierTopography.py`
- 追加figure：各No_subの `Topography/GrandAverage/` にある `..._ExploratorySet1AbsolutePSD_SustainedChangeExcluded.png`
- 条件別フラグ：`Sub/tables/ExploratorySet1AbsolutePSD_SustainedChange_SessionFlags.csv`
- paired OR後の除外セル：`..._ExcludedCells.csv`
- Set×chのGrand-average、N、近傍残差：`..._GroupAudit.csv`
- No別実行要約：`..._RunSummary.json`
- 全No要約：`Phase4_脳波解析/Sub/logs/Phase4_PSDChange_ConditionwiseBidirectionalOutlierExclusion_RunSummary.json`

元の主要Grand-average topography、PSD cache、個人結果は変更しない。監査CSVには再現に必要なセッションIDを含むため、OneDrive認可済み結果ツリーにだけ保存する。
