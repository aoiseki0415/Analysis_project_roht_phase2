# Phase 3 瞬き解析仕様

## 1. 適用範囲

Phase 3解析1（No1）では、Phase 1で保存した瞬き解析用信号から瞬きイベントを検出し、瞬き率の時間変化とセット別定量値を算出します。Cキューブ群とVロートプレミアム群を分け、各群内で同一被験者の目薬あり条件とコントロールを比較します。

本書は現行実装の確定仕様です。パイロットIDで出力と検出妥当性を確認してから、全対象へ同一コードを適用します。

## 2. 入力と解析単位

- 入力はPhase 1のセット別 `IDxxx_SetN_blink_signal.h5` です。
- 主解析信号は、除去Eye成分をセンサー空間へ復元した `Fp1_Fp2_mean` とします。
- `Fp1` と `Fp2` でも同じ検出を補助的に行い、セット別検出数だけを記録します。主解析値、条件比較、figureの算出には使用しません。
- サンプリング周波数、セット内相対時刻、`OriginalTimestamp`、ICA学習除外区間・チャンネルのmaskと記録はHDF5から読み込み、整合性を検証します。
- 瞬き検出とBlink Rate算出はセットごとに独立して行い、セット間をまたいでフィルタ、ピーク検出、移動窓集計を行いません。
- 製品群、2セッションID、目薬あり・なしの対応は、許可されたGoogleスプレッドシートと確定manifestから取得します。IDの番号帯から条件を推測しません。
- ID 130／230は解析対象外です。
- Phase 1で作成されなかったID 109 Set 1、ID 120 Set 6、ID 135 Set 2、ID 225 Set 4は欠測のまま扱い、補間・前詰め・擬似データ生成をしません。

## 3. 瞬きイベント検出

### 3.1 検出信号

主解析では `Fp1_Fp2_mean` を使用します。Fp1・Fp2の一方だけに依存しにくい擬似垂直EOGとして扱い、同じセットのFp1単独・Fp2単独の検出数を補助QCに用います。

### 3.2 フィルタとピーク検出

- 検出前に各セットの信号へ **1–10 Hz** の4次Butterworthバンドパスフィルタを `sosfiltfilt` でゼロ位相適用します。これはMNEのEOGイベント検出で用いられる帯域に合わせ、低周波ドリフトと高周波成分を抑えて瞬き様の低周波ピークを強調するためです。
- ピーク検出には `scipy.signal.find_peaks` を使用します。
- まず、同一セッションの解析可能な全セットで、制約なしの局所最大点を候補として列挙します。
- Peak height閾値は設定しません。局所的には明瞭でも絶対振幅が小さい瞬きを一律に落とさないためです。
- 主解析のPeak prominence閾値は、全候補のprominenceを $P_i$ として、`median(P) + 10 × (1.4826 × MAD(P))` とします。`MAD(P) = median(|P_i - median(P)|)` です。Prominenceは周囲の谷に対してピークがどれだけ突出しているかを表し、`1.4826 × MAD` は正規分布で標準偏差と同じ尺度になるrobust SDです。係数3ではID101・201の小振幅な揺れを過剰検出したため、パイロット比較に基づいて係数10へ変更しました。
- 閾値はセットごとに変えず、セッションにつき1組を固定して全使用セットへ適用します。
- パーセンタイル方式は各セッションから上位一定割合を選ぶため、瞬き総数を分布順位によって強く規定する問題があります。本解析では使用せず、ノイズ水準に対する突出度をMADで評価します。係数10は全被験者で固定し、IDごとに変更しません。
- minimum peak distanceは100 ms、peak widthは20–320 msとします。前者は一つの瞬き周辺の近接ピークを重複計数しないための安全条件、後者は極端に狭い／広い揺れを除外する形状条件です。
- 検出されたピーク時刻、セット番号、セット内相対時刻、`OriginalTimestamp`、振幅、prominence閾値を保存します。互換用のheight欄は空欄とします。

Chengら（2023）は、垂直眼球運動ICへ `findpeaks` を適用し、peak height 96パーセンタイル、peak prominence 97パーセンタイル、minimum peak distance 100 ms等を使用しています。本解析では小振幅でも局所的に明瞭な瞬きをheight基準で除外しないためpeak heightを設けず、また抽出割合を固定しないためprominenceのパーセンタイル方式も採用しません。MADは外れ値の影響を受けにくい散布尺度として使用し、minimum peak distance 100 msとpeak width 20–320 msは先行研究の範囲を参考に固定します。

参考：

- Cheng B, et al. *Using spontaneous eye blink-related brain activity to investigate cognitive load during mobile map-assisted navigation.* Frontiers in Neuroscience. 2023. https://doi.org/10.3389/fnins.2023.1024583
- Kleifges K, et al. *BLINKER: Automated Extraction of Ocular Indices from EEG Enabling Large-Scale Analysis.* Frontiers in Neuroscience. 2017. https://doi.org/10.3389/fnins.2017.00012
- Nyström M, et al. *What is a blink? Classifying and characterizing blinks in eye openness signals.* Behavior Research Methods. 2024. https://doi.org/10.3758/s13428-023-02333-9
- MNE-Python. *Overview of artifact detection.* EOGイベント検出で1–10 Hzのバンドパスを使用。https://mne.tools/stable/auto_tutorials/preprocessing/10_preprocessing_overview.html

## 4. 瞬き検出確認HTML

- セッションIDごとに、height基準なし・MAD方式の検出確認HTMLを1ファイル作成します。被験者ペアを1つのHTMLへ統合しません。
- 横軸にはセット内データだけを使用し、セット間の休憩時間は含めません。
- Set 1〜6を一つの横軸へ連結し、各セットの実時間を同じ幅の100単位へ線形変換します。Set 1は0〜100、Set 2は100〜200、以降も同様にSet 6の600までとします。
- 横軸名は `Experimental Progress, %` とします。進捗座標とセット内実時間の対応は保持し、ホバーでSet、進捗、セット内秒、振幅、ピーク判定を表示します。
- 1–10 Hzフィルタ後の `Fp1_Fp2_mean` と、検出されたピーク位置の中抜き丸印を表示します。
- セット境界へグレー点線を入れ、`Set 1`〜`Set 6` を表示します。欠測セットはデータのない区間として明示します。
- Phase 1の確認HTMLと同様に、x・y方向の拡大縮小、ドラッグ移動、左右矢印キーによる表示幅比率ベースの移動、全体表示への復帰、カーソル位置の値確認を可能にします。
- ICA学習で除外した時間・チャンネルの表示はPhase 1のQC成果物に任せ、Phase 3 HTMLへ重複表示しません。

## 5. Blink Rateの時間変化

- 指標名と縦軸名は **`Blink Rate (blinks/min)`** とします。
- 各セット内で、中心時刻の前後30秒を含む **60秒の中心化移動窓**を1秒刻みで移動し、窓内の検出数を実際の窓長（分）で割ります。
- 窓は開始時刻を含み終了時刻を含まない半開区間として数え、境界上のイベントを重複計上しません。
- セット端では利用可能な時間だけを用い、実際に使用した窓長で分母を補正します。端点を削除せず、セット全体の出力位置を保持します。
- セット境界を越えて別セットの瞬きを同じ窓へ含めません。
- 60秒窓で得た1秒刻みのBlink Rateへ、各セット内だけで **15秒の中心化単純移動平均**を適用します。セット境界をまたいで平滑化しません。未平滑化Blink Rateも補助表へ保持します。
- Blink Rateと15秒平滑値は実時間で計算し、平滑化完了後にHTMLと同じ0〜600の `Experimental Progress, %` へ対応付けます。各セットの実時間差は横軸だけを線形伸縮し、Blink Rate計算の60秒窓には影響させません。
- 被験者別figureでは、同一被験者のEye DropとControlの2本の線を同一図へ描きます。
- 個人解析の後、Cキューブ群とVロートプレミアム群を分けてGrand-averageを作成します。各進捗位置で個人値の平均、標本SD（`ddof=1`）、有効人数Nを算出し、平均線と平均±1 SDの帯を表示します。
- 欠測値を補間・前詰めしません。被験者内対応を保つ群比較では、Phase 1で一方のセッションが欠測となったセットについて、対応するもう一方の条件も同じセットを群集計から外します。

## 6. セット別定量化

- 被験者・条件・セットごとの定量値は、**セット内の主解析信号で検出した瞬き総数 ÷ セット実時間（分）**で求めます。
- 移動窓Blink Rateの時間平均を定量値として再利用しません。
- Cキューブ群とVロートプレミアム群を分け、それぞれSet 1〜6の独立した6パネルを横一列で作成します。
- 各パネルは左に `Eye Drop (C Cube)` または `Eye Drop (V Rohto Premium)`、右に `Control` を置きます。
- バーは条件内の被験者間平均、ドットは被験者値、接続線は同一被験者の2条件の対応を表します。
- 縦軸は6パネル共通の `Blink Rate (blinks/min)` とします。
- 欠測セットはドット、接続線、平均へ含めません。被験者内対応を保つ群比較では対応条件も同じセットから外します。
- 推測統計は現段階では実施しません。

## 7. Figureの共通仕様

- Figure内はArial・英語表記とし、軸名、単位、凡例、色・線の意味を明記します。
- Phase 2の意味対応は維持しつつ、RT・ミスタッチと同一色を使わないPhase 3専用色に固定します。
  - Control：`#4B5563`
  - C Cube：`#21867A`
  - V Rohto Premium：`#3268A8`
- 同じ指標の個人、Grand-average、定量化で色を変更しません。
- 線幅、文字サイズ、バー幅、ドットサイズ、条件順は全ID・両製品群で固定し、データ内容によって変えません。

## 8. 出力

指定OneDriveの次の場所へ保存します。

```text
Phase3_瞬き解析/
  No1_BlinkRate/
    CCube/
      Individual/
      GrandAverage/
      SetQuantification/
      HTML/
      ProminenceDistribution/
    VRohtoPremium/
      Individual/
      GrandAverage/
      SetQuantification/
      HTML/
      ProminenceDistribution/
    Sub/
      tables/
      logs/
```

- 各製品群の `HTML/`：セッションID別にMAD方式の検出確認HTMLを保存する
- 各製品群の `ProminenceDistribution/`：セッションID別に、全候補prominenceの0–500 µVヒストグラムを対数縦軸で表示し、MAD閾値線と500 µV超の候補数を示すPNGを保存する
- 各製品群の `Individual/`：被験者ペア別PNGを直下へ保存し、被験者別サブフォルダを作らない
- 各製品群の `GrandAverage/`：製品群別PNGだけを保存する
- 各製品群の `SetQuantification/`：6パネルPNGを直下へ保存し、被験者別サブフォルダを作らない
- `Sub/tables/`：検出ピーク一覧、未平滑化・15秒平滑化Blink Rate、ID・Set別検出数、閾値、欠測・QC要約
- `Sub/logs/`：実行条件、入力、完了・失敗、出力一覧を含む実行要約

Phase 3では、現段階でローカルデスクトップの `解析に必要なデータたち/` へ新しい中間データを保存しません。Phase 1 HDF5を読み込み、再現に必要な検出結果と成果物を指定OneDriveへ保存します。

## 9. Notion結果記録

Notionの「フェーズ３：まばたきの解析」配下に、ID・Setごとに次を記録する結果テーブルを置きます。

- セッションID、被験者ペア、製品群、条件、Set
- 使用状態（使用／欠測／要確認）
- `Fp1_Fp2_mean` の検出数
- Fp1単独・Fp2単独の補助検出数
- セット実時間とセットBlink Rate
- セッション共通のprominence閾値、候補数、中央値、MAD、robust SD、係数10（peak heightは未設定）、minimum peak distance 100 ms、peak width 20–320 ms
- HTMLとOneDrive出力先
- 検出異常、左右差、欠測その他の備考

観察結果と解釈を分離し、Fp1・Fp2単独の検出数を主解析結果として扱いません。

## 10. 実装・実行条件

- 実行前にルートREADME、運用ルール、解析上の注意事項、本仕様、Phase 3実行README、NotionのPhase 3ページを確認します。
- 全対象を同じPythonコードと固定パラメータのループで処理し、IDごとにコードや閾値を手修正しません。
- まずパイロットIDで、HDF5読込、閾値、ピーク重複、HTML操作、Blink Rate、定量化、欠測、保存、Notion記録を検証します。
- パイロットID 101／201では、height基準を設けず、prominenceの `中央値 + 10 × 1.4826 × MAD` をセッション共通閾値とし、minimum peak distance 100 ms・peak width 20–320 msを併用する方式を検証します。HTML、0–500 µV・対数縦軸のprominence分布PNG、Blink Rate、定量化、補助表、Notion記録を確認します。
- 実行成功だけで完了とせず、OneDrive成果物、CSV・JSONの読み戻し、HTML操作、Notion読み戻しを確認します。
- 許可済み範囲の通常実行、出力確認、Notion更新、Git操作に利用者承認を求めません。許可範囲外、安全上の問題、または自力で解決できない阻害要因がある場合だけ停止します。
