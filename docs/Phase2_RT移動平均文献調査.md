# Phase 2 RT移動平均 文献調査

## 調査目的

Phase 2解析1で、各セット320試行のRT推移を可視化するための窓幅と平滑化型を決めます。単一論文の設定をそのまま採用せず、持続的注意、continuous performance task、trial-wise response time、一般的な反応時系列法を横断して、複数研究で反復される方法を優先しました。

## 調査範囲

次の方法を比較しました。

1. Gaussian kernelによる重み付き平滑化
2. 等重みの単純移動平均
3. 固定時間・固定試行ビン
4. スプライン、一般化加法モデル、状態空間・HMMなどのモデルベース手法

本解析の主目的は、各被験者の目薬あり条件とコントロールについて、セット内RTの局所推移を同じ320位置で見やすく示すことです。注意状態の分類や、時点ごとの推測統計は現段階の目的に含めません。

## 主要文献の方法

| 文献 | 対象 | 時系列処理 | 本解析への示唆 |
|---|---|---|---|
| Esterman et al., 2013 | gradCPT・持続的注意 | RT変動のVTCを用いる原法 | trial-wise RT変動を連続指標として扱う主要系統 |
| Fortenbaugh et al., 2018 | gradCPT再現研究 | Gaussian、FWHM 9試行、周辺20試行を重み付き統合 | Gaussianと20試行近傍を直接支持する最も近い設定 |
| Teramoto et al., 2021 | 視覚・聴覚gradCPT | Gaussian、FWHM 7秒 | モダリティを越えてGaussian平滑化を採用 |
| Kondo et al., 2022 | 聴覚持続的注意 | Gaussian、FWHM 7秒 | auditory CPTでも同系統を反復 |
| Brain-wide associations of RT variability, 2025 | 大規模ABCD・RT時系列 | VTCとz-scoreをGaussian、FWHM 7.2秒で平滑化 | 大規模データでもGaussianを採用 |
| van Leeuwen et al., 2019 | one-sample-per-trial反応時系列 | Gaussian kernelと寄与量による重み正規化（SMART） | 欠損・端点を含む連続時系列を、利用可能データの重みで正規化可能 |
| Brand et al., 2022 | Go/No-go持続的注意 | 25試行単純移動平均と回帰・スプライン | 20〜30試行程度の窓が別系統でも使われる例 |
| Esterman系 reward研究, 2016 | gradCPTのtime-on-task | 2分窓・5区間と傾き | 固定ビンは全体的な低下の推測には適するが、局所推移を粗くする |
| Decker et al., 2023 / attention feedback研究 | trial-wise注意状態 | 直前3試行の移動平均 | 短窓は瞬間的状態検出向けで、今回の緩徐な推移表示には細かすぎる |

## 方法別の評価

### Gaussian kernel

- gradCPT/VTCを中心とした持続的注意研究で、複数の独立したデータセットと感覚モダリティに反復して使われています。
- 近い試行を強く、遠い試行を弱く反映するため、窓境界で寄与が急に切り替わりません。
- 端点やNaNで利用可能な重みを再正規化でき、試行位置を詰めずに320点を維持できます。
- 文献間でFWHMは9試行、7〜7.2秒など異なり、幅に唯一の標準値はありません。

### 単純移動平均

- 3試行、20試行、25試行など、目的に応じた使用例があります。
- 解釈は簡単ですが、窓内の全試行を等しく扱い、窓境界で寄与が急に変わります。
- 「最もメジャーな唯一の窓幅」は確認できず、窓幅は研究目的に強く依存します。

### 固定ビン

- 2分区間、四分位、五分位など、vigilance decrementの全体傾向や推測統計に広く使われています。
- ただし、今回求める320試行位置の連続曲線には時間解像度が不足します。
- Grand-averageの統計解析では、移動平均とは別に検討する価値があります。

### モデルベース手法

- スプライン、GAMM、HMMは非線形変化や潜在状態を扱えます。
- 仮定と解釈が増え、今回の最初の個人別可視化には過剰です。後続の推測統計候補として分離します。

## 結論

### 平滑化型

**等重みの単純移動平均**を採用します。単純移動平均には、持続的注意・連続遂行課題で3試行や25試行など複数の使用例があります。ただし、Gaussianより使用例が多いとは結論しません。今回の採用理由は、前回プロジェクトとの方法的一貫性と、窓内の各試行を等しく扱う説明の明快さです。

### 窓幅

**30試行幅**を採用します。

- 30試行は1セット320試行の9.375%で、試行ごとの変動を抑えながら緩徐なRT推移を表示します。
- 25試行単純移動平均など近い規模の使用例はありますが、30試行が唯一の標準値という文献的根拠はありません。
- 幅30は前回プロジェクトとの方法的一貫性を優先した分析上の決定です。

### 端点・NaN

- セットごとに独立して計算し、セット境界を越えません。
- Trial `i` は原則 `i-15`〜`i+14` の30試行を使います。
- 端点では存在する試行だけの算術平均を求めます。
- RT長による試行除外は行いません。EEG欠損セットなどのNaNは位置を詰めず、窓内に有限値があれば、その有限値だけの算術平均を求めます。補間は行いません。

## 解釈上の限界

単純移動平均にもGaussian平滑化にも使用例があり、窓幅は研究目的に依存します。したがって、30試行単純移動平均をraw RT推移に対する唯一の標準設定とは主張しません。Grand-averageで統計的結論を出す方法は、可視化用平滑化と分けて決定します。

## 参考文献

- Esterman M, et al. *In the zone or zoning out? Tracking behavioral and neural fluctuations during sustained attention.* Cerebral Cortex. 2013. https://doi.org/10.1093/cercor/bhs261
- Fortenbaugh FC, et al. *Tracking behavioral and neural fluctuations during sustained attention: A robust replication and extension.* NeuroImage. 2018. https://doi.org/10.1016/j.neuroimage.2018.01.002
- Teramoto W, et al. *Common principles underlie the fluctuation of auditory and visual sustained attention.* Quarterly Journal of Experimental Psychology. 2021. https://doi.org/10.1177/1747021820972255
- Kondo H, et al. *Dynamic Transitions Between Brain States Predict Auditory Attentional Fluctuations.* Frontiers in Neuroscience. 2022. https://doi.org/10.3389/fnins.2022.816735
- *Brain-wide associations of reaction time variability in the ABCD study.* Imaging Neuroscience. https://direct.mit.edu/imag/article/doi/10.1162/IMAG.a.18/130766/
- van Leeuwen J, et al. *Forget binning and get SMART: Getting more out of the time-course of response data.* Attention, Perception, & Psychophysics. 2019. https://doi.org/10.3758/s13414-019-01788-3
- Brand J, et al. *Completing a Sustained Attention Task Is Associated With Decreased Distractibility and Increased Task Performance Among Adolescents With Low Levels of Media Multitasking.* Frontiers in Psychology. 2022. https://doi.org/10.3389/fpsyg.2021.804931
- Esterman M, et al. *Anticipation of Monetary Reward Can Attenuate the Vigilance Decrement.* PLOS ONE. 2016. https://doi.org/10.1371/journal.pone.0159741
