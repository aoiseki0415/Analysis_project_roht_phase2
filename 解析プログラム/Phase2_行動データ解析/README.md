# Phase 2：行動データ解析

行動データ解析のPythonスクリプトを配置します。命名形式は `Phase2_No<番号>_<内容>.py` です。

成果物は同じNoを使って指定OneDriveへ保存します。No1・No2ではローカルデスクトップの `解析に必要なデータたち/` へ何も保存しません。

## 実行状態

No1・No2は、2026年10月1日に解析対象40被験者ペアへ同一の確定Pythonスクリプトを適用して完了しました。指定OneDrive成果物とNotion結果記録も確認済みです。以後は、合意済みの仕様変更または成果物不具合がない限り、正常完了した解析を再実行しません。

## No1：RTの試行進行解析

現行仕様の正本は [Phase 2 行動データ解析仕様](../../docs/Phase2_行動データ解析仕様.md) です。実装前・実行前に必ず確認します。

- 入力は生の `*_blockN_results.csv` とする
- RTは非Sys列から `KeyPress(ms) - TiltOnset(ms)` で再計算する
- 各セット320刺激試行・320 RTを検証する。ミスタッチを含むCSV総行数とは区別する
- EEG欠損セットは個人解析では該当セッション側だけ全320試行をNaN化する。対象はID 109 Set 1、ID 120 Set 6、ID 135 Set 2、ID 225 Set 4
- EEG欠損セットをNaN化した後、200 ms未満のRTだけを予期反応として除外しNaN化する。200 ms以上には上限除外を設けず、長いRTも注意の逸脱（lapse）を捉える情報として保持する
- 各セットを独立に、30試行幅の等重み単純移動平均で320点を出力する
- Trial `i` は原則 `i-15`〜`i+14` を使い、端点とNaNでは利用可能な有限RTだけを算術平均し、セット境界を越えない
- 分割記録のあるID 109、120、135、225も個人別解析を行い、各セットで重複のない320刺激試行を確認する。重複は二重計上せず、欠損補間はしない
- Google Driveの匿名共有タブで、被験者の2セッションID、製品群、目薬ありの実施回を実行前に確認し、100番台／200番台から条件を推測しない
- 同じPythonコード内のループで全被験者を処理し、被験者ごとにコードを複製・変更しない
- Cキューブ群とVロートプレミアム群を分け、それぞれで目薬あり条件とコントロールを被験者内比較する
- FigureはArial、英語表記とし、Set 1〜6を一つの横軸へ連結する。セット境界をグレー点線、セット名を図内上部へ示し、縦軸は0 msから開始する
- 縦軸上限は移動平均の最大値がおおむね70%位置になるよう100 ms単位で切り上げる。y方向のグリッド線は表示せず、凡例は図本体から離して上側へ配置する
- 横軸はSet 1〜6を累積0〜600で表し、Set 1は0〜100、Set 2は100〜200、以降も同様とする。横軸名は `Experimental Progress, %`、目盛りは0から600まで50刻みとし、数字の個別移動を行わず短い目盛り線を通常どおり表示する。y軸目盛りは0から500 ms刻みとする
- 色はControl `#563A7C`、C Cube `#C84A4A`、V Rohto Premium `#E58A2B` に固定する
- 凡例は `Control` と、製品群に応じた `Eye Drop (C Cube)` または `Eye Drop (V Rohto Premium)` とし、被験者タイトルは付けない
- 出力フォルダ、ファイル名、Notion結果はセッション単独ではなく `ID<1回目>-<2回目>` の被験者ペア単位とする
- 個人別出力とGrand-averageは同じNo1に属する。個人figureは30試行幅とする。Grand-averageは個人ごとに30試行幅または50試行幅で平滑化してから同じセット・同じ進捗位置で被験者間平均し、両窓幅を別PNGで保存する。シェードは平均±SEM（標本SD/√N）とし、条件別に平均・標本SD・SEM・有効人数Nを保存する。欠測値は前詰め・補間しない
- Grand-averageでは、EEG欠損セットを持つ被験者ペアについて、対応するもう一方の条件も同じセットをNaN化してから集計する。個人figureではこの対称化を行わない
- Grand-averageの凡例に変動帯のタイトルを付けない。縦軸はCキューブ群・Vロートプレミアム群とも0〜1800 msに固定する
- 同じNo1内でセット別RT定量化を行う。各被験者・各条件・各セットについて、移動平均値ではなくEEG欠損セットのNaN化と200 ms未満の除外後の試行別RTから、`AllTrials`（Trial 1〜320）と `Last80Trials`（Trial 241〜320）の2種類の算術平均を必ず作成する
- 定量化では製品群ごとにSet 1〜6の独立6パネルを横一列で作り、各パネルの左にEye Drop、右にControlを配置する。バーは被験者間平均、ドットは被験者値、線は同一被験者の条件対応を示す
- EEG欠損セットを持つペアはGrand-averageと同様に両条件の同じセットをNaNとし、そのセットのドット・接続線・平均から除外する
- 定量化の縦軸は6パネル共通の `Reaction Time (ms)` とし、数字を全パネルに表示する。バーは中央付近（中心-0.32／0.32、幅0.42）、横軸範囲は-0.90〜0.90、ドットサイズは150とし、左右端へ余白を取る。横軸の条件名は22 pt、括弧内の目薬名だけ18 ptとする。Set名は縦軸上限より内側へ置き、Arialと既存No1の固定色を用いる。推測統計は未実施とする

実行スクリプトは `Phase2_No1_ReactionTime.py` です。被験者対応はコードへ埋め込まず、Googleスプレッドシートで確認した対応を次のいずれかで渡します。

- 1名または少人数：`--participant 101:201:101:VRohtoPremium` のように、`1回目ID:2回目ID:目薬ありID:製品群` を指定する
- 全被験者：`first_session_id,second_session_id,drops_session_id,product` の4列を持つ非公開manifest CSVを `--manifest` で指定する

どちらも同じコード内のループを通り、被験者別にコードを変更しません。EEG欠損セット対応は全員共通スクリプト内の確定表から自動適用します。標準偏差はMATLAB `std` と同じ標本標準偏差（`ddof=1`）です。`Individual/` は全被験者のPNGだけを直下に並べ、`GrandAverage/` と `SetMeanQuantification/` もPNGだけを置きます。補助CSVはNo1直下の `Sub/tables/`、実行要約JSONは `Sub/logs/` へ分離します。試行別の `RT_TrialData.csv` は保存しません。

Grand-averageを作成するときは、対象者を確定したmanifestを指定し、同じコマンドへ `--grand-average --skip-invalid-participants` を追加します。製品群ごとの `GrandAverage/` へ30試行幅・50試行幅のPNG、`Sub/tables/GrandAverage/` へ平均・SD・SEM・NのCSV、`Sub/logs/GrandAverage/` へ実行要約JSONを保存します。必要試行を確定できないペアはペア全体を除外し、No1の `Sub/logs/` にあるバッチ実行要約JSONへ理由を残して他のペアを継続します。

Grand-averageだけを再出力するときは `--grand-average-only --skip-invalid-participants` を使用します。このモードでは個人figure、個人QC、セット別定量化、通常バッチ要約を変更しません。

セット別RT定量化だけを実行するときは、対象者を確定したmanifestを指定し、`--set-mean-quantification-only --skip-invalid-participants` を使用します。この実行は試行別RTの再計算、EEG欠損セットNaN化、200 ms未満の除外を再現して定量値を作り、既存の `Individual/`、`GrandAverage/`、個人QC、通常バッチ要約を変更しません。製品群ごとの `SetMeanQuantification/` 直下へAllTrials・Last80TrialsのPNG、`Sub/tables/SetMeanQuantification/` へ補助CSV、`Sub/logs/SetMeanQuantification/` へ実行要約JSONを保存します。

## No2

ミスタッチ解析の確定仕様は [Phase 2 行動データ解析仕様](../../docs/Phase2_行動データ解析仕様.md) の「解析2（No2）」を正本とします。実装前・実行前に必ず確認します。

- 入力は生の `*_blockN_results.csv` とし、非Sys列の `KeyPress(ms)` を使用する
- 基本は `ResponseType = mistouch` の1行を1回とする
- 他イベントを挟まない隣接mistouchは、間隔が50 ms以下なら同じ操作として1回にまとめる
- mistouch間にcorrectがちょうど1行あり、mistouch間が100 ms以下かつcorrect RTが50 ms以下なら、3行全体を1回にまとめる
- No1のRT 200 ms未満除外はNo2へ適用せず、`correct` をRTの短さだけでmistouchへ再分類しない。50 ms以下のcorrectは、上記の連続押し例外を判定する材料としてだけ使用する
- 50 msは、全17,796隣接間隔中17,107件（96.1%）が50 ms以内だった実測結果に基づく
- correctを挟む例外規則は、実測453例がすべてcorrect 1行、RT 0〜48 msだったことに基づく
- 上記以外は別のミスタッチとし、セット境界・ファイル境界をまたいで結合しない
- 元mistouch行数、確定回数、各規則での結合件数、時刻異常をセット別に記録する
- Cキューブ群とVロートプレミアム群を分け、各群内で同一被験者の目薬あり条件とコントロールを比較する
- FigureはNo1セット別RT定量化と同じ6パネルの対応あり構成とし、縦軸を `Mistouch (count)` とする
- No2の固定色はNo1より暗くし、Control `#402B5D`、C Cube `#963838`、Vロートプレミアム `#AC6820` とする
- 推測統計は実施しない。Phase 1でEEG欠損と確定した4セットは、No1の群集計と同様に被験者内対応を保つため両条件とも同じSetをNaNとし、ドット・接続線・平均から除外する
- 主解析ではID132-232のCキューブ目薬ありSet 1（375回）を含める。追加の感度分析だけ、ID132-232のSet 1を目薬あり・Controlの両条件ともNaN化し、Set 2〜6は変更しない
- Cキューブ群は主解析Figureに加えて感度分析Figure・Set集計CSV・実行要約JSONを別名で保存する。Vロートプレミアム群には適用せず、主解析成果物を上書きしない

実行スクリプトは `Phase2_No2_Mistouch.py`、出力先は指定OneDriveの `Phase2_行動データ解析/No2_Mistouch/` です。`CCube/`・`VRohtoPremium/` にはPNGだけを置き、補助CSVと製品群別JSONは `Sub/` 直下へまとめます。全体バッチ要約JSONはNo2直下に保存します。非公開manifestを入力し、全被験者を同一コードのループで処理します。
