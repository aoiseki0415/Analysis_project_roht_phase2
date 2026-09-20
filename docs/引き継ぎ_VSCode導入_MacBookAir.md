# MacBook AirへのVS Code導入引き継ぎ

## 1. この資料の目的

別のCodexプロジェクトから、**MacBook AirへVisual Studio Code（VS Code）だけを安全に導入し、PythonスクリプトとJupyter Notebookを扱うための拡張機能まで準備する**ための引き継ぎ資料です。

対象デバイスはMacBook Airです。現在の解析環境があるMac miniへインストールする手順ではありません。

## 2. 今回の作業範囲

実施することは次の4点だけです。

1. MacBook AirのCPUアーキテクチャと既存インストール状況を確認する
2. Microsoft公式配布の安定版VS Codeを導入する
3. `code` コマンドを使用可能にする
4. Microsoft公式のPython・Pylance・Jupyter拡張機能を導入し、状態を確認する

次は今回の作業範囲に含めません。

- Python本体、uv、Conda、Homebrew、解析ライブラリの導入
- Gitリポジトリのclone、pull、編集、commit、push
- ロート案件の生データ、解析結果、設定ファイルのコピーや同期
- OneDrive、Google Drive、Notionへの接続
- GitHub、Microsoft、Settings Syncへのサインイン
- VS CodeからのPython仮想環境作成

これらが必要な場合は、MacBook Air側の別プロジェクトで対象範囲と保存先を確認してから、別工程として実施します。

## 3. 実行前の確認

MacBook Airのターミナルで、次を確認します。

```bash
sw_vers -productVersion
uname -m
test -d "/Applications/Visual Studio Code.app" && echo "VS Code installed" || echo "VS Code not installed"
command -v code || true
```

`uname -m` の結果は、通常次のどちらかです。

- `arm64`：Apple Silicon版を選択
- `x86_64`：Intel版を選択

既にVS Codeがある場合は重複インストールせず、版と動作状況を確認します。既存設定や拡張機能を削除・初期化しません。

## 4. VS Code本体の導入

1. ブラウザでMicrosoft公式のダウンロードページ（<https://code.visualstudio.com/Download>）を開く。
2. `uname -m` の結果に合うmacOS安定版を選ぶ。判断できない場合はUniversal版を使用できる。
3. ダウンロードした公式インストーラーを開く。
4. `Visual Studio Code.app` を `/Applications` へ移動する。
5. `/Applications/Visual Studio Code.app` を起動する。
6. macOSが公式配布元から取得したアプリであることを示す確認を出した場合は、内容を確認して開く。

カレンダー、連絡先、写真など、この作業に不要なmacOS権限をVS Codeへ付与しません。Settings Syncや各種アカウントへのサインインも行いません。

## 5. `code` コマンドの有効化

VS Codeを起動し、次を実行します。

1. `⌘ + Shift + P` でCommand Paletteを開く
2. `Shell Command: Install 'code' command in PATH` を検索して実行する
3. ターミナルをいったん閉じ、新しく開く
4. 次を実行する

```bash
code --version
```

バージョン番号が表示されれば完了です。シェル設定ファイルを手作業で変更するのは、公式コマンドで設定できなかった場合に限ります。

## 6. Python・Jupyter拡張機能の導入

VS CodeのExtensions画面を `⇧ + ⌘ + X` で開き、発行元がMicrosoftであることを確認して次を導入します。

| 用途 | 拡張機能 | Extension ID |
|---|---|---|
| Pythonスクリプトの実行・デバッグ・テスト | Python | `ms-python.python` |
| コード補完・型情報・エラー表示 | Pylance | `ms-python.vscode-pylance` |
| Jupyter Notebook | Jupyter | `ms-toolsai.jupyter` |

`code` コマンドが使える場合は、次でも導入できます。

```bash
code --install-extension ms-python.python
code --install-extension ms-python.vscode-pylance
code --install-extension ms-toolsai.jupyter
```

Python拡張機能がPylanceなどを依存関係として自動導入する場合があります。既に導入済みと表示された拡張機能は、重複して追加しません。Microsoft以外が公開している同名・類似名の拡張機能は導入しません。

## 7. 導入確認

次を実行します。

```bash
code --version
code --list-extensions --show-versions
```

出力に少なくとも次が含まれることを確認します。

```text
ms-python.python
ms-python.vscode-pylance
ms-toolsai.jupyter
```

続いてVS Codeを開き、次を確認します。

1. 新しいウィンドウが正常に開く
2. Extensions画面で3拡張機能がEnabledになっている
3. `⌘ + Shift + P` で `Python: Select Interpreter` が検索結果に現れる
4. Command PaletteでJupyter関連コマンドが検索結果に現れる

Python本体は今回導入しないため、Python interpreterが未検出でも、この工程では異常ではありません。新しいPython環境を作成する案内が表示されても、今回の作業では実行しません。

## 8. 完了条件

次をすべて満たしたら完了です。

- MacBook Airの `/Applications` にVS Code安定版が1つ存在する
- VS Codeが起動する
- `code --version` が成功する
- Python、Pylance、JupyterのMicrosoft公式拡張機能が有効である
- Python本体、解析環境、Gitリポジトリ、案件データには変更を加えていない

## 9. 別Codexプロジェクトからの完了報告

実行後は、次の形式で報告します。

```text
対象デバイス：MacBook Air
macOS：<確認したバージョン>
CPU：<arm64 または x86_64>
VS Code：<バージョン>
codeコマンド：使用可能 / 未完了
Python拡張機能：<バージョン>
Pylance拡張機能：<バージョン>
Jupyter拡張機能：<バージョン>
今回変更していないもの：Python本体、解析環境、Git、案件データ
問題・未完了事項：<なければ「なし」>
```

## 10. 公式参照先

- VS Code for macOS：<https://code.visualstudio.com/docs/setup/mac>
- VS Code拡張機能：<https://code.visualstudio.com/docs/configure/extensions/extension-marketplace>
- VS Code CLI：<https://code.visualstudio.com/docs/configure/command-line>
- Python拡張機能：<https://marketplace.visualstudio.com/items?itemName=ms-python.python>
