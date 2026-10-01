# Phase 2 No1：反応時間（RT）解析 共有用仕様書

> **確定版（2026年10月2日）**：本書には、現行スクリプトで再現される最終決定事項だけを記載する。

## 1. 解析の目的

ガボール課題中の反応時間（Reaction Time; RT）が実験の進行に伴ってどのように変化するかを可視化・定量化し、目薬あり条件と目薬なし条件（Control）を比較する。

被験者は、使用した目薬に基づいて次の2群に分ける。2製品群は混合せず、各群内で同一被験者の2条件を対応付けて比較する。

- Cキューブ群：Eye Drop vs Control
- Vロートプレミアム群：Eye Drop vs Control

## 2. 解析の概要

解析には、生の行動データに含まれる各セットのresults CSVを使用する。各被験者は2セッション、各セッションは6セット、各セットは320刺激試行で構成される。

No1では、次の3種類の結果を作成する。

1. 被験者別のRT推移：セット内で平滑化したRTを、6セット連続の時間推移として表示する。
2. 製品群別のGrand-average：被験者別の平滑化RTを、同じセット・同じ進捗位置で被験者間平均する。
3. セット別RT定量化：平滑化前の試行別RTから、各セットの全320試行平均と最後80試行平均の2種類を算出し、Eye DropとControlを被験者内で比較する。

## 3. 解析の流れと確定設定

### 3.1 被験者・条件の対応付け

被験者ごとに、1回目と2回目のセッションID、使用した目薬、目薬ありセッションを対応付ける。IDの番号帯から条件を推測せず、匿名化された被験者対応表で確定した情報を入力する。

全被験者を同一のPythonスクリプト内のループで処理し、被験者ごとのコード変更は行わない。

**理由：** 同一被験者の2条件を正しく対応させ、全被験者へ同一処理を適用することで、条件割付の誤りと解析手順のばらつきを防ぐため。

### 3.2 入力データの読み込み

- 入力：各セッションの `*_block1_results.csv`～`*_block6_results.csv`
- 使用セット数：6
- 刺激試行数：各セット320試行
- 練習試行とミスタッチ行：RT解析の対象外
- 分割・再開始された記録：Trial番号を基準に重複を除き、欠損を補間せずに1～320試行を確定する

**理由：** 行動RTは行動results CSVに直接記録されており、EEG用に保存した加工済みデータを経由せず、元の行動時刻から再計算できるため。

### 3.3 RTの再計算

各刺激試行のRTを次式で再計算する。

```text
RT [ms] = KeyPress(ms) - TiltOnset(ms)
```

- `KeyPressSys(ms)` と `TiltOnsetSys(ms)` は使用しない。
- 入力時刻とRTの単位はミリ秒とする。
- EEGのサンプリング周波数はRT計算に使用しない。
- 再計算RTとCSVの `RT(ms)` を照合し、不一致数と最大差をQCへ記録する。

**理由：** 行動指標には実験プログラム側の非Sys時刻を使用するという本解析の同期方針を維持し、保存済みRTだけに依存せず計算の再現性を確認するため。

### 3.4 試行数の品質確認

各セットについて、次の3項目を個別に確認する。

- 刺激試行：320件
- Trial番号：重複のない320種類
- 算出可能RT：320件

CSV総行数は、ミスタッチ行が含まれるため320行を超えても異常とはしない。必要試行の欠損や競合を解消できない場合は、対応する被験者ペア全体をNo1から除外し、理由を記録する。

**理由：** CSVの行数だけでは、刺激試行の完全性とミスタッチ行を区別できないため。

### 3.5 EEG欠損セットの反映

Phase 1でEEG欠損と確定したセットは、該当セッションの全320試行をNaNへ置換する。

- 個人別解析：欠損があるセッション側だけをNaN化し、対応するもう一方の条件は表示する。
- Grand-averageとセット別RT定量化：被験者内対応を保つため、同一被験者のもう一方の条件も同じセットをNaN化する。
- 欠損試行の補間、推定、前詰めは行わない。

**理由：** 行動解析と後続のEEG解析で使用するセットを一致させるとともに、集団比較ではEye DropとControlの対応するデータ数を揃えるため。

### 3.6 RT試行の採用

EEG欠損セットのNaN化後、**200 ms未満のRTだけを予期反応として除外しNaN化する**。200 ms以上には平均±SDや固定上限による試行除外を行わない。算出可能な長いRTも注意の逸脱（lapse）を反映しうる情報として保持する。平均と標本SD（`ddof=1`）は除外後の記述用QCとして保存する。

**理由：** 本解析は実験進行に伴う注意低下を調べるため、長いRTを機械的に除くと、研究対象であるlapseを過小評価する可能性があるため。

### 3.7 30試行の単純移動平均

移動平均は各セット内で独立に計算し、セット境界を越えない。

| 項目 | 設定 |
|---|---|
| 平滑化方法 | 等重み単純移動平均 |
| 局所範囲 | 30試行 |
| 通常の範囲 | Trial `i-15`～`i+14` |
| 端点 | 存在する試行だけの算術平均 |
| NaN | 除外し、残る有限値の算術平均 |
| 全値NaNの窓 | 出力もNaN |
| 出力点数 | 各セット320点を維持 |

Trial 1ではTrial 1～15、Trial 2ではTrial 1～16を使用し、Trial 16で初めて30試行を使用する。終端側も同じ考え方で利用可能範囲へ短縮する。

**理由：** 前回プロジェクトとの方法的一貫性を保ち、窓内の各試行を等しく扱う透明で説明しやすい処理とするため。単純移動平均にも持続的注意・連続遂行課題で複数の使用例があるが、Gaussianより多数とは断定しない。

### 3.8 被験者別RT推移の可視化

- Eye DropとControlを同一figureへ表示する。
- Set 1～6を累積0～600の横軸へ連結する。
- 横軸：`Experimental Progress, %`、0～600、50刻み
- 縦軸：`Reaction Time (ms)`、下限0 ms、目盛り500 ms刻み
- 縦軸上限：両条件の移動平均最大値がおおむね70%位置になるよう100 ms単位で切り上げる。
- セット境界：グレーの縦点線
- セット名：各区間の上部に `Set 1`～`Set 6`
- フォント：Arial
- 軸名：28 pt、目盛り：20 pt、凡例：18～20 pt、主要線：3 pt
- Figureタイトルとy方向のグリッド線は付けない。

条件色と凡例は全出力で固定する。

| 条件 | 色 | 凡例 |
|---|---|---|
| Control | `#563A7C` | `Control` |
| Cキューブ | `#C84A4A` | `Eye Drop (C Cube)` |
| Vロートプレミアム | `#E58A2B` | `Eye Drop (V Rohto Premium)` |

**理由：** 6セットを通した時間変化とセット境界を同時に読み取れるようにし、個人・製品群・後続解析で表示規則を統一するため。

### 3.9 Grand-average

全被験者の移動平均が完了した後、被験者別の移動平均値を、同じセット・同じ進捗位置で被験者間平均する。生RTを被験者間で先にプールしてから平滑化しない。個人figureは30試行幅だけ、Grand-averageは30試行幅版と50試行幅版を別PNGで作成する。

- 製品群：Cキューブ群とVロートプレミアム群を別々に集計
- 中心線：被験者間平均
- 帯：平均 ± SEM
- SEM：各位置の標本標準偏差（`ddof=1`）を、その位置の有効人数Nの平方根で割る
- 欠測値：補間せず、その位置の有限値だけで平均・SD・有効人数Nを算出
- 縦軸：両製品群とも0～1800 msに固定
- 横軸、色、フォント、セット境界：被験者別figureと同じ

**理由：** 被験者を同じ重みで集計し、条件ごとの平均推移と被験者間のばらつきを示すため。両製品群の縦軸を固定することで、製品群間で視覚的スケールを統一する。

### 3.10 セット別RT定量化

各被験者・各条件・各セットについて、移動平均後の値ではなく、EEG欠損処理後の試行別RTから次の2種類の被験者値を作成する。

- `AllTrials`：Trial 1〜320の全試行の算術平均
- `Last80Trials`：各Setの最後1/4に当たるTrial 241〜320の算術平均
- 200 ms未満のRTは除外済みのNaNとして扱い、それ以外のNaNとともに平均から除外する。
- EEG欠損セットはどちらの定量化でも両条件をNaNとする。
- 2種類それぞれに同じ6パネルfigure、被験者別CSV、Set別集計CSV、実行要約を作成する。

- 製品群ごとに、Set 1～6の独立した6パネルを横一列で表示する。
- 各パネルは左をEye Drop、右をControlとする。
- バー：条件内の被験者間平均
- ドット：各被験者のセット平均RT
- 線：同一被験者の2条件の対応
- バー中心：`-0.32`、`0.32`
- バー幅：`0.42`
- 横軸範囲：`-0.90`～`0.90`
- ドットサイズ：`150`
- ドットの横ずらし：各中心から最大±`0.055`
- 縦軸：6パネル共通、下限0 ms、500 ms刻み
- 条件名：22 pt、括弧内の目薬名：18 pt、縦軸数字：23 pt、Set名：26 pt、縦軸名：30 pt
- 推測統計と有意差記号は表示しない。

**理由：** 平滑化による値の変形を避け、被験者を解析単位として、セットごとの条件差と被験者内対応を同時に示すため。

## 4. 出力

実行スクリプト：

```text
解析プログラム/Phase2_行動データ解析/Phase2_No1_ReactionTime.py
```

解析結果は、指定OneDriveの次の構造へ保存する。

```text
Phase2_行動データ解析/
└── No1_ReactionTime/
    ├── CCube/
    │   ├── Individual/  # 全被験者PNGのみ
    │   ├── GrandAverage/
    │   └── SetMeanQuantification/  # AllTrials・Last80Trials PNGのみ
    ├── VRohtoPremium/
        ├── Individual/  # 全被験者PNGのみ
        ├── GrandAverage/
        └── SetMeanQuantification/  # AllTrials・Last80Trials PNGのみ
    └── Sub/
        ├── tables/
        │   ├── Individual/
        │   ├── GrandAverage/
        │   └── SetMeanQuantification/
        └── logs/
            ├── Individual/
            ├── GrandAverage/
            └── SetMeanQuantification/
```

- 個人別：RT推移figure、セッション別QC、実行要約
- Grand-average：30試行幅・50試行幅のPNG。各位置の平均・SD・SEM・有効人数NのCSVと実行要約はNo1直下の `Sub/tables/`・`Sub/logs/` へ分離
- セット別RT定量化：`SetMeanQuantification/` 直下にAllTrials・Last80Trialsの6パネルPNGを保存し、被験者別セット値CSV・製品群×Set集計CSV・実行要約は `Sub/tables/`・`Sub/logs/` へ分離
- 試行別の `RT_TrialData.csv` は保存しない。
- ローカルデスクトップの `解析に必要なデータたち/` には保存しない。

## 5. 実行と再現性

被験者対応は、次の4列を持つ非公開manifestから読み込む。

```text
first_session_id, second_session_id, drops_session_id, product
```

主な実行モードは次のとおり。

| 目的 | オプション | 変更する成果物 |
|---|---|---|
| 個人解析＋Grand-average | `--grand-average --skip-invalid-participants` | 個人結果、Grand-average、通常バッチ要約 |
| Grand-averageのみ再出力 | `--grand-average-only --skip-invalid-participants` | `GrandAverage/`のみ |
| セット別RT定量化のみ | `--set-mean-quantification-only --skip-invalid-participants` | `SetMeanQuantification/`のみ |

すべてのモードで、RT再計算、EEG欠損セット処理、200 ms未満のRT除外、単純移動平均という同じ確定処理を使用する。解析結果はOneDriveへ保存し、条件対応、試行数QC、欠損セット、除外数、出力完了状態をNotionへ記録する。Figure用フォルダにはPNGだけを置き、補助CSV・JSONは `Sub/tables/`・`Sub/logs/` へ分離する。

## 6. 参考文献

- Fortenbaugh FC, et al. *Tracking behavioral and neural fluctuations during sustained attention: A robust replication and extension.* NeuroImage. 2018. https://doi.org/10.1016/j.neuroimage.2018.01.002
- Teramoto W, et al. *Common principles underlie the fluctuation of auditory and visual sustained attention.* Quarterly Journal of Experimental Psychology. 2021. https://doi.org/10.1177/1747021820972255
- van Leeuwen J, et al. *Forget binning and get SMART: Getting more out of the time-course of response data.* Attention, Perception, & Psychophysics. 2019. https://doi.org/10.3758/s13414-019-01788-3
