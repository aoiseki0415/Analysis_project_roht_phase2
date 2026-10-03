# Phase 4：脳波解析

脳波解析のPythonスクリプトを配置します。命名形式は `Phase4_No<番号>_<内容>.py` です。

成果物と計算済みPSDは、同じNoを使って指定OneDriveと `解析に必要なデータたち/Phase4_脳波解析/` へ保存します。現時点では運用仕様と保存先だけを確定し、解析スクリプトはまだ作成しません。

## 事前定義した解析対象

時間変化解析とセット別定量化では、文献調査に基づき次の単一ch×周波数帯を使用します。

- No1 frontal-midline theta（Fmθ）：Fz、4–7 Hz
- No2 occipital alpha：Oz、8–15 Hz
- No3 frontal delta：Fz、帯域未確定

根拠と解釈上の注意は [`docs/Phase4_解析対象チャンネル文献調査.md`](../../docs/Phase4_解析対象チャンネル文献調査.md) を参照します。FCzとPOzは現行32chに含まれません。

No1は、全32chを1秒Hann窓・0.5秒移動・256点FFTのWelch法で解析し、4–7 Hz平均PSDをHDF5へ一度だけ保存します。そのデータからFzの個人時間変化、製品群別Grand-average、定量化・統計、全32chの条件差topographyを作ります。現行の確定仕様、figure様式、欠測Set、フォルダ構造は [`docs/Phase4_脳波解析仕様.md`](../../docs/Phase4_脳波解析仕様.md) を唯一の実装正本とします。

## No1実装時の必須構成

- スクリプト名は `Phase4_No1_FmTheta.py` とします。
- `--preflight-only`、`--compute-psd`、`--individual-only`、`--group-outputs-only`、`--all`、`--force-recompute` を独立させます。
- `--force-recompute` がない限り、設定hashと入力情報が一致して検証済みのPSD cacheを再利用します。
- 全対象へ同じコード・同じ定数を適用し、既知欠測Set以外のID固有分岐を作りません。

## No1実装時の固定事項

- 入力：Phase 1の `brain_activity_eeg` HDF5、256 Hz、V単位、固定32ch順
- PSD：MNE `psd_array_welch`、1秒Hann窓、外側窓を0.5秒移動、256点FFT、4–7 Hzの4 bin平均、線形µV²/Hz
- Set端：前後128 samplesの反射padding、Set開始・終了を窓中心として評価
- 現行非適用：追加平滑化、区間mask NaN化、ICA用ch maskによる除外、平均参照、ラプラシアン
- cache：全32chの帯域平均PSD時間変化、中心時刻、progress、mask監査情報をHDF5保存
- figure：個人Fz、製品群別Fz Grand-average、定量化、全32ch差topography
- 欠測：個人時間変化は欠測側だけ空白、集団集計・定量化・topographyは対応条件も対称除外

Figureの寸法、フォント、軸名、目盛、Set位置、線幅、色、y上限、統計マーク位置、topographyのmontage・カラースケールはPhase 4仕様書の数値をコード定数としてそのまま実装します。Phase 2・3を再解釈して別の値を採用しません。
