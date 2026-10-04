# Phase 4 No1_sub：Fmθ PSD Change仕様

## 1. 位置づけ

本書は、Phase 4 No1の追加解析として、Set 1を基準にしたFmθ PSD変化率を解析する確定仕様です。No1本体およびNo1_addとは、Pythonスクリプト、OneDrive成果物、Notion見出しを分離します。

- 解析名：`No1_sub_FmThetaChange`
- Python：`解析プログラム/Phase4_脳波解析/Phase4_No1_sub_FmThetaChange.py`
- 入力：ローカルデスクトップに保存済みのNo1 PSD HDF5 cache
- ローカルへの派生データ保存：行わない
- OneDrive：`Phase4_脳波解析/No1_sub_FmThetaChange/`
- 状態：スクリプト作成済み、解析未実行

No1_subはWelch PSDを再計算しません。No1のPhase 1区間maskと、セッションID・ch別の全Set一括log10上側3SD maskを適用した未平滑PSDを読み込みます。

## 2. 目的と比較

Set 1の条件差が後続Setの絶対PSD比較へ与える影響を分離するため、各セッションID・各chのSet 1平均を100%とした変化率を求めます。Cキューブ群とVロートプレミアム群を分け、各製品群内でEye DropとControlを被験者内比較します。

## 3. Set 1基準変化率

セッションID、chごとに独立して、mask適用後・未平滑PSDのSet 1有限値から基準値を計算します。

```text
baseline(ID, ch) = mean(finite PSD values in Set 1)
PSD Change(t, ID, ch) = (PSD(t, ID, ch) / baseline(ID, ch) - 1) × 100
```

- baselineは条件間、ID間、ch間で共有しない
- baselineは有限かつ正であることを必須とし、0または極端に0へ近い値を任意にクリップしない
- 変換は平滑化より前に行う
- Set 1の時間平均は定義上0%になる
- 単位：`%`

## 4. 時間変化

- 代表ch：Fz
- 変化率へ変換後、各Set内だけで60秒中心化単純移動平均する
- NaNを無視し、窓内に1点以上の有限値があれば算出する。窓全体がNaNの場合だけNaNとする
- Set間をまたいで平滑化しない
- 平滑化後に各Setを100 progress点へ対応付ける
- x軸：`Experimental Progress, %`、0–600
- y軸：`PSD Change, %`
- 0%の水平線を表示する
- 個人figureは最大絶対値がy軸絶対上限の約70%、Grand-averageは平均±SEMの最大絶対値が約75%となる、0中心の左右対称軸を用いる
- 色、線幅、Arial、Set境界、Set名、凡例、文字サイズはNo1本体に合わせる

## 5. Grand-average

- 製品群別にEye DropとControlの平均±SEMを表示する
- 個人の60秒平滑化後系列をSet別100点へ対応付けてから被験者間平均する
- Set・条件・progress点ごとの有限値だけを用い、有効Nを保存する
- y軸は両製品群で共通にする

## 6. 定量化と統計

- 定量化は平滑化前のPSD Changeを用いる
- Set別値：そのSet内の有限な全時間窓の算術平均
- Set 1：定義上0%のBaselineとして表示し、t検定を行わない
- Set 2–6：対応ありt検定でEye DropとControlを比較する
- 全Set統合版：Set 1を含めず、Set 2–6の有限な全時間窓から条件ごとの1値を作る
- figureは未補正p値を表示する
- CSVには未補正、Bonferroni、Holm、FDR-BHの結果を保存する。補正対象はSet 2–6の5比較とする
- y軸：`PSD Change, %`、0中心の左右対称軸

## 7. Topography

全32chについて、平滑化前のSet別PSD Change平均を計算し、被験者内条件差を作ります。

```text
Difference in PSD Change(ch, Set) = Eye Drop - Control
```

- 個人topographyと製品群別Grand-average topographyを作る
- 6 Setを横一列に表示する
- Set 1は定義上0%であるため平坦なBaseline mapとする
- colorbar：`Difference in PSD Change, %`
- 各figure内の6 Setは共通、0中心・左右対称スケールとする
- 上限は有限値の最大絶対値がカラースケールの約85%となる切りのよい値にする
- 10-20 system、全32電極点、No1本体と同じ頭部輪郭・補間・文字サイズを用いる

## 8. 欠測SetとSet 1欠測

- 個人時間変化：通常は欠測側だけを非表示にし、対応条件側は表示する
- Grand-average、定量化、topography：欠測Setでは対応条件側も同じSetから除外する
- 既知欠測：ID120 Set 6（対応ID220）、ID135 Set 2（対応ID235）、ID225 Set 4（対応ID125）
- ID109はSet 1が欠測しbaselineを定義できないため、ペア109–209をNo1_sub全体から除外する。対応ID209だけを残さない
- 欠測を0、補間値、前後Setの値で置換しない

## 9. Preflight

実行前に次を全件検証し、違反時は成果物を書かず停止します。

- manifestのID、Eye Drop条件、製品群、重複、対象人数
- No1 cacheが全対象セッションに存在し、No1の設定hash・チャンネル順・6 Set構造と整合すること
- 各セッションID×chのSet 1 baselineが有限かつ正であること
- 既知のペア109–209だけがSet 1欠測による除外であること
- 変換後Set 1平均が数値誤差の範囲で0%となること

## 10. OneDrive成果物

```text
Phase4_脳波解析/
  No1_sub_FmThetaChange/
    CCube/
      Individual/
      GrandAverage/
      SetQuantification/
      Topography/
        Individual/
        GrandAverage/
    VRohtoPremium/
      Individual/
      GrandAverage/
      SetQuantification/
      Topography/
        Individual/
        GrandAverage/
    Sub/
      tables/
        Set1Baseline/
        GrandAverage/
        SetQuantification/
        Topography/
      logs/
```

主成果物フォルダにはPNGだけを置き、基準値、Grand-average数値、有効N、定量値、統計、topography数値、除外ペア、成果物一覧は`Sub/tables/`と`Sub/logs/`へ保存します。

## 11. 実行モード

- `--preflight-only`：cacheとSet 1 baselineを検証するだけ
- `--individual-only`：個人時間変化と個人topography
- `--group-outputs-only`：Grand-average、定量化、統計、群topography
- `--all`：preflight後に個人・群成果物を順に作る

No1_subにPSD再計算モードは設けません。figure調整時にもローカルのNo1 cacheを読み直し、Welch PSDは再計算しません。

## 12. 実装状態

運用文書、独立スクリプト、単体テスト、OneDrive成果物構造の定義まで作成済みです。実フォルダは初回解析実行時にスクリプトが作成します。pilotおよび全対象の解析実行は未実施です。
