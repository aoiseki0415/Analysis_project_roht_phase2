# Phase 4 No10_sub：topographyの条件別外れ値除外感度分析

更新日：2026-11-13。**8–10 HzのSet 1基準PSD Change topographyだけを対象とする追加分析。主要結果は保持する。** 方法は第1–4節、検証済み結果は第5節、検討過程は[意思決定履歴](history/Phase4_No10_sub_Topography感度分析_20261113.md)へ分離する。

対応Notion：[確定方法・結果](https://app.notion.com/p/417161f2809781548b9ccf57cab2cd19)。

## 1. 目的・適用範囲

- 一部の個人図で単一電極付近の大きな条件差が認められ、Grand-averageを引っ張る可能性を確認する。
- [従来No1_sub–No3_subの方法](Phase4_PSDChange_Topography外れ値除外感度解析.md)を**数値閾値を変更せず**No10_subへ適用する。生理的信号とノイズを確定診断する方法ではなく、事後・探索的な頑健性確認である。
- 対象は全32ch、Cキューブ・VロートプレミアムのGrand-average topography。Fz時間変化・定量化の `SpecifiedPairsExcluded` とは別の除外で、その指定3ペアを自動的に除かない。
- 主subのbaseline適格39ペアから開始する。既知欠測・条件対応は[注意事項](解析上の注意事項.md)と既存manifestに従う。
- 元cache、個人図、主要群図、No10本体、他Noは変更しない。Welch再計算、PSD値の補間・補正、空間平滑化の追加、ch別統計は行わない。

## 2. 入力と評価指標

1. 現行No10の80 HDF5を読み取り専用で検証する。8/9/10 Hz、設定hash、Phase 1入力fingerprint、manifestのID・条件・製品を照合する。
2. Phase 1区間maskと帯域固有log3SD maskを再適用した**未平滑PSD**を使う。
3. 描画するPSD Changeは既存どおり、ID×chごとのSet 1 **算術平均**をBとして `(PSD/B−1)×100`。Set平均を求め、被験者内で `Eye Drop−Control` を計算する。
4. **QC判定だけはSet 1の中央値を基準とする。** 絶対PSD指標も各Setの中央値。描画値の算術平均baselineを中央値へ変更するわけではない。
5. QCではSet内実時間を60秒非重複blockに分け、各blockの有限PSD中央値÷Set 1中央値を求める。最後の短いblockも1block。したがって「2block連続」は厳密な120秒以上を保証しない。
6. 従来実装に合わせ、block占有率の分母は存在する全block。全NaN blockは高値・低値のいずれにも該当せず、連続判定も途切れる。PSDのゼロ埋めではない。
7. robust zは正値のlog10について `(値−中央値)/(1.4826×MAD)`。参照集合はbaseline適格な**両製品・両条件の全セッション**、ch別（後続SetはさらにSet別）。判定自体はEye Drop／Controlを個別に行う。近傍は既存montage座標の最近傍4電極の中央値。

## 3. 確定した除外規則

各行の条件はすべてAND。上昇3経路はOR。同じ閾値を全セッションに適用する。

| 経路 | 条件 |
|---|---|
| Set 1絶対PSD高値 | Set 1絶対PSDのlog robust z >4.5、同ch参照中央値の2.5倍以上、近傍中央値の2倍以上 |
| 持続上昇：中央傾向 | block比中央値≥2.5、そのlog robust z >3.5、比≥2のblockが50%以上、2block以上連続 |
| 持続上昇：上側占有 | block比75パーセンタイル≥3、そのlog robust z >3.5、比≥2のblockが40%以上、2block以上連続 |
| 持続上昇：空間裏付け | block比中央値≥2.5、比≥2が50%以上・2block以上連続、Set絶対PSDが同ch参照中央値の2.5倍以上・近傍中央値の2倍以上 |
| 持続低下＋絶対低値 | block比中央値≤0.30、比≤0.5が60%以上・2block以上連続、Set絶対PSDのlog robust z <−4、同ch参照中央値の0.35倍以下・近傍中央値の0.45倍以下 |

- 片条件で該当した**ペア×ch×Setを両条件から除外**する（paired OR）。被験者丸ごと・他chへ拡張しない。
- Set 1高値のみ、基準値の問題として同一ペア×chのSet 2–6へ適用する。Set 1図は既存の0を保持する。
- 元から欠測のセルは新規除外数へ数えない。分母はSet 2–6の元々有限なペア×ch×Setセル数。
- 残る被験者内差を製品×Set×chごとに等重み平均する。**chごとにNが変わる**ためN表を保存し、電極間で構成員が同一とは仮定しない。
- ±800以上の個人図は検証対象の目安であり、除外の直接閾値にしない。色軸は最大絶対差÷0.85を丸めるため、±800でも実値800を意味しない。効果方向・p値・期待する領域の色によって判定を変更しない。

## 4. Figure・保存・再現

- 既存No10_subと同じ6 Set横並び、Arial、頭輪郭・電極点・文字寸法・`RdBu_r`、ラベル `Difference in PSD Change, %`。単位は変化率の差なので数値的にはpercentage points。
- 除外後の全Set×ch最大絶対値Mから、±V（V≥M/0.85、切りのよい値）を再計算する。原図と追加図はスケールが異なり得るため、色だけで増減を判定せずカラーバー・数値表を併読する。
- 専用入口：`解析プログラム/Phase4_脳波解析/Phase4_No10_sub_TopographySensitivity.py`。既存No1–3とNo10のコード・閾値は書き換えず、No10設定・検証・描画を再利用する。
- `--dry-run` は検証・集計結果を標準出力へ返し、成果物を書かない。`--execute --source-audit <照合JSON>` はNotionとのmanifest照合証跡を検証してから以下だけを追加する。
- `--record-review <確認JSON>` は解析を再実行せず、6 PNGの目視対象・hash、Notion参照、テスト、Gitのローカル／remote commitを記録する。実行後のソースhash・元成果物・cache・出力hashの不変を再検証して、専用ログだけを完了状態にする。

```text
Phase4_脳波解析/
  No10_sub_FzLowAlphaChange/
    <製品>/Topography/GrandAverage/
      <stem>_Topography_GrandAverage_<製品>.png             # 原図：保持
      <stem>_Topography_GrandAverage_<製品>_ExploratorySet1AbsolutePSD_SustainedChangeExcluded.png
    Sub/tables/TopographySensitivity/                      # 指標・条件別フラグ・除外セル・群値とN
    Sub/logs/                                             # 実行・入力照合・検証・保存hash
  補足分析（被験者除外あり）/No10_sub_FzLowAlphaChange/
    <製品>/GrandAverage/
      <stem>_Topography_GrandAverage_<製品>_BeforeOutlierExclusion.png
      <stem>_Topography_GrandAverage_<製品>_AfterOutlierExclusion.png
```

製品はCCube／VRohtoPremium、stemはNo10_sub_FzLowAlphaChange。新規図は2種類、比較コピー込みで6 PNGを追加する。個別IDを含む監査表は認可済みOneDriveのSubにだけ保存する。ローカル派生cacheは作らない。

## 5. 結果・検証

### 5.1 実行結果（2026-11-13）

専用スクリプト `20261113_no10_topography_conditionwise_sensitivity_v1` を全39適格ペアへ実行した。従来法 `phase4-psd-change-conditionwise-bidirectional-qc-2026-10-17.3` の閾値は変更していない。

| 指標 | Cキューブ | Vプレ |
|---|---:|---:|
| 開始時baseline適格ペア | 20 | 19 |
| Set 2–6の元々有限なペア×ch×Set | 3,168 | 2,976 |
| 新たに除外したセル | 87 | 90 |
| 除外率 | 2.75% | 3.02% |
| 除外後の電極別・Set別N | 17–20 | 16–19 |
| 群平均の最大絶対条件差（除外前→後、pp） | 117.04→48.33 | 92.51→37.84 |
| 近傍4電極中央値からの最大絶対逸脱（前→後、pp） | 132.57→28.03 | 96.29→31.22 |
| 共通カラーバー（前→後） | ±150→±60 | ±150→±50 |

- 合計**177/6,144セル＝2.88%**。被験者全体を新たに除外したものではない。候補表は179行で、元々有限なセルへ実際に適用された177行は `applied_to_original_finite_cell` で識別できる。
- ±800以上の個人色軸となった8例について、**各例で最大絶対差を生じた電極・Setは8/8で除外対象**になった。この事後確認のために閾値を調整してはいない。詳細は `large_scale_individual_benchmark.csv`。
- 新規Grand-average 2 PNG、Before/After比較コピー4 PNG、監査CSV 5件、保護inventory JSON、専用実行JSONを保存した。No10主168 PNG・sub既存92 PNGは保持し、主／subの現行PNGは合計262枚、別の補足フォルダに比較4枚となる。

### 5.2 図の確認と解釈

- **Cキューブ**：元図Set 3–6の左前頭端の孤立した強い赤が消失。追加図は広い範囲の負方向の差を示す。ただし、これはPointごとのNが変わる探索的群平均であり、生理的分布と確定できない。
- **Vプレ**：元図の後頭部の局所的に強い青と中央の赤は弱まった。一方、Set 5–6などでは局所的な正負の違いが残る。すべての不均一な分布が解消したとは判断しない。
- 新しい図は色軸が狭いため、除外後でも色が濃く見える。図の色だけを直接比較せず、上表の実数値とカラーバーで判断する。
- 追加図2枚と比較コピー4枚を実画像で確認。Set、電極点、頭輪郭、色軸、ラベルの欠け・重なりに修正必須の問題はない。追加の空間平滑化は行っていない。

### 5.3 検証・監査の所在

- live Notionの40ペア割付とmanifestを全行照合。主subのbaseline適格39ペア、既知欠測、指定ペア除外との分離を確認。
- 除外前の再集計は既存の保存済みtopography値・Nと一致（最大値誤差0）。全39ペアの条件差を元の未平滑PSDから独立再計算し、除外後の平均・Nも別計算と一致。
- 全343テスト（専用10件を含む）、新規コード・テストのRuffに合格。No10の既存331ファイルと80 cacheはSHA256不変、他解析1,977ファイルはpath・size・mtime不変を確認。
- `Sub/tables/TopographySensitivity/`：全条件指標、条件側判定、ペア×ch×Set除外理由、群値・N・除外前値、±800目安の照合、保護inventory。個人の情報はここで管理する。
- `Sub/logs/No10_sub_FzLowAlphaChange_TopographySensitivity_RunSummary.json`：source hash、manifest、Notion照合証跡、設定、除外数、出力hash、検証範囲と限界。最終目視・文書・Git確認も同ログへ追記し、解析を再実行しない。
- OneDriveローカル同期先への保存・読戻しを確認した。クラウドサーバー側の同期完了は独立確認していない。

## 6. 解釈上の限界

- 大きな条件差や局所的な色だけでノイズと断定しない。今回の閾値は既存の探索的QC規則であり、独立データで妥当性が確立した診断基準ではない。
- 事後に見つかった極端例を含む結果への感度分析。除外後だけを主要結果として示さず、原図と並べる。
- 単一chの孤立色、隣接chの反転がどこまで弱まるかを確認するが、滑らかさや仮説通りの領域分布を強制しない。残る分布は生理・記録品質・baseline比率・ch別構成員の影響を分離しきれない。
- 本topographyだけを追加するため、元のFz線図・定量化とは対象集合が異なる場合がある。両者の完全一致を要求したり、元の線図を今回黙って更新したりしない。
