# M7a進行記録 — claude.ai/モバイル接続の試行と未解決課題

作成日: 2026-08-16 ／ 作成者: クリーデ（PM）
用途: 技術顧問が事実関係を調査するための記録。提案・推奨は含まない。

---

## 1. 要求

claude.ai（Web）およびモバイルアプリ（Pixel 10のclaude.aiアプリ）から、フラン上で稼働するrag-systemのMCPツールを利用可能にする。

## 2. 前提環境

### フラン（自宅PC・Windows 11）
- rag-system MCPサーバー: `src/mcp_server.py`、stdioトランスポートでClaude Codeから利用可能（M5c完了済み）
- ポート8766でSSE HTTPサーバーとして起動可能（M7a本体で実装済み）
- 認証: data/auth_tokens.yamlによる複数Bearerトークン管理（M7a本体で実装済み）
- OAuth 2.1最小エンドポイント実装済み（M7a追補で実装）

### Tailscale
- フラン・ラ・ルキエラ・Pixel 10がメッシュネットワーク上
- Tailscale Funnelで公開インターネットにHTTPS公開可能
- フランのTailscaleドメイン: `fraine.tail204746.ts.net`

### chat-pwa（既存・稼働中）
- `https://fraine.tail204746.ts.net/` でTailscale Funnel経由で公開中
- Pixel 10でstandalone PWAとして日常利用
- Tailscale serve設定: ポート443 → `http://127.0.0.1:8787`
- Tailscale Funnel: ポート443で有効（`Funnel on`）

### claude.ai
- Maxプラン（$110/月）
- カスタムコネクタ機能あり（設定→コネクタ→追加→カスタム）

## 3. M7a本体の実装内容

### 実装済み
1. `mcp_server.py` に `--transport sse` 引数でSSE HTTPトランスポート追加（uvicorn、0.0.0.0:8766）
2. `_AuthRateLimitMiddleware`: Bearer認証・レート制限（10req/分/IP）・ブルートフォース抑止（5回失敗→10分ブロック）
3. 入力サイズ制限（質問2,000字・query 500字等）
4. doc_slugバリデーション（パストラバーサル防止）
5. `start-mcp-remote.bat`（ASCII-only・CRLF）
6. `data/auth_tokens.yaml`（gitignore対象）による複数トークン管理（ID付き・ゲスト期限管理）
7. `scripts/show_token_ids.py`（batから呼び出すヘルパー）
8. `docs/mcp-remote-setup.md`（手順書）

### 疎通確認結果（ローカル・9項目全PASS）
- 有効トークン→SSE接続成功
- 無効トークン→401・3秒sleep
- レート制限→429
- ブルートフォースブロック→403
- 入力打ち切り→確認
- stdio回帰→正常

## 4. 接続試行の時系列と各段階で判明した事実

### 4-1. Tailscale Funnelのポート443競合

**試行**: `tailscale funnel 8766`
**結果**: エラー `listener already exists for port 443`
**原因**: chat-pwaが既にポート443でFunnelを使用中

### 4-2. 別ポート（8443）での回避試行

**試行**:
```
tailscale serve --bg --https 8443 http://127.0.0.1:8766
tailscale funnel --bg 8443
```
**結果**: `tailscale serve status` で8443は `(tailnet only)` 表示。Funnel ONにならない。
**判明した事実**: **Tailscale Funnelは公開インターネットへの露出をポート443でしかできない。** 443以外のポートは `tailscale serve` でtailnet内には公開できるが、`tailscale funnel` でインターネットには公開できない。これはTailscale側の仕様制約。

### 4-3. ポート10000での追加試行

**試行**:
```
tailscale serve --bg --https 10000 http://127.0.0.1:8766
tailscale funnel --bg 10000
```
**結果**: 同様に `(tailnet only)`。ポート番号を変えても結果は同じ。

### 4-4. 443ポート共有の検討（PM提案・未実施）

PMから二つの選択肢を提示:
- **A**: chat-pwaをtailnet only（8443等）に移し、rag-systemに443を譲る。chat-pwaはPixel 10（tailnet上）からのアクセスのみのためFunnel不要。ただしPWA再登録が必要。
- **B**: 443でリバースプロキシによるパスベース同居。`/sse` `/register` `/authorize` `/token` `/.well-known/*` →rag-system、その他→chat-pwa。常駐プロセス1本追加。

**発注者判断**: 差し戻し。サーバー側の要件定義からやり直す。

### 4-5. claude.aiカスタムコネクタのOAuth必須

**試行**: claude.aiのカスタムコネクタ追加画面でURL `https://fraine.tail204746.ts.net:8443/sse` を入力して「追加」
**結果**: 「rag-systemのサインインサービスに登録できませんでした」（参照: ofid_7d424832cbf579a7）
**原因**: claude.aiカスタムコネクタはOAuth 2.1フローを必須とする。単純なBearer tokenでは接続できない。

### 4-6. URLクエリパラメータでのトークン認証試行

**試行**: 認証ミドルウェアに `?token=` クエリパラメータのチェックを追加。URL `https://fraine.tail204746.ts.net:8443/sse?token={token}` で登録試行。
**結果**: 同じエラー。OAuthフロー（Dynamic Client Registration）の失敗であり、Bearer認証の方式の問題ではない。

### 4-7. OAuth 2.1最小エンドポイント実装（M7a追補）

**実装**: 4エンドポイントを追加
1. `GET /.well-known/oauth-authorization-server` → メタデータJSON
2. `POST /register` → Dynamic Client Registration（固定client_id、claude-ai用トークンをclient_secretとして返却）
3. `GET /authorize` → 自動承認→302リダイレクト（認可コード付き）
4. `POST /token` → PKCE S256検証→access_token返却

**ローカル疎通**: 8項目全PASS（メタデータ返却・登録・認可コード・トークン発行・PKCE検証・不正secret拒否・SSE接続・stdio回帰）

### 4-8. OAuth実装後のclaude.ai接続試行

**試行**: claude.aiのカスタムコネクタで `https://fraine.tail204746.ts.net:8443/sse` を登録。OAuth Client ID・Client Secretは空。
**結果**: 「接続の問題 — サーバーに接続できませんでした」
**原因**: 8443がtailnet onlyのままであり、Anthropicのサーバーからフランに到達できない（4-2/4-3の制約と同じ）。OAuthエンドポイントの問題ではなく、ネットワーク到達性の問題。

### 4-9. Pixel 10からの外部到達性検証

**試行**: Pixel 10のモバイル回線（Tailscaleネットワーク外）から `https://fraine.tail204746.ts.net:8443/.well-known/oauth-authorization-server` にブラウザアクセス
**結果**: アクセスできない（4-2の制約の実証）

## 5. 判明した制約の一覧

| # | 制約 | 判明時点 | 根拠 |
|---|---|---|---|
| C-1 | Tailscale Funnelは公開インターネット露出をポート443のみで行える | 4-2 | tailscale serve status の出力（443以外は tailnet only） |
| C-2 | ポート443はchat-pwaが占有中 | 4-1 | `listener already exists for port 443` |
| C-3 | claude.aiカスタムコネクタはOAuth 2.1フロー必須 | 4-5 | 「サインインサービスに登録できませんでした」エラー |
| C-4 | claude.aiカスタムコネクタのRequest Header認証はベータ機能で未開放 | 4-5 | コネクタ追加画面にRequest Headersセクションが表示されない |
| C-5 | claude.aiカスタムコネクタはAnthropicのクラウドから接続する（ユーザーのデバイスからではない） | 設計時 | Anthropic公式ドキュメント |
| C-6 | batファイルにUTF-8日本語を含めるとcmd.exeで構文崩壊する | 4-1後 | 既知の教訓（devスキルに記載済み）だがstart-mcp-remote.batで再発 |
| C-7 | PowerShellではカレントディレクトリのコマンド実行に `.\` プレフィックスが必要 | 4-1後 | 発注者指摘 |

## 6. 現在のTailscale serve設定

```
# tailscale serve status 出力（2026-08-16最終）
https://fraine.tail204746.ts.net:10000 (tailnet only)
|-- / proxy http://127.0.0.1:8766
https://fraine.tail204746.ts.net (Funnel on)
|-- / proxy http://127.0.0.1:10000
```

注: 試行の過程で複数回設定変更しているため、最新の状態は発注者に確認が必要。chat-pwaの元の設定（443 → http://127.0.0.1:8787）が維持されているかも要確認。

## 7. 実装済みコードの状態

| ファイル | 状態 | 備考 |
|---|---|---|
| src/mcp_server.py | 896行・OAuth含むフル実装 | SSE+stdio共存・認証・レート制限・OAuth 4エンドポイント |
| start-mcp-remote.bat | ASCII-only・cd /d付き | ローカルでは正常動作 |
| data/auth_tokens.yaml | 発注者作成済み（3トークン） | gitignore対象 |
| docs/mcp-remote-setup.md | 手順書 | Tailscale Funnel部分は実態と乖離 |
| scripts/show_token_ids.py | ヘルパー | 正常動作 |

## 8. 未検証事項

- chat-pwaの443設定が試行の過程で影響を受けていないか
- OAuth 2.1エンドポイントがAnthropicサーバーからの実リクエストに正しく応答するか（ローカル疎通のみ完了。外部からの到達性が確保できていないため未検証）
- Tailscale Funnelの443制約が仕様か設定か（Tailscale公式ドキュメントでの確認が未了）
- ngrok・Cloudflare Tunnel等の代替トンネルでの到達性
- chat-pwaのTailscale Funnel依存度（Pixel 10はtailnet上にいるためFunnel不要の可能性があるが、standalone PWAのURLが変わる影響は未検証）
