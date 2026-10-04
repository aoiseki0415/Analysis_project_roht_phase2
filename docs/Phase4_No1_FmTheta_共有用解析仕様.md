# Phase 4 No1：Fmθ解析 共有用仕様書

## 1. 目的

ガボール課題中のfrontal-midline theta（Fmθ）パワーが実験進行に伴ってどのように変化するかを、同一被験者のEye Drop条件とControl条件で比較する。被験者は使用製品に基づき、Cキューブ群とVロートプレミアム群へ分け、製品群ごとに解析する。

代表指標は **Fzの4–7 Hzパワー**とする。加えて、条件差の空間分布を確認するため、全32チャンネルのtopographyを作成する。Fmθは認知負荷・認知的努力に関連する指標として扱うが、単一指標だけで心理状態を断定しない。

## 2. 解析対象と入力

- 対象：40被験者ペア、80セッション
- 製品群：Cキューブ20名、Vロートプレミアム20名
- 比較：各製品群内のEye Drop対Control（被験者内比較）
- 入力：Phase 1で作成したSet別脳活動解析用HDF5
- EEG：Eye成分除去後、256 Hz、V単位、固定32チャンネル順
- 代表チャンネル：Fz
- 対象帯域：4、5、6、7 Hz

IDの番号帯だけから条件を推測せず、確定manifestの `drops_session_id` と `product` を使用する。ID130・230は対象に含めない。

## 3. PSDの計算

全32チャンネルについて、MNE-Pythonの `mne.time_frequency.psd_array_welch()` を用いてPSDを計算する。

| 項目 | 設定 |
|---|---|
| 入力単位 | VからµVへ変換 |
| サンプリング周波数 | 256 Hz |
| 時間窓 | 1秒（256 samples） |
| 窓移動 | 1秒（256 samples） |
| 窓関数 | Hann |
| FFT点数 | 256 |
| segment長 | 256 |
| 関数内overlap | 0 |
| 周波数分解能 | 1 Hz |
| 対象周波数 | 4、5、6、7 Hz |
| 帯域代表値 | 4周波数binの算術平均 |
| PSD単位 | µV²/Hz |
| 対数・dB変換 | なし |

外側で1秒窓を1秒ずつ移動し、各窓には256 samplesだけを渡すため、Welch関数内のoverlapは0とする。Set先頭・末尾まで値を定義するため、信号の前後128 samplesを反射paddingする。PSDは実時間上で計算し、その後にprogressへ変換する。

## 4. Phase 1の除外情報の扱い

Phase 1の `ica_training_excluded_mask` と各1秒PSD窓の重なり率を計算する。重なり率が **1%以上**の窓は、時間位置を詰めず、全32チャンネルの解析値をNaNとして扱う。

その後、セッションID・チャンネルごとに利用可能な全Setの有限かつ正の未平滑4–7 Hz平均PSDをまとめ、`log10(PSD)`の平均＋3標準偏差（`ddof=1`）を超える上側値だけを、そのチャンネル・時間窓でNaNとする。閾値をSetごとに作らず、対応セッション、条件、被験者、チャンネルを混ぜず、下側外れ値も除外しない。

元の有限PSDとmask重複率はcacheへ保持し、cache自体は上書きしない。log閾値、線形閾値、除外mask、Set・チャンネル別の除外数と除外率を別途保存する。Phase 1のICA学習用チャンネル除外maskはPSDには適用せず、最終HDF5に保持された32チャンネルを解析する。平均参照、ラプラシアン、追加フィルタは行わない。

## 5. PSD cache

4–7 Hz平均後の **未平滑・全32チャンネルPSD時間変化**を、セッションごとのHDF5として次へ保存する。

```text
解析に必要なデータたち/
  Phase4_脳波解析/
    No1_FmTheta/
      PSDTimeSeries/
        Pair101-201_01_ID101_FmTheta_AllChannelsPSD.h5
        Pair101-201_02_ID201_FmTheta_AllChannelsPSD.h5
        ...
```

HDF5にはSet別の元PSD、チャンネル順、相対秒、OriginalTimestamp、Set内・全体progress、窓中心sample、区間mask重複率、log10上側3SD閾値・mask・除外数・率、ICA用チャンネルmask、PSD設定、入力fingerprint、設定hashを保存する。設定hashと入力情報が一致するcacheは再利用し、figureの調整だけではPSDを再計算しない。

## 6. Fz時間変化

### 個人figure

Phase 1区間maskとlog10上側3SD maskを適用したFzの未平滑PSDへ、Set内だけで **60秒中心化単純移動平均**を適用する。NaNは無視し、窓内に1点以上の有限値があれば平均し、窓全体がNaNの場合だけNaNとする。Set境界をまたいで平滑化しない。

平滑化後、各Setを0–100%へ対応付け、6 Setを0–600%として横に連結する。

- x軸：`Experimental Progress, %`
- y軸：`PSD (µV²/Hz)`
- 1被験者ペアにつき1 PNG
- ControlとEye Dropを同一figureへ描画
- Set境界：100、200、300、400、500
- 主figure：60秒平滑化後
- `Individual/Unsmoothed/BeforeThresholdExclusion/`：3SD閾値除外前の未平滑PSD確認用figure
- `Individual/Unsmoothed/AfterThresholdExclusion/`：3SD閾値除外後の未平滑PSD確認用figure

主figureのy軸下限は0とし、両条件・全Setの平滑化後有限最大値が軸高のおよそ70%以内に入る切りのよい上限を使う。

### Grand-average

各被験者・条件・Setについて、60秒平滑化後の系列を100点のprogress格子へ対応付け、その後に被験者間平均を計算する。各点で平均、標本SD、有効N、`SEM = SD / √N`を保存し、figureは平均線と平均±SEMを示す。

標準表示規則は `mean + SEM` の最大を軸高のおよそ75%へ置く。平均線だけを基準にする特例や95%表示は使用しない。

## 7. 定量化と統計

定量化にはPhase 1区間maskとlog10上側3SD maskを適用後、平滑化前の有限なFz PSD窓を使用する。

- Set別値：各Set内の有限PSD窓の時間平均
- 全Set統合値：両条件で共通利用可能なSetの有限PSD窓をすべて連結した平均
- Set平均を再平均する方法は使わない

統計は製品群別に、Eye DropとControlの両方が有限な被験者だけを用いた **両側対応ありt検定**とする。

- 主PNG：未補正p値を表示
- `p < 0.05`：`*`
- `p < 0.01`：`**`
- `p < 0.001`：`***`
- それ以外：`n.s.`
- 統計CSV：未補正、Bonferroni、Holm、Benjamini–Hochberg FDRを併記
- 全Set統合：1検定のため多重比較補正なし

figureは条件平均のbar、被験者値のdot、同一被験者を結ぶ線で構成する。

## 8. Topography

各被験者・Set・チャンネルについて、mask適用後の未平滑PSDを時間平均し、次の条件差を計算する。

```text
Eye Drop − Control
```

個人topographyと製品群別Grand-average topographyを作り、Set 1–6を横一列に表示する。

- montage：MNE `colin27_1020`
- colormap：`RdBu_r`
- 0を中心とする左右対称スケール
- 6 Setで共通スケール
- 電極点を表示、チャンネル名と等高線は表示しない
- 統計maskや有意電極は重ねない

同一図内の最大絶対差を `M` とし、`M / 0.85` 以上となる切りのよい値 `V` を選び、`−V`から`+V`を表示する。個人figure間ではVを変えてよい。

## 9. 欠測Set

| 欠測セッション | 欠測Set | 対応セッション |
|---|---:|---|
| ID109 | 1 | ID209 |
| ID120 | 6 | ID220 |
| ID135 | 2 | ID235 |
| ID225 | 4 | ID125 |

- 個人時間変化：欠測セッション側だけを非表示にし、対応セッション側は描画する
- Grand-average・定量化：被験者内対応を保つため、対応セッション側も同じSetから除外する
- 個人topography：該当Setを `Missing` とする
- Grand-average topography：該当Setではその被験者ペアを除外する
- 補間、前詰め、Set間結合は行わない

## 10. 結果の保存場所と読み方

```text
実験本番_本解析/
  Phase4_脳波解析/
    No1_FmTheta/
      CCube/
        Individual/
          Unsmoothed/
            BeforeThresholdExclusion/
            AfterThresholdExclusion/
        GrandAverage/
        SetQuantification/
        Topography/
          Individual/
          GrandAverage/
      VRohtoPremium/
        Individual/
          Unsmoothed/
            BeforeThresholdExclusion/
            AfterThresholdExclusion/
        GrandAverage/
        SetQuantification/
        Topography/
          Individual/
          GrandAverage/
      Sub/
        tables/
        logs/
```

- `Individual/`：60秒平滑化後のFz時間変化
- `Individual/Unsmoothed/BeforeThresholdExclusion/`：3SD閾値除外前の未平滑Fz時間変化
- `Individual/Unsmoothed/AfterThresholdExclusion/`：3SD閾値除外後の未平滑Fz時間変化
- `GrandAverage/`：製品群別の平均±SEM
- `SetQuantification/`：Set別・全Set統合のbar＋dot figureと統計CSV
- `Topography/Individual/`：被験者別の全32ch条件差
- `Topography/GrandAverage/`：製品群別の条件差平均
- `Sub/tables/`：Grand-average値、定量値、統計、topography値
- `Sub/logs/`：実行条件、対象、検証結果、警告、成果物一覧

## 11. 実装と再現

- Python：`解析プログラム/Phase4_脳波解析/Phase4_No1_FmTheta.py`
- 詳細な実装正本：`docs/Phase4_脳波解析仕様.md`
- 同一スクリプト・同一パラメータを全被験者へ適用する
- 本番解析前に40ペア・80セッション、製品群各20名、対象外ID、欠測Set、入力HDF5構造をpreflightする
- PSD計算、個人出力、集団出力を実行モードで分離し、検証済みcacheを再利用する

本仕様はPhase 4 No1 Fmθ解析の確定版を共有用に要約したものである。コード実装に必要な全figure定数、HDF5 schema、検証条件は詳細仕様書を参照する。
