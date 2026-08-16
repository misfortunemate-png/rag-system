# 規程エージェント M7a追補指示書（OAuth 2.1最小エンドポイント）

作成日: 2026-08-16 ／ PM: クリーデ ／ 緊急
位置づけ: M7a本体完了後の追加工事。claude.aiカスタムコネクタがOAuth 2.1を必須とすることが判明したため、最小エンドポイントを追加する。

## 背景

claude.aiのカスタムコネクタは接続時にOAuth 2.1 Discovery→Dynamic Client Registration→Authorization Code Grant→Token Exchange のフローを実行する。Bearer tokenのみ・URLクエリパラメータのみでは「サインインサービスに登録できませんでした」で失敗する。

利用者は発注者1名＋少数ゲストのため、OAuth実装は最小限の簡易スタブとする。

## 作業項目

### W-1: OAuth 2.1最小エンドポイント（mcp_server.pyまたは別ファイル）

SSEモード起動時のASGIアプリに以下の4エンドポイントを追加する。既存の認証ミドルウェア（_AuthRateLimitMiddleware）の前段で処理し、OAuthエンドポイントへのリクエストはBearer認証をバイパスする。

#### 1. `GET /.well-known/oauth-authorization-server`

```json
{
  "issuer": "https://fraine.tail204746.ts.net:8443",
  "authorization_endpoint": "https://fraine.tail204746.ts.net:8443/authorize",
  "token_endpoint": "https://fraine.tail204746.ts.net:8443/token",
  "registration_endpoint": "https://fraine.tail204746.ts.net:8443/register",
  "response_types_supported": ["code"],
  "grant_types_supported": ["authorization_code"],
  "token_endpoint_auth_methods_supported": ["client_secret_post"],
  "code_challenge_methods_supported": ["S256"]
}
```

issuerのURLはハードコードせず、リクエストのHost/X-Forwarded-Hostから動的に構築するか、環境変数 `MCP_PUBLIC_URL`（既定: `https://fraine.tail204746.ts.net:8443`）から取得する。

#### 2. `POST /register`（Dynamic Client Registration）

リクエストボディからclient_nameを取得し、固定のclient_id/client_secretを返す:

```json
{
  "client_id": "rag-system-client",
  "client_secret": "{auth_tokens.yamlのclaude-ai用トークン}",
  "client_name": "{リクエストから}",
  "redirect_uris": ["{リクエストから}"]
}
```

注: claude.aiはDynamic Client Registrationで自分のredirect_urisを登録する。これを記録し、/authorizeでのリダイレクト先に使う。

インメモリ辞書で `{client_id: {client_secret, redirect_uris}}` を保持する。サーバー再起動で消えてよい（claude.aiが再登録する）。

#### 3. `GET /authorize`（認可エンドポイント）

クエリパラメータ: client_id, redirect_uri, response_type=code, state, code_challenge, code_challenge_method

処理:
1. client_idが登録済みか確認
2. redirect_uriが登録時のredirect_urisに含まれるか確認
3. 認可コード（ランダム文字列・有効期限60秒）を生成し、インメモリ辞書に保存
4. code_challenge/code_challenge_method（PKCE）も保存
5. redirect_uri に `?code={認可コード}&state={state}` を付けて302リダイレクト

**認可画面は表示しない**（自動承認）。利用者はショウゴさん1人であり、コネクタ登録の時点で認可の意思表示が完了している。

#### 4. `POST /token`（トークンエンドポイント）

リクエストボディ（application/x-www-form-urlencoded）:
- grant_type=authorization_code
- code={認可コード}
- client_id
- client_secret
- code_verifier（PKCE検証）
- redirect_uri

処理:
1. client_id/client_secretを検証
2. 認可コードの有効性・有効期限を検証
3. PKCE検証（code_verifier → SHA256 → base64url → code_challengeと照合）
4. 成功時、アクセストークンを返す:

```json
{
  "access_token": "{auth_tokens.yamlのclaude-ai用トークン}",
  "token_type": "Bearer",
  "expires_in": 86400
}
```

認可コードは使用後に無効化する（1回限り）。

### W-2: ミドルウェア調整

- OAuthエンドポイント（/.well-known/*, /register, /authorize, /token）へのリクエストはBearer認証・レート制限をバイパスする
- /registerと/tokenにはブルートフォース抑止（認証失敗時のsleep）を適用する
- 既存のSSE/MCPエンドポイントへのリクエストは従来通りBearer認証を適用する（OAuthフローで取得したaccess_tokenがBearerトークンとして送られる）

### W-3: 設定

- .env.exampleに `MCP_PUBLIC_URL=https://fraine.tail204746.ts.net:8443` を追加
- ドキュメント（docs/mcp-remote-setup.md）にOAuthフローの説明を追記（ユーザー操作は変わらない。claude.aiが自動的にOAuthフローを実行する）

### W-4: 疎通確認

1. `GET /.well-known/oauth-authorization-server` がメタデータJSONを返すこと
2. `POST /register` がclient_id/client_secretを返すこと
3. `GET /authorize` が302リダイレクトし、認可コード付きURLにリダイレクトすること
4. `POST /token` がaccess_tokenを返すこと
5. 取得したaccess_tokenでSSEエンドポイントにアクセスできること
6. stdio回帰

## 禁止事項

- 既存のツール定義を変更しない
- auth_tokens.yamlの構造を変更しない
- 既存のBearer認証を無効化しない（OAuthで取得したトークン＝既存のBearerトークン）

## 完了条件

- W-1〜W-3の実装
- W-4の疎通確認結果
- サーバー起動ログに「OAuth endpoints enabled」が表示されること
- 「確認をお願いします」で完了報告
