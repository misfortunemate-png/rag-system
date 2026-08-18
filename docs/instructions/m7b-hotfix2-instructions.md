# M7b hotfix-2 指示書 — RFC 9728 Protected Resource Metadata 対応

文書種別: PG指示書 ／ 作成日: 2026-08-18 ／ 作成者: クリーデ（PM）
対象ファイル: src/mcp_server.py, docs/mcp-remote-setup.md

## 背景

claude.aiカスタムコネクタの接続が③で失敗し続けていた。原因はclaude.aiのOAuth発見フローにある。
claude.aiは以下の順序でOAuth認可サーバーを発見する:

1. `/mcp` に未認証リクエスト → **401 + `WWW-Authenticate: Bearer resource_metadata="<URL>"`** ヘッダーを期待
2. `/.well-known/oauth-protected-resource` を取得 → `authorization_servers` フィールドで認可サーバーURLを発見
3. 認可サーバーの `/.well-known/oauth-authorization-server` を取得
4. `/register`（DCR）→ `/authorize` → `/token`

現在の実装はステップ3以降のみ。ステップ1-2が欠落しているため、claude.aiはDCRに到達すらしない。

## 修正内容（3箇所）

### W-1: `/.well-known/oauth-protected-resource` エンドポイント追加

`_oauth_metadata` 関数の近くに新しい関数を追加する。

```python
async def _oauth_protected_resource(request):
    """GET /.well-known/oauth-protected-resource (RFC 9728)"""
    base = _MCP_PUBLIC_URL
    return JSONResponse({
        "resource": base,
        "authorization_servers": [base],
        "bearer_methods_supported": ["header"],
    })
```

`_build_oauth_app` 内のルート一覧にこのルートを追加する:

```python
Route("/.well-known/oauth-protected-resource", _oauth_protected_resource, methods=["GET"]),
```

### W-2: 認証ミドルウェアの401レスポンスに `WWW-Authenticate` ヘッダー追加

`_AuthRateLimitMiddleware._send_error` メソッド（L616付近）を修正する。
status が 401 のとき、レスポンスヘッダーに以下を追加する:

```python
(b"www-authenticate", f'Bearer resource_metadata="{_MCP_PUBLIC_URL}/.well-known/oauth-protected-resource"'.encode()),
```

実装方法: `_send_error` に status を判定するロジックを追加するか、
あるいは 401 専用のヘッダーリストを _send_error の引数で受け取る形でもよい。
`_MCP_PUBLIC_URL` が空文字列の場合（stdioモード）はヘッダーを付けない。

### W-3: `_OAUTH_PATHS` への追加

`_OAuthSSEDispatcher._OAUTH_PATHS` frozenset（L910付近）に以下を追加する:

```
"/.well-known/oauth-protected-resource",
```

これにより、このパスも認証ミドルウェアをバイパスしてOAuthアプリに直接ルーティングされる。

注: L928の `path.startswith("/.well-known/")` で既にキャッチされるが、
明示的に frozenset にも含めて意図を明確にする。

## 手順書の修正（W-4）

`docs/mcp-remote-setup.md` の §5（claude.ai接続手順）で、コネクタURLを以下に変更する:

```
変更前: https://fraine.tail204746.ts.net:8443/sse
変更後: https://fraine.tail204746.ts.net:8443/mcp
```

`/sse` でも技術的には動作するが、claude.aiのGitHub issueで `/sse` 使用時に
認証完了後の無限ループが報告されており、`/mcp`（Streamable HTTP）が推奨される。

## テスト

1. 構文チェック（`ast.parse`）
2. MCPサーバー起動確認（SSEモード）
3. `curl https://fraine.tail204746.ts.net:8443/.well-known/oauth-protected-resource` → JSONにresource, authorization_serversが含まれること
4. `curl -I https://fraine.tail204746.ts.net:8443/mcp` → 401 + `WWW-Authenticate` ヘッダーにresource_metadataが含まれること

テスト3-4はFunnelが有効な状態でないと外部から確認できない。
ローカルでは `curl http://localhost:8766/.well-known/oauth-protected-resource` と
`curl -I http://localhost:8766/mcp` で代替可。

## 台帳との照合（配線指針§5）

本修正でclaude.aiコネクタのURLが `/sse` → `/mcp` に変わる。
NW台帳（ai-family-memory ops/state/network.yaml）の `url_dependents` は
PM側で更新済み（2026-08-18）。PGは以下を確認すること:

- 台帳の claude.ai コネクタ行が `https://fraine.tail204746.ts.net:8443/mcp` になっていること
- 手順書（docs/mcp-remote-setup.md）のコネクタURLと台帳が一致していること

ポート・serve/funnel設定の変更はないため、台帳の配線行の変更は不要。

## 完了条件

- src/mcp_server.py の W-1〜W-3 修正
- docs/mcp-remote-setup.md の W-4 修正
- docs/reports/m7b-hotfix2-completion.md 提出（テスト結果記載）
- _STATUS.md 更新
- 5W1Hコミット
