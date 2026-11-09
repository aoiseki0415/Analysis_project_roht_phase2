# Phase 4 No6・No7：Fz序盤絶対PSD｜探索解析仕様

## 目的・位置づけ

No4／No5で扱ったSet 1基準の変化率とは別に、同じ時間窓を**絶対PSD**（µV²/Hz）で評価する。No6はFzシータ4–7 Hz、No7はFzデルタ1–3 Hzであり、上端binを含む。Cキューブ群とVロートプレミアム群を別々に、Eye DropとControlを被験者内で対応づける。点眼直後の改善を立証する解析ではなく、各Set序盤とSet境界に着目する探索である。Set境界を実際の点眼時刻と同一視しない。

| No | 代表ch・帯域 | 読み取り専用入力 | OneDrive出力 |
|---|---|---|---|
| No6 | Fz・4,5,6,7 Hz | No1_FmTheta のPSDTimeSeries cache | `Phase4_脳波解析/No6_FzThetaEarlyAbsolutePSD/` |
| No7 | Fz・1,2,3 Hz | No3_FrontalDelta のPSDTimeSeries cache | `Phase4_脳波解析/No7_FzDeltaEarlyAbsolutePSD/` |

No1／No3の既存の個人時間変化・Grand-average・全Set定量化は変更しない。新しいWelch計算、平滑化、ローカル派生cache、topography、TFMは作らない。**No6・No7の主結果**は、目視で挙がった特定ペアも追加除外せず、各群20ペア、計40ペアを対象とする。Set 1が欠損したペアも、Set 1の基準値を要しないため、利用可能な他Setには含める。No7のVロートプレミアム群だけに、後述する指定ペア除外の追加感度分析を置き、主結果とは混同しない。

## 入力確認・計算

1. 非公開manifestの1回目ID、2回目ID、点眼ID、製品から条件を確定し、cacheのID・ペア・製品・Eye Drop／Control属性と照合する。100番台／200番台で条件を推定しない。
2. 既存cacheの周波数bin、256 Hz、1秒（256 sample）窓・1秒step、設定hash、既知欠測Setを検証する。cacheの線形・未平滑の帯域平均PSDを用いる。cacheにはPhase 1 ICA学習用除去区間と1%以上重なるPSD窓のNaN化、およびセッションID×chの全利用可能Setにまたがる`log10(PSD)`平均＋3SDを超えた上側値のNaN化が記録されている。これを従前通り適用する。Phase 1のch除去maskやNo1_subのtopography用感度除外は追加しない。
3. Fzの`set_progress_pct`で各Setを切る。前半は`0 ≤ progress < 50`、最初の4分の1は`0 ≤ progress < 25`。該当範囲の有限な1秒窓の算術平均を、ペア×条件×Setの代表値とする。Set間で平滑化・補間・前詰めはしない。
4. 隣接する5境界ごとに、50%版は前Setの`50 ≤ progress ≤ 100`と次Setの`0 ≤ progress < 50`、25%版は前Setの`75 ≤ progress ≤ 100`と次Setの`0 ≤ progress < 25`を別々に平均する。各条件の境界値は**次Set序盤 − 前Set終盤**（µV²/Hz）。同一ペアの条件差はEye Drop − Controlとする。
5. 欠測Setはペアの両条件でそのSet値をNaNにする。そのSetに隣接する境界もペアの両条件でNaNとする。有限なPSD窓がない側の値もNaN。0で埋めない。群平均・SD・Nは、該当Set／境界で両条件が有限なペアだけから求める。
6. 同じcacheで各Set全時間の未平滑平均もQC専用に再計算し、No1／No3の保存済みSetQuantification値と、全40ペア・利用可能Set・両条件で数値照合する。QC値は新規の主figureにはしない。

## Figure・数値・色

製品群ごとに各Set序盤の50%版・25%版（各6パネル）と境界の50%版・25%版（各5パネル）の計4 PNG、Noごとに8 PNGを保存する。各パネルでEye Dropを左、Controlを右に置き、バーは被験者間平均、白枠の点と薄い結線は対応する各ペアを示す。統計検定・有意記号は設けない。縦軸はSet序盤では`PSD (µV²/Hz)`、境界では`Between-Set PSD Difference (µV²/Hz)`。同一figure内の全パネルでy軸を共通とし、Set序盤は0始まり、境界は正負を扱う。図はArial、180 dpi、Set版34×9 inch・境界版30×9 inch、バー幅0.42、点サイズ150、軸名30 pt、目盛23 pt、Set名26 pt、条件名22 pt、製品名18 pt。ペア点のジッターは固定seedとする。

色はNo1〜No5と区別する新規配色。No6の点眼線系はCキューブ`#A73F50`、Vロート`#C75F69`、定量化バー・点は各`#BB6875`、`#D6878D`。No7の点眼線系は各`#6E594F`、`#96796A`、バー・点は各`#90786B`、`#AF9384`。Controlバー・点は既定`#66547D`。本解析では時間変化の新規線figureは作らないので、線系の色は系列の識別用設定としてのみ保持する。

## No7・Vロートプレミアム群の追加感度分析

No7の主結果は全40ペアのまま保持する。追加解析では、Vロートプレミアム群のペア**101–201をEye Drop・Controlの両条件とも**群集計から除く。これはNo7のSet序盤の図とペア別値で高値が目立ったペアの寄与を調べるための**事後・探索的な指定ペア除外**であり、ノイズ由来の確定診断でも、全被験者へ適用する機械的な除外基準でもない。Cキューブ群、No6、およびNo7の主結果には適用しない。

元の保存済みペア別Set値CSVとペア別境界値CSVの完全性、製品群とペア101–201の帰属を検証してから、このペアの行だけを外す。元cache・元ペア別CSV・主結果の図と群集計CSVは上書きせず、No7の4定義（Set序盤50%・25%、Set境界50%・25%）を同じ計算法・配色・図式で再集計する。図中とファイル名に`ExcludePair101-201`を明示する。Set図と境界図それぞれの共通y軸は、除外後の値から元と同じ規則で再設定する。Vロートプレミアム群の対象ペア数は20から19となるが、既知欠測Setと有限窓条件によるSet別・境界別の対応ありNは別途計算し、群集計CSVと実行ログに残す。推測統計は行わない。

追加成果物は、既存の`VRohtoPremium/SetQuantification/`と`VRohtoPremium/BetweenSetQuantification/`にPNG各2枚、対応する`Sub/tables/`の2フォルダに別名の群集計CSV各1件、`Sub/logs/`に入力CSV・除外指定・各N・未変更範囲を記載したJSON 1件とする。探索的な除外の前後を比較するための追加出力であり、「Vロートの効果」や一般化可能な差の証拠とはしない。

2026-11-09に保存済みのペア別CSV2件と主結果の群集計CSV2件の整合を検証して追加図4枚を出力した。Set序盤の対応ありNはSet 1–6の順に`18, 18, 19, 18, 19, 19`（50%・25%共通）、Set境界の対応ありNは1→2から5→6の順に`17, 18, 18, 18, 19`（50%・25%共通）。VロートのSet 6序盤50%の群平均差（Eye Drop−Control）は、主結果`+5.816`から感度分析`+0.170 µV²/Hz`になった。これは指定ペアの寄与を示す記述値であり、有意性や点眼効果を示さない。追加図の出力ログは`Sub/logs/No7_FzDeltaEarlyAbsolutePSD_ExcludePair101-201_RunSummary.json`。保存済みペア別値から再実行する場合は、No7入口に`--production-batch --excluded-pair-sensitivity-only`を指定する。

```text
実験本番_本解析/Phase4_脳波解析/
  No6_FzThetaEarlyAbsolutePSD/  （No7_FzDeltaEarlyAbsolutePSD/ も同型）
    CCube/{SetQuantification,BetweenSetQuantification}/  # PNGのみ
    VRohtoPremium/{SetQuantification,BetweenSetQuantification}/  # PNGのみ
    Sub/tables/{SetQuantification,BetweenSetQuantification}/  # ペア別値と群別集計CSV
    Sub/logs/  # 実行JSON
```

No7のVロートプレミアム群には、上記の同じ図フォルダへ`ExcludePair101-201`付きPNGを各2枚追加する。追加群集計CSV2件と追加実行JSON1件も`Sub/`配下へ主結果と区別できる名前で置く。

ペア別CSVには両条件の値・有限PSD窓数・欠損フラグ、境界の前後平均と差を残す。群別CSVには製品・窓幅・Set／境界ごとの対応ありN、条件別平均・SD、条件差の平均を残す。実行JSONに入力、cache設定、照合、対象数、図数、注意点を記録する。PNGや表からIDと条件の再照合が必要なら、非公開manifestおよびcacheメタデータに戻る。GitやNotionにペア別生データ・不要なID一覧を置かない。

## 実行済み検証・結果の読み方

2026-11-09に同じ共通エンジンからNo6・No7の**主結果**を別入口で実行した。No6・No7とも全40ペア（製品別20ペア）、各8 PNG、ペア別2 CSV、群集計2 CSV、実行JSONを出力した。Set別の対応ありNは19〜20、境界別は18〜20。これは既知の欠測Setと隣接境界による減少で、主結果への新たな被験者除外はない。全SetQCの値はNo1／No3保存値と一致した。図の生成と読み戻しを確認した。

観察として、Set 6序盤のEye Drop − Control群平均は、No6のVロートで前半`+0.119`・1/4`+0.068 µV²/Hz`、No7のVロートで前半`+5.816`・1/4`+4.422 µV²/Hz`だった。Set境界の条件差の符号はNo6で両製品とも5境界中2境界が正、No7ではCキューブ1境界、Vロート4境界が正だった。これは**記述値**であり、推測統計は行っていない。No7のVロートの正値を「低周波パワーの軽減」とは読めない。絶対PSDには個人差・残存ノイズがあり得るため、No4／No5の変化率結果と同一の主張に置き換えない。

実行入口は`解析プログラム/Phase4_脳波解析/Phase4_No6_FzThetaEarlyAbsolutePSD.py`と`Phase4_No7_FzDeltaEarlyAbsolutePSD.py`。共通計算は`phase4_early_fz_absolute.py`。非公開manifestを`--manifest`に指定し、`--production-batch --preflight-only`で全cacheを検証してから`--production-batch --all`を実行する。
