# Phase 4 脳波解析仕様

## 1. 位置づけ

Phase 4では、事前定義した単一チャンネル×周波数帯について、目薬あり条件とコントロール条件の脳活動を比較します。使用した目薬で被験者をCキューブ群とVロートプレミアム群に分け、製品群ごとに解析します。

| No | 指標 | 代表ch | 周波数帯 | 主な解釈 | 状態 |
|---|---|---:|---:|---|---|
| No1 | frontal-midline theta（Fmθ） | Fz | 4–7 Hz（両端を含む） | 認知負荷 | 本書で確定 |
| No2 | occipital alpha | Oz | 8–15 Hz（両端を含む） | 不注意・マインドワンダリング | 代表chと帯域のみ確定 |
| No3 | frontal delta | Fz | 未確定 | 疲労・眠気 | 代表chのみ確定 |

代表chの文献根拠は[Phase 4 解析対象チャンネル文献調査](Phase4_解析対象チャンネル文献調査.md)を参照します。

## 2. No1 Fmθ解析の目的

Fzの4–7 Hzパワーについて、次を作成します。

1. 個人ごとの時間変化
2. 製品群別Grand-average
3. Set別および全Set統合の定量化と条件間比較
4. 全32chの条件差から作る、Set別topography

## 3. 入力データ

- Phase 1で保存した `IDxxx_SetN_brain_activity.h5` を入力とします。
- サンプリング周波数は256 Hzです。
- 保存信号はV単位のため、PSD計算前にµVへ変換します。
- 平均参照とラプラシアンは追加しません。
- 代表chのfigureはFzを使いますが、PSDは最初から全32chで一度だけ計算します。
- Phase 1の区間除外mask、ICA除外チャンネルmask・名称・理由を読み込み、キャッシュへ引き継ぎます。

## 4. PSD時間変化の計算

MNE-PythonのWelch法を用い、次を固定します。

| 項目 | 設定 |
|---|---|
| 手法 | Welch PSD |
| 窓 | Hann窓、1秒（256 samples） |
| 移動幅 | 0.5秒（128 samples） |
| overlap | 50% |
| FFT長 | 256 |
| 周波数分解能 | 1 Hz |
| No1の帯域 | 4、5、6、7 Hzの算術平均 |
| 単位 | µV²/Hz |
| Set両端 | 反射paddingを前後0.5秒付加し、Set開始・終了を窓中心として評価 |
| 時間平滑化 | 現時点では行わない |
| 区間maskによるPSD除外 | 現時点では行わない |
| ICA除外chによるPSD除外 | 現時点では行わない |

PSDは線形値のまま扱い、対数変換やdB変換は行いません。平滑化、区間maskによるNaN化、チャンネル除外は将来追加する可能性がありますが、現行主解析には含めません。

## 5. 計算データの保存と再利用

PSD計算とfigure作成を分離し、figure調整のたびにPSDを再計算しません。全32chについて4–7 Hz平均後のPSD時間変化を、セッションIDごとに1つのHDF5へ保存します。HDF5内はSet単位で分けます。

保存内容は次のとおりです。

- 全32chの帯域平均PSD時間変化
- 固定したチャンネル順
- Set内相対秒
- 各窓中心の `OriginalTimestamp`
- Set内progressと、6 Setを連結した全体progress
- PSDパラメータと単位
- Phase 1の区間mask、ICA除外ch mask・名称・理由
- 元入力ファイルとSet番号

ファイルは同一被験者の2セッションが連続する名称にします。

```text
Pair101-201_01_ID101_FmTheta_AllChannelsPSD.h5
Pair101-201_02_ID201_FmTheta_AllChannelsPSD.h5
Pair102-202_01_ID102_FmTheta_AllChannelsPSD.h5
Pair102-202_02_ID202_FmTheta_AllChannelsPSD.h5
```

将来作る同一スクリプト内では、少なくとも「PSD計算・保存」「個人figure」「Grand-average」「定量化・統計」「topography」を独立して実行できる構成にします。

## 6. 時間変化figure

### 6.1 個人figure

- 1被験者ペアにつき1枚とし、Eye DropとControlの2線を描きます。
- Set 1〜6を横方向へ連結します。
- 横軸は `Experimental Progress, %` とし、Set 1を0–100、Set 2を100–200、最終的に600までとします。
- 横軸への変換は、各Setの実時間上のPSD窓中心を、そのSet内の0–100%へ線形変換してから連結します。
- Set境界は薄いグレーの点線、Set名は図内上部へ表示します。
- 縦軸は `PSD (µV²/Hz)` とします。二乗は上付き文字で表示します。
- 同一figureの両条件・全Setで縦軸を共通化します。縦軸範囲は被験者ごとに調整できます。
- Arialを使用し、軸名、目盛り、凡例、Set名の大きさと余白はPhase 2・3の確定figure様式へ合わせます。
- 現時点では平滑化しません。

### 6.2 Grand-average

- Cキューブ群とVロートプレミアム群を別々に作成します。
- 各Setを共通progress格子へ補間した後、被験者間平均を計算します。
- 平均線と平均±SEMのシェードを表示します。
- 凡例にNやシェードの説明文は追加しません。有効Nは表へ保存します。
- 同一figureの両条件・全Setで縦軸を共通化します。

## 7. 配色

| 解析 | Control | Cキューブ Eye Drop | Vロートプレミアム Eye Drop |
|---|---|---|---|
| No1 Fmθ | `#402B5D` | `#A94F2D` | `#D97852` |
| No2 alpha | `#402B5D` | `#C23B8A` | `#E36A8D` |
| No3 delta | `#402B5D` | `#8F7300` | `#C29A00` |

定量化figureは同じ対応関係を保ち、時間変化figureと区別できるよう明度または彩度だけを調整します。

## 8. 定量化と統計

- 被験者ごとのSet値は、そのSet内のFzの線形PSD時間変化を時間方向に単純平均して算出します。
- 全Set統合値は、両条件で共通して利用可能なSetのPSD時点をまとめ、時間方向に単純平均します。
- Set別figureは6パネルを横一列に並べます。
- 左にEye Drop、右にControlを置き、平均バー、被験者ドット、被験者内対応線を描きます。
- ドットには再現可能なjitterを適用し、白い枠線を付けます。
- 全Set統合figureは1パネルとします。
- 検定は両側対応ありt検定です。
- 主PNGは未補正p値を表示します。
- Set別統計CSVには未補正、Bonferroni、Holm、Benjamini–Hochberg FDRを併記します。
- 全Set統合は1検定なので、多重比較補正を行いません。
- 両条件に有限値がある被験者だけを各検定に使用します。

## 9. Topography

各被験者ペア・各Set・各chで、`Eye Drop − Control` のSet平均PSD差を算出します。

### 9.1 個人topography

- 1被験者ペアにつき、Set 1〜6を横一列に並べます。
- 発散色を用い、0を色中心とします。
- カラースケールは、その被験者の利用可能な全Set・全chの最大絶対値から対称に決め、Set間で共通化します。
- 被験者間ではカラースケールが異なって構いません。
- 欠測Setは補間せず、空欄または `Missing` と表示します。

### 9.2 Grand-average topography

- 製品群ごとに作成します。
- 各Setで、利用可能な被験者の条件差topographyを被験者間平均します。
- 6 Setを横一列に並べ、同一製品群のSet間で共通の対称カラースケールを使います。
- colorbarは `ΔPSD (µV²/Hz)` とします。
- 現時点では有意差記号や統計マスクを重ねません。

電極座標はMNEの `colin27_1020` montageを使用します。現行32chは32/32すべて対応するため、追加の座標ファイルは不要です。

## 10. 欠測Setの扱い

既知の欠測は次のとおりです。

| 欠測セッション | 欠測Set | 対応セッション |
|---|---:|---|
| ID109 | Set 1 | ID209 |
| ID120 | Set 6 | ID220 |
| ID135 | Set 2 | ID235 |
| ID225 | Set 4 | ID125 |

- 個人時間変化figure：欠測セッション側の該当Setだけ線を描かず、対応条件側は描画します。
- Grand-average・定量化：被験者内対応を保つため、対応条件側も同じSetを除外します。
- 全Set統合：両条件で共通して利用可能なSetだけを使います。
- 個人topography：条件差が作れないため、そのSetを空欄または `Missing` とします。
- Grand-average topography：そのSetでは該当ペアを除外します。
- 欠測を補間しません。Setごとの有効Nを保存します。

## 11. 保存先

### ローカル計算データ

```text
/Users/aoiseki/Desktop/SandBox_ロート案件（データ）/解析に必要なデータたち/
  Phase4_脳波解析/
    No1_FmTheta/
      PSDTimeSeries/
```

### OneDrive成果物

```text
実験本番_本解析/
  Phase4_脳波解析/
    No1_FmTheta/
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
        logs/
```

## 12. 実装前確認

- 本書とNotionのPhase 4親ページ・No1詳細ページを読み直す。
- 入力HDF5、256 Hz、V→µV、32ch順、欠測Setを確認する。
- PSD計算とfigure再描画を分離する。
- progress変換はPSD窓中心のSet内実時間に基づく。
- 全figureに英語の軸名、単位、凡例、色の意味を明記する。
- No1の解析スクリプトは、仕様確認が完了するまで作成しない。

最終更新：2026年10月3日
