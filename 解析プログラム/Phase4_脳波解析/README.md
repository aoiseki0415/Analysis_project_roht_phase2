# Phase 4：脳波解析

脳波解析のPythonスクリプトを配置します。命名形式は `Phase4_No<番号>_<内容>.py` です。

成果物と中間データは、同じNoを使って指定OneDriveと `解析に必要なデータたち/Phase4_脳波解析/` へ保存します。

## 事前定義した解析対象

時間変化解析とセット別定量化では、文献調査に基づき次の単一ch×周波数帯を使用します。

- frontal-midline theta（Fmθ）：Fz
- occipital alpha：Oz
- frontal delta：Fz

根拠と解釈上の注意は [`docs/Phase4_解析対象チャンネル文献調査.md`](../../docs/Phase4_解析対象チャンネル文献調査.md) を参照します。FCzとPOzは現行32chに含まれません。周波数帯の厳密な境界、電力スペクトル推定、時間窓、正規化、欠測・mask、統計、topographyの実装は未確定であり、実装開始前に別途確定します。
