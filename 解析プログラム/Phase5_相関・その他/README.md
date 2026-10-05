# Phase 5：相関・その他

相関解析など、Phase 1〜4を横断する解析のPythonスクリプトを配置します。命名形式は `Phase5_No<番号>_<内容>.py` です。実装・実行前にルートREADME、運用ルール、解析上の注意事項、Notionの解析ストーリー、該当するPhase 5仕様書を確認します。

## No1：DEQSとRT点眼効果の相関

現行仕様の正本は [Phase 5 No1 DEQS・RT点眼効果相関解析仕様](../../docs/Phase5_No1_DEQS_RT点眼効果相関解析仕様.md) です。

- DEQSは問1〜15の程度得点から `程度得点合計 / 有効回答数 × 25` で0〜100点へ換算し、問16を使用しない
- RTはPhase 2 No1 `AllTrials` のSet 1・Set 6平均RTを使い、Phase 2保存値との完全な対応・数値一致を確認してから解析する
- `Eye Drop Effect = (Control Set6 / Control Set1 - Eye Drop Set6 / Eye Drop Set1) × 100`
- 正値を点眼によってRT増加が抑えられた方向とする
- Cキューブ群とVロートプレミアム群を分け、製品別にDEQSとのPearson相関を算出する
- ID・製品・点眼実施回・条件対応はGoogle Drive匿名被験者リストを正本とし、ID番号から推測しない
- ID109–209はSet 1、ID120–220はSet 6欠測のためEye Drop Effectを算出しない
- Figureは製品別の散布図、最小二乗回帰線、95%信頼帯とし、横軸をDEQS、縦軸をEye Drop Effectとする
- 出力は指定OneDriveの `Phase5_相関・その他/No1_DEQS_RT_EyeDropEffect/` に限定する
- 本解析ではローカルデスクトップの `解析に必要なデータたち/` へ新規中間データを保存しない

実装スクリプトは `Phase5_No1_DEQS_RT_EyeDropEffect.py` です。匿名被験者対応表から作成した非Git管理manifestと、Google Sheetsから確定保存したDEQS得点CSVを入力します。初回実行後はOneDriveの `Sub/tables/No1_DEQS_Scores.csv` が固定スナップショットとなるため、Figureや統計の再生成でGoogle Sheetsを再参照する必要はありません。

実行時にはPhase 2の処理関数を直接再利用して全員分のSet平均RTを再計算し、Phase 2保存済み `AllTrials` 値と `atol=1e-9, rtol=0` で全行照合します。不一致が1件でもあれば相関解析と成果物出力を中止します。
