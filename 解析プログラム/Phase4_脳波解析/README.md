# Phase 4：脳波解析

脳波解析のPythonスクリプトを配置します。命名形式は `Phase4_No<番号>_<内容>.py` です。

成果物と計算済みPSDは、同じNoを使って指定OneDriveと `解析に必要なデータたち/Phase4_脳波解析/` へ保存します。No1の現行スクリプトは `Phase4_No1_FmTheta.py` です。スクリプトと単体テストに加え、ID101–201の実データ試行を完了しています。1ペアだけの試行ではGrand-averageの平均を出力し、SD・SEMと推測統計は算出不能として保持します。

## 事前定義した解析対象

時間変化解析とセット別定量化では、文献調査に基づき次の単一ch×周波数帯を使用します。

- No1 frontal-midline theta（Fmθ）：Fz、4–7 Hz
- No2 occipital alpha：Oz、8–15 Hz
- No3 frontal delta：Fz、帯域未確定

根拠と解釈上の注意は [`docs/Phase4_解析対象チャンネル文献調査.md`](../../docs/Phase4_解析対象チャンネル文献調査.md) を参照します。FCzとPOzは現行32chに含まれません。

No1は、全32chを1秒Hann窓・1秒移動・256点FFTのWelch法で解析し、4–7 Hz平均の未平滑PSDをHDF5へ一度だけ保存します。そのデータからFzの30秒平滑化時間変化、製品群別Grand-average、未平滑PSDの定量化・統計、全32chの条件差topographyを作ります。現行の確定仕様、figure様式、欠測Set、フォルダ構造は [`docs/Phase4_脳波解析仕様.md`](../../docs/Phase4_脳波解析仕様.md) を唯一の実装正本とします。

## No1の実行モード

- `--preflight-only`、`--compute-psd`、`--individual-only`、`--group-outputs-only`、`--all` から1つを選択します。
- `--force-recompute` は `--compute-psd` または `--all` と併用し、明示的な再計算決定がある場合だけ使用します。
- `--force-recompute` がない限り、設定hashと入力情報が一致して検証済みのPSD cacheを再利用します。
- 全対象へ同じコード・同じ定数を適用し、既知欠測Set以外のID固有分岐を作りません。

本番manifestはリポジトリ外の非公開CSVを `--manifest` で渡します。実行例は次のとおりです。

```bash
MPLCONFIGDIR=/tmp/mplconfig-roht .venv/bin/python \
  '解析プログラム/Phase4_脳波解析/Phase4_No1_FmTheta.py' \
  --manifest /absolute/path/to/private_manifest.csv \
  --production-batch \
  --preflight-only
```

preflight完了後の本計算では、同じmanifestに `--all` を指定します。入力、cache、OneDriveのデフォルトパスは確定仕様に固定しています。このREADME更新時点で `--all` はまだ実行していません。

## No1実装時の固定事項

- 入力：Phase 1の `brain_activity_eeg` HDF5、256 Hz、V単位、固定32ch順
- PSD：MNE `psd_array_welch`、1秒Hann窓、外側窓を1秒移動、256点FFT、4–7 Hzの4 bin平均、線形µV²/Hz
- Set端：前後128 samplesの反射padding、Set開始・終了を窓中心として評価
- 区間mask：Phase 1のICA学習除外区間と1%以上重なるPSD窓を全32chでNaN化し、時刻・progressは保持
- ch mask：ICA学習用ch除外maskはPSDへ適用せず、32chを保持
- 時間変化：各Set内で30秒中心化単純移動平均。NaNは無視し、窓内全てがNaNの場合のみNaN
- 現行非適用：平均参照、ラプラシアン
- cache：全32chの帯域平均PSD時間変化、中心時刻、progress、mask監査情報をHDF5保存
- figure：30秒平滑化した個人Fzと製品群別Fz Grand-average、未平滑PSDの定量化、全32ch差topography
- 個人Fz：平滑化後の自動y軸版を `Individual/` 直下、未平滑の自動y軸版を `Individual/Unsmoothed/` に保存。固定y軸版と比較フォルダは作成しない
- 欠測：個人時間変化は欠測側だけ空白、集団集計・定量化・topographyは対応条件も対称除外

Figureの寸法、フォント、軸名、目盛、Set位置、線幅、色、y上限、統計マーク位置、topographyのmontage・カラースケールはPhase 4仕様書の数値をコード定数としてそのまま実装します。定量化はPhase 3と同様に条件名22 ptと製品名18 ptを分離します。Topographyは6 Set横一列、太い円形頭部輪郭・鼻、8 ptの電極点、等高線なしの滑らかな色面、十分な間隔を空けた太いSet別colorbarで描画し、全Set共通の左右対称かつ切りのよい上限を使います。Phase 2・3を再解釈して別の値を採用しません。

Phase 4の被験者別結果表や日次実行記録はNotionへ作成しません。preflight、本計算、cache検証、出力確認、警告、失敗理由、成果物一覧はOneDriveの `No1_FmTheta/Sub/logs/` と `Sub/tables/` へ保存し、コード・文書の版はGit履歴で追跡します。NotionはPhase 4の概要・確定仕様・文献調査の管理に限定します。
