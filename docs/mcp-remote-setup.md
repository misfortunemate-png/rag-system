# rag-system リモートセットアップ手順書

作成日: 2026-08-17 ／ 対象: フランのWindowsデスクトップ（M7b-2対応版）

---

## 1. 概要

rag-systemには3種類のアクセス経路がある。

| 経路 | プロトコル | ポート | 対象 |
|---|---|---|---|
| MCP（SSE / Streamable HTTP） | HTTPS | 8443 | claude.ai・ChatGPT・CLIクライアント |
| ブラウザUI（Streamlit） | HTTPS | 10000 | ゲスト・ブラウザ利用者 |
| stdioローカル | 標準入出力 | — | Claude Codeローカル利用 |

---

## 2. 前提

- **フラン**（Windows デスクトップ）でサーバーが起動していること
- **Tailscale**がインストール・ログイン済みであること（ホスト名: `fraine.tail204746.ts.net`）
- `data/auth_tokens.yaml`が作成済みであること（後述）

### 2-1. auth_tokens.yaml のセットアップ

トークン生成:

```
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
```

`data\auth_tokens.yaml.example` を `data\auth_tokens.yaml` にコピーし、トークン値を設定する:

```yaml
tokens:
  - id: "shougo"
    token: "（生成したトークン）"

  - id: "claude-ai"
    token: "（生成したトークン）"

  - id: "guest-demo"
    token: "（生成したトークン）"
    expires: "2026-09-01"
```

- `data/auth_tokens.yaml` は `.gitignore` に登録済み。**絶対にコミットしないこと。**
- `expires` は省略可。設定した場合、その翌日から自動無効化される。

---

## 3. Tailscale Funnel 設定（三ポート構成）

chat-pwaが443を使用中のため、MCP（8443）とゲストUI（10000）を別ポートで公開する。

```
tailscale funnel --bg --https=443 http://127.0.0.1:8787
tailscale funnel --bg --https=8443 http://127.0.0.1:8766
tailscale funnel --bg --https=10000 http://127.0.0.1:8501
```

設定確認:

```
tailscale serve status
```

出力に3ポートすべて `(Funnel on)` が表示されれば正常。

**注意:** `tailscale serve` と `tailscale funnel` を同一ポートに混在させると競合する。`funnel` コマンド一発で設定すること。

---

## 4. サーバー起動

### 4-1. MCPサーバー

```
.\start-mcp-remote.bat
```

または:

```
.\.venv\Scripts\python.exe -m src.mcp_server --transport http
```

### 4-2. Streamlit（ゲストUI）

```
.\start.bat
```

または:

```
.\.venv\Scripts\python.exe -m streamlit run app.py --server.port 8501
```

---

## 5. MCP接続手順 — claude.ai

1. claude.ai にログインする
2. 画面右上のアカウントアイコン → **設定** → **コネクタ** を開く
3. **コネクタを追加** → **カスタム** → URL に以下を入力:

   ```
   https://fraine.tail204746.ts.net:8443/mcp
   ```

4. 保存するとブラウザにアクセストークン入力画面が開く
5. `data/auth_tokens.yaml` に登録したトークン文字列を入力 → 接続完了

モバイルアプリでも同じアカウントのコネクタが自動で使える（追加設定不要）。

---

## 6. MCP接続手順 — ChatGPT

1. 設定 → Apps → Advanced settings → **Developer Mode** を ON にする
2. 設定 → Connectors → **Create** を開く
3. URL に以下を入力:

   ```
   https://fraine.tail204746.ts.net:8443/mcp
   ```

   （`/sse` でも可）
4. OAuth承認画面でアクセストークンを入力

---

## 7. MCP接続手順 — Antigravity CLI / ローカルクライアント

Bearer トークンをヘッダーに直接設定する:

```
Authorization: Bearer {token}
```

例（curl）:

```
curl -H "Authorization: Bearer {token}" \
  https://fraine.tail204746.ts.net:8443/mcp
```

---

## 8. ブラウザUI（ゲスト向け）

URL:

```
https://fraine.tail204746.ts.net:10000
```

アクセスするとトークン入力画面が表示される。ゲスト用トークンを入力してログイン。

ゲストモードでは以下が非表示（閲覧のみ）:
- モデル・パラメータ設定
- コスト・処理時間の表示
- デバッグ情報

---

## 9. ゲスト招待手順

1. トークン生成:

   ```
   .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

2. `data/auth_tokens.yaml` に追記（IDは `guest-` で始める・`expires` 設定推奨）:

   ```yaml
   - id: "guest-yamada"
     token: "（生成したトークン）"
     expires: "2026-10-01"
   ```

3. サーバーを再起動（設定は起動時に読み込む）

4. ゲストに渡すもの:
   - URL: `https://fraine.tail204746.ts.net:10000`
   - トークン文字列（Slack DM等で安全に共有）

---

## 10. トークン管理

### 追加

`data/auth_tokens.yaml` にエントリを追記してサーバーを再起動する。

### 失効・無効化

`expires` を過去日に設定するか、エントリを削除してサーバーを再起動する。

### ローテーション

1. 新しいトークンを生成する
2. `data/auth_tokens.yaml` の該当エントリの `token` 値を更新する
3. サーバーを再起動する
4. 接続クライアント側のトークンも更新する（claude.aiはコネクタ再登録が必要な場合あり）

---

## 11. トラブルシューティング

| 症状 | 確認事項 |
|---|---|
| 接続できない | Tailscale が起動中か、Funnel が3ポートすべて有効か確認（`tailscale serve status`） |
| 認証失敗 | `data/auth_tokens.yaml` の token 値が正確か、`expires` が未来日か確認 |
| ゲストUIが開かない | `start.bat` が起動済みか（ポート8501）、Funnel 10000番が有効か確認 |
| 日次上限エラー | 翌日まで待つ。緊急時は `.env` の `MCP_DAILY_QUERY_LIMIT` を増やしてサーバー再起動 |
| `daily_limit` エラー（MCP） | 同上 |

---

## セキュリティ仕様（参考）

| 項目 | 設定値 |
|---|---|
| レート制限 | 1 IP あたり 10 リクエスト/分 |
| ブルートフォース検知 | 同一 IP で 1 分以内に 5 回認証失敗 |
| ブルートフォースブロック期間 | 10 分 |
| 認証失敗時の遅延 | 3 秒 |
| 日次実行上限（既定） | 50 回（MCP・Streamlit合算）|
| 入力テキスト打ち切り | 質問文: 2,000字 / correction: 5,000字 |
