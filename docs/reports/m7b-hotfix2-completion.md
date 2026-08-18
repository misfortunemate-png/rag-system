# M7b hotfix-2 完了報告

報告日: 2026-08-18 ／ PG → PM（クリーデ）

## 修正内容

W-1〜W-4をすべて実装しました。確認をお願いします。

### W-1: `/.well-known/oauth-protected-resource` エンドポイント追加（RFC 9728）

- `_oauth_protected_resource` 関数を新設（`resource`, `authorization_servers`, `bearer_methods_supported` を返す）
- `_build_oauth_starlette` のルート一覧に `Route("/.well-known/oauth-protected-resource", ...)` を追加

### W-2: 認証ミドルウェアの401レスポンスに `WWW-Authenticate` ヘッダー追加

`_AuthRateLimitMiddleware._send_error` を修正。

- `status == 401` かつ `_MCP_PUBLIC_URL` が空でない場合のみヘッダーを付与
- ヘッダー値: `Bearer resource_metadata="{MCP_PUBLIC_URL}/.well-known/oauth-protected-resource"`
- 403・429などはヘッダーなし（後方互換）

### W-3: `_OAuthSSEDispatcher._OAUTH_PATHS` に追加

`"/.well-known/oauth-protected-resource"` をfrozensetに追加。認証ミドルウェアをバイパスしてOAuthアプリに直接ルーティング。

### W-4: `docs/mcp-remote-setup.md` のコネクタURL変更

```
変更前: https://fraine.tail204746.ts.net:8443/sse
変更後: https://fraine.tail204746.ts.net:8443/mcp
```

---

## テスト結果

| # | テスト内容 | 結果 |
|---|---|---|
| — | 構文チェック（`ast.parse`） | PASS ✅ |
| — | W-1〜W-3 実装7項目の存在確認 | PASS ✅ |
| — | `_oauth_protected_resource` レスポンス確認（resource / authorization_servers） | PASS ✅ |
| — | 401時の `WWW-Authenticate` ヘッダー値確認 | PASS ✅ |
| — | 403時は `WWW-Authenticate` ヘッダーなしを確認 | PASS ✅ |
| 1 | MCPサーバー再起動 | 発注者依頼 |
| 2 | `curl .../oauth-protected-resource` → JSON確認 | 発注者依頼 |
| 3 | `curl -I .../mcp` → 401 + WWW-Authenticate確認 | 発注者依頼 |
| 4 | claude.aiコネクタ再登録（URL: `/mcp`）→ 承認画面表示 | 発注者依頼 |

---

MCPサーバーの再起動後、claude.aiのカスタムコネクタを削除して `https://fraine.tail204746.ts.net:8443/mcp` で再登録をお願いします。確認をお願いします。
