# Phase 4：Vプレ効果候補の探索まとめ

最終確認：2026-11-16。現行No4–12の結果を読むための共有資料です。研究のメインNo1–3との関係は[全体ガイド](Phase4_解析全体ガイド.md)、詳細な計算・図設定は各仕様を参照してください。

## 1. 現時点で注目する候補

**前頭〜中央部のlow-alpha（8–10 Hz）について、Set 1からのパワー増加がEye DropではControlより小さい可能性**を、次に検証する候補とします。代表する現行結果は**No12_sub**です。

- VプレのNo12_subでは、Set 2–6すべてで平均条件差がこの方向でした。ただし、各Set・全Set統合とも未補正でも統計的有意差はありません。
- Cキューブにも同方向の傾向があり、一部ではより明瞭です。Vプレだけの現象、製品間の優劣は示していません。
- No12_subはFz単独No10_subと似た結果です。ROI平均で明確に差が拡大したとはいえません。
- したがって、**検証に値する候補を得た段階**です。点眼の有効性、注意改善・疲労軽減という心理的意味、前頭特異性を確立した結果ではありません。

## 2. この候補に至った経緯

以下は意思決定の要約です。変更前の仕様・旧結果そのものは`docs/history/`へ分離しています。

| 段階 | 見たこと・次の問い |
|---|---|
| No1_add：Fz TFM | 1–30 Hzの条件差で、Vプレの8–9 Hz付近、とくにSet 4–5に青い部分。low-alphaを調べる契機になった |
| No10／No10_sub：Fz | 8–10 Hzの絶対PSDとSet 1基準Changeで確認。Vプレも増加抑制方向だが、明確な差の確証には至らなかった |
| No10_sub topography | 全頭のChange条件差を確認。品質に基づくv3追加版では、VプレSet 4で前頭〜中央に青い領域。単極から領域平均への検討につながった |
| No11／No11_sub：Pz | 後頭頂でも同帯域を確認。前頭だけの特徴かを考える比較材料とした |
| No12／No12_sub：10ch ROI | 前頭〜中央を平均し、単極だけに限定しない指標として確認。Fz単独に似た増加抑制方向はあるが、条件差が明確になったとはいえなかった |

注意：TFMの青は**絶対PSDのEye Drop−Controlが負**という意味です。Set 1からの増加率抑制と同義ではありません。TFMと帯域解析は除外maskも異なり、図同士の直接一致を前提にしません。

## 3. No4–12：何を試し、どこを読むか

起点はOneDrive `実験本番_本解析/Phase4_脳波解析/`。下記の各フォルダ内に`CCube/`と`VRohtoPremium/`があります。以下の所見は製品別Eye Drop対Controlの比較で、製品間検定ではありません。

| 解析フォルダ | 検討した指標・時間帯 | 結果の位置付け |
|---|---|---|
| `No4_FzThetaEarlyChange` | Fzシータ4–7 Hz、Set 1基準Change。Set序盤50%／25%と隣接Set境界 | Vプレで低下方向の境界もあるが、境界間で符号が揃わず個人差も大きい |
| `No5_FzDeltaEarlyChange` | Fzデルタ1–3 Hz、No4と同じ定量化 | 点眼後低下の可能性を探索したが、一貫した効果とはまとめられない |
| `No6_FzThetaEarlyAbsolutePSD` | 同じ序盤・境界を絶対PSDで評価 | Changeのbaseline依存を避けた補助的確認。安定した低下効果は確定していない |
| `No7_FzDeltaEarlyAbsolutePSD` | デルタの絶対PSD、同じ序盤・境界 | 高値被験者を除く追加版で結果が変わる。主要版と感度分析を区別して読む |
| `No8_PzSetwiseIAF` | Pz、Set全体のアルファピーク周波数 | 周波数自体の変動を検討した別の指標。全利用可能版と明瞭単峰選別版を併記 |
| `No9_FzSetwiseIAF` | Fz、No8と同じIAF | 前頭でのピーク周波数。パワー増減とは別の問い |
| `No10_FzLowAlpha`／`No10_sub_FzLowAlphaChange` | Fz low-alphaの絶対PSD／Change | Vプレは増加抑制方向の記述傾向。subの被験者除外は検討済みで追加版不要と判断 |
| `No11_PzLowAlpha`／`No11_sub_PzLowAlphaChange` | Pz、同じlow-alpha | Vプレは主要版・指定除外版とも各Setで未補正非有意。Cキューブは結果が採用集合に依存する |
| `No12_FrontalROILowAlpha`／`No12_sub_FrontalROILowAlphaChange` | 前頭〜中央10ch ROI、同じlow-alpha | 現時点の主要な探索候補。subの被験者除外は検討済みで追加版不要と判断 |

No4–7とIAFのNo8／9は推測統計を行っていません。「有意でなかった」と「検定していない」は区別します。No4／5／7の旧来の指定除外は事後的な感度分析であり、後から確立した品質診断や全解析共通の除外規則へ置き換えません。

### フォルダの読み分け

- **No4／5**：`Individual/`、`GrandAverage/`、`SetQuantification/`、`BetweenSetQuantification/`、`SensitivityAnalysis/`。Set全体と序盤は`SetQuantification/`、前後Set境界は`BetweenSetQuantification/`。指定除外版も各定量化フォルダ内の`ExcludePair...`付きPNGで、予約用`SensitivityAnalysis/`は空です。
- **No6／7**：`SetQuantification/`は序盤50%／25%、`BetweenSetQuantification/`は境界50%／25%。絶対PSDの個人時間変化はNo1／3を参照。
- **No8／9**：`Individual/`はPSD2条件＋IAF推移の3パネル。`GrandAverage/`直下に全利用可能版（`AllAvailable`）と追加選別版（`SelectedParticipants`）を別名PNGで置き、Set 1との差（Hz）の2条件平均を示します。現行は各Set1値で、旧前後半解析ではありません。
- **No10–12（本体・sub）**：`Individual/`は平滑化後時間変化。本体には`Individual/Unsmoothed/`配下に閾値除外前／後も保存します。`GrandAverage/`と`SetQuantification/`が群の傾向と定量値。No11の指定除外版定量化は`SetQuantification/SpecifiedPairsExcluded/`。
- **Topography**：この探索群ではNo10／subのみ。`Topography/GrandAverage/`に原図、**No10_subに限りv3追加図**があり、比較コピーは`補足分析（被験者除外あり）/No10_sub_FzLowAlphaChange/<製品>/GrandAverage/`。No11／12は重複作成していません。
- **補助表・履歴**：各Noの`Sub/tables/`、`Sub/logs/`、`Sub/history/`。旧版は現在の結果として読まないでください。

No4–9の詳しい軸・色・各図の読み方は[専用閲覧ガイド](Phase4_No4_No9_結果フォルダとFigureの読み方.md)にまとめています。

## 4. low-alphaの現行結果を数値で確認

### No12_sub：ROIのSet 1基準Change

値は未平滑時間変化を定量化した被験者平均の差、**Eye Drop−Control（percentage points）**。負は点眼条件の変化率が小さい方向です。線図を見た印象だけでなく、現行保存統計と照合しています。

| Set | Vプレの差 | 未補正p | Cキューブの差 | 未補正p |
|---|---:|---:|---:|---:|
| 2 | −6.75 | .493 | −12.72 | .163 |
| 3 | −11.32 | .461 | −21.68 | .065 |
| 4 | −25.05 | .234 | −40.54 | .027 |
| 5 | −20.16 | .347 | −29.05 | .058 |
| 6 | −12.12 | .571 | −21.78 | .149 |
| 全Set統合 | −11.91 | .366 | −21.60 | .040 |

- Set 1はbaselineのため単独検定なし。全Set統合にはSet 1を含み、被験者ごとの全有限時間窓を平均します。Set差の単純平均ではありません。
- 検定は両側対応ありt検定。CキューブSet 4はBonferroni／Holm／FDR補正後には非有意。全Set統合は現行仕様上1検定・未補正です。
- 探索全体の多数の解析選択を一括調整したp値ではありません。Cキューブの未補正有意性も確認的な効果証明とは扱いません。
- Vプレの線が全時間点で下にあるわけではありません。群平均の方向は、全員に共通する反応や原因を保証しません。

### Fz単独・Pz・全頭との関係

- **No10_sub（Fz）**：VプレSet 2–6の差は順に−7.09、−13.80、−23.27、−19.60、−9.63 pp。No12_subと似ていますが同一データではありません。
- **No12_subの計算**：ch別品質mask後の絶対PSDを有効ch間で平均し、ROI自身のSet 1平均でChange化します。ch別Changeの平均やFzのコピーではありません。
- **No11_sub（Pz）**：Vプレに明確な検定上の差はありません。Cキューブでは主要版の一部Setに補正後有意差がある一方、除外追加版Set 4は未補正p=.045、補正後非有意。版を混ぜず比較します。
- **No10_sub v3 topography**：VプレSet 4で前頭〜中央の負方向が見え、ROI選定の参考になりました。ただしch×Set単位で採用者が変わり、Fz／Pz／ROI線図と同じ集団・同じ平均操作ではありません。色は検定結果ではありません。

## 5. 確定事項・解釈・未検証事項

| 層 | 現時点の扱い |
|---|---|
| 確定した解析仕様 | low-alphaは8–10 Hz。ROIはF3・Fz・F4・FC5・FC1・FC2・FC6・C3・Cz・C4の10ch |
| 観察 | No12_subでは両製品ともSet 2–6の平均差が負。Vプレは未補正でも非有意 |
| 次の仮説 | 前頭〜中央low-alphaの課題進行に伴う増加を、点眼が抑える可能性 |
| 未確定 | Vプレ固有性、製品間の優劣、注意・疲労・眠気への対応、領域特異性、独立データでの再現性 |

同じデータのTFM・topographyから帯域とROIを選んだ**事後探索**です。No12は独立した追試ではありません。Cキューブに同方向があることは候補の検討材料になりますが、それだけで生理的な正しさやノイズでないことを保証しません。

被験者単位除外とtopographyのch×Set除外は区別します。No10_subとNo12_subで追加被験者除外を行わないのは、信号品質を検討した上での決定です。「検討していない」「どのデータにもノイズがない」とは意味しません。

## 6. 詳細・数値の正本

- [No4／5仕様](Phase4_No4_No5_Fz序盤PSDChange_解析仕様.md)、[No6／7仕様](Phase4_No6_No7_Fz序盤絶対PSD_解析仕様.md)、[No8／9仕様](Phase4_No8_No9_共有用解析仕様.md)
- [No1統合仕様：TFMを含む](Phase4_No1_共有用解析仕様.md)、[No10仕様](Phase4_No10_解析仕様.md)、[No11仕様](Phase4_No11_解析仕様.md)、[No12仕様](Phase4_No12_解析仕様.md)
- [No10_sub topography v3](Phase4_No10_sub_Topography感度分析.md)、[除外あり追加解析の共通方針](Phase4_除外あり追加解析の共通方針.md)
- 数値表：各No_subの`<製品>/SetQuantification/*Statistics*.csv`と`Sub/tables/SetQuantification/`。上記No12値は現行保存表を照合、丸めて掲載しています。

この資料は現行結果の要約です。詳細な試行錯誤・廃止版の数値・更新証跡は履歴側に残し、現行結論へ混在させません。
