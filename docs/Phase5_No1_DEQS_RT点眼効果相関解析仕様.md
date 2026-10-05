# Phase 5 No1：DEQSとRT点眼効果の相関解析仕様

## 1. 目的

実験前のドライアイ傾向を表すDEQSスコアと、点眼によって持続課題中のRT増加がどれだけ抑えられたかを表す `Eye Drop Effect` の関連を調べます。解析は使用した目薬ごとに分け、Cキューブ群とVロートプレミアム群を混合しません。

相関は関連の強さを表すものであり、因果効果とは解釈しません。

## 2. 解析単位と対応表

- 解析単位は1被験者ペアです。1回目IDと2回目IDを同一被験者として対応付けます。
- 製品群、点眼実施回、Eye Drop条件ID、Control条件IDは、Google Driveの匿名被験者リスト `共有用（匿名）` を正本として決定します。
- 100番台／200番台、奇数／偶数などから条件や製品を推測しません。
- 匿名被験者リストの `Vロート` は、既存成果物との整合のため出力上 `VRohtoPremium` として正規化します。
- ID130–230は既存の解析対象外方針に従い、Phase 5にも含めません。
- DEQS回答ID、1回目ID、2回目ID、点眼条件ID、Control条件ID、製品群の対応に重複・欠損・矛盾があれば解析を停止します。

## 3. DEQSスコア

### 3.1 対象項目

- DEQSの問1〜15を使用し、問16は得点化しません。
- 各項目は頻度回答と程度回答の組み合わせから0〜4点へ変換します。
- 頻度が `なかった` の場合は0点です。
- 頻度が `なかった` 以外の場合、程度を1〜4点へ変換します。
  - `あまり気にならなかった`／`あまり困らなかった`：1点
  - `やや気になった`／`やや困った`：2点
  - `気になった`／`困った`：3点
  - `非常に気になった`／`非常に困った`：4点

### 3.2 総合スコア

```text
DEQS Score = 程度得点合計 / 有効回答数 × 25
```

- 範囲は0〜100点で、高いほどドライアイ傾向が強いことを表します。
- 有効回答数が10項目未満の場合は算出しません。
- 現回答では解析対象40名全員が15項目有効であることを確認済みです。
- 実装時も有効回答数と分岐矛盾を再検証し、過去の手計算値だけを入力しません。

## 4. RTセット平均値

### 4.1 使用する値

Phase 2 No1の主解析 `AllTrials` で確定したセット別平均RTを使用します。`Last80Trials`、移動平均後RT、Grand-averageは使用しません。

各セッション・各Setの値は、Phase 2と同じ順序で算出します。

1. 生の `*_blockN_results.csv` からmistouch行を除いた320刺激試行を取得する。
2. 非Sys列から `RT [ms] = KeyPress(ms) - TiltOnset(ms)` を再計算する。
3. Phase 1でEEG欠損と確定したSetをNaN化する。
4. `RT < 200 ms`だけを予期反応としてNaN化する。200 ms以上には上限除外を設けない。
5. Trial 1〜320の有限な `RT_clean_ms` を算術平均する。

### 4.2 Phase 2との一致確認

Eye Drop Effectを計算する前に、Phase 5で使用するEye Drop／ControlのSet 1・Set 6平均RTを、Phase 2の `AllTrials` 被験者値CSVと照合します。

- Pair ID、製品群、Eye Drop ID、Control ID、Set番号、条件を照合します。
- 平均RTと有効試行数を照合します。
- 有限値は浮動小数点許容誤差 `atol=1e-9`、`rtol=0` で一致させます。
- 両方がNaNの場合だけ欠測として一致と判定します。
- 1件でも不一致、重複、欠落、条件逆転があれば相関計算とFigure作成を停止します。
- 照合結果は全行をCSVへ保存し、合否、差、利用可否、除外理由を残します。

## 5. Eye Drop Effect

各被験者について次式を用います。

```text
Control RT Ratio  = Control Set 6 mean RT / Control Set 1 mean RT
Eye Drop RT Ratio = Eye Drop Set 6 mean RT / Eye Drop Set 1 mean RT

Eye Drop Effect = (Control RT Ratio - Eye Drop RT Ratio) × 100
```

- 単位はpercentage pointsです。
- 正の値：ControlのRT増加のほうが大きく、点眼によってRT増加が抑えられた方向です。
- 0付近：Set 1からSet 6までの相対変化が両条件で同程度です。
- 負の値：Eye Drop条件のRT増加のほうが大きい方向です。
- 4つの元平均RT、2つの比、最終効果値を被験者別解析表へ保存します。
- 分母となるSet 1平均が非有限または0以下の場合は算出せず、理由を記録します。

### 5.1 既知の欠測

Phase 2の被験者内対応ルールにより、次のペアはEye Drop Effectを算出できません。

- ID109–209：Set 1欠測
- ID120–220：Set 6欠測

ID135–235のSet 2欠測とID125–225のSet 4欠測は、本指標がSet 1とSet 6だけを使用するため除外理由にしません。確定有効人数はCキューブ19名、Vロートプレミアム19名です。

## 6. 相関解析

- Cキューブ群とVロートプレミアム群を分けて解析します。
- 横軸を `DEQS Score`、縦軸を `Eye Drop Effect (percentage points)` とします。
- 主解析はPearsonの積率相関係数とし、製品群ごとに `r`、両側p値、95%信頼区間、有効人数Nを保存します。
- 自動的な外れ値除外は行いません。非有限なDEQSまたはEye Drop Effectだけを欠測として除外し、対象外理由を保存します。
- 2製品の相関を直接同一母集団として統合しません。
- 現段階では製品別の2相関について未補正p値を保存します。多重比較補正を追加する場合は、実行前に仕様を更新します。

## 7. Figure

製品群ごとに1枚のPNGを作成します。

- Figure：8 × 7 inch、180 dpi、白背景
- フォント：Arial
- 横軸：`DEQS Score`、0〜100、20点刻み
- 縦軸：`Eye Drop Effect (percentage points)`
- 縦軸は2製品で共通とし、両群全データの最大絶対値に10%程度の余白を加え、0を中心とする左右対称範囲へ切り上げます。
- 0を示す薄いグレーの水平線を表示します。
- 各点は1被験者を表します。Figure上へIDは表示しません。
- 製品色はPhase 2 No1の対応を継承し、Cキューブ `#C84A4A`、Vロートプレミアム `#E58A2B` とします。
- 製品ごとに最小二乗回帰線と95%信頼帯を表示します。
- Figure内に `N`、Pearsonの `r`、両側p値を簡潔に表示します。
- 軸名28 pt、目盛20 pt、製品名22 pt、統計注記18 ptを基準とします。
- 上・右の枠線を非表示とし、軸線1.5 pt、点90 pt、回帰線2.5 ptを基準とします。

Figureは関連の可視化であり、回帰線を因果効果として解釈しません。

## 8. 出力構造

```text
実験本番_本解析/
└── Phase5_相関・その他/
    └── No1_DEQS_RT_EyeDropEffect/
        ├── CCube/
        │   └── No1_DEQS_EyeDropEffect_Correlation_CCube.png
        ├── VRohtoPremium/
        │   └── No1_DEQS_EyeDropEffect_Correlation_VRohtoPremium.png
        └── Sub/
            ├── tables/
            │   ├── No1_DEQS_Scores.csv
            │   ├── No1_Phase2_RT_ConsistencyCheck.csv
            │   ├── No1_DEQS_RT_EyeDropEffect_AnalysisDataset.csv
            │   └── No1_CorrelationStatistics.csv
            └── logs/
                └── No1_DEQS_RT_EyeDropEffect_RunSummary.json
```

- `No1_DEQS_Scores.csv`：ID、製品群、有効回答数、程度得点合計、DEQS Score
- `No1_Phase2_RT_ConsistencyCheck.csv`：Phase 5使用値とPhase 2値の照合結果
- `No1_DEQS_RT_EyeDropEffect_AnalysisDataset.csv`：ID対応、4平均RT、2比、Eye Drop Effect、DEQS Score、採否理由
- `No1_CorrelationStatistics.csv`：製品別のN、r、p値、95%信頼区間
- ログ：入力、対象数、除外理由、照合結果、出力先、警告、完了状態

本解析では計算量の大きい中間データを作らないため、ローカルデスクトップの `解析に必要なデータたち/` へ新規データを保存しません。再現に必要な派生値と照合結果はOneDriveの `Sub/tables/` へ保存します。

## 9. 実装・実行時の完了条件

- 同一のPythonスクリプトで全対象を処理する。
- Google Drive匿名対応表に基づく40被験者ペア、製品群各20名、対象外ID130–230を事前検証する。
- DEQS 15項目の得点化、有効回答数、問16除外を検証する。
- Phase 2 `AllTrials` Set 1・Set 6平均RTとの照合が全件合格する。
- Eye DropとControlの条件入れ替わりがないことを確認する。
- 既知欠測を含む除外理由と製品別有効人数を保存する。
- CSVを読み戻し、式からEye Drop Effectと相関統計を独立再計算して一致確認する。
- 2枚のPNG、4つの表、実行ログが指定OneDriveに存在し、0バイトでないことを確認する。

## 10. ファイル対応

- Python：`解析プログラム/Phase5_相関・その他/Phase5_No1_DEQS_RT_EyeDropEffect.py`
- GitHub正本：本仕様書
- Notion：`フェーズ５：相関解析など / No1：DEQSとRT点眼効果の相関｜詳細仕様`
- OneDrive：`Phase5_相関・その他/No1_DEQS_RT_EyeDropEffect/`

2026年10月5日に、同一スクリプトで40被験者ペアを実行しました。Phase 2保存済み240行との完全一致、対象外ID、製品群各20名、既知欠測による製品別有効人数19名、4表・2 Figure・実行ログの読戻しを確認済みです。DEQS得点はOneDriveの `No1_DEQS_Scores.csv` を確定スナップショットとして保存し、以後の再描画・再集計ではGoogle Sheetsを再参照せず使用できます。
