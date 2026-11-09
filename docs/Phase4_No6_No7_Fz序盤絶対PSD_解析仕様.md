# Phase 4 No6・No7：Fz序盤絶対PSD｜探索解析仕様

## 目的・位置づけ

No4／No5で扱ったSet 1基準の変化率とは別に、同じ時間窓を**絶対PSD**（µV²/Hz）で評価する。No6はFzシータ4–7 Hz、No7はFzデルタ1–3 Hzであり、上端binを含む。Cキューブ群とVロートプレミアム群を別々に、Eye DropとControlを被験者内で対応づける。点眼直後の改善を立証する解析ではなく、各Set序盤とSet境界に着目する探索である。Set境界を実際の点眼時刻と同一視しない。

| No | 代表ch・帯域 | 読み取り専用入力 | OneDrive出力 |
|---|---|---|---|
| No6 | Fz・4,5,6,7 Hz | No1_FmTheta のPSDTimeSeries cache | `Phase4_脳波解析/No6_FzThetaEarlyAbsolutePSD/` |
| No7 | Fz・1,2,3 Hz | No3_FrontalDelta のPSDTimeSeries cache | `Phase4_脳波解析/No7_FzDeltaEarlyAbsolutePSD/` |

No1／No3の既存の個人時間変化・Grand-average・全Set定量化は変更しない。新しいWelch計算、平滑化、ローカル派生cache、topography、TFMは作らない。目視で挙がった特定ペアも追加除外せず、各群20ペア、計40ペアを対象とする。Set 1が欠損したペアも、Set 1の基準値を要しないため、利用可能な他Setには含める。

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

```text
実験本番_本解析/Phase4_脳波解析/
  No6_FzThetaEarlyAbsolutePSD/  （No7_FzDeltaEarlyAbsolutePSD/ も同型）
    CCube/{SetQuantification,BetweenSetQuantification}/  # PNGのみ
    VRohtoPremium/{SetQuantification,BetweenSetQuantification}/  # PNGのみ
    Sub/tables/{SetQuantification,BetweenSetQuantification}/  # ペア別値と群別集計CSV
    Sub/logs/  # 実行JSON
```

ペア別CSVには両条件の値・有限PSD窓数・欠損フラグ、境界の前後平均と差を残す。群別CSVには製品・窓幅・Set／境界ごとの対応ありN、条件別平均・SD、条件差の平均を残す。実行JSONに入力、cache設定、照合、対象数、図数、注意点を記録する。PNGや表からIDと条件の再照合が必要なら、非公開manifestおよびcacheメタデータに戻る。GitやNotionにペア別生データ・不要なID一覧を置かない。

## 実行済み検証・結果の読み方

2026-11-09に同じ共通エンジンからNo6・No7を別入口で実行した。No6・No7とも全40ペア（製品別20ペア）、各8 PNG、ペア別2 CSV、群集計2 CSV、実行JSONを出力した。Set別の対応ありNは19〜20、境界別は18〜20。これは既知の欠測Setと隣接境界による減少で、新たな被験者除外はない。全SetQCの値はNo1／No3保存値と一致した。図の生成と読み戻しを確認した。

観察として、Set 6序盤のEye Drop − Control群平均は、No6のVロートで前半`+0.119`・1/4`+0.068 µV²/Hz`、No7のVロートで前半`+5.816`・1/4`+4.422 µV²/Hz`だった。Set境界の条件差の符号はNo6で両製品とも5境界中2境界が正、No7ではCキューブ1境界、Vロート4境界が正だった。これは**記述値**であり、推測統計は行っていない。No7のVロートの正値を「低周波パワーの軽減」とは読めない。絶対PSDには個人差・残存ノイズがあり得るため、No4／No5の変化率結果と同一の主張に置き換えない。

実行入口は`解析プログラム/Phase4_脳波解析/Phase4_No6_FzThetaEarlyAbsolutePSD.py`と`Phase4_No7_FzDeltaEarlyAbsolutePSD.py`。共通計算は`phase4_early_fz_absolute.py`。非公開manifestを`--manifest`に指定し、`--production-batch --preflight-only`で全cacheを検証してから`--production-batch --all`を実行する。
