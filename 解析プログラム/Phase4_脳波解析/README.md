# Phase 4：脳波解析

脳波解析のPythonスクリプトを配置します。命名形式は `Phase4_No<番号>_<内容>.py` です。

成果物と計算済みPSDは、同じNoを使って指定OneDriveと `解析に必要なデータたち/Phase4_脳波解析/` へ保存します。現時点では運用仕様と保存先だけを確定し、解析スクリプトはまだ作成しません。

## 事前定義した解析対象

時間変化解析とセット別定量化では、文献調査に基づき次の単一ch×周波数帯を使用します。

- No1 frontal-midline theta（Fmθ）：Fz、4–7 Hz
- No2 occipital alpha：Oz、8–15 Hz
- No3 frontal delta：Fz、帯域未確定

根拠と解釈上の注意は [`docs/Phase4_解析対象チャンネル文献調査.md`](../../docs/Phase4_解析対象チャンネル文献調査.md) を参照します。FCzとPOzは現行32chに含まれません。

No1は、全32chを1秒Hann窓・0.5秒移動・256点FFTのWelch法で解析し、4–7 Hz平均PSDをHDF5へ一度だけ保存します。そのデータからFzの個人時間変化、製品群別Grand-average、定量化・統計、全32chの条件差topographyを作ります。現行の確定仕様、figure様式、欠測Set、フォルダ構造は [`docs/Phase4_脳波解析仕様.md`](../../docs/Phase4_脳波解析仕様.md) を正本とします。
