# Phase 3：瞬き解析

瞬き解析のPythonスクリプトを配置します。命名形式は `Phase3_No<番号>_<内容>.py` です。

現行の確定仕様は [Phase 3 瞬き解析仕様](../../docs/Phase3_瞬き解析仕様.md) です。実装・実行前に必ず確認します。

## No1：瞬き検出・Blink Rate解析

- 入力はPhase 1のセット別 `IDxxx_SetN_blink_signal.h5`
- 主解析信号は `Fp1_Fp2_mean`、Fp1・Fp2単独はセット別検出数の補助QCのみ
- 検出用フィルタは1–10 Hz、ピーク検出は `scipy.signal.find_peaks`
- Peak height基準は設けず、同一セッションの使用可能な全セットからprominenceの中央値・MADを求め、`中央値 + 3 × 1.4826 × MAD`を全セットへ共通適用
- minimum peak distanceは設定しない。パイロットHTMLで多重検出を確認する
- 検出確認HTMLはセッションIDごとにMAD方式の1ファイルを作る
- 全候補prominenceの分布とMAD閾値線を、通常の線形軸のPNGとしてセッションIDごとに作る
- Blink Rate時間変化は60秒中心化窓、1秒刻み、端点は実際の窓長で補正する。さらにセット内だけで15秒中心化単純移動平均を適用し、その後0〜600へ変換する
- セット別定量値は検出総数をセット実時間（分）で割る。移動窓値の時間平均は使用しない
- Cキューブ群とVロートプレミアム群を分け、各群でEye Drop対Controlを被験者内比較
- 個人時間変化、製品群別Grand-average、6パネルセット別定量化を同じNo1で出力
- 欠測セットは補完しない。ID 109 Set 1、ID 120 Set 6、ID 135 Set 2、ID 225 Set 4を欠測として扱う
- Phase 3専用色はControl `#4B5563`、C Cube `#21867A`、V Rohto Premium `#3268A8`
- 指定OneDriveの `Phase3_瞬き解析/No1_BlinkRate/` で、製品群ごとに `Individual/`、`GrandAverage/`、`SetQuantification/`、`HTML/`、`ProminenceDistribution/` を置き、被験者別サブフォルダを作らない。表・ログはNo1直下の `Sub/` へ分離する
- Phase 3ではローカルデスクトップへ新しい中間データを保存しない
- Notionの結果表へID・Set別の平均信号／Fp1／Fp2検出数、セット時間、Blink Rate、閾値、欠測・備考を記録

実行スクリプトは `Phase3_No1_BlinkRate.py` です。被験者ペアは、条件表で確認した1回目ID・2回目ID・目薬ありID・製品を明示します。

```bash
MPLCONFIGDIR=/tmp/mplconfig-roht .venv/bin/python \
  '解析プログラム/Phase3_瞬き解析/Phase3_No1_BlinkRate.py' \
  --participant '101:201:101:VRohtoPremium'
```

複数被験者は `--participant` を繰り返すか、`first_session_id`、`second_session_id`、`drops_session_id`、`product` の4列を持つ非公開manifestを `--manifest` で指定します。ID番号帯から条件を推測しません。

## 実装・実行の完了条件

1. ルートREADME、運用ルール、解析上の注意事項、Phase 3仕様、NotionのPhase 3ページを確認する
2. 全対象を同一コードと固定パラメータのループで処理する
3. パイロットIDで入力、検出、欠測、HTML操作、figure、CSV・JSON、Notion記録を検証する
4. OneDrive成果物とNotionの読み戻しまで確認する
5. 許可済みの通常工程では利用者承認を求めない
