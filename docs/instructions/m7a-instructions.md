# 規程エージェント M7a作業指示書（MCP HTTP化・Tailscale Funnel・claude.ai接続）

作成日: 2026-08-16 ／ PM: クリーデ
位置づけ: rag-systemをclaude.ai・モバイルアプリから利用可能にする。

## 背景

mcp_server.pyは現在stdioトランスポートでClaude Code（フラン上ローカル）から利用可能。claude.aiのカスタムコネクタはAnthropicのクラウドインフラから接続するため、MCPサーバーが公開インターネットからHTTPSで到達可能である必要がある。Tailscale Funnelを使えば、フラン上のHTTPサービスを追加インフラなしでHTTPS公開できる。

## 作業項目

### W-1: HTTPトランスポートの追加（mcp_server.py）

既存のstdioトランスポートに加え、SSE（Server-Sent Events）HTTPトランスポートを追加する。

- MCPServerインスタンスの `sse_app()` メソッドでStarlette/ASGIアプリを取得する
- uvicornでホスト・ポートを指定して起動する
- コマンドライン引数で `--transport stdio`（既定・後方互換）と `--transport sse`（HTTP）を切り替える
- SSEモード時のホスト: `0.0.0.0`（Tailscale Funnelがアクセスするため）
- SSEモード時のポート: 環境変数 `MCP_HTTP_PORT`（既定: 8766）

`sse_app()` が存在しない場合は、MCPライブラリのバージョンに応じて `streamable_http_app()` を試行する。いずれも利用できない場合はエラーメッセージを出して終了する。

### W-2: Bearer認証ミドルウェア

公開インターネットに露出するため、認証は必須。

- 環境変数 `MCP_AUTH_TOKEN` にBearerトークンを設定する
- SSEモード時、すべてのHTTPリクエストの `Authorization: Bearer {token}` ヘッダーを検証する
- トークン不一致・未設定時は 401 Unauthorized を返す
- stdioモード時は認証ミドルウェアを適用しない（ローカル利用のため不要）
- `MCP_AUTH_TOKEN` が未設定のままSSEモードで起動しようとした場合、起動を拒否しエラーメッセージを表示する（認証なしでの公開を防止）

実装方法: Starlette/ASGIミドルウェアとして `sse_app()` の返値をラップする。

### W-3: 起動スクリプト

以下の納品物を作成する:

1. **start-mcp-remote.bat**（Windows・ASCII・CRLF）:
   - .envの存在確認
   - `MCP_AUTH_TOKEN` の設定確認（未設定なら警告して停止）
   - `python src/mcp_server.py --transport sse` で起動
   - 起動メッセージに接続URL（`http://localhost:{port}`）を表示

2. **.env.example** への追記:
   - `MCP_AUTH_TOKEN=`（必須・SSEモード時）
   - `MCP_HTTP_PORT=8766`（任意）

### W-4: Tailscale Funnel設定手順

docs/mcp-remote-setup.md に以下を記載する:

1. Tailscale Funnelの有効化手順（tailscale funnel コマンド）
2. `tailscale funnel 8766` でHTTPS公開（https://fraine.tail204746.ts.net:8766）
3. claude.aiでのカスタムコネクタ追加手順:
   - 設定 → コネクタ → 追加 → カスタム → Web
   - URLに `https://fraine.tail204746.ts.net:8766/sse` を入力
   - Request Headersに `Authorization: Bearer {MCP_AUTH_TOKEN の値}` を設定
4. モバイルアプリ（Pixel 10）でも同じコネクタが自動的に利用可能になる旨

### W-5: 疎通確認

フラン上で以下の疎通確認を実施する:

1. **ローカル疎通**: `python src/mcp_server.py --transport sse` を起動し、curlで `http://localhost:8766/sse` にアクセスしてSSEストリームが返ること（認証ヘッダー付き）
2. **認証拒否**: 認証ヘッダーなし・誤ったトークンで401が返ることを確認
3. **stdio回帰**: `--transport stdio` で従来通りClaude Codeから利用可能なことを確認
4. **Tailscale Funnel**: `tailscale funnel 8766` 後、公開URL経由でSSEストリームが返ること

Tailscale Funnel設定とclaude.aiコネクタ登録は発注者の物理層操作（秘密の貼り付け・ネットワーク設定）なので、手順書（W-4）を納品し、実行は発注者に委ねる。

## 禁止事項

- 既存のstdioトランスポートを削除しない（共存）
- 既存のツール定義を変更しない
- MCP_AUTH_TOKEN をコードにハードコードしない
- 認証なしでSSEモードを起動可能にしない

## 完了条件

- W-1〜W-3の実装
- W-4の手順書
- W-5の疎通確認結果（ローカルcurl・認証拒否・stdio回帰）
- docs/reports/m7a-completion.md 提出
- _STATUS.md・CLAUDE.md更新
- 「確認をお願いします」で完了報告
