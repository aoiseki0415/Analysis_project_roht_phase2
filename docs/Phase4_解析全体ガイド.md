# Phase 4 脳波解析：全体ガイド

最終確認：2026-11-16。共有用の入口資料です。方法・結果の詳細は各Noの現行仕様を参照してください。

## 1. 研究の構造

| 区分 | 解析 | 役割 |
|---|---|---|
| **研究のメイン** | **No1–3（本体・sub・addを含む）** | 事前に選んだ領域・周波数帯から、課題進行に伴う脳活動と点眼条件差を評価する |
| **Vプレ効果候補の探索** | **No4–12（subを含む）** | 時間帯、指標、周波数帯、領域を追加検討し、次に検証する候補を絞る |

両区分とも、`CCube`（Cキューブ）と`VRohtoPremium`（Vロートプレミアム／Vプレ）を分け、**同じ被験者のEye DropとControlを比較**します。製品群は別の被験者集団です。「メイン」は研究上の位置付けであり、その周辺解析すべてが事前登録された確認的検定という意味ではありません。

## 2. メイン解析：No1–3

| No | 代表電極・帯域 | 見るもの | 共有仕様 |
|---|---|---|---|
| No1 | Fz・シータ4–7 Hz | 認知的負荷・努力に関連する活動 | [No1統合仕様](Phase4_No1_共有用解析仕様.md) |
| No2 | Oz・アルファ8–15 Hz | 外的注意低下等に関連する活動。Pz補助版`No2-2_sub`もあり | [No2統合仕様](Phase4_No2_共有用解析仕様.md) |
| No3 | Fz・デルタ1–3 Hz | 疲労・眠気・覚醒水準に関連する低周波活動 | [No3統合仕様](Phase4_No3_共有用解析仕様.md) |

帯域端は両端を含みます。指標と心理状態は一対一ではなく、単独で注意・疲労・眠気を断定しません。

3つのNoは共通して、以下の構造です。

- **本体**：帯域平均した絶対PSD。個人時間変化、Grand-average、Set別／全Set統合定量化、全頭topography。
- **sub**：各条件・各chのSet 1平均を基準にした`(PSD / baseline − 1) × 100`。出力の型は本体と同じ。
- **add**：代表chの1–30 Hzを保持したGrand-average TFM。Eye Drop、Control、両者の差を縦3段で表示。
- **No2-2_sub**：No2_subの代表chをOzからPzへ変えた補助解析。重複するtopographyは作りません。

OneDrive `Phase4_脳波解析/`直下の対応フォルダ：

| No | 本体 | sub | add |
|---|---|---|---|
| 1 | `No1_FmTheta` | `No1_sub_FmThetaChange` | `No1_add_FzTimeFrequencyMap` |
| 2 | `No2_OccipitalAlpha` | `No2_sub_OccipitalAlphaChange` | `No2_add_OzTimeFrequencyMap` |
| 3 | `No3_FrontalDelta` | `No3_sub_FrontalDeltaChange` | `No3_add_FzTimeFrequencyMap` |

Pz補助版は`No2-2_sub_OccipitalAlphaChange_Pz/`です。

## 3. Vプレ効果候補の探索：No4–12

| No | 指標・対象 | 主な検討 | OneDriveの解析フォルダ |
|---|---|---|---|
| 4 | Fzシータ・Set 1基準Change | Set序盤50%／25%、前Set終盤→次Set序盤 | `No4_FzThetaEarlyChange` |
| 5 | Fzデルタ・Set 1基準Change | No4と同じ時間帯 | `No5_FzDeltaEarlyChange` |
| 6 | Fzシータ・絶対PSD | 同じ序盤・Set境界を絶対値で確認 | `No6_FzThetaEarlyAbsolutePSD` |
| 7 | Fzデルタ・絶対PSD | No6と同じ時間帯 | `No7_FzDeltaEarlyAbsolutePSD` |
| 8 | Pz・アルファピーク周波数（IAF） | 各Set全体のピーク、Set 1からのHz差 | `No8_PzSetwiseIAF` |
| 9 | Fz・IAF | No8と同じ周波数指標 | `No9_FzSetwiseIAF` |
| 10／sub | Fz・low-alpha 8–10 Hz | 絶対PSD／Set 1基準Change、全頭分布 | `No10_FzLowAlpha`／`No10_sub_FzLowAlphaChange` |
| 11／sub | Pz・low-alpha 8–10 Hz | No10の代表chをPzへ変更 | `No11_PzLowAlpha`／`No11_sub_PzLowAlphaChange` |
| 12／sub | 前頭〜中央10ch ROI・low-alpha 8–10 Hz | ch平均の絶対PSD／ROI自身のSet 1基準Change | `No12_FrontalROILowAlpha`／`No12_sub_FrontalROILowAlphaChange` |

No12の10ch：F3、Fz、F4、FC5、FC1、FC2、FC6、C3、Cz、C4。No11・12に独自のtopography／TFMはありません。探索の経緯と現時点の結論は[探索まとめ](Phase4_Vプレ効果探索まとめ.md)へ。

**現行番号のみを使用します。** No8／9はSet全体IAFです。廃止した半Set IAFや旧IAF No10／11を、現在のlow-alpha No10／11と混同しないでください。

## 4. 結果を開く場所

起点：OneDrive `実験本番_本解析/Phase4_脳波解析/`。各解析の下に製品別フォルダと補助資料用`Sub/`があります。

| 製品フォルダ内 | 内容 |
|---|---|
| `Individual/` | 個人図 |
| `GrandAverage/` | 被験者間平均の時間変化。通常のパワー系列では平均±SEM |
| `SetQuantification/` | Set別・全Set統合の定量化。棒は被験者平均、点は被験者値 |
| `Topography/Individual/`、`Topography/GrandAverage/` | 全頭の条件差。下記の該当Noのみ |

No4–7の序盤・境界、No8／9のIAFには専用階層があります。具体的な軸・色・読み方は[No4–9閲覧ガイド](Phase4_No4_No9_結果フォルダとFigureの読み方.md)、No10–12は各仕様を参照してください。`Sub/tables/`は数値、`Sub/logs/`は実行・検証、`Sub/history/`は過去版の記録で、現行figureとは区別します。

## 5. Topographyの場所と意味

| 解析 | 元の全頭図 | 除外あり追加のGrand-average |
|---|---|---|
| No1・2・3本体 | シータ／アルファ／デルタの絶対PSD条件差 | この追加版の対象外 |
| No1_sub・2_sub・3_sub | 各帯域のSet 1基準Change条件差 | 最新v3あり |
| No10本体／No10_sub | low-alphaの絶対PSD差／Change差 | subのみ最新v3あり |

各Noの`<製品>/Topography/GrandAverage/`で、無印が元の図、`ExploratorySpatialTemporalExcluded`付きが最新の除外追加図です。比較用の同一画像は以下にもあります。

```text
補足分析（被験者除外あり）/
  <No1_sub・No2_sub・No3_sub・No10_subの各解析フォルダ>/
    <CCube または VRohtoPremium>/GrandAverage/
      ...BeforeOutlierExclusion.png  ← 元の図
      ...AfterOutlierExclusion.png   ← 最新v3追加図
```

- 6つの頭部図はSet 1–6。色は**Eye Drop − Control**。青は点眼条件が低い方向、赤は高い方向です。
- 絶対PSD差の単位はµV²/Hz。Change差はpercentage points（図ラベルは`Difference in PSD Change, %`）。
- 追加版は**被験者ペア×ch×Set**の除外です。フォルダ名に「被験者除外」とあっても、全員の全ch・全Setを一括除去する意味ではありません。
- 時間変化・定量化の被験者単位除外とは別集合です。ch・Setで残存Nが変わるため、線図と同一集団とは限りません。
- 色は差の大きさであって有意性ではありません。青い領域だけで効果・領域特異性は確定しません。

## 6. 詳細と記録の探し方

| 読みたい内容 | 正本 |
|---|---|
| 全体の構造 | この資料 |
| 探索の経緯・現時点の候補と限界 | [Vプレ効果探索まとめ](Phase4_Vプレ効果探索まとめ.md) |
| 詳細な方法・図・現在の結果 | `docs/Phase4_No…_解析仕様.md`／`共有用解析仕様.md` |
| 除外の考え方と単位 | [除外あり追加解析の共通方針](Phase4_除外あり追加解析の共通方針.md) |
| topography v3の具体的方法・結果 | [No1–3](Phase4_PSDChange_Topography外れ値除外感度解析.md)、[No10_sub](Phase4_No10_sub_Topography感度分析.md) |
| 変更理由・旧方法・旧実績 | `docs/history/`。現行手法として使わない |

NotionもPhase 4親ページを概要、各Noの子ページを詳細、履歴を別ページとする構造です。方法の確定と、効果についての結論は区別します。
