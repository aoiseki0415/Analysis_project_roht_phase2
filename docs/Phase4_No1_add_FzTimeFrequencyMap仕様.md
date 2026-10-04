# Phase 4 No1_add：Fz Time-Frequency Map仕様

## 1. 位置づけ

本書は、Phase 4 No1の追加解析として実施するFz Time-Frequency Map（TFM）の確定方針を定めます。No1本体のFz 4–7 Hz時間変化、定量化、統計、全32ch topographyとは、スクリプト、ローカルcache、OneDrive成果物、Notion見出しを分離します。

- 解析名：`No1_add_FzTimeFrequencyMap`
- 将来のPython：`解析プログラム/Phase4_脳波解析/Phase4_No1_add_FzTimeFrequencyMap.py`
- 状態：運用仕様確定、スクリプト未実装
- 成果物：製品群別Grand-average TFMだけを作成し、個人TFM figureは作成しない

No1本体のシータ平均値やシータ用外れ値maskをNo1_addへ流用しません。

## 2. 目的と比較

Fzの1–30 Hzパワーが実験進行に伴ってどのように変化するかを、Cキューブ群とVロートプレミアム群に分け、各製品群内でEye DropとControlを被験者内比較します。No1本体で観察する4–7 Hz変化が周辺周波数と比べてどの程度周波数特異的かを補助的に確認します。

- 対象：No1本体と同じ40被験者ペア、80セッション
- 条件対応：非公開manifestの `drops_session_id` と `product`
- 入力：Phase 1のSet別脳活動解析用HDF5
- 対象ch：Fzだけ
- 周波数：1–30 Hz、1 Hz刻み
- 0 Hz：DC成分のため解析対象に含めない
- 比較差：`ΔPSD = Eye Drop − Control`

## 3. TFM計算

FzをVからµVへ変換し、No1本体と同じ実時間窓で線形PSDを計算します。

| 項目 | 設定 |
|---|---|
| 使用関数 | `mne.time_frequency.psd_array_welch()` |
| サンプリング周波数 | 256 Hz |
| 外側窓 | 1秒、256 samples |
| 外側窓移動 | 1秒、256 samples |
| 窓関数 | Hann |
| `n_fft` / `n_per_seg` | 256 / 256 |
| 関数内overlap | 0 |
| `remove_dc` | `True` |
| 周波数 | 1–30 Hz、1 Hz刻み |
| 出力 | 線形power |
| 単位 | µV²/Hz |
| 対数・dB変換 | 出力値には行わない |

Set端はNo1本体と同じく前後128 samplesの反射paddingを使い、Set開始とSet終了を窓中心として評価します。PSDは実時間で計算し、progress変換後にPSDを計算しません。

## 4. ノイズmask

### 4.1 Phase 1区間mask

Phase 1の `ica_training_excluded_mask` と1秒PSD窓が1%以上重なる場合、その時刻の1–30 Hz全binをNaNとして扱います。時刻とprogressは詰めず、補間しません。

### 4.2 No1_add専用Broadband 3SD mask

No1本体の4–7 Hz平均から作るch別maskは使用しません。No1_addでは、各IDのFzについて次の順序で独立した時間maskを作ります。

1. Phase 1区間mask適用後の各1秒窓について、1–30 Hzの線形PSDを周波数方向に算術平均し、Broadband PSDを作る
2. 欠測Setを除く全Setの有限かつ正のBroadband PSDを1本に連結する
3. `x = log10(Broadband PSD)` を求める
4. ID単位で全Set共通の `threshold_log = mean(x) + 3 × SD(x, ddof=1)` を求める
5. `x > threshold_log` の時間窓を追加除外する
6. 該当時刻の1–30 Hz全binをNaNにする

閾値はSet別、条件ペア共通、製品群共通、被験者間共通では計算しません。各セッションIDで1個です。下側外れ値は除外しません。Broadband平均は30個の等間隔binを用いるため、周波数和を用いてもlog空間の判定は定数差となりますが、実装と記録は算術平均に固定します。

## 5. 平滑化、progress、Grand-average

1. 区間maskとBroadband 3SD maskを適用した未平滑TFMを用意する
2. 各周波数binを個別に、各Set内だけで60秒中心化単純移動平均する
3. NaNを無視し、移動窓の全値がNaNのときだけ平滑化結果もNaNとする
4. 平滑化後に、被験者・条件・Setごとに100点のprogress格子へ対応付ける
5. Set間をまたいで平滑化・補間しない
6. 対応するEye DropとControlを被験者内で揃える
7. 各製品群で、条件別TFMを被験者間平均する
8. `ΔPSD` は被験者ごとに `Eye Drop − Control` を計算してから被験者間平均する

Grand-averageより前に個人系列をprogressへ対応付けます。Setの実時間長が異なっても、PSD計算、mask、60秒平滑化までは実時間上で行います。

## 6. 欠測Set

No1本体と同じ既知欠測Setを使用します。

- ID109 Set 1（対応ID209）
- ID120 Set 6（対応ID220）
- ID135 Set 2（対応ID235）
- ID225 Set 4（対応ID125）

No1_addはGrand-averageだけを作るため、該当Setでは欠測セッションと対応セッションの両条件を除外します。欠測を補間せず、Set・条件・周波数・progress点ごとの有効Nを保存します。

## 7. Cache

未平滑の線形TFMを再計算しないため、セッションIDごとのHDF5を保存します。

```text
解析に必要なデータたち/
  Phase4_脳波解析/
    No1_add_FzTimeFrequencyMap/
      TimeFrequencySeries/
        Pair101-201_01_ID101_FzTFM.h5
        Pair101-201_02_ID201_FzTFM.h5
```

最低限、次を保存します。

- Set別の未平滑Fz PSD `[n_windows, 30 frequencies]`
- 周波数 `[1, 2, ..., 30] Hz`
- 相対秒、OriginalTimestamp、Set内progress、全体progress、窓中心sample
- Phase 1区間mask重複率
- Broadband PSD、log平均、log標本SD、log閾値、線形閾値
- Broadband 3SD時間mask、Set別・全体の除外数と除外率
- PSD・padding・mask・平滑化・progressの全設定
- 入力fingerprintと設定hash

元の未平滑TFMを上書きせず、maskは別datasetとして保存します。保存後にshape、周波数、単位、時刻、progress、mask、設定hashを読み戻して検証します。

## 8. Grand-average figure

製品群ごとに1枚のPNGを作り、次の3パネルを縦に並べます。

1. Eye Drop Grand-average
2. Control Grand-average
3. `ΔPSD = Eye Drop − Control` Grand-average

- x軸：`Experimental Progress, %`、0–600
- y軸：`Frequency (Hz)`、1–30
- Set境界：100、200、300、400、500
- Set名：各Set中央
- 条件mapのcolorbar：`PSD (µV²/Hz)`
- 差分mapのcolorbar：`ΔPSD (µV²/Hz)`
- Eye DropとControlは共通カラースケール
- 差分は0中心の左右対称カラースケール
- 対数・dB・ベースライン補正は行わない
- Arial、英語表記、単位、panel名、colorbarの意味を明記する

絶対PSDでは低周波が色を支配し得ますが、本解析ではそれを許容し、線形PSDの絶対値を表示します。正確なfigure寸法、文字サイズ、colormap、colorbar tick、余白は、実装時にPhase 2–4の既存figureと照合したパイロット出力で最終固定します。固定後は本書、Notion、コード定数を同時に更新します。

## 9. OneDrive出力

```text
実験本番_本解析/
  Phase4_脳波解析/
    No1_add_FzTimeFrequencyMap/
      CCube/
        GrandAverage/
      VRohtoPremium/
        GrandAverage/
      Sub/
        tables/
        logs/
```

主成果物フォルダにはPNGだけを置きます。条件別・差分のGrand-average値、有効N、カラースケール、閾値、除外数、検証結果、成果物一覧は `Sub/tables/` と `Sub/logs/` に保存します。Notionへ被験者別結果表や日次実行記録は作成しません。

## 10. No1本体との分離

- No1本体：全32chの4–7 Hz平均PSD、Fz時間変化・定量化、全32ch topography
- No1_add：Fzだけの1–30 Hz TFM、Grand-averageだけ
- スクリプト、cache root、OneDrive root、Notion見出し、詳細ページを分ける
- No1本体のシータ用3SD maskをNo1_addへ流用しない
- No1_addのBroadband 3SD maskをNo1本体へ流用しない
- No1_addのfigure調整だけでは検証済みTFM cacheを再計算しない

## 11. 実装前の残事項

- パイロットfigureで寸法、文字サイズ、colormap、colorbar tick、余白を最終固定する
- No1本体とは別の単体テストとpreflightを作る
- 同一スクリプト・同一設定を全対象へ適用できることを確認する
