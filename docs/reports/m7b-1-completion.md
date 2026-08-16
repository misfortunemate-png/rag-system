# M7b-1 完了報告

提出日: 2026-08-17 ／ PG: フラン

## 実施内容

指示書 `docs/instructions/m7b-1-instructions.md` に従い W-1・W-2 を実施した。

### W-1: Streamable HTTPトランスポートの追加

`mcp.streamable_http_app()` が利用可能であることを確認し、`/mcp` パスでマウントした。
SSE (`/sse`) と Streamable HTTP (`/mcp`) を同一ポート・同一 ASGI アプリで同居させた。

**実装の要点:**

- `_OAuthSSEDispatcher` に `_handle_lifespan()` メソッドを追加した。`streamable_http_app()` が返す Starlette アプリは anyio の task group を lifespan で初期化する必要があるため、SSE アプリと Streamable HTTP アプリの両方へ lifespan イベントをファンアウトする実装とした。
- `--transport sse` を `--transport http` にリネームした（SSE と Streamable HTTP の両方を含むため）。
- `start-mcp-remote.bat` の起動引数を更新した。
- 起動ログに `/sse (SSE)` と `/mcp (Streamable HTTP)` の両エンドポイントを表示する。

### W-2: OAuth承認画面方式への改修

D-1（実質無認証問題）を解消した。

**変更点:**

| エンドポイント | 変更前 | 変更後 |
|---|---|---|
| `/.well-known/...` | `token_endpoint_auth_methods_supported: ["client_secret_post"]` | `["none"]` |
| `POST /register` | client_secret（claude-ai固定）を返す | client_secretを返さない |
| `GET /authorize` | 自動承認・即リダイレクト | HTML承認画面を返す |
| `POST /authorize` | — | トークン検証・認可コード発行（token_id紐付け） |
| `POST /token` | `claude-ai` 固定トークンを返す | code_info["token_id"] から対応トークンを返す |

`_oauth_authorize_html()` ヘルパーを追加。承認画面にはトークン入力欄・隠しフィールド（PKCE含む）を含む。無効トークン投入時はブルートフォース保護（sleep(3) + _bf_failures記録）を適用する。

## テスト結果

```
=== 1. メタデータ ===                          PASS
=== 2. /register（client_secret なし）===      PASS
=== 3. GET /authorize → HTML承認画面 ===       PASS
=== 4. POST /authorize 無効トークン+3s遅延 === PASS
=== 5. POST /authorize 有効トークン → 302 === PASS
=== 6. POST /token → access_token ===          PASS
=== 7. SSE接続（Bearer）===                    PASS
=== 8. Streamable HTTP /mcp（Bearer）===       PASS
=== 9. stdio 回帰（--transport {stdio,http}）== PASS
```

全9項目 PASS。

## 実機系（発注者依頼）

以下は発注者環境での確認が必要:

1. `tailscale funnel --bg --https=8443 http://127.0.0.1:8766` 実行後、Pixel 10 モバイル回線から `https://fraine.tail204746.ts.net:8443/.well-known/oauth-authorization-server` アクセス → JSON返却
2. ブラウザから `/authorize?...` にアクセスして承認画面表示 → トークン入力で認可
3. claude.ai カスタムコネクタ: URL `https://fraine.tail204746.ts.net:8443/mcp` （または `/sse`）で接続

## 変更ファイル一覧

| ファイル | 変更内容 |
|---|---|
| `src/mcp_server.py` | W-1・W-2 全実装 |
| `start-mcp-remote.bat` | `--transport sse` → `--transport http` |
| `CLAUDE.md` | M7b-1 への更新 |
| `_STATUS.md` | M7b-1 状態へ更新 |
| `docs/reports/m7b-1-completion.md` | 本報告書 |

---

確認をお願いします。
