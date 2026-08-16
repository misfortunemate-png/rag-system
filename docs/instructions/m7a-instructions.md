# 規程エージェント M7a作業指示書（MCP HTTP化・認証・Tailscale Funnel・claude.ai接続）

作成日: 2026-08-16（改訂） ／ PM: クリーデ
位置づけ: rag-systemをclaude.ai・モバイルアプリから利用可能にする。

## 背景

mcp_server.pyは現在stdioトランスポートでClaude Code（フラン上ローカル）から利用可能。claude.aiのカスタムコネクタはAnthropicのクラウドインフラから接続するため、MCPサーバーが公開インターネットからHTTPSで到達可能である必要がある。Tailscale Funnelでフラン上のHTTPサービスをHTTPS公開する。

利用者は発注者（ショウゴさん）、指定されたLLMクライアント（claude.ai）、デモ的な少数のゲストを想定。不特定多数への公開ではない。

## 作業項目

### W-1: HTTPトランスポートの追加（mcp_server.py）

既存のstdioトランスポートに加え、SSE（Server-Sent Events）HTTPトランスポートを追加する。

- MCPServerインスタンスの `sse_app()` メソッドでStarlette/ASGIアプリを取得する（存在しない場合は `streamable_http_app()` を試行。いずれも利用できない場合はエラーで終了）
- uvicornでホスト・ポートを指定して起動する
- コマンドライン引数で `--transport stdio`（既定・後方互換）と `--transport sse`（HTTP）を切り替える
- SSEモード時のホスト: `0.0.0.0`
- SSEモード時のポート: 環境変数 `MCP_HTTP_PORT`（既定: 8766）
- リクエストボディサイズ上限: 1MB

### W-2: 認証・セキュリティ

#### 複数Bearerトークン方式

`data/auth_tokens.yaml` で複数トークンを管理する:

```yaml
# data/auth_tokens.yaml — gitignore対象
tokens:
  - id: "shougo"
    token: "（32文字以上のランダム文字列）"
  - id: "claude-ai"
    token: "（32文字以上のランダム文字列）"
  - id: "guest-demo"
    token: "（32文字以上のランダム文字列）"
    expires: "2026-09-01"
```

- サーバー起動時に `data/auth_tokens.yaml` を読み込み、トークンのルックアップテーブルを構築する
- `expires` があるエントリは、現在日時が期限を過ぎていたら無効扱いにする
- SSEモード時、すべてのHTTPリクエストの `Authorization: Bearer {token}` ヘッダーを検証する
- トークンが有効なエントリにマッチした場合、リクエストコンテキストに `auth_id`（例: "shougo"）を付与し、ログに記録する
- stdioモード時は認証ミドルウェアを適用しない
- `data/auth_tokens.yaml` が存在しない、または空のままSSEモードで起動しようとした場合、起動を拒否しエラーメッセージを表示する
- `.gitignore` に `data/auth_tokens.yaml` を追加する

#### レート制限

- IPアドレスベースで1分あたり10リクエストの制限を設ける（簡易実装・インメモリカウンタで可）
- 制限超過時は 429 Too Many Requests を返す
- ログに制限超過のIPと回数を記録する

#### ブルートフォース抑止

- 認証失敗時に `time.sleep(3)` を挿入する
- 認証失敗をログに記録する（IPアドレス・タイムスタンプ。トークン文字列は記録しない）
- 同一IPから1分以内に5回認証失敗した場合、そのIPからの全リクエストを10分間ブロックし、ログに記録する

#### 入力サイズ制限

- submit_questionの質問文: 2,000字で打ち切り
- report_feedbackの各フィールド: correction 5,000字、evidence 2,000字で打ち切り
- search_chunksのquery: 500字で打ち切り
- web_search_toolのquery: 500字で打ち切り

#### doc_slugバリデーション

- read_sectionのdoc_slug引数がdocuments.yaml内に存在するかチェックする（パストラバーサル防止）。存在しない場合はエラーを返す。既に実装されている場合は確認のみ

### W-3: 起動スクリプトと設定テンプレート

以下の納品物を作成する:

1. **start-mcp-remote.bat**（Windows・ASCII・CRLF）:
   - .envの存在確認
   - `data/auth_tokens.yaml` の存在確認（なければ警告して停止）
   - `python src/mcp_server.py --transport sse` で起動
   - 起動メッセージに接続URL・登録済みトークンID一覧（トークン文字列は非表示）を表示

2. **data/auth_tokens.yaml.example**:
   - 構造のテンプレート。トークン値はプレースホルダー
   - トークン生成コマンドを記載: `python -c "import secrets; print(secrets.token_urlsafe(32))"`

3. **.env.example** への追記:
   - `MCP_HTTP_PORT=8766`（任意）

4. **.gitignore** への追記:
   - `data/auth_tokens.yaml`

### W-4: Tailscale Funnel設定手順

docs/mcp-remote-setup.md に以下を記載する:

1. auth_tokens.yamlの作成手順（トークン生成コマンド含む）
2. start-mcp-remote.batの実行
3. Tailscale Funnelの有効化: `tailscale funnel 8766`
4. 公開URLの確認（例: `https://fraine.tail204746.ts.net:8766`）
5. claude.aiでのカスタムコネクタ追加手順:
   - 設定 → コネクタ → 追加 → カスタム → Web
   - URLに公開URLの `/sse` パスを入力
   - Request Headersに `Authorization: Bearer {claude-ai用トークン}` を設定
6. モバイルアプリでも同じコネクタが自動的に利用可能になる旨
7. ゲストへのトークン発行と期限管理の手順
8. トークンローテーション手順（yaml編集→サーバー再起動→claude.aiのRequest Header更新）

### W-5: 疎通確認

フラン上で以下の疎通確認を実施する:

1. **認証成功**: 有効なBearerトークンでSSEエンドポイントにアクセスし、SSEストリームが返ること
2. **認証失敗**: トークンなし・誤トークンで401が返ること
3. **期限切れトークン**: expiresが過去のトークンで401が返ること
4. **レート制限**: 1分以内に11回連続リクエストし、11回目で429が返ること
5. **入力サイズ**: 3,000字の質問文をsubmit_questionに送り、2,000字に打ち切られること
6. **auth_idログ**: 認証成功時にログにトークンIDが記録されること
7. **stdio回帰**: `--transport stdio` で従来通りClaude Codeから利用可能なことを確認
8. **Tailscale Funnel**: `tailscale funnel 8766` 後、公開URL経由で疎通確認（発注者の操作が必要な場合は手順書への記載で代替可）

## 禁止事項

- 既存のstdioトランスポートを削除しない
- 既存のツール定義を変更しない
- トークンをコードにハードコードしない
- auth_tokens.yamlをgitにコミットしない
- 認証なしでSSEモードを起動可能にしない

## 完了条件

- W-1〜W-3の実装
- W-4の手順書
- W-5の疎通確認結果
- docs/reports/m7a-completion.md 提出
- _STATUS.md・CLAUDE.md更新
- 「確認をお願いします」で完了報告
