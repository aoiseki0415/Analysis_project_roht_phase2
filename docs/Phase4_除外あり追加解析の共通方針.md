# Phase 4：除外あり追加解析の共通方針

更新日：2026-11-16。**最新判断：No10_subは信号品質の観点で検討した上で、両製品とも被験者除外追加版を不要と確定。No11_subは再検討して既存集合を維持すると再確認。** No10の旧追加版整理・検証は第9節に分け、数値不変のNo11は再生成しない。先行したNo2_sub Cキューブ／No2-2_sub Vプレ改訂の実行済み結果は第7節のまま保持する。No1–3、No11絶対PSD、topography v3は今回変更しない。

## 1. 目的と共通の判断姿勢

**同日後続の確定判断：No12_subも、利用者が個人データの信号品質を検討した上で、両製品とも被験者除外の追加解析は不要と決定。** 未検討・保留ではない。既存主結果を維持し、今回の文書更新で解析・図は変更しない。詳細は[No12統合仕様](Phase4_No12_解析仕様.md)、判断過程は[No12履歴](history/Phase4_No12_意思決定.md)に分ける。

信号品質に問題があり、解析値がノイズや記録不良に大きく影響されている可能性に対して、全利用可能データの主結果と除外追加版を比較する。**他者と異なる傾向、大きな変化率、平均への寄与、期待する効果方向だけを優先的な除外理由にしない。**

- Change解析でも、対応する絶対PSD・Set 1 baseline・未平滑波形・既存maskを重視する。比率だけでは記録不良を確定できない。
- ほぼゼロへの低下、急激な不連続、Set境界での復帰、近傍chとの局所的な不整合、短時間値への極端な集中は確認の手掛かり。単独所見だけで原因を断定しない。
- 持続的な増減や広域に一貫する変化は生理的変化でも起こり得る。数値の大きさだけで機械的に切らない。
- 記録は「観察」「信号品質への懸念という解釈」「除外の決定」を分ける。今回の個人図に関する所見は利用者の定性的評価であり、新たなEEG監査で記録障害を実証したと書かない。
- 検討の結果として除外対象なしと判断することもある。「未検討」「判断保留」とは明確に区別し、不要な追加版を作らず既存主結果を採用する。採用へ戻す判断をノイズ皆無の証明ともしない。
- 事後・非盲検の探索的感度分析であり、真の神経活動とノイズを完全に判別する方法でも、製品効果を確証する解析でもない。

## 2. 二つの追加解析の共通点・相違点

| 観点 | 代表ch／ROIのGrand-average・定量化 | 全頭topographyのGrand-average |
|---|---|---|
| 除外単位 | 被験者ペア全体。両条件・全Setを外す | 被験者ペア×ch×Set。該当セルを両条件から外す |
| 判定方法 | 個人結果の信号品質を定性的に判断し、解析別に対象を事前固定 | 条件ごとの空間的孤立・時間的集中を現行v3の4経路で判定 |
| 見るデータ | 代表ch／ROIのChangeと絶対PSD、baseline、時間経過等 | 各条件のSet平均baseline比R、絶対PSD中央値D、平均/中央値H、上位窓の占有率Q |
| 条件の対応 | 一方の条件への懸念でも指定ペアの両条件を全Setから外す | 条件側のflagをSet 1伝播後にpaired ORし、同一ch・同一Setの両条件を外す |
| 単位を分ける理由 | Set間推移を同じ指定cohortで比較するため。ただし既知欠測によるSet別N差は残る | 局所的な問題で全頭・全Setの利用可能データまで失わないため。ch別・Set別Nを必ず示す |
| 出力 | 平均±SEMの時間変化、Set別・全Set統合定量化、統計・採否表 | 条件差の群map、ch×Set別N・除外理由・監査表 |
| 相互流用 | topographyのflagや別Noの対象者を自動継承しない | 代表chの被験者除外集合を自動継承しない |

両者とも、元のPSD・主結果・個人図を保持し、被験者内の条件対応を崩さない。**除外単位と判定基準は別の軸**であり、被験者除外とセル除外で同じ対象数・群値になることは求めない。線図とmapを比較するときは、ch、Set、baseline、構成員、実有効Nを先に揃えて確認する。

topographyは単なる「Set除外」でも「被験者除外」でもない。Set 1の品質flagは同chの後続Setへ伝播するが、他ch・他人へ広げない。最終の色は `Eye Drop − Control` のChange差で、色の符号や有意性を判定に入力しない。空間規則にcohort参照が含まれていても「他人と違う」だけで除外する規則ではなく、近傍との不整合等との組合せである。

## 3. 現行方法と実行状態の対応表

対応Notion：[共通方針・単位・現行管理](https://app.notion.com/p/419161f2809781c9bde9f40a355b5066)、[意思決定履歴](https://app.notion.com/p/419161f2809781489343f12cd8cc2286)。

具体的な匿名ID・個別理由の正本は[解析上の注意事項](解析上の注意事項.md#phase-4-sub被験者除外の現行指定2026-11-16)。各No仕様書からこの一覧へリンクし、共有仕様に対象IDを重複転記しない。

| 解析 | 代表ch・帯域 | 被験者除外版の今回確定方法 | 被験者除外版の現状 | topography追加版 |
|---|---|---|---|---|
| No1_sub | Fz・4–7 Hz | Vプレ1ペア、Cキューブなし | 新規追加・実行／検証済み | v3実行済み・変更なし |
| No2_sub | Oz・8–15 Hz | Vプレ2ペア、Cキューブ5ペア | Cキューブの追加改訂を再実行・検証済み。Vプレ数値・図は保持 | v3実行済み・変更なし |
| No2-2_sub | Pz・8–15 Hz | Vプレ2ペアを再指定、Cキューブ3ペア | Vプレの追加改訂を再実行・検証済み。CキューブはGA軸表示だけ更新 | 重複生成しない。No2_sub参照 |
| No3_sub | Fz・1–3 Hz | Vプレ1ペア、Cキューブなし | 新規追加・実行／検証済み | v3実行済み・変更なし |
| No10_sub | Fz・8–10 Hz | **再検討済み・両製品とも被験者除外なし。追加版不要** | 全baseline適格主結果を使用。旧指定版の撤去・生成停止は第9節 | v3実行済み・変更なし |
| No11_sub | Pz・8–10 Hz | 信号品質から再検討しVプレ1ペア・Cキューブ3ペアを維持 | 既存指定版を保持。採否・数値・図は不変、再生成なし | 生成しない。No10_sub参照 |
| No12_sub | 前頭〜中央10ch ROI・8–10 Hz | **信号品質を検討済み・両製品とも被験者除外なし。追加版不要** | baseline適格主結果（C20／V19）を維持。再計算・再描画なし | 重複生成しない |

No10_subの旧選定が「大きな変化率を契機とした」事実を、今回の方針でノイズ確認済みへ書き換えない。絶対PSDも確認した利用者の新しい判断で旧指定を取り消した。No11_subは再検討して維持した判断で、具体的原因の新診断ではない。両者の過程・旧実績は[再検討履歴](history/Phase4_No10_No11_sub被験者除外再検討_20261116.md)。No4–9、絶対PSD本体、TFM、他フェーズは今回の更新対象外。

## 4. 被験者除外版の確定方法

1. 当該Noの既存cache、帯域、代表ch、条件対応、mask、Set 1 baseline要件をそのまま使う。Welch、log3SD、baseline、個人値を除外者に合わせて再定義しない。
2. 主subの利用可能集合から、当該No専用の指定ペアを両条件・全Setで外す。manifestや元データ自体は削除しない。
3. 残存被験者でGrand-average（従来の1秒刻みPSDに対する60点平滑化〔通称60秒、末尾の追加点では厳密な時間幅とは異なる〕→Set別progress格子→等重み平均±SEM）を再集計する。
4. 定量化は従来の未平滑ChangeのSet内時間平均、全Set統合はSet 1を含む全有限時間窓の平均。各Set平均を単純平均する方式へ変更しない。
5. 既存の両側対応ありt検定・未補正PNG・補正CSVを維持。Set 1はBaselineで検定せず、Set 2–6の5比較にBonferroni・Holm・BH-FDR、全Set統合は1検定・補正なし。
6. y軸、統計表示、Set名は除外後の値へ既存の比率・丸め規則を適用。配色、Arial、文字サイズ等は変えない。Grand-averageの共通y軸は、同じ追加版で実際に生成する製品群を範囲とする。両製品を生成するNo2_sub・No2-2_subは両製品共通、Vプレだけ生成するNo1_sub・No3_subは残存Vプレの値から決める。未更新のCキューブ主結果と軸を共通化したとは扱わない。定量化の軸は各図の残存個人値から再計算する。
7. No1_sub・No3_subは除外のあるVプレだけ追加し、Cキューブに同一内容の重複版は作らない。No2_sub・No2-2_subは両製品で作る。

今回の部分更新では、No2_sub CキューブとNo2-2_sub Vプレの数値表・定量化・Grand-averageを上書きする。同じNoの他製品群は採否・数値・定量化を変えない。ただしGrand-averageの両製品共通y軸を守るため、両群の現行値から共通上限を再計算し、上限が変わる場合だけ他製品群のGA PNGも表示更新する。製品ごとの独立軸へ変更しない。

既知欠測Setの両条件対応、Set 1欠測によるbaseline不能、今回の指定除外を別理由で記録する。指定cohortが固定でも欠測によりSet別Nは異なる。実数N・結果・検証は第7節に分離して記録する。

## 5. Topographyの確定方法・対象の追跡（今回変更なし）

- No1–3：[帯域別v3の完全規則・方法と結果](Phase4_PSDChange_Topography外れ値除外感度解析.md)。各帯域の全32chに独立適用する。
- No10_sub：[v3の完全規則・方法と結果](Phase4_No10_sub_Topography感度分析.md)。No11_subでは同じ全頭量を重複生成しない。
- 四つの条件側経路はChangeの空間的孤立、絶対PSDの空間的孤立、時間的集中、v3追加Change空間経路。閾値・近傍・固定参照pool・Set 1伝播は上記仕様を変更せず使う。
- 具体的な被験者・ch・Set・条件側のflag、伝播、paired OR後の実適用は各専用仕様から辿れるOneDrive `Sub/tables/` の監査CSVが正本。長いセル一覧をGitへ重複転記・手動固定しない。
- 元欠測と追加除外、基準Set flagと実適用セル数を区別する。局所色が残る／消えることは、それ自体ではノイズや製品効果の証明ではない。

## 6. 保存と新旧の切り分け

No1_sub・No2_sub・No2-2_sub・No3_subの追加版はNo11_sub等と共通の配置（旧No10_subで使用した型）に統一する。以下は**追加版を採用している解析の実装・保存・読戻し済み構造**。現在追加版不要と判断したNo10_sub・No12_subには適用しない。

```text
<No_sub>/<製品>/
  GrandAverage/
    <主結果>.png
    <追加結果>_SpecifiedPairsExcluded.png
  SetQuantification/
    <主結果のSet・AllSets PNGと統計CSV>
    SpecifiedPairsExcluded/
      <Set結果>_SpecifiedPairsExcluded.png
      <AllSets結果>_SpecifiedPairsExcluded.png
      <Set統計>_SpecifiedPairsExcluded.csv
<No_sub>/Sub/
  tables/GrandAverage/                 # 追加版の群値・N
  tables/SetQuantification/            # 追加版の個人値・統計・採否
  logs/                               # 方法版・実行・検証
  history/                            # 旧追加版の非PNG監査・ログ
```

No2_sub・No2-2_subは新版の独立数値検証と全PNG目視後、旧追加PNGを各2枚、計4枚撤去した。旧監査CSVは各5件、計10件を各 `Sub/history/BeforeSpecifiedPairsExcluded_20261116/` へ移管し、内容ハッシュを保持する。主結果・個人図・topography・元cacheは保護する。No11_subの現存構造は維持。No10_subだけは不要と決定した旧追加6 PNGを撤去し、旧非PNG監査をSub/historyへ隔離する。第9節で独立して実行状態を管理する。

## 7. No1–3系の実行結果・検証（2026-11-16・今回保持）

追加改訂対象2群を再実行・検証済み。未変更4群の値は初回確認済み結果を保持し、今回No1_sub・No3_subを再実行・再監査したとは扱わない。変更前2群の値と初回実績は[履歴第7節](history/Phase4_sub被験者除外方針更新_20261116.md#7-同日の追加改訂前の結果履歴専用)へ分離する。

| 解析 | 製品 | Set 1–6の対応N | AllSets N | AllSets Eye Drop 平均±SEM (%) | AllSets Control 平均±SEM (%) | AllSets未補正p |
|---|---|---|---|---|---|---|
| No1_sub | Vプレ | 18/18/18/17/18/18 | 18 | 16.84 ± 4.25 | 11.66 ± 6.38 | 0.4882 |
| No2_sub（Oz） | Vプレ | 17/16/17/17/17/17 | 17 | 11.01 ± 5.73 | 13.52 ± 6.87 | 0.7078 |
| No2_sub（Oz） | Cキューブ | 15/15/15/15/15/15 | 15 | 4.83 ± 7.20 | 15.95 ± 6.87 | 0.2554 |
| No2-2_sub（Pz） | Vプレ | 17/16/17/16/17/17 | 17 | 20.41 ± 5.65 | 23.38 ± 6.83 | 0.6198 |
| No2-2_sub（Pz） | Cキューブ | 17/17/17/17/17/16 | 17 | 12.67 ± 6.37 | 28.18 ± 8.97 | 0.1053 |
| No3_sub | Vプレ | 18/17/18/17/18/18 | 18 | 5.58 ± 7.89 | -5.76 ± 3.50 | 0.1473 |

- 変更2群のSet 2–6・AllSetsはいずれも未補正p ≥ .05。未変更群の初回結果も同様だが、非有意は無効果・条件同等の証明ではない。
- AllSets群平均差（Eye Drop − Control）はOz Cキューブ−11.11 pp、Pz Vプレ−2.98 pp。主結果は変更せず、追加版だけの再集計結果である。
- 更新：変更2群の6 PNG、Pz Cキューブの共通GA軸表示1 PNG、計7 PNGを上書き。数値8 CSVと解析別採否2 CSVを更新。全体の追加版総数18 PNG・24数値CSV＋4採否CSVは変えない。
- GAの共通軸：Oz両製品±80%を保持。Pz両製品は±90%、目盛−80／−40／0／40／80%。CキューブPzの群値・SEM・定量化は不変で、軸変更だけである。
- 対象2解析の全12追加PNGを開き、Arial、軸・凡例・Set名・n.s.・点の収まりを確認。元cacheからの独立計算で24 CSV・5,836行を照合し、保護対象2,164ファイル（元cacheを含む）の内容hash一致を確認した。
- 関連36テストと既存帯域4テストが成功。元PSD再計算なし。無変更製品群の数値・定量化PNG、主結果・個人・topography・他Noの成果物は保持。
- OneDriveは指定ローカル同期領域への保存・読戻しを確認。クラウドサーバー側の同期完了は未検証。

今回の独立監査はNo2_subの `Sub/logs/SpecifiedPairsExcluded_IndependentValidation_20261116_Revision2.json`（passed）。各数値表・採否は第6節の保存先、実行記録は各Noの `Sub/logs/*_SpecifiedPairsExcluded_RunSummary.json`。初回の統合検証は当時の集合の証跡として保持し、追加改訂後の検証記録と混同しない。試行時の監査制約を含む過程は[履歴第8節](history/Phase4_sub被験者除外方針更新_20261116.md#8-同日の採否追加改訂意思決定実装過程)へ分ける。

## 8. 実装と再実行

- 共通追加版専用：`解析プログラム/Phase4_脳波解析/run_phase4_sub123_sensitivity.py`。
- 独立検証：`解析プログラム/Phase4_脳波解析/validate_phase4_sub_specified_pairs.py`。production計算関数をimportせず保存cacheから再現する。
- 対象は注意事項の現行指定表を読み、当日照合済みsource auditの集合と一致させる。40ペアmanifestのハッシュ、80セッションの対応、帯域・ch・cache設定ハッシュを検査し、不一致なら停止する。PSDは再計算・保存しない。
- source auditは同日のタイムゾーン付き確認日時、`matched_pairs=40`、`matched_sessions=80`、`mismatches=0`、manifest SHA256、4解析の明示除外集合を持つ。ID一覧をコードへ重複埋込みしない。
- 同日の追加改訂はNo2_subの `Sub/logs/SpecifiedPairsExcluded_SourceAudit_20261116_Revision2.json` を使う。No1_subに残る初回source auditは当時の証跡で、新集合の実行へ使用しない。
- 既存No2 Oz/Pzの主要解析entrypointから旧単独ペア版の自動生成設定を撤去。主要計算は不変。最新追加版は下記runnerから独立して実行する。

```bash
MPLCONFIGDIR=/tmp/mplconfig-roht .venv/bin/python 解析プログラム/Phase4_脳波解析/run_phase4_sub123_sensitivity.py \
  --analysis all --manifest <40ペアmanifest> --source-audit <当日照合JSON> --preflight-only
# 生成：同じ引数の --preflight-only を --execute に置換
# 追加版が既にある場合だけ --replace-existing を併記
.venv/bin/python 解析プログラム/Phase4_脳波解析/validate_phase4_sub_specified_pairs.py \
  --manifest <40ペアmanifest> --analysis No2_sub --analysis No2-2_sub \
  --report <No2_sub/Sub/logs/独立検証JSON>
```

生成runnerは `--analysis no1|no2|no2-pz|no3`、独立検証は `--analysis No1_sub|No2_sub|No2-2_sub|No3_sub` で対象を限定する。両スクリプトのCLI名を混同しない。旧No2版の整理は生成runnerの `--retire-legacy --analysis no2|no2-pz --review <全画像hash付き合格レビューJSON>` に限定し、数値・画像検証の前には実行しない。最新成果物は新版だけ、旧CSVはhistoryへ分ける。

今回の部分更新は `--analysis no2 --product CCube` と `--analysis no2-pz --product VRohtoPremium` をそれぞれpreflight後、`--execute --replace-existing` で実行する。`--product` は単一analysisとだけ併用する。相手製品の現行群値・採否を照合し、共通GA軸変更時の表示更新以外は保護する。置換対象の旧数値表・採否・run summaryを各Sub/historyへ保存し、旧PNGの複製は残さない。

独立検証も上例の対象2解析に限定する。初回No1のrun記録には正式撤去済みの旧No2ファイルが保護対象として残るため、今回のNo2更新を検証する目的で既定の全4解析監査を使わない。旧記録を改変して整合したように見せず、履歴と今回の監査範囲を区別する。

## 9. No10_sub・No11_subの再検討後の実装・整理（2026-11-16）

- 方法：No10_subは旧指定3ペアを採用へ戻し、全baseline適格39ペア（C20／V19）の既存主結果を使用する。主結果には既に含まれているので同じPSD・群数値を再計算しない。
- 現行No10_sub入口は主結果だけを生成し、旧`--sensitivity-only`は廃止理由を示して出力前に停止する。
- 旧追加6 PNGだけを撤去し、9 CSV・1 JSONは `No10_sub_FzLowAlphaChange/Sub/history/RetiredSpecifiedPairsExcluded_20261116/` へ元相対パス・hashを保持して隔離する。旧PNGを履歴にも複製しない。
- No11_subは再検討して指定を維持したため、既存の追加6 PNG・表・統計を保持する。No11絶対PSD、No10本体、全topography、元cache、他Noも保護する。
- 実行と検証は `run_phase4_no10_sub_exclusion_retirement.py --plan` → `--execute`。記録はNo10_subの `Sub/logs/No10_sub_SpecifiedPairsRetirement_20261116.json`。主結果の採用集合、不要旧版の不在、履歴移管hash、保護対象の不変を確認する。
- 事後の読み取り専用再確認は同runnerの`--verify`。当時の保護snapshotとの一致を要求するため、将来の正当な別解析更新も不一致として停止し得る。旧成果物を復活させたり当時の監査を自動改変したりしない。
- **実行結果：2026-11-16 11:50:17–11:50:19 JSTに実行、completed。** 旧6 PNG撤去、旧9 CSV＋1 JSONの履歴移管hash一致、保護2,191ファイル（うちNo11関連242）の内容SHA-256一致を確認。事後の`--verify`は`verified_completed`、旧指定版16ファイルの現行残存0件。主C20／V19に旧指定3ペアが含まれ、主6 PNG読込を確認した。実画像目視はVプレGA・CキューブSet別の2図。PSD・主図・No11・topographyは再生成していない。No11_subは既存C17／V18の追加版を維持する。
- 今回の検証を第7節のNo2系実績や2026-11-14のNo11独立監査で代用しない。個別の現行結果は[No10仕様第13節](Phase4_No10_解析仕様.md#13-2026-11-16再検討後の実装整理検証)、[No11仕様第11.5節](Phase4_No11_解析仕様.md#115-2026-11-16再検討後も既存結果を維持)へ分ける。OneDriveのローカル保存・読戻しは確認、クラウド側同期は未検証。

## 10. No1–3・No10・No11の完了時整合確認（2026-11-16）

現行文書・Notion・保存済み成果物を照合した。対象は本体、sub、No1–3のadd、およびNo2-2_sub。**新しい除外判定や再解析ではない。** 第3節の現行採否、主結果と追加版の分離を維持する。

| 解析系列 | 本体PNG | sub PNG | add PNG | 補足比較コピーPNG |
|---|---:|---:|---:|---:|
| No1 | 168 | 91 | 2 | 4 |
| No2 | 168 | 94 | 2 | 4 |
| No2-2（Pz補助） | — | 51 | — | — |
| No3 | 168 | 91 | 2 | 4 |
| No10 | 168 | 88 | — | 4 |
| No11 | 132 | 51 | — | — |

- 計1,292 PNGについて形式・読込を確認。フォルダ件数、追加版の採否表・Set別N・保存先、記録済み88ファイルのSHA-256を照合し、不一致なし。全画像の信号品質を今回再目視した意味ではない。
- 追加GAは製品別`GrandAverage/`直下、追加定量化は`SetQuantification/SpecifiedPairsExcluded/`。No1_sub・No3_subのCキューブ、No10_sub両製品には不要な重複版がない。No11本体の既存追加版も保持する。
- No1–3_sub・No10_subの各製品のtopographyは、原図＋最新v3の2枚。補足フォルダのBefore／Afterとの16組のSHA-256一致を確認。実適用除外数はNo1／No2／No3／No10で311／245／435／247セル。No2-2_sub・No11関連に重複topographyを作らない。
- 生成時点の`pending`を残すrun記録は、後続の完了記録と区別する。No1–3 topographyの最終状態はPhase 4共通`Sub/logs/No123_sub_TopographySensitivity_RunSummary.json`の`delivery_verified`、No11指定版はNo11本体`Sub/logs/No11_SpecifiedPairsExcluded_DeliveryVerification.json`の`passed`を参照する。過去の生成時点を遡及改変しない。
- No10_subの廃止版履歴CSVが1件、保存記録の場所に見当たらなかった。同じ履歴内の個人定量値から、既存関数・round-trip読込で再構成し、**当時記録した1,189 bytes・SHA-256と完全一致**する内容に限り元の履歴位置へ復元した。欠落原因は未確定。現行図・表・cacheの更新や旧追加版の復活ではない。
- 復元後、退役runnerの`--verify`は`verified_completed`。履歴10件の一致・旧版の現行残存0件・当時の保護2,191ファイルの不変を確認した。元の撤去記録は変更していない。
- 今回の照合・復元・検証範囲の記録：Phase 4共通`Sub/logs/No1_No3_No10_No11_CompletionAudit_20261116.json`。この新規監査ログを保存した後は、旧退役runnerの全ファイル集合比較が新規ログを検出し得るため、第9節の制約に従う。
- 関連テスト4ファイル（No10退役、No1–3 sub指定版、No11指定版、No1–3 topography）の計80テストが成功。Notionの更新8ページは本文読戻し・既存子ページリンク保持を確認した。

残る制約はOneDriveサーバー側同期の独立未確認と、各感度解析に明記した探索的解釈の限界。今回は保存済み成果物の整合確認であり、全数値を元EEGから再計算した検証ではない。現行解析のコード・パラメータ・図・除外集合は変更しない。
