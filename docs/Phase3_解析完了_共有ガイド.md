# Phase 3 瞬き解析 解析完了共有ガイド

> **確定版（2026年10月3日）**：Phase 3の瞬き検出・Blink Rate解析について、確定手法、Quality Check、結果の見方、成果物の場所をまとめた共有用文書である。

## 1. 比較設計

- 解析対象は40被験者ペア（80セッション）で、Cキューブ群20名とVロートプレミアム群20名に分ける。
- 各製品群内で、同一被験者のEye Drop条件とControl条件を対応付けて比較する。
- ID番号帯から条件を推測せず、匿名化された被験者対応表で条件と製品群を確定する。
- ID130・230のペアは解析対象外とする。
- Phase 1でEEG欠測と確定したID109 Set 1、ID120 Set 6、ID135 Set 2、ID225 Set 4は、集団比較では同一被験者の両条件から外す。補間しない。
- 全被験者へ同じPythonスクリプトと固定設定を適用する。

実行スクリプト：

```text
解析プログラム/Phase3_瞬き解析/Phase3_No1_BlinkRate.py
```

## 2. Eye Blink Component Signal

1. Phase 1でICAを行い、ICLabelの `eye blink` 確率0.80以上のICを選ぶ。
2. 選択したICのチャンネル別寄与を混合行列でセンサー空間へ戻す。この信号は `ICA前EEG − 瞬き関連IC除去後EEG` と同値である。
3. 使用可能なFp1・Fp2を時点ごとに平均する。一方がICA学習から除外された場合は残るFp信号を使う。
4. Phase 3でSetごとに1～10 Hzのゼロ位相バンドパスを適用し、Eye Blink Component Signalとする。

Fp1・Fp2単独信号は検出数の補助QCだけに使用し、主解析や条件比較には用いない。

## 3. 瞬き検出

- `scipy.signal.find_peaks` を使用する。
- Peak heightは設定しない。
- Prominence閾値は、同一セッションの全使用Setの候補分布から `median(P) + 12 × 1.4826 × MAD(P)` とする。
- 係数12は文献値ではなく、4被験者ペアの8・10・12比較と、係数10の全対象出力で確認した過剰検出を踏まえた探索的な固定値である。
- パーセンタイル方式は、IDごとの上位一定割合を選ぶことで抽出総数をID間で似通わせる可能性があるため使用しない。
- Minimum peak distanceは100 ms、Peak widthは20～320 ms。

## 4. Blink Rateと定量化

### 4.1 時間変化

1. 60秒中心化窓を1秒刻みで移動する。
2. 窓内の検出数を実窓長で割り、`Blink Rate (blinks/min)` を算出する。
3. Set端は利用可能な実窓長で補正する。
4. 同じSet内で15秒の中心化単純移動平均を適用する。
5. 各Setの実時間を0～100%へ変換し、6Setを0～600の進捗軸へ連結する。

### 4.2 Set定量値

```text
Set Blink Rate [blinks/min]
= Set内の検出瞬き総数 ÷ Set実時間 [min]
```

Set別と全Set統合のEye Drop対Controlを両側対応ありt検定で比較する。全Set統合値は、使用可能なSetの総検出数を総記録時間（分）で割る。

## 5. Quality Check

- `QualityCheck/BlinkDetection/`：青線がEye Blink Component Signal、中抜き丸が検出瞬き。HTMLと同じResetスケールの横長PNGを保存する。
- `QualityCheck/ProminenceDistribution/`：候補prominence分布、採用閾値、500 µV超の候補数を確認する。
- HTMLは個々のスパイクが見える幅までx軸を拡大し、最大3分で先頭から末尾まで連続する表示窓を送り、全使用時間を少なくとも1回確認する。
- 評価は「良好／概ね良好／要確認」とし、確認後はHTMLを閉じる。
- 同一被験者の両条件について、共通Setの総検出数の大きい方÷小さい方が2倍以上、または片方0なら条件間バランスを「要確認」とする。このQCだけを理由に除外や閾値変更を行わない。
- QCは真の瞬きラベルに対する感度・適合率ではなく、自動検出と信号形状の定性的整合性を示す。

## 6. 結果の見方

- `Individual/`：同一被験者のEye DropとControlのBlink Rate時間変化。
- `GrandAverage/`：個人Blink Rateを同じ進捗位置で被験者間平均した線。帯は平均±SEM。0始まり標準版と10～30 blinks/min拡大版がある。
- `SetQuantification/`：Set別と全Set統合の対応あり比較。主PNGは未補正p値、CSVは未補正と3種類の補正後p値を示す。
- Vロートプレミアムの `ExcludePair133-233_Sets1-3/`：ID233 Control前半3Setの信号品質上の懸念に対し、Pair 133-233の両条件Set 1～3を集団集計から外した追加解析。主要結果を置き換えない。

## 7. 確認済みの結果

- 40被験者ペア・80セッションを同一設定で処理した。
- Notion結果表は40被験者ペアを1行ずつ記録し、総合QCと条件間瞬き数バランスはいずれも40件すべて「要確認」なし。
- 主要版とPair 133-233除外版のSet別・全Set統合は、未補正を含めて有意差なし。Bonferroni・Holm・FDR補正後も有意差なし。

## 8. OneDriveの結果フォルダ

```text
実験本番_本解析/
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

## 9. 統計figure

- 左がEye Drop、右がControl。バーは被験者間平均、ドットは被験者値、線は同一被験者の対応を表す。
- `*`：p<0.05、`**`：p<0.01、`***`：p<0.001、`n.s.`：p≥0.05。
- 6パネルの主PNGは未補正p値を表示する。CSVへBonferroni・Holm・FDRも保存する。
- 全Set統合版は1検定だけなので多重比較補正を行わない。
- CSVにはN、t値、自由度、p値、平均差、差の95%信頼区間、Cohen's dzを保存する。

## 10. 詳細仕様と記録

- 詳細：[Phase 3 No1 瞬き解析 共有用仕様書](Phase3_No1_瞬き解析_共有用仕様書.md)
- 運用正本：[Phase 3 瞬き解析仕様](Phase3_瞬き解析仕様.md)
- Notion：`解析ストーリー / フェーズ３：まばたきの解析`

Figureだけで傾向を判断せず、対応する統計CSV、追加解析、NotionのQC記録を合わせて読む。
