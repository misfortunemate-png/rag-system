# 規程エージェント M7b-1 作業指示書（MCP Streamable HTTP化・OAuth承認画面方式）

文書種別: 権威文書

作成日: 2026-08-16 ／ PM: クリーデ ／ 対応要件: docs/m7b-requirements-v2.md v2.1 ／ 本書一枚で完結（追補なし）

## 添付マニフェスト（着工前照合・必須）

以下がすべて交換所（リポジトリ）に存在すること。**1つでも欠けたら着工せず docs/reports/ に報告。**

| # | パス | 種別 | SHA-256 |
|---|---|---|---|
| 1 | docs/m7b-requirements-v2.md | 要件定義書 | — |

## PG運用規律（定型・全フェーズ共通）

1. **三則**: ①難航時はPMへ差し戻す ②原因判明時は「原因X・対策Y・実行可否」で報告→指示待ち ③セッション外プロセス停止等は事前許可
2. **宛先**:
   - **仕様の疑義・技術判断** → docs/reports/ にpushしてPMへ
   - **環境・インフラの問題**（ファイルが見つからない、権限、起動不能等）→ 発注者に直接聞いてよい
   - **実機試験の依頼・承認** → 発注者
3. **支給物改変禁止**: PM支給物はdiffゼロで検収される。技術的整合の調整もPMへ差し戻す
4. **発注者指示による仕様外修正**: 発注者から直接指示を受けた修正は実施・効果確認してよい。報告時に「発注者の指示により実装/修正」と明記する。権威文書は書き換えない
5. **着工前**: `git pull` → マニフェスト照合・版確認。不一致なら着工しない
6. **完了宣言禁止**: テスト結果を添えて「確認をお願いします」で止める

## 作業範囲

- 何を: (W-1) MCP Streamable HTTPトランスポートの追加、(W-2) OAuth承認画面方式への改修
- なぜ: claude.ai・ChatGPTカスタムコネクタからのMCP接続を実現するため（要件§0）
- どこで: misfortunemate-png/rag-system

## W-1: Streamable HTTPトランスポートの追加

### 目的

現在のSSEトランスポート（`/sse`）に加え、Streamable HTTP（`/mcp`）を追加する。MCP標準がStreamable HTTPへ移行済みであり、Gemini EnterpriseはSSEを非サポートとしているため。SSEは既存互換として維持する。

### 実装

1. `mcp` パッケージの `streamable_http_app()` メソッドが利用可能か確認する。利用可能なら `/mcp` パスでマウントする
2. 利用不可（`AttributeError` 等）の場合は **SSEのみで続行し、起動ログに警告を出す**（`mcp` パッケージのバージョンが古い場合。`pip install --upgrade mcp` で解決する可能性がある）
3. SSEの `/sse` パスは引き続き維持する。両トランスポートを同一ポート・同一ASGIアプリで同居させる
4. `--transport` 引数の `sse` 選択肢は `http` にリネームする（SSEとStreamable HTTPの両方を含むため）。`stdio` はそのまま
5. 起動ログに利用可能なエンドポイントを列挙する（例: `/sse (SSE)`, `/mcp (Streamable HTTP)`）

### 制約

- 既存のstdioトランスポートを削除しない
- 既存のツール定義（8ツール）を変更しない
- SSEの既存パス `/sse` `/messages/` を変更しない

## W-2: OAuth承認画面方式への改修

### 目的

現在のOAuth実装は `/register` がclient_secretを返し `/authorize` が自動承認する。公開網では実質無認証であり、要件§0.3に反する（D-1）。

OAuth入口を既存のトークン台帳（`data/auth_tokens.yaml`）に一本化し、接続操作をしている本人（ショウゴさんまたはゲスト）が**ブラウザ上でトークンを入力する**ことで認可を行う方式に変更する。

### 実装

#### /register（Dynamic Client Registration）

変更前: `_AUTH_TOKENS_BY_ID["claude-ai"]` のトークンをclient_secretとして返す。
変更後: client_secretを返さない。client_idを発行し、redirect_urisを保存するだけ。

```python
# レスポンスからclient_secretを除去
return JSONResponse({
    "client_id": client_id,
    "client_name": client_name,
    "redirect_uris": redirect_uris,
    # client_secretは返さない
})
```

`token_endpoint_auth_methods_supported` を `["none"]` に変更する（client_secretを使わないため）。

#### /authorize（承認画面方式）

変更前: リクエストを受けると即座にリダイレクト（自動承認）。
変更後: HTML承認画面を返す。

1. GETリクエストで以下を含むHTML画面を返す:
   - 「規程エージェント MCPアクセス認可」というタイトル
   - 「接続を許可するにはアクセストークンを入力してください」という説明
   - テキスト入力欄（type="password"・placeholder="アクセストークン"）
   - 「許可する」ボタン
   - client_id・redirect_uri・state・code_challenge・code_challenge_methodはhiddenフィールドで保持
   - スタイリングは最小限（読める程度。CSSフレームワーク不要）
2. POSTで送信を受け取る:
   - 入力されたトークンを `_AUTH_TOKENS` で検証する
   - 有効 → 認可コードを発行し、redirect_uriにリダイレクト（従来と同じ302レスポンス）。認可コードにはトークンIDを紐付ける
   - 無効 → 同じHTML画面を「トークンが無効です」のエラーメッセージ付きで再表示。ブルートフォース保護（既存の `_bf_failures` / `_bf_blocks` 辞書）を適用する
3. `/authorize` のルーティングを `methods=["GET", "POST"]` に変更する

#### /token（トークン発行）

変更前: 固定で `_AUTH_TOKENS_BY_ID["claude-ai"]` を返す。
変更後: 認可コードに紐付いたトークンIDから、対応するトークンを返す。

```python
# 認可コードから紐付いたトークンIDを取得
token_id = code_info["token_id"]
access_token = _AUTH_TOKENS_BY_ID.get(token_id, "")
```

client_secret_postの検証を削除する（`token_endpoint_auth_methods_supported` が `["none"]` のため）。

#### _OAuthSSEDispatcher

`/authorize` はPOSTも受け付けるため、パスベースのルーティング判定に影響しないことを確認する（既存は `scope["path"]` のみで判定しており、メソッドは見ていないので問題ないはず）。

#### /.well-known/oauth-authorization-server

以下を変更:
- `token_endpoint_auth_methods_supported`: `["none"]`
- `response_types_supported` に `"code"` があることを確認

### Bearer直経路（変更なし）

`_AuthRateLimitMiddleware` のBearerヘッダー検証はそのまま維持する。OAuthを経由せず、ヘッダーにトークンを直接設定できるクライアント（Antigravity CLI・Claude Code等）は従来通り接続可能。

### 不要になるもの

- `_AUTH_TOKENS_BY_ID` 辞書自体は残す（/token で使用する）が、`_load_auth_tokens_by_id` 関数が「claude-ai」IDに特別な意味を持つ前提（648行目）は廃止する。すべてのトークンIDが等価に扱われる

## 禁止事項

- 既存のstdioトランスポートを削除しない
- 既存のツール定義を変更しない
- `data/auth_tokens.yaml` のフォーマット（id/token/expires構造）を変更しない
- OAuthエンドポイントにフレームワーク（Flask等）を追加しない（既存のStarlette/ASGIで完結）
- 承認画面にJavaScriptフレームワークを使わない（素HTMLで完結）
- 認証なしでHTTPモードを起動可能にしない

## テスト

### PG自己完結分（curlまたはスクリプト）

1. `python src/mcp_server.py --transport http` で起動し、以下を確認:
   - 起動ログに `/sse` と（利用可能なら）`/mcp` のエンドポイントが表示される
   - `curl http://localhost:8766/sse` にBearerヘッダー付きでSSE接続できる（既存互換）
   - `/mcp` が利用可能な場合: `curl -X POST http://localhost:8766/mcp` にBearerヘッダー付きでアクセスできる
2. `GET /.well-known/oauth-authorization-server` がメタデータを返す（`token_endpoint_auth_methods_supported: ["none"]`）
3. `POST /register` がclient_idを返し、**client_secretを含まない**
4. `GET /authorize?client_id=...&redirect_uri=...&response_type=code&code_challenge=...&code_challenge_method=S256&state=...` がHTML承認画面を返す
5. `POST /authorize` に**有効なトークン**を送信 → 302リダイレクト（認可コード付き）
6. `POST /authorize` に**無効なトークン**を送信 → エラーメッセージ付きHTML再表示
7. `POST /token` に認可コード＋client_id → access_token返却（Bearer形式）
8. 取得したaccess_tokenでSSEまたはStreamable HTTP接続が通る
9. `--transport stdio` で従来通りClaude Codeから利用可能（回帰）

### 実機系（発注者に依頼）

1. **Tailscale Funnel疎通**: `tailscale funnel --bg --https=8443 http://127.0.0.1:8766` 後、Pixel 10のモバイル回線（Tailscale外）から `https://fraine.tail204746.ts.net:8443/.well-known/oauth-authorization-server` にアクセスしてJSONが返ること
2. **ブラウザ承認画面**: Pixel 10のブラウザから `https://fraine.tail204746.ts.net:8443/authorize?...` にアクセスして承認画面が表示され、トークン入力で認可が通ること
3. **claude.aiカスタムコネクタ**: URLに `https://fraine.tail204746.ts.net:8443/sse` を登録し、承認画面でトークンを入力して接続が成立すること

## 完了条件

- W-1・W-2の実装
- テスト項目1〜9の結果
- `start-mcp-remote.bat` の更新（`--transport sse` → `--transport http`）
- docs/reports/m7b-1-completion.md 提出
- _STATUS.md・CLAUDE.md更新（フロントマター含む）
- 5W1Hコミット
- 「確認をお願いします」で完了報告
