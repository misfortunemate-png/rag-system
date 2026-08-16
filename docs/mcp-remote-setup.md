# MCP Remote セットアップ手順書（Tailscale Funnel + claude.ai）

作成日: 2026-08-16 ／ 対象: フランのWindowsデスクトップ

## 概要

`mcp_server.py --transport sse` でSSE HTTPサーバーを起動し、Tailscale Funnelで公開、claude.aiのカスタムコネクタから接続する。

---

## 1. auth_tokens.yaml の作成

### 1-1. トークン生成

ターミナルで以下を実行し、各IDに1つずつトークンを生成する:

```
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
```

3回実行して3つのトークン文字列を控えておく。

### 1-2. ファイル作成

`data\auth_tokens.yaml.example` を `data\auth_tokens.yaml` にコピーし、トークン値を置き換える:

```yaml
tokens:
  - id: "shougo"
    token: "（1-1で生成したトークン1）"

  - id: "claude-ai"
    token: "（1-1で生成したトークン2）"

  - id: "guest-demo"
    token: "（1-1で生成したトークン3）"
    expires: "2026-09-01"
```

- `data/auth_tokens.yaml` は `.gitignore` に登録済み。**絶対にコミットしないこと。**
- `expires` フィールドは省略可。設定した場合、その日を過ぎると自動で無効化される。

---

## 2. start-mcp-remote.bat の実行

プロジェクトルートで:

```
.\start-mcp-remote.bat
```

成功すると以下のような出力が表示される:

```
[rag-system MCP] SSEモードで起動します
[rag-system MCP] ポート         : 8766
[rag-system MCP] SSEエンドポイント: http://0.0.0.0:8766/sse
[rag-system MCP] 有効トークンID  : ['shougo', 'claude-ai', 'guest-demo']
[rag-system MCP] Tailscale Funnel: tailscale funnel 8766
```

---

## 3. Tailscale Funnel の有効化

別のターミナルで:

```
tailscale funnel 8766
```

公開URLが表示される（例）:

```
https://fraine.tail204746.ts.net:8766
```

---

## 4. claude.ai カスタムコネクタの追加手順

1. **claude.ai** にログインする
2. 画面右上のアカウントアイコン → **設定** → **コネクタ** を開く
3. **コネクタを追加** → **カスタム** → **Web（HTTP SSE）** を選択
4. **URL** に以下を入力:
   ```
   https://（tailscaleで表示されたドメイン）:8766/sse
   ```
5. **Request Headers** に以下を追加:
   ```
   Authorization: Bearer （claude-ai用のトークン文字列）
   ```
6. **保存** して接続テストを実行する

### モバイルアプリ

claude.aiで設定したコネクタは、**同じアカウントでログインしたモバイルアプリにも自動的に反映される**。追加設定は不要。

---

## 5. ゲストへのトークン発行と期限管理

1. `data/auth_tokens.yaml` に新しいエントリを追加する:
   ```yaml
   - id: "guest-suzuki"
     token: "（新しく生成したトークン）"
     expires: "2026-10-01"    # 期限を明示的に設定する
   ```
2. `.\start-mcp-remote.bat` を再起動する（設定は起動時に読み込む）
3. ゲストにトークン文字列を安全な方法で共有する（Slackのダイレクトメッセージ等）

期限切れのトークンはサーバー起動時に自動的に無効化される（yaml から削除する必要はない）。

---

## 6. トークンローテーション手順

1. 新しいトークンを生成する（`secrets.token_urlsafe(32)`）
2. `data/auth_tokens.yaml` の該当エントリの `token` 値を新しいものに更新する
3. サーバーを再起動する（`.\start-mcp-remote.bat`）
4. **claude.ai のコネクタ設定** → Request Headers の `Authorization` 値を新しいトークンに更新する

---

## セキュリティ仕様（参考）

| 項目 | 設定値 |
|---|---|
| レート制限 | 1 IP あたり 10 リクエスト/分 |
| ブルートフォース検知 | 同一 IP で 1 分以内に 5 回認証失敗 |
| ブルートフォースブロック期間 | 10 分 |
| 認証失敗時の遅延 | 3 秒 |
| リクエストボディサイズ上限 | 1 MB |
| 入力テキスト打ち切り | 質問文: 2,000字 / correction: 5,000字 / evidence: 2,000字 / query: 500字 |
