# Phase 4 No4–9｜結果フォルダとFigureの読み方

確認日：2026-11-10。OneDriveの現行フォルダ、代表PNG、描画コード、確定仕様を照合した共有用ガイド。

目的は、**Vロートプレミアムの効果につながる可能性のある脳波指標を探索し、Cキューブでも同じ見方で確認すること**。本書は結果の探し方・読み方を扱う。解析方法や採否を新たに変更するものではない。

## 最初に：保存場所と解析の対応

OneDrive内の起点：

```text
デスクトップ/SandBoxプロジェクト/ロート製薬フェーズ2 2026.5/
実験本番_本解析/Phase4_脳波解析/
```

| フォルダ | 対象 | 主に見る量 | 主な結果 |
|---|---|---|---|
| `No4_FzThetaEarlyChange/` | Fz・シータ4–7 Hz | Set 1からのPSD変化率 | 全時間推移、Set別、Set境界 |
| `No5_FzDeltaEarlyChange/` | Fz・デルタ1–3 Hz | Set 1からのPSD変化率 | 全時間推移、Set別、Set境界 |
| `No6_FzThetaEarlyAbsolutePSD/` | Fz・シータ4–7 Hz | 絶対PSD | Set序盤、Set境界 |
| `No7_FzDeltaEarlyAbsolutePSD/` | Fz・デルタ1–3 Hz | 絶対PSD | Set序盤、Set境界 |
| `No8_PzSetwiseIAF/` | Pz・アルファ8–15 Hz | アルファピーク周波数（IAF） | 個人PSD・IAF、IAF差分の群平均 |
| `No9_FzSetwiseIAF/` | Fz・アルファ8–15 Hz | アルファピーク周波数（IAF） | 個人PSD・IAF、IAF差分の群平均 |

帯域は上下端を含む。**現行No9はFzのSet全体IAF**。以前のPz前後半解析ではない。旧No10はNo9へ改番済み、前後半12値の解析は廃止済み。

### 共通のフォルダ名・比較単位

| 表記 | 意味 |
|---|---|
| `CCube`／図中`C Cube` | Cキューブを使用した被験者群 |
| `VRohtoPremium`／`V Rohto Premium` | Vロートプレミアム（Vプレ）を使用した被験者群 |
| `Eye Drop` | その製品を点眼した条件 |
| `Control` | 同じ被験者の点眼なし条件 |
| `Individual` | 1被験者＝2条件をまとめた個人PNG |
| `GrandAverage` | 製品群内の被験者間平均のPNG |
| `SetQuantification` | Setごとの代表値を2条件で比較するPNG |
| `BetweenSetQuantification` | 前Set終盤→次Set序盤の変化を2条件で比較するPNG |
| `Sub` | 数値表・採否・確認図・実行記録。主figureとは分離 |

- Cキューブ群とVプレ群は別の被験者群。各図の主な比較は、**同じ群のEye Drop対Controlという被験者内比較**。
- 個人ファイル名の`ID<初回ID>-<2回目ID>`／`Pair<初回ID>-<2回目ID>`は1人のペア。先に書かれたIDが必ずEye Dropとは限らない。
- `Sub`は補助資料のフォルダであり、No1–3の解析名に含まれる`_sub`とは別。
- 主figureはArial。PNGを拡大して軸の数値・単位・凡例・ファイル名の条件を確認する。

### 先に区別する3つの縦軸

| 量 | 意味 | 0の意味 |
|---|---|---|
| `PSD Change, %` | `(PSD ÷ 同じ条件のSet 1全体平均 − 1) × 100` | 自分自身・同じ条件のSet 1平均と同じ |
| `PSD (µV²/Hz)` | 正規化していない帯域平均パワースペクトル密度 | PSDが0。基準Setとの差ではない |
| `IAF Change (Hz)` | `そのSetのIAF − 同じ条件のSet 1のIAF` | 自分自身・同じ条件のSet 1と同じ周波数 |

PSD Changeの+100%は基準の2倍、−50%は半分。IAF Changeの+0.5 Hzはピークが0.5 Hz高いという意味で、パワーが増えたという意味ではない。

## No4｜`No4_FzThetaEarlyChange`：前頭シータの変化率

### フォルダ構造

```text
No4_FzThetaEarlyChange/
├── CCube/
│   ├── Individual/
│   ├── GrandAverage/
│   ├── SetQuantification/
│   ├── BetweenSetQuantification/
│   └── SensitivityAnalysis/          空
├── VRohtoPremium/                   上と同じ5フォルダ
└── Sub/
    ├── tables/
    │   ├── Set1Baseline/
    │   ├── SetQuantification/
    │   ├── BetweenSetQuantification/
    │   ├── GrandAverage/
    │   └── OutlierReview/            空
    └── logs/
```

| 製品内のフォルダ | 中身 | 現行PNG数：Cキューブ／Vプレ |
|---|---|---:|
| `Individual` | 全6 Setの個人PSD Change推移 | 20／19 |
| `GrandAverage` | 全時間推移の群平均±SEM | 1／1 |
| `SetQuantification` | `FullSet`・`FirstHalf`・`FirstQuarter`の各6パネル図 | 3／6（主3＋除外版3） |
| `BetweenSetQuantification` | `BoundaryHalf`・`BoundaryQuarter`の各5パネル図 | 2／4（主2＋除外版2） |
| `SensitivityAnalysis` | 予約用。**現在は空** | 0／0 |

除外版を探すときは`SensitivityAnalysis`ではなく、**2つの定量化フォルダ内の`ExcludePair...`付きPNG**を見る。

### `Individual`：個人の全時間推移

| 要素 | 読み方 |
|---|---|
| 横軸 | `Experimental Progress, %`、0–600。Set 1=0–100、Set 2=100–200、…、Set 6=500–600 |
| progressの基準 | 各Setの**実時間**の開始〜終了を0–100%へ換算。試行番号でも秒でもない |
| 縦軸 | `PSD Change, %`。Fz・4–7 Hzの、各条件自身のSet 1全体平均からの変化率 |
| 線 | Eye DropとControlの2本。個人の系列で、群平均ではない。シェードなし |
| 平滑化 | 実時間でSet内60秒平均をかけてからprogress表示。Setをまたいで平均しない |
| 灰色の縦破線 | Set境界。休憩中の時間は表示していない |
| 灰色の横線 | 0%。条件自身のSet 1平均と同じ水準 |
| 縦軸スケール | 0中心の対称軸。個人ごとの表示値に合わせて変わる |

各Setは横幅が同じでも、実際の継続時間は同じとは限らない。線の傾きから秒あたりの変化速度を直接比較しない。Set間は別々の系列であり、休憩中の変化を描いた線ではない。

### `GrandAverage`：全時間推移の群平均

- 軸・Set境界・0の意味は個人図と同じ。
- 2本の実線＝個人の平滑化済み変化率を、各Set100 progress点へそろえた後の**被験者等重み平均**。
- 同色の薄い帯＝平均±SEM（標準誤差）。SD・95%信頼区間・有意差範囲ではない。
- 同じNoの2製品で共通の対称y軸。平均線の最大絶対値を基準に余白を設ける。No5や個人図とは軸範囲が異なり得る。
- このフォルダは主結果のみ。定量化の指定ペア除外をGrand-averageへは適用していない。
- NはSet・progress点により変わり得る。正確な値は`Sub/tables/GrandAverage`。

### `SetQuantification`：どの時間帯を平均したか

1枚にSet 1–6の**独立した6パネル**。各パネルは左Eye Drop・右Control。バー・点・結線の共通の見方は後述。

| ファイル名の語 | 図のタイトル | 対象範囲 | 縦軸 |
|---|---|---|---|
| `FullSet` | `Full Set` | 各Setの0–100% | `PSD Change, %` |
| `FirstHalf` | `First 50% of Each Set` | 各Setの0%以上50%未満 | 同上 |
| `FirstQuarter` | `First 25% of Each Set` | 各Setの0%以上25%未満 | 同上 |

- 各点＝その被験者・条件・Setの対象時間帯における、**平滑化前**の変化率の平均。
- baselineは3版とも「その条件のSet 1全体平均」。前半版でもSet 1前半をbaselineにし直さない。
- `FullSet`は「各Setを全時間で平均した6つの比較」。**6 Setをまとめた1つの比較ではない**。
- Set 1の`FullSet`は定義上ほぼ0%。`FirstHalf`・`FirstQuarter`のSet 1は0%でなくてよい。
- 例：`No4_FzThetaEarlyChange_SetQuantification_FirstHalf_VRohtoPremium.png`。

### `BetweenSetQuantification`：Setをまたぐ差

1枚に`Set 1 → 2`から`Set 5 → 6`までの**独立した5パネル**。

| ファイル名の語 | 前Setで使う範囲 | 次Setで使う範囲 |
|---|---|---|
| `BoundaryHalf` | 後半50–100% | 前半0%以上50%未満 |
| `BoundaryQuarter` | 終盤75–100% | 序盤0%以上25%未満 |

**各点・各バーの縦軸は、条件ごとの「次Set序盤平均 − 前Set終盤平均」**。`Transition in PSD Change (pp)`と表記する。

- 単位pp＝percentage point。変化率同士の引き算で、もう一度割り算した増減率ではない。
- 例：前Set終盤が+30%、次Set序盤が+10%なら−20 pp。
- 負：次Set序盤で低下。正：上昇。0：前後の平均が同じ。
- 左バーはEye Dropでの前後差、右バーはControlでの前後差。**バーそのものはEye Drop − Controlではない**。
- 左が右より低い：Eye Dropでより低下した、または上昇が小さかった方向。疲労改善の証明ではない。
- 図のタイトル`Previous Last 50% to Next First 50%`等で範囲を確認する。

### 除外版・欠測・補助資料

- 主結果：利用可能39ペア（Cキューブ20、Vプレ19）。片条件のSet 1欠測でbaselineが作れない1ペアは対象外。
- Vプレの指定1ペア除外版：定量化だけに計5枚追加。`ExcludePair<ペア>`／タイトル`Excluding Pair ...`で識別する。
- 除外版は両条件から同じペアを除外。候補18名、Set／境界の実有効Nは17–18。縦軸は除外後に再設定する。
- 個人図は欠測条件だけ空白。群平均・定量化はそのSetを両条件とも除外。境界比較は前後2 Set×両条件が必要。
- `Sub/tables/Set1Baseline`＝条件別baseline、`SetQuantification`＝個人代表値・群平均・SD・N、`BetweenSetQuantification`＝前後平均・差・群集計、`GrandAverage`＝progress点別の平均・SD・SEM・N。
- `Sub/logs`＝入力・適用範囲・出力・検証記録。`OutlierReview`は現状空。

## No5｜`No5_FzDeltaEarlyChange`：前頭デルタの変化率

### フォルダ構造

```text
No5_FzDeltaEarlyChange/
├── CCube/
│   ├── Individual/
│   ├── GrandAverage/
│   ├── SetQuantification/
│   ├── BetweenSetQuantification/
│   └── SensitivityAnalysis/          空
├── VRohtoPremium/                   上と同じ5フォルダ
└── Sub/
    ├── tables/
    │   ├── Set1Baseline/
    │   ├── SetQuantification/
    │   ├── BetweenSetQuantification/
    │   ├── GrandAverage/
    │   └── OutlierReview/            空
    └── logs/
```

No4と同じ図式・時間範囲で、**対象帯域をFzデルタ1–3 Hzに変更**した結果。baselineもデルタ帯のSet 1平均であり、シータのbaselineは使わない。

| フォルダ | 横軸・構成 | 縦軸・線／点の意味 | PNG数：C／V |
|---|---|---|---:|
| `Individual` | 全6 Setのprogress 0–600% | `PSD Change, %`。個人2条件の60秒平滑化後の推移 | 20／19 |
| `GrandAverage` | 同じprogress | `PSD Change, %`。被験者平均2線±SEM | 1／1 |
| `SetQuantification` | Set 1–6の6パネル、各々左Eye Drop・右Control | `PSD Change, %`。未平滑の`FullSet`・`FirstHalf`・`FirstQuarter`平均 | 3／6 |
| `BetweenSetQuantification` | Set 1→2〜5→6の5パネル、各々2条件 | `Transition in PSD Change (pp)`。次序盤−前終盤、50%／25% | 2／4 |
| `SensitivityAnalysis` | 現状空 | 除外版は上の定量化フォルダ内に並置 | 0／0 |

- No4と同様、Set 1全体がbaseline。前半・1/4版のSet 1は0%に固定されない。
- 時間推移の縦破線＝Set境界、横線＝基準の0%。個人は可変対称軸、Grand-averageはNo5内2製品で共通対称軸。
- 線は緑系Eye Dropと深紫Control。バー・点は同系統の少し淡い色（色一覧参照）。
- Vプレの指定1ペアを除いた定量化5図を追加済み。**No4とは除外するペアが異なる**。ファイル名の`ExcludePair...`を確認する。
- 主結果39ペア、Vプレ除外版候補18名。個人図・Grand-averageは指定ペア除外前の主結果のまま。
- 欠測規則・バー／点・差の正負・軸の読み方はNo4と共通。`Sub`の各フォルダもNo4と同じ役割。
- 例：`No5_FzDeltaEarlyChange_BetweenSetQuantification_BoundaryQuarter_VRohtoPremium.png`は、デルタ変化率の「前Set最後25%→次Set最初25%」の主結果。

## No6｜`No6_FzThetaEarlyAbsolutePSD`：前頭シータの絶対PSD

### フォルダ構造

```text
No6_FzThetaEarlyAbsolutePSD/
├── CCube/
│   ├── SetQuantification/
│   └── BetweenSetQuantification/
├── VRohtoPremium/                   上と同じ2フォルダ
└── Sub/
    ├── tables/
    │   ├── SetQuantification/
    │   └── BetweenSetQuantification/
    └── logs/
```

**Set 1で割らない、Fzシータ4–7 Hzの絶対PSD**。No4と同じ序盤・境界を、元のパワーの単位で見る。

| フォルダ | 保存図 | 横軸・構成 | 縦軸 |
|---|---|---|---|
| `SetQuantification` | `FirstHalf`・`FirstQuarter`、各製品2枚 | Set 1–6の6パネル。各々左Eye Drop・右Control | `PSD (µV²/Hz)` |
| `BetweenSetQuantification` | `BoundaryHalf`・`BoundaryQuarter`、各製品2枚 | Set 1→2〜5→6の5パネル。各々2条件 | `Between-Set PSD Difference (µV²/Hz)` |

- Set図の各点＝その条件のSet序盤50%／25%における未平滑の帯域平均PSDの時間平均。バー＝被験者平均。
- Set図は0始まり。値が大きいほど、その時間帯のシータPSDが大きい。**Set 1に対する増加率ではない**。
- 境界図の各点＝**次Set序盤の絶対PSD平均 − 前Set終盤の絶対PSD平均**。No4のppと単位が異なる。
- 境界図の負＝低下、正＝上昇。左右2本のバーは各条件の前後差で、条件差そのものではない。
- 色は赤〜ローズ系Eye Drop、紫Control。点・結線の意味は共通ルール参照。
- 同一PNGの全パネルは同じ縦軸。Set図と境界図、50%版と25%版、製品間では範囲が変わり得る。
- 主結果は各製品20ペアから利用可能なSet／境界を採用。Set 1欠測だけで他Setまで全除外しない。追加の指定ペア除外版はない。
- **`FullSet`、個人時間変化、Grand-average、TFM、topographyのPNGはNo6にはない**。全Set平均はNo1との整合確認用で、今回の主figureにはしていない。
- `Sub/tables`の2フォルダ＝個人の範囲別値・前後平均・差と、群平均・SD・N。`Sub/logs`＝実行・照合記録。
- 例：`No6_FzThetaEarlyAbsolutePSD_SetQuantification_FirstHalf_CCube.png`。

## No7｜`No7_FzDeltaEarlyAbsolutePSD`：前頭デルタの絶対PSD

### フォルダ構造

```text
No7_FzDeltaEarlyAbsolutePSD/
├── CCube/
│   ├── SetQuantification/
│   └── BetweenSetQuantification/
├── VRohtoPremium/                   上と同じ2フォルダ
└── Sub/
    ├── tables/
    │   ├── SetQuantification/
    │   └── BetweenSetQuantification/
    └── logs/
```

No6と同じ定義を、**Fzデルタ1–3 Hzの絶対PSD**へ適用した結果。No5の変化率版との違いはSet 1基準の割り算をしないこと。

| フォルダ | 中身・軸の意味 | PNG数：C／V |
|---|---|---:|
| `SetQuantification` | `FirstHalf`・`FirstQuarter`。6 Set×2条件。縦軸`PSD (µV²/Hz)` | 2／4（主2＋除外版2） |
| `BetweenSetQuantification` | `BoundaryHalf`・`BoundaryQuarter`。5境界×2条件。縦軸`Between-Set PSD Difference (µV²/Hz)` | 2／4（主2＋除外版2） |

- Set図：序盤の平均PSD。境界図：**次Set序盤平均 − 前Set終盤平均**。負ならその条件で低下。
- バー＝条件内の被験者平均、白枠点＝個人値、薄い結線＝同じ人の2条件。色は茶系Eye Drop、紫Control。
- Set図は0始まり。境界図は正負を表示。同一PNG内では全パネル共通、除外版は残った値で縦軸を再設定する。
- 主結果は各製品20ペアから開始。Vプレだけ、指定**2ペア**を両条件から除いた4図を並置。
- 除外版の語は`ExcludePairs<ペア>_<ペア>`。タイトルも`Excluding Pairs ... and ...`。以前の**1ペアだけの除外版は現行には残していない**。
- 現行除外版の候補は18名。Set別の有効Nは順に17・17・18・17・18・18、境界別は16・17・17・17・18（50%／25%とも）。
- 個人推移、Grand-average、`FullSet`、TFM、topographyはNo7内にない。`Sub`にはNo6と同じ数値表に加え、除外版の群集計・記録を別名で保存。
- No5とNo7ではbaselineの有無も除外集合も異なるため、図の似た色・形だけで同じ解析とみなさない。

## No8｜`No8_PzSetwiseIAF`：頭頂Pzのアルファピーク周波数

### フォルダ構造

```text
No8_PzSetwiseIAF/
├── CCube/
│   ├── Individual/                  個人3パネルPNG 20枚
│   └── GrandAverage/                全利用可能版・追加選別版 各1枚
├── VRohtoPremium/                   上と同じ構造・枚数
└── Sub/
    ├── tables/
    │   └── GrandAverage/
    ├── PeakClarityReview/           No8・No9の共通採否表もここ
    │   ├── CCube/                  No8の確認図20枚
    │   └── VRohtoPremium/           No8の確認図20枚
    ├── logs/
    └── history/                    過去版。現行採否には使わない
```

### `Individual`：1人につき横3パネル

ファイル名：`Pair<初回ID>-<2回目ID>_No8_Pz_SetwiseIAF_ThreePanel.png`。

| 要素 | 左パネル：Eye Drop | 中央パネル：Control | 右パネル：IAF |
|---|---|---|---|
| 横軸 | `Frequency (Hz)`、1–30 Hz | 同左 | `Set`、1–6 |
| 縦軸 | `PSD (µV²/Hz)` | 同左 | `IAF (Hz)`、7.5–15.5表示・目盛8–15 |
| 線 | Set 1–6の各1本、最大6本 | 同左 | Eye DropとControlの2本 |
| 丸点 | なし | なし | 各Setから推定したピーク周波数 |
| 色 | 点眼色の明→暗でSet 1→6 | 紫の明→暗でSet 1→6 | 点眼基本色と深紫Control |
| 灰色点線 | 8 Hz・15 Hzの探索帯域境界 | 同左 | 帯域境界線なし |

- PSDパネル：各Set全体の有効データから得た**1回周波数平滑化済みPSD**。Setの途中経過を6本にした図ではない。
- 平滑化：0.1 Hz gridの中心5点（前後0.2 Hz）を1回平均。同じPSDから8–15 Hz内の最も高い局所ピークを選ぶ。
- **左と中央の縦軸は独立**。各パネル内の全Set・1–30 Hzの最高点が軸高約80%になる。alpha以外の大きな値でも軸が広がる。
- 左右の見かけの高さだけで条件間パワー差を判断しない。数値目盛を確認する。軸に`×10ⁿ`等があればその倍率も読む。
- 右図は**絶対周波数**。上なら高周波、下なら低周波。PSDの大きさ・%変化ではない。
- 右図の線は6つの離散値の結線。Set内の連続変化を観測したものではない。NaN位置をまたいで結ばない。
- `unavailable`／`No usable PSD`や欠けた点は算出不能。0 Hzや「ピークが低い」という意味ではない。
- 小さい峰や複数峰でも局所ピークが計算されることがある。大きなIAFジャンプは、別の山への選択切替の場合もある。右図だけでなく左・中央を併読する。

### `GrandAverage`：絶対IAFではなく、Set 1からの差

| ファイル末尾 | 図のタイトル | 対象 |
|---|---|---|
| `AllAvailable.png` | `All available participants` | 基準と当該SetのIAFが両条件で使える全対象 |
| `SelectedParticipants.png` | `Selected participants` | 明瞭な単峰の定性確認・最新採否を反映した追加対象 |

- 横軸：`Set`、1–6。縦軸：`IAF Change (Hz)`。
- 個人・条件ごとに**その条件自身のSet 1 IAFを引いてから**被験者平均する。PSDを被験者平均してからピークを再検出する方法ではない。
- 2本の実線と丸点＝条件別の平均差分。同色の帯＝平均±SEM。点は個人ではなく群平均。
- Set 1は計算上0 Hz差。正＝基準より高周波化、負＝低周波化。点眼線が下なら点眼でより低周波側へ変化した方向であり、直ちに「改善」ではない。
- **全No8・No9、2製品、2対象版で縦軸−1.1〜+1.1 Hz共通**。目盛は−1、−0.5、0、0.5、1。
- 基準Set 1が片条件でも欠測なら、その人は当該Noの群図全体に使えない。後続Set欠測はそのSetだけ両条件を群平均から外す。
- 個人図には40名が残る。追加選別版で不採用でも個人図や元IAFは消していない。

### 現行の選別版と人数

- 「一つの山として明瞭なalphaピークが見える人」への追加選別。律動的・櫛状の複数峰で代表峰が曖昧な例などを除く。
- 全Set明瞭は必須ではない。各条件に明瞭区間があること等を最低条件とし、最新の利用者判断・品質上の追加除外を適用する。
- 採用者の不明瞭な後続Setを一律に捨てる方式ではない。既存の有限IAFを保持する。
- No8の確定採用はCキューブ12名・Vプレ10名。実有効NはCキューブ11–12名、VプレはSet順に10・10・10・9・10・10名。
- Vプレ選別版には、低PSDとIAF急変を確認した指定1ペアの追加除外を反映済み。全利用可能版には適用していない。PSD<1の一律除外規則ではない。
- 詳細な採否は`Sub/PeakClarityReview/GrandAverageSelection_Final.csv/.md`。`ParticipantReview.csv`のID横の**「Grand-average採用（追加選別版）」**も確認できる。

### `Sub`：数値・ピーク確認図の見方

| 保存先 | 内容・使いどころ |
|---|---|
| `tables/No8_IAF_Estimates.csv` | SetごとのIAF、候補峰、選択峰PSD、有効窓量、欠測理由 |
| `tables/No8_PeakAvailability.csv` | IAFが算出できた／できなかった件数 |
| `tables/ParticipantManifest.csv` | 非公開の被験者・条件・製品対応 |
| `tables/GrandAverage/ParticipantIAFChange.csv` | 個人IAF、基準IAF、差分、採否 |
| `tables/GrandAverage/GroupSummary.csv` | 群平均・SD・SEM・Set別N。線・帯の数値を確認する表 |
| `tables/GrandAverage/InclusionByInterval.csv` | No・対象版・Setごとの採否と理由 |
| `PeakClarityReview/CCube`・`VRohtoPremium` | Set別に拡大したPSD確認PNG。主図に小さく見える峰の確認用 |
| `PeakClarityReview/GrandAverageSelection_Final.*` | **No8・No9両方の最新の確定採否** |
| `PeakClarityReview/ParticipantReview.csv`・`IntervalReview.csv` | ペア別／条件・Set別の元の形状観察、理由、最新採否との対応 |
| `PeakClarityReview/GroupSummary.csv` | 形状観察の集計。上の同名の群平均表とは別物 |
| `PeakClarityReview/PeakClarityReview.md`・`SavedEstimateInventory.csv` | 観察の説明、保存IAFの照合資料 |
| `logs` | 再集計・採否改訂・独立検証の記録 |
| `history` | 改番前・採否変更前の表や監査。最新の結果・採否の参照先ではない |

ピーク確認PNGは**上段Eye Drop、下段Control、列はSet 1–6**。横軸6–17 Hz、縦軸PSD、黒い線＝保存済み平滑化PSD、赤い点＝保存IAFの選択位置。8/15 Hzの点線と、1–30 Hz全体の小図を添える。各小パネルのy軸は独立。**赤い点は「明瞭と合格判定した印」ではない**。

観察記号はC＝明瞭、A＝判断保留、U＝不明瞭、M＝PSD欠測等で評価不能。記号は元の観察であり、最新の採用／不採用と同一ではない。

## No9｜`No9_FzSetwiseIAF`：前頭Fzのアルファピーク周波数

### フォルダ構造

```text
No9_FzSetwiseIAF/
├── CCube/
│   ├── Individual/                  個人3パネルPNG 20枚
│   └── GrandAverage/                全利用可能版・追加選別版 各1枚
├── VRohtoPremium/                   上と同じ構造・枚数
└── Sub/
    ├── tables/
    │   └── GrandAverage/
    ├── PeakClarityReview/
    │   ├── CCube/                  No9の確認図20枚
    │   └── VRohtoPremium/           No9の確認図20枚
    └── logs/
```

No8と同じ計算・図式を**Fz**へ適用。周波数は同じ8–15 Hzであり、Fzだからシータ／デルタを推定しているわけではない。

| 保存先 | Figureの読み方 |
|---|---|
| `Individual`左 | Eye DropのPSD。横軸1–30 Hz、縦軸µV²/Hz。Set 1→6を赤系の明→暗の6線で表示 |
| `Individual`中央 | ControlのPSD。軸・Set順は同じ、色は紫系。左とは独立y軸 |
| `Individual`右 | 横軸Set 1–6、縦軸`IAF (Hz)`。絶対周波数の2条件推移、7.5–15.5 Hz表示 |
| `GrandAverage/*AllAvailable.png` | 利用可能者の条件別Set 1差分を平均。横軸Set、縦軸`IAF Change (Hz)`、平均±SEM |
| `GrandAverage/*SelectedParticipants.png` | Fzで明瞭な単峰が見える人への追加選別版。同じ軸・計算法 |
| `Sub/PeakClarityReview/<製品群>` | FzのSet別PSD確認図。上Eye Drop／下Control、黒線と赤い保存IAF点。読み方はNo8と共通 |

- 色以外の表示規則はNo8と同じ：PSD左・中央は各々最大値が約80%、灰色点線8/15 Hz、右図は白枠丸点と2条件の線。
- 個人図は`Pair<初回ID>-<2回目ID>_No9_Fz_SetwiseIAF_ThreePanel.png`。旧No10の内容を現行No9として読む。
- 群図は全版−1.1〜+1.1 Hz。Set 1は0。欠測位置は詰めない。追加選別は個人図へ逆適用しない。
- 確定採用はCキューブ11名・Vプレ10名。実有効Nはそれぞれ10–11名・9–10名。
- **PzとFzの採用集合は別**。同じ被験者が両方で採用されるとは限らず、No8の除外をNo9へ自動適用しない。
- `Sub/tables`はNo8と同じ構成（推定表等のNo表記だけNo9）。群平均の値・SEM・Nはその配下の`GrandAverage`。
- 両Noの確定採否・元評価の統合表は**No8側の`Sub/PeakClarityReview`**にある。No9側には自身の確認図と保存推定値一覧を置く。

## 共通の読み方：定量化、色、ファイル名

### No4–7のバー・点・結線

| 見える要素 | 意味・注意 |
|---|---|
| 左バー／右バー | Eye Drop／Controlの**被験者間算術平均**。試行数・時間窓数で重み付けした平均ではない |
| 白い枠の色付き点 | 1被験者の、その条件・Set／境界の代表値。1点＝1試行ではない |
| 薄い灰色の斜線 | **同じ人の2条件を結ぶ線**。Set間の推移線、回帰線、信頼区間ではない |
| 左右の点の散らばり | 重なりを避ける横ジッター。横位置に数量的な意味はない |
| 灰色の水平線 | 正負のある図の0基準。統計的な判定線ではない |
| 誤差棒・シェード | バー図には付けていない。散らばりは個人点で示す。SDは補助CSVにある |
| `*`・`n.s.`・p値 | **No4–9では推測統計を実施しておらず、表示しない**。印がないことを「非有意」と読まない |
| 縦軸 | 同一PNGの全6 Set／5境界で共通。別PNG・除外前後では自動調整されるため、数値目盛で比較する |

No4・5および境界図の正負軸は、0より上の幅が下の約2倍。上下対称とは限らない。No6・7のSet序盤図は0始まり。目盛は概ね3–6個のキリのよい数字。

**差の向きの再確認**：境界図＝「次−前」を各条件で計算した2群。補助表の`EyeDropMinusControl...`＝その2条件の値をさらに「Eye Drop−Control」で引いたもの。両者を混同しない。

### 色一覧

色は条件・製品・解析を識別するためのもの。効果の正負や有意性を表すものではない。下表は指定色であり、バー・点・帯は透明度により淡く見える。

| No | Eye Drop：Cキューブ | Eye Drop：Vプレ | 主figureでの使い分け |
|---|---|---|---|
| No4 | 青 `#2679A8`／バー・点`#5A9FC3` | シアン `#3AA4B8`／バー・点`#70B7C3` | 前者＝時間推移線、後者＝定量化 |
| No5 | 深緑 `#347C62`／バー・点`#60A184` | 緑 `#66A86B`／バー・点`#87BC8B` | 同上 |
| No6 | ローズ系 `#BB6875` | 淡いローズ系 `#D6878D` | バー・点。時間推移の新規線図はない |
| No7 | 茶系 `#90786B` | 淡い茶系 `#AF9384` | バー・点。時間推移の新規線図はない |
| No8 | 青 `#2456A6` | 明るい青 `#5689CF` | 個人IAF・群IAF差分の基本線色 |
| No9 | 赤 `#A63D46` | 淡い赤 `#CF7278` | 個人IAF・群IAF差分の基本線色 |

- Control：時間推移・IAFの線は深紫`#402B5D`、No4–7のバー・点は紫`#66547D`。
- No8・9のPSD6線は上記基本色と同系色の**Set 1が明るく、Set 6が暗い濃淡**。右のIAF線やGrand-averageにはSet別濃淡を使わない。

### ファイル名の読み分け

| 語 | 何を選ぶか |
|---|---|
| `FullSet` | 各Set全時間の平均。No4・5のみ |
| `FirstHalf`／`FirstQuarter` | 同じSetの前半50%／最初25% |
| `BoundaryHalf`／`BoundaryQuarter` | 前Set最後50%／25%と次Set最初50%／25%の差 |
| `ExcludePair...` | 指定1ペア除外の追加図。No4・5のVプレ定量化 |
| `ExcludePairs..._...` | 指定2ペア除外の追加図。No7のVプレ定量化 |
| 除外語なし | 追加の指定ペア除外をしない主結果。既知欠測等は処理済み |
| `ThreePanel` | No8・9の個人PSD2図＋IAF1図 |
| `AllAvailable`／`SelectedParticipants` | No8・9の全利用可能版／追加選別版 |

除外された具体的なペアはファイル名・図のタイトル・最新採否表で確認する。本ガイドでは個人ごとのファイル列挙を省略する。

## 数値を確かめたいとき・解釈上の注意

### 補助CSVを探す語

| ファイル名・場所 | 役割 |
|---|---|
| `*_PairSetWindowValues.csv` | No4–7の被験者ごとのSet・定量化範囲の値 |
| `*_GroupSetWindowSummary*.csv` | 同上の製品別・条件別平均、SD、対応ありN |
| `*_PairSetTransitionValues.csv` | No4–7の個人の前後平均、次−前、Eye Drop−Control |
| `*_GroupSetTransitionSummary*.csv` | 同上の群集計・N。除外版はファイル名にも除外語がある |
| `GrandAverage`配下の値CSV | No4・5はprogress別、No8・9はSet別の平均・SEM・N |
| No8の`GrandAverageSelection_Final.*` | No8・9の**現在の採否**。古いログ・形状記号から採否を推測し直さない |

### 最小限の方法・欠測の前提

- No4–7：Phase 1不良区間と重なるPSD窓、および各セッション・chのlog PSD上側3SDを超える窓を除いた保存値を使用。定量化は未平滑。No4・5の推移だけ60秒平滑化。
- No8・9：各Setの有効10秒Hann窓（5秒間隔）のPSDを平均し、周波数方向5点で1回平滑化してピークを選ぶ。Phase 1不良区間を含む窓は使わない。No4–7のlog3SDを重ねて適用する方式ではない。
- 欠測は0で埋めない。群図では原則、同一Set／境界で使える**両条件の対応ペア**をそろえる。Set・境界によりNが違う。
- No4・5はbaselineが必要なため主対象39名、No6・7は40名から開始。No8・9の個人図は各40名、全利用可能Grand-averageのSet別Nは各製品18–19名。対象数の違いを図の違いと取り違えない。

### 結果を見る順序

1. 解析No・ch・単位・製品群を確認する。
2. 通常版を見て、個人点／個人図で少数の極端値への依存を確認する。
3. 同じ時間範囲の除外・選別版があれば並べる。軸の数値と対象Nも確認する。
4. 境界図では「次−前」の符号と、Eye Drop／Controlの両方を見る。
5. IAFでは元PSDの山の形を確認してから、基準差の群図を読む。

いずれも探索結果。線やバーの高低、SEM帯の重なり、特定ペアを外した後の見た目だけで、製品効果・疲労／眠気改善・ノイズ原因を確定しない。**Set開始／境界は、実際の点眼時刻そのものを示すイベント軸ではない**。今回のNo4–9にtopographyや個人TFMは含まれない。

## 方法の詳細・確認範囲

- [No4・No5：Fz序盤PSD Change解析仕様](Phase4_No4_No5_Fz序盤PSDChange_解析仕様.md)
- [No6・No7：Fz序盤絶対PSD解析仕様](Phase4_No6_No7_Fz序盤絶対PSD_解析仕様.md)
- [No8・No9：IAF共有用解析仕様](Phase4_No8_No9_共有用解析仕様.md)
- [解析上の注意事項・採否の例外](解析上の注意事項.md)

本書は2026-11-10時点の**指定OneDriveローカル同期先**のファイル名・階層・件数、代表figure、現行描画実装と上記仕様を確認して作成した。再解析・figure変更・採否変更は行っていない。クラウドサーバー側の同期完了を示す文書ではない。最新仕様・最新採否は上記の正本と現行`Sub`を参照し、`history`の記録とは区別する。
