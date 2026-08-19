# hotfix-3 実施報告書（最終版）

文書種別: 報告書
作成日: 2026-08-19 ／ 報告者: PG ／ 対応指示書: docs/instructions/hotfix-3-instructions.md

---

## 1. 実装内容の要約

MCPサーバーのsrcインポート障害（`No module named 'src'`）を **H-Aの1箇所のみ**で修正した。

**H-A: src/mcp_server.py — sys.pathブートストラップ挿入（適用）**

`os.chdir(_PROJECT_ROOT)` の直後に3行を追加:

```python
import sys
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
```

**H-B: start-mcp-remote.bat — モジュール実行化（除外）**

指示書ではスクリプト直接実行を `-m src.mcp_server` に変更する内容だったが、**OAuth認可障害を引き起こしたため除外**。H-Aが同じインポート問題を解決しており、H-Bは不要。

---

## 2. 障害経緯

| 時刻（JST） | 事象 |
|---|---|
| 19:41 | H-A + H-B を適用しサーバー再起動 |
| 19:46 | claude.aiから `auth_success`（最後の成功） |
| 19:53〜20:24 | `oauth_register → auth_failure` ループ。`oauth_authorize` が一度も成功せず |
| 20:22 | H-A + H-B を `git revert` で全切り戻し・サーバー再起動 |
| 20:25 | `oauth_authorize → oauth_token_issued → auth_success` 即座に完走 |
| 20:37 | H-Aのみ再適用・サーバー再起動 |
| 20:37〜 | claude.aiから正常接続を確認 |

---

## 3. 原因分析

`python -m src.mcp_server`（H-B）は、Pythonの仕様として `src/__init__.py` をサーバー本体より先に実行する。これがOAuthミドルウェアの初期化に干渉し、`/authorize` エンドポイントが認可を完了できない状態を引き起こした。

`python src\mcp_server.py`（直接実行）では `__init__.py` は実行されないため、この問題は発生しない。H-Aの `sys.path.insert` でプロジェクトルートを明示的に追加すれば、直接実行でも `from src.agent import run` 等の遅延インポートは正常に解決される。

**結論: H-Bは不要。H-A単独でインポート障害は解決済み。**

---

## 4. 完了条件の充足状況

| 条件 | 状況 |
|---|---|
| srcインポート障害の修正 | ✅ H-Aで解決 |
| PG自己テスト（stdioモード・list_documents応答） | ✅ |
| PG自己テスト（httpモード・インポートエラーなし） | ✅ |
| 発注者実機確認（claude.ai接続） | ✅ 発注者確認済み |
| サーバー再起動・コミット・プッシュ | ✅ |
| _STATUS.md更新 | ✅ |

---

## 5. コミット履歴

| コミット | 内容 |
|---|---|
| `c0f8365` | H-A + H-B 適用（初回） |
| `c5bf9fa` | `c0f8365` の revert（OAuth障害のため全切り戻し） |
| `cac8314` | H-Aのみ再適用（最終版） |
| `4327a6c` | _STATUS.md更新 |

---

## 6. 教訓

`start-mcp-remote.bat` を `-m` 実行に変更してはならない。`src/__init__.py` の実行がOAuth認可フローを破壊する。今後 `src/` 配下のインポート問題が発生した場合は、`sys.path` 操作で対処すること。
