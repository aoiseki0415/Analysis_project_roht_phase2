# Phase 1 脳波前処理仕様（確定版）

この文書はPhase 1本番処理の正本です。本文には採用済みの仕様だけを記載します。過去の3パターン比較とID101追加IC検証は、歴史資料 `Phase1_区間・チャンネル除去パラメータ比較報告書.md` だけに残します。

## 1. 目的

各セッションの連続EEGを前処理し、最後に1セットを1保存単位として、次の2種類を作成します。

- Eye成分除去後の脳活動解析用EEG
- 除去したEye成分のセンサー投影から得る瞬き解析用信号

フィルタ、時刻同期、トレンド除去は前回MATLAB実装 `ERP_and_Power_analysis.m` と同じ考え方を用い、ICAの前処理とEye成分選択を自動化します。

## 2. 入力・同期・単位

- EEG CSVは1行目が記録メタデータ、2行目が列名です。
- EEGは32チャンネル、256 Hz、CSV上の電位単位はµVです。MNEへ渡すときだけVへ変換します。
- EEGの同期はUnix秒の`OriginalTimestamp`を`x1000`してmsに揃えます。
- セット境界は`events.csv`の`block_start` / `block_end`と`SysUnixTime(ms)`を使います。
- EEGと対応させる行動時刻は`TiltOnsetSys(ms)` / `KeyPressSys(ms)`を使います。行動RT自体は非Sys列から算出します。
- JSONとintervalMarkerは必須入力にしません。
- IDごとにヘッダ、チャンネル名・数、256 Hz、電位単位、時刻の単調増加、非数、セット境界を監査します。

セット開始・終了サンプルは入力監査時に確定しますが、波形を物理的にセット分割するのはICA適用後です。

## 3. 分割記録

取得区間の空白は補間せず、Partごとに独立してフィルタ・detrendを行います。使用可能なサンプルを論理的にまとめてIDごと1つのICAを学習し、同じICAモデルを各Partへ別々に適用します。

| ID | 除外セット | 使用セット | 取得区間 |
|---|---:|---|---|
| 109 | 1 | 2～6 | Part2 |
| 120 | 6 | 1～5 | Part1 |
| 135 | 2 | 1 / 3～6 | Part1 / Part2 |
| 225 | 4 | 1～3 / 5～6 | Part1 / Part2 |

上表の4 IDは各自5セットを出力します。対応はコード定数と回帰テストで固定します。

## 4. フィルタとトレンド除去

Partごとに次の順で実行します。

1. 49～51 Hz帯域阻止
2. 1～100 Hzバンドパス
3. チャンネルごとの線形detrend

ゼロ位相の`sosfiltfilt`を用い、100 Hzの独立ノッチと共通平均参照は追加しません。フィルタ・detrend後の中間EEGと専用figureは保存しません。

## 5. ICA学習用チャンネル除外

最終EEGのチャンネルは削除しません。次の自動判定で該当したチャンネルだけをICA学習・適用行列から除外します。

| 検出 | 候補基準 | 自動除外基準 |
|---|---|---|
| 連続0・完全flatline | 5秒以上 | 候補になった時点で除外 |
| 線雑音 | 4 robust SD超 | 6 robust SD以上 |
| RANSAC | 相関0.75未満が記録の40%以上 | 記録の60%以上 |
| 複数理由 | 上記3種の候補 | 2種類以上に該当 |

RANSACは45 Hz以下のコピー、5秒epoch、50回再標本化、最低25%のチャンネルからの再構成で判定します。除外は事前承認を求めず、除外ch名と理由を記録します。

ICA適用後は、除外chの列にフィルタ・detrend後信号を戻し、元の32ch順・32列で保存します。削除もNaN化もしません。`ica_channel_excluded_mask`、チャンネル名、理由を脳活動・瞬き解析用データの両方へ付帯します。

## 6. ICA学習用区間除外

不良区間はICA学習用コピーからだけ実際に除外し、補間・波形置換をしません。最終保存用EEGは短縮しません。

| 項目 | 確定値 |
|---|---:|
| ASR BurstCriterion相当 | 20 |
| ASR検出窓 | 0.5秒、50%オーバーラップ |
| ASR基準データ | 全chのlog RMS robust zが−3.5～3.5の0.5秒窓。基準窓が `max(20窓, 全窓の5%)` 未満なら、逸脱の小さい順に `max(20窓, 全窓の10%)` を採用 |
| WindowCriterion | 不良ch比率25%超 |
| 最終窓 | 1.0秒、66%オーバーラップ |
| WindowCriterionTolerances | `[-3.5, 7]` |
| 絶対振幅 | 400 µV以上＋前後1秒 |

ASRはEEGLAB `clean_rawdata`の考え方を参考にした検出であり、ASR波形再構成そのものではありません。検出した窓と絶対振幅区間を統合します。絶対振幅400 µVは現時点の採用値で、利用者から明示的な変更指示があった場合だけ改訂します。

WindowCriterionの不良ch比率は、ICA学習から除外したchを除く残存chを分母にします。各1秒窓でlog RMS robust zが−3.5未満または7超のchを不良と数え、その割合が25%を超えた窓を除外します。32chがすべて残る場合は9ch以上で除外です。

保存する区間情報は開始時刻、終了時刻、理由、影響チャンネル数です。影響チャンネル数は「その区間の異常判定に寄与したch数」であり、除外ch数ではありません。

## 7. ICAとEye成分除去

- extended Infomax
- 乱数シード：97
- 最大反復：1000
- 停止判定：重み変化量`1e-6`
- 学習率：`0.00065 / log(データランク)`
- ブロックサイズ：`ceil(min(5 * log(学習サンプル数), 0.3 * 学習サンプル数))`
- anneal step：0.98
- 入力：1～100 Hz、detrend後、不良ch・区間除外後のICA学習用EEG
- 共通平均参照：行わない

MNE-ICALabelの7分類確率のうち、`eye blink >= 0.80`のICだけを自動除去します。0個なら除去せず、その事実を記録します。Muscle、Heart、Line noise、Channel noise、Otherは除去しません。`ICA.find_bads_eog()`、Fp1/Fp2相関、左右対称性、ピーク形状は除去判定に追加しません。途中の承認も求めません。

## 8. OneDrive成果物

`Phase1_脳波前処理/No2_AutomatedPreProcessing/IDxxx/`に次を保存します。`Pattern`等の探索用語は付けません。

- 除去ICごとのtopomap、時系列、PSD、ICLabel確率
- `IDxxx_PartN_QC01_BlinkCheck_ICA_before_after.html`：Fp1・Fp2のBefore / After
- `IDxxx_PartN_QC05_ICAExclusionReview_BeforeICA.html`：Before ICA全32ch、除外区間の赤帯、除外chの黄色行と`[ICA除外]`
- セット別のFp1・Fp2・平均の瞬き解析用信号PNG
- ICA学習除外ch、除外区間、ICA収束、除去ICの品質管理表と実行ログ

QC02～QC04のICA前後HTML、10秒PNG、トレンド除去専用figure、瞬き平均波形、バタフライプロットは作成しません。

HTMLは256 Hzの全サンプルを持ち、チャンネル間とID内Part間の初期縦軸を統一します。x/y軸拡大縮小、ドラッグ、左右キー長押し、全体表示、チャンネル切替、カーソル位置の元サンプル値表示を備え、Set境界を縦線で示します。分割記録はPart別にQC01とQC05を出力します。

## 9. 目視QCとNotion記録

保存後・完了確定前に次を実施します。

### 瞬き成分除去精度

- 必ずファイル名が`QC01_BlinkCheck`のHTMLだけを開きます。
- HTMLを開いてから最大3分で、約150～200秒幅の表示窓を重複なく連続的に送り、記録開始から終了までを少なくとも1回高速走査します。
- BeforeのFp1・Fp2の同時刻に現れる約100 ms程度の同期した尖りまたは丘状波形を瞬き候補とします。片側だけの不規則波形やSet境界の巨大変動は瞬きと断定しません。
- Afterで両側から明瞭に消失・抑制されたら正常除去、片側のみまたは部分的なら不完全除去、残存・悪化は未除去とします。
- 全時間走査の所感から、5～10点刻みの0～100点で概算します。精密な自動指標として扱いません。
- 確認後はHTMLタブを必ず閉じます。

### 除去ICの空間的バランス

除去したICごとのtopomap PNGを確認し、Fp1とFp2の寄与を次の3段階で記録します。赤・青の符号ではなく、色の絶対的な濃さと空間分布を見ます。

- `良好`：各ICが概ね左右バランスする、または除去IC全体でFp1寄りとFp2寄りが補完する
- `一部偏り`：一部ICに偏りはあるが、除去IC全体で両側が代表される
- `片側偏重`：除去IC全体がFp1またはFp2の一方に偏る

この評価は事後QCであり、IC除去条件には使いません。

### Notion「ICA処理結果（ID別）」

- ICA学習除外chと理由
- 区間除外の区間数、合計時間、主な理由
- ICA収束、99%振幅とRMSの前後値
- 除去IC番号とEye blink確率
- 瞬き成分除去精度
- 空間的バランスの3段階評価と2文程度の定性所見
- 必要な場合だけ使用Part・SetとOneDrive保存先

長文は書かず、詳細な時刻表とfigureはOneDriveに残します。

## 10. ローカル保存データ

`SandBox_ロート案件（データ）/解析に必要なデータたち/Phase1_脳波前処理/No2_AutomatedPreProcessing/IDxxx/SetN/`へ保存します。

### 脳活動解析用EEG HDF5

- Eye成分除去後のEEG、32ch・256 Hz
- 各行と対応するセット内相対時刻と`OriginalTimestamp`
- ICA学習除外区間maskと注釈
- 32要素の`ica_channel_excluded_mask`、除外ch名、理由
- 対応する`results.csv`の行動データ

ICA除外chはフィルタ・detrend後信号のまま原列に残します。

### 瞬き解析用HDF5

- 除去Eye ICのセンサー投影によるFp1、Fp2、平均の3列、256 Hz
- 各行と対応する相対時刻、`OriginalTimestamp`、区間mask、行動データ
- 同じICA除外ch mask・名・理由

Fp1またはFp2自体がICAから除外された場合、該当瞬き信号列はNaNとし、maskで明示します。

両HDF5で、信号行数と時刻・maskの長さ、チャンネル順、行動データの対応を保存後に検証します。

## 11. 完了条件

Notion「前処理完了確認（ID別）」で次の10項目を確認します。

- データの読み込み
- 入力データの異常有無
- フィルタリング
- トレンド除去
- ICA学習除外chの判定・記録
- ICA学習用区間除外
- ICA
- Eye成分除去
- セット分割
- 保存と読み戻し検証

10項目、瞬き成分除去精度の記録、topomapの空間的バランス評価がすべて完了した場合だけ「完了」とします。

## 12. 再現性と変更管理

- 全IDに同じGit版、確定パラメータ、乱数シード97、色、レイアウト、命名を適用します。
- 正常完了IDを理由なく再処理しません。再処理は実装不具合、出力欠損、合意済み仕様変更に限ります。
- 本番スクリプトは比較プロファイル、追加IC指定、比較ラベル、ローカル保存スキップを受け付けません。
- パラメータ変更時は本書、Notion、コード、回帰テストを同時に更新します。

## 13. 根拠資料

- 前回MATLAB `参考資料（プログラミング関連）/実験初期の解析プログラミング/実験本番_初期解析/ERP_and_Power_analysis.m`
- Google Drive `EEG前処理自動化の実装要件定義書 No 2.pdf`
- [EEGLAB clean_rawdata documentation](https://eeglab.org/plugins/clean_rawdata/Documentation.html)
- [MNE-ICALabel ICLabel API](https://mne.tools/mne-icalabel/stable/generated/api/mne_icalabel.iclabel.iclabel_label_components.html)
- [ICLabel原著論文](https://pubmed.ncbi.nlm.nih.gov/31103785/)

最終更新：2026年9月28日
