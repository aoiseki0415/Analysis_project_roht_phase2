"""作業ディレクトリに依存せず、アプリの配置先を返す。"""

import os


def application_root():
    """データや外部設定を置く、ユーザーから見えるアプリフォルダを返す。"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
