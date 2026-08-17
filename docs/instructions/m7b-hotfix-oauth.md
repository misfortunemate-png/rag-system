# M7b hotfix: /register に client_secret を復活させる

文書種別: 権威文書
作成日: 2026-08-16 ／ PM: クリーデ ／ 緊急度: 高（実機試験③ブロック中）

## 問題

claude.aiカスタムコネクタ登録で「サインインサービスに登録できませんでした」エラー。
原因: M7b-1で `/register` レスポンスから `client_secret` を除去したが、claude.aiはDCRレスポンスに `client_secret` が含まれることを必要とする。

## 修正内容（src/mcp_server.py のみ）

### 1. `_oauth_register` 関数（約664行目）

変更前:
```python
    client_id = "rag-system-client"
    with _oauth_lock:
        _oauth_clients[client_id] = {"redirect_uris": redirect_uris}

    _log("oauth_register", ip=ip, client_name=client_name)
    return JSONResponse({
        "client_id": client_id,
        "client_name": client_name,
        "redirect_uris": redirect_uris,
    }, status_code=201)
```

変更後:
```python
    import secrets as _secrets
    client_id = "rag-system-client"
    client_secret = _secrets.token_urlsafe(32)
    with _oauth_lock:
        _oauth_clients[client_id] = {
            "redirect_uris": redirect_uris,
            "client_secret": client_secret,
        }

    _log("oauth_register", ip=ip, client_name=client_name)
    return JSONResponse({
        "client_id": client_id,
        "client_name": client_name,
        "redirect_uris": redirect_uris,
        "client_secret": client_secret,
        "token_endpoint_auth_method": "client_secret_post",
    }, status_code=201)
```

### 2. `_oauth_metadata` 関数（約649行目）

変更前:
```python
        "token_endpoint_auth_methods_supported": ["none"],
```

変更後:
```python
        "token_endpoint_auth_methods_supported": ["client_secret_post", "none"],
```

### 3. `/token` エンドポイント（client_secret検証を追加、約820行目付近）

`client_secret` が送られてきた場合に保存済みの値と照合する。
不一致なら `invalid_client` を返す。送られてこない場合はスキップ（後方互換）。

```python
    # client_secret validation (if provided)
    client_secret_provided = body.get("client_secret")
    if client_secret_provided:
        with _oauth_lock:
            stored = _oauth_clients.get(client_id, {}).get("client_secret")
        if not stored or not hmac.compare_digest(client_secret_provided, stored):
            return JSONResponse({"error": "invalid_client"}, status_code=401)
```

`import hmac` が未インポートの場合は先頭のimportブロックに追加する。

## セキュリティ上の根拠

`client_secret` はOAuthセッション内でのクライアント識別に使う。
本システムの実際のアクセスゲートは `/authorize` の承認画面（auth_tokens.yaml照合）であり、
`client_secret` を知っていても有効な `code` を取得するためには承認画面でのトークン入力が必要。
セキュリティモデルは変わらない。

## テスト

1. MCPサーバー再起動
2. `curl -X POST https://fraine.tail204746.ts.net:8443/register -H "Content-Type: application/json" -d '{"client_name":"test","redirect_uris":["https://example.com"]}'` → レスポンスに `client_secret` が含まれること
3. claude.aiカスタムコネクタを再登録（削除→追加）→ 承認画面が表示されること

## 完了条件

- src/mcp_server.py の上記3箇所の修正
- MCPサーバー再起動（発注者に依頼）
- docs/reports/m7b-hotfix-completion.md 提出
- 5W1Hコミット
