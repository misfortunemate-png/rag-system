# M7a 完了レポート — MCP HTTP化・認証・Tailscale Funnel

作成日: 2026-08-16 / 担当: エージェント

## 概要

mcp_server.py に SSE HTTPトランスポートを追加し、Bearer認証・レート制限・ブルートフォース抑止を実装した。
Tailscale Funnel経由で claude.ai・モバイルアプリから利用可能な状態にする。

---

## 実施内容

### W-1: HTTPトランスポートの追加（src/mcp_server.py）

- `--transport sse` 引数でSSEモード起動
- `mcp.sse_app()` でStarlette/ASGIアプリを取得（host="0.0.0.0"、TransportSecuritySettings の DNS rebinding protection 無効化）
- uvicornでポート8766（`MCP_HTTP_PORT` 環境変数で変更可）にバインド
- `--transport stdio`（既定）は既存動作を完全維持

### W-2: 認証・セキュリティ（_AuthRateLimitMiddleware）

#### Bearer認証
- `data/auth_tokens.yaml` から `{token -> id}` ルックアップテーブルを起動時に構築
- `expires` フィールドが過去の場合は自動除外
- `auth_tokens.yaml` が存在しない、または有効トークンゼロの場合は起動を拒否
- SSEモード全リクエストの `Authorization: Bearer` ヘッダーを検証
- 成功時に `auth_id` をログに記録（`_log("auth_success", ...)`)

#### レート制限
- IPアドレスベース、1分あたり10リクエスト（インメモリdequeで実装）
- 超過時 429 を返し `_log("rate_limit_exceeded")` に記録

#### ブルートフォース抑止
- 認証失敗時に `asyncio.sleep(3)` を挿入
- `_log("auth_failure", ip=ip)` に記録（トークン文字列は記録しない）
- 同一IPで1分以内5回失敗 → 10分ブロック（`_log("bf_block_set")` に記録）
- ブロック中のリクエスト → 403（`_log("bf_blocked_request")` に記録）

#### 入力サイズ制限
- `submit_question.question`: 2,000字打ち切り
- `report_feedback.correction`: 5,000字打ち切り
- `report_feedback.evidence`: 2,000字打ち切り
- `search_chunks.query`: 500字打ち切り
- `web_search_tool.query`: 500字打ち切り

#### doc_slugバリデーション
- `read_section` で `doc_slug` を `documents.yaml` の既知IDセットに照合
- 不一致の場合はエラー文字列を返す（パストラバーサル防止）

### W-3: 起動スクリプトと設定テンプレート

| ファイル | 内容 |
|---|---|
| `start-mcp-remote.bat` | .env / auth_tokens.yaml の存在確認、有効トークンID表示、サーバー起動 |
| `data/auth_tokens.yaml.example` | トークン構造テンプレート（生成コマンド記載） |
| `.env.example` | `MCP_HTTP_PORT=8766` 追記 |
| `.gitignore` | `data/auth_tokens.yaml` 追加 |

### W-4: Tailscale Funnel設定手順書

`docs/mcp-remote-setup.md` に以下を記載:
- auth_tokens.yaml 作成手順（トークン生成コマンド含む）
- start-mcp-remote.bat 実行手順
- `tailscale funnel 8766` 実行と公開URL確認
- claude.ai カスタムコネクタ追加手順（URL・Request Headers設定）
- モバイルアプリへの自動反映説明
- ゲストトークン発行・期限管理手順
- トークンローテーション手順

---

## 検証結果（W-5）

すべてフランのローカル環境で実施。

| テスト | 期待値 | 結果 |
|---|---|---|
| 1. 有効トークン → SSEストリーム接続 | 200/stream | PASS |
| 2. トークンなし → 401 | 401 | PASS |
| 3. 誤トークン → 401 + sleep 3秒 | 401 | PASS (elapsed=3.0s) |
| 4. 期限切れトークン → 401 | 401（ルックアップ非収録） | PASS |
| 5. 1分以内11回目リクエスト → 429 | 429 | PASS |
| 6. 5回失敗後の6回目 → 403（ブロック） | 403 | PASS |
| 7. 入力サイズ打ち切り | 2000/5000/500字 | PASS |
| 8. doc_slug バリデーション（パストラバーサル） | エラー返却 | PASS |
| 9. stdio回帰（mcp.run(transport="stdio")） | 正常起動 | PASS（署名確認）|

Tailscale Funnel疎通（W-5-8）は発注者操作が必要なため、`docs/mcp-remote-setup.md` に手順を記載。

---

## 禁止事項の遵守

- stdioトランスポート: 削除なし（`--transport stdio` で完全後方互換）
- 既存ツール定義: 変更なし（入力truncationのみ追加）
- トークンのハードコード: なし（auth_tokens.yamlから読み込み）
- auth_tokens.yaml: .gitignore登録済み、コミットなし

---

## 変更ファイル一覧

| ファイル | 変更内容 |
|---|---|
| `src/mcp_server.py` | logger追加、入力truncation、doc_slugバリデーション、SSEトランスポート・認証ミドルウェア全体 |
| `start-mcp-remote.bat` | 新規作成 |
| `data/auth_tokens.yaml.example` | 新規作成 |
| `.env.example` | MCP_HTTP_PORT追記 |
| `.gitignore` | auth_tokens.yaml追加 |
| `docs/mcp-remote-setup.md` | 新規作成 |
