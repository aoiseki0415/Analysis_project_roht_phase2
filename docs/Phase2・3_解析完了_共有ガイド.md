# Phase 2・3 解析完了 共有ガイド

> **確定版（2026年10月3日）**：Phase 2の行動データ解析とPhase 3の瞬き解析について、確定手法、結果の見方、成果物の場所を一つにまとめた共有用文書である。

## 1. 共通の比較設計

- 解析対象は40被験者ペア（80セッション）で、Cキューブ群20名とVロートプレミアム群20名に分ける。
- 各製品群内で、同一被験者のEye Drop条件とControl条件を対応付けて比較する。
- ID番号帯から条件を推測せず、匿名化された被験者対応表で `first_session_id`、`second_session_id`、`drops_session_id`、`product` を確定する。
- ID130・230のペアは解析対象外とする。
- Phase 1でEEG欠測と確定したID109 Set 1、ID120 Set 6、ID135 Set 2、ID225 Set 4は、集団比較では同一被験者の両条件から外す。補間や前詰めは行わない。
- 全被験者へ同じPythonスクリプトと固定設定を適用し、被験者ごとのコード変更は行わない。

## 2. 実行スクリプト

| 解析 | スクリプト |
|---|---|
| Phase 2 No1 RT | `解析プログラム/Phase2_行動データ解析/Phase2_No1_ReactionTime.py` |
| Phase 2 No2 ミスタッチ | `解析プログラム/Phase2_行動データ解析/Phase2_No2_Mistouch.py` |
| Phase 3 No1 瞬き | `解析プログラム/Phase3_瞬き解析/Phase3_No1_BlinkRate.py` |
| 共通の対応あり統計・定量化figure | `解析プログラム/paired_statistics.py` |

## 3. Phase 2 No1：RT解析

### 3.1 計算手順

1. 生の行動results CSVから、各Setの320刺激試行をTrial番号で確定する。
2. 非Sys時刻を用いて `RT [ms] = KeyPress(ms) - TiltOnset(ms)` を再計算する。
3. EEG欠測SetをNaN化する。
4. 200 ms未満だけを予期反応としてNaN化する。200 ms以上の長いRTはlapseを反映しうるため残す。
5. 各Set内で30試行の等重み単純移動平均を計算する。端点では存在する試行だけを用い、320点を維持する。
6. 個人RT推移、製品群別Grand-average、セット別定量化を作成する。

### 3.2 出力の読み方

- `Individual/`：同一被験者のEye DropとControlの30試行移動平均。横軸0～600は、各Setの0～100%を6Set連結した実験進捗である。
- `GrandAverage/`：個人の平滑値を同じSet・同じ進捗位置で被験者間平均した線。帯は平均±SEM。MA30、MA50、MA30の400～1400 ms拡大版がある。
- `SetMeanQuantification/`：平滑化前の有効な試行別RTを用いる主解析 `AllTrials`。6パネルPNGはSet別、`AllSets` PNGは全Set統合の対応あり比較である。
- `SetMeanQuantification/Last80Trials/`：各SetのTrial 241～320だけを用いた追加解析。
- 主PNGの `*`、`**`、`***`、`n.s.` は未補正p値に基づく。CSVには未補正・Bonferroni・Holm・Benjamini–Hochberg FDRを併記する。

### 3.3 確認済みの結果

- 個人解析40名、除外0名。
- CキューブAllTrialsの未補正比較ではSet 3（p=0.023）とSet 4（p=0.039）、Last80TrialsではSet 3（p=0.038）とSet 4（p=0.048）が有意表示となった。
- Vロートプレミアム群のSet別、両製品群の全Set統合、全てのBonferroni・Holm・FDR補正後比較は有意ではなかった。

## 4. Phase 2 No2：ミスタッチ解析

### 4.1 計算手順

1. `ResponseType = mistouch` を候補とする。
2. 他イベントを挟まない隣接mistouchのKeyPress差が0～50 msなら同一操作として1回にまとめる。
3. `mistouch → correct → mistouch` で、外側mistouch間が0～100 ms、かつcorrect RTが50 ms以下なら3行を1回にまとめる。
4. EEG欠測Setを両条件から外し、被験者・条件・Setごとの確定ミスタッチ数を作成する。
5. Set別と全Set統合のEye Drop対Controlを可視化し、両側対応ありt検定を行う。

50 msは、全データの隣接mistouch間隔17,796件中17,107件（96.1%）が50 ms以内だった実測分布に基づく。

### 4.2 出力の読み方

- `SetQuantification/`：主解析。6パネルPNGはSet別、`AllSets` PNGは全Setの確定ミスタッチ数を合計した比較である。
- Cキューブの `SensitivityAnalysis_ExcludeID132-232_Set1/`：ID132-232 Set 1を両条件から外した追加の感度分析。主解析の置き換えではない。
- 主PNGは未補正p値、統計CSVは未補正と3種類の補正後p値を示す。

### 4.3 確認済みの結果

- 40被験者ペアを処理し、KeyPress時刻欠損・時刻逆転・除外ペアはいずれも0。
- 主解析・感度分析のSet別と全Set統合は、未補正を含めて有意差なし。3種類の補正後も有意差なし。
- CキューブSet 1はID132-232の大きな実測値の影響を受けるため、主解析と感度分析の両方を確認する。

## 5. Phase 3 No1：瞬き解析

### 5.1 Eye Blink Component Signal

1. Phase 1でICAを行い、ICLabelの `eye blink` 確率0.80以上のICを選ぶ。
2. 選択したICのチャンネル別寄与を混合行列でセンサー空間へ戻す。この信号は `ICA前EEG − 瞬き関連IC除去後EEG` と同値である。
3. 使用可能なFp1・Fp2を時点ごとに平均する。一方がICA学習から除外された場合は残るFp信号を使う。
4. Phase 3でSetごとに1～10 Hzのゼロ位相バンドパスを適用し、Eye Blink Component Signalとする。

### 5.2 瞬き検出とBlink Rate

- `scipy.signal.find_peaks` を使用する。
- Peak heightは設定しない。
- Prominence閾値は、同一セッションの全使用Setの候補分布から `median(P) + 12 × 1.4826 × MAD(P)` とする。
- 係数12は文献値ではなく、4被験者ペアの8・10・12比較と、係数10の全対象出力で確認した過剰検出を踏まえた探索的な固定値である。
- Minimum peak distanceは100 ms、Peak widthは20～320 ms。
- Blink Rateは60秒中心化窓を1秒刻みで動かし、実窓長で `blinks/min` へ換算する。その後、Set内で15秒の中心化単純移動平均を適用する。
- Set定量値は `Set内検出総数 ÷ Set実時間 [min]` とする。

### 5.3 出力の読み方

- `QualityCheck/BlinkDetection/`：青線がEye Blink Component Signal、中抜き丸が検出瞬き。HTMLは拡大して全時間のピーク位置を確認でき、同じResetスケールの横長PNGもある。
- `QualityCheck/ProminenceDistribution/`：候補prominence分布、採用閾値、500 µV超の候補数を確認する。
- `Individual/`：同一被験者のEye DropとControlのBlink Rate時間変化。
- `GrandAverage/`：個人Blink Rateを同じ進捗位置で被験者間平均した線。帯は平均±SEM。0始まり標準版と10～30 blinks/min拡大版がある。
- `SetQuantification/`：Set別と全Set統合の対応あり比較。主PNGは未補正p値、CSVは未補正と3種類の補正後p値を示す。
- Vロートプレミアムの `ExcludePair133-233_Sets1-3/`：ID233 Control前半3Setの信号品質上の懸念に対し、Pair 133-233の両条件Set 1～3を集団集計から外した追加解析。

### 5.4 QCと確認済みの結果

- 40被験者ペア・80セッションを同一設定で処理した。
- 各セッションについて、HTMLを個々のスパイクが見える幅まで拡大し、最大3分で全使用時間を連続走査する運用とした。
- Notion結果表は40被験者ペアを1行ずつ記録し、総合QCと条件間瞬き数バランスはいずれも40件すべて「要確認」なし。
- 主要版とPair 133-233除外版のSet別・全Set統合は、未補正を含めて有意差なし。3種類の補正後も有意差なし。
- QCは真の瞬きラベルに対する感度・適合率ではなく、自動検出と信号形状の定性的整合性を示す。

## 6. OneDriveの結果フォルダ

```text
実験本番_本解析/
├── Phase2_行動データ解析/
│   ├── No1_ReactionTime/
│   │   ├── CCube/
│   │   │   ├── Individual/
│   │   │   ├── GrandAverage/
│   │   │   └── SetMeanQuantification/
│   │   │       └── Last80Trials/
│   │   ├── VRohtoPremium/              # CCubeと同じ構成
│   │   └── Sub/
│   │       ├── tables/
│   │       └── logs/
│   └── No2_Mistouch/
│       ├── CCube/SetQuantification/
│       │   └── SensitivityAnalysis_ExcludeID132-232_Set1/
│       ├── VRohtoPremium/SetQuantification/
│       └── Sub/
│           ├── tables/
│           └── logs/
└── Phase3_瞬き解析/
    └── No1_BlinkRate/
        ├── CCube/
        │   ├── Individual/
        │   ├── GrandAverage/
        │   ├── SetQuantification/
        │   └── QualityCheck/
        │       ├── BlinkDetection/
        │       └── ProminenceDistribution/
        ├── VRohtoPremium/
        │   ├── Individual/
        │   ├── GrandAverage/
        │   ├── SetQuantification/
        │   │   └── ExcludePair133-233_Sets1-3/
        │   └── QualityCheck/
        │       ├── BlinkDetection/
        │       └── ProminenceDistribution/
        └── Sub/
            ├── tables/
            └── logs/
```

## 7. 統計figureの共通表示

- 左がEye Drop、右がControl。バーは被験者間平均、ドットは被験者値、線は同一被験者の対応を表す。
- `*`：p<0.05、`**`：p<0.01、`***`：p<0.001、`n.s.`：p≥0.05。
- 6パネルの主PNGは未補正p値を表示する。補正法の最終選択に備え、CSVへBonferroni・Holm・FDRも保存する。
- 全Set統合版は1検定だけなので多重比較補正を行わない。
- CSVにはN、t値、自由度、p値、平均差、差の95%信頼区間、Cohen's dzを保存する。
- 主要結果と追加・感度分析を混同しない。追加解析は主解析を置き換えず、特定の品質懸念や極端値の影響を確認するために併記する。

## 8. 詳細仕様と記録

- RT詳細：[Phase 2 No1 RT解析 共有用仕様書](Phase2_No1_RT解析_共有用仕様書.md)
- ミスタッチ詳細：[Phase 2 No2 ミスタッチ解析 共有用仕様書](Phase2_No2_ミスタッチ解析_共有用仕様書.md)
- 瞬き詳細：[Phase 3 No1 瞬き解析 共有用仕様書](Phase3_No1_瞬き解析_共有用仕様書.md)
- GitHubの運用正本：[Phase 2 行動データ解析仕様](Phase2_行動データ解析仕様.md)、[Phase 3 瞬き解析仕様](Phase3_瞬き解析仕様.md)
- Notion：`解析ストーリー / フェーズ２：行動データの解析` と `解析ストーリー / フェーズ３：まばたきの解析` に、確定方針、被験者別QC、集計結果を記録する。

Figureだけで傾向を判断せず、対応する統計CSV、追加解析、NotionのQC記録を合わせて読む。
