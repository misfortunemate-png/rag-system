# rag-system 公開アクセス要件定義 v2（M7a差し戻し→M7bとして再定義）

作成日: 2026-08-16 ／ 作成者: クリーデ（技術顧問席）
承認者: ショウゴさん（承認待ち）
位置づけ: m7a-progress-record.md の事実整理を受け、要件から再構築する。M7aの実装物（SSE・認証ミドルウェア・OAuthスタブ）は資産として流用可能なものを流用する。

---

## 0. 要求（当初から不変）

1. ショウゴさんと数名のゲストが**ブラウザ**でrag-systemを利用できること
2. Claude・Gemini・ChatGPT等のAIクライアントが**MCP**でrag-systemのツールを利用できること
3. **世間に公開しない**。到達可能な面を最小化し、すべての入口に認証を置くこと

## 1. 調査で確定した事実（進行記録の制約表を改訂）

| # | 事実 | 帰結 |
|---|---|---|
| F-1 | **Tailscale Funnelは443・8443・10000の三ポートで公開できる**（Tailscale公式docs）。進行記録のC-1「443のみ」は誤り | ポート枯渇問題は存在しない。リバースプロキシもchat-pwa退避も不要 |
| F-2 | 4-2/4-3の失敗は手順の問題。`serve`を先に打つと「同一ポートはserveとfunnelを兼用できず、**最後に打ったコマンドが勝つ**」仕様に抵触。また`tailscale funnel --bg 8443`は「ローカル8443番を443で公開」の意味になる | 正しくは一発で `tailscale funnel --bg --https=8443 http://127.0.0.1:8766` |
| F-3 | 進行記録§6の現況では **443のFunnelが127.0.0.1:10000を向いており、chat-pwa（8787）への転送が失われている** | chat-pwaの公開URLは現在断線中の可能性が高い。緊急復旧が必要（§5） |
| F-4 | claude.aiカスタムコネクタはOAuth 2.1（DCR+PKCE）必須。C-3は正しい。OAuthスタブは実装済・ローカル全PASS | 到達性（F-1/F-2）さえ直せば検証可能 |
| F-5 | ChatGPTはDeveloper Modeのカスタムコネクタでリモート MCP に接続可能（有料プラン・HTTPS必須・OAuthまたは認証なし・Streamable HTTP/SSE両対応） | OAuth経路をclaude.ai専用にせず、クライアント非依存にすれば両対応できる |
| F-6 | **消費者向けGeminiアプリにはカスタムMCPコネクタがない**。Gemini系からの接続はAntigravity CLI/IDE・Gemini API・Android Studio・Gemini Enterprise経由。個人向けGemini CLIは2026-06に終了しAntigravity CLIへ移行。Gemini Enterprise系カスタムMCPは**Streamable HTTPのみ対応（旧SSE非対応）** | 「GeminiからのMCPアクセス」はヘッダー設定可能なローカルクライアント（Antigravity等）で満たす。これらはBearerヘッダー直挿しで足りる |
| F-7 | MCP標準トランスポートはStreamable HTTPへ移行済み。SSEはレガシー | 新規実装はStreamable HTTPを主とし、SSEは互換で残す |

## 2. 現OAuthスタブの欠陥（D-1・要修正）

現実装は `/register` が**呼んだ者全員に**client_secret（=claude-ai用トークン）を返し、`/authorize` が**自動承認**する。つまり公開網では、URLを知る第三者がOAuthの手続きを完走するだけでaccess_tokenを取得できる。**実質無認証**であり、要求3に反する。

修正方針: `/authorize` を自動承認から**承認画面方式**へ変える。認可リクエストが来るとブラウザに画面が開き（この画面を開くのは接続操作をしている本人＝ショウゴさんまたはゲスト）、`data/auth_tokens.yaml` のトークンの入力を要求する。有効なトークンが入力された場合のみ認可コードを発行する。これでOAuthの入口が既存のトークン台帳（本人用・期限付きゲスト用）に一本化される。

## 3. アーキテクチャ

### 3.1 ポート配分（Funnel三枠の使い切り）

| 公開ポート | 転送先 | 用途 | 認証 |
|---|---|---|---|
| 443 | 127.0.0.1:8787 | chat-pwa（現状復旧・変更なし） | 既存のまま |
| 8443 | 127.0.0.1:8766 | MCP（Streamable HTTP主・SSE従）+ OAuthエンドポイント | OAuth（承認画面方式）＋Bearerヘッダー直（併存） |
| 10000 | 127.0.0.1:8501 | ゲスト用ブラウザUI（Streamlit） | トークンゲート（§3.3） |

新規プロセスはゲストUI分のStreamlit常駐のみ。リバースプロキシ・新ベンダー（ngrok/Cloudflare）は導入しない。

### 3.2 MCP認証の二経路併存

- **OAuth経路**: claude.ai・ChatGPTカスタムコネクタ用。DCR・PKCE・承認画面（§2）。特定クライアント名への依存を排し、クライアント非依存に実装する
- **Bearer直経路**: Antigravity CLI・Claude Code・その他ヘッダーを設定できるクライアント用。既存の`_AuthRateLimitMiddleware`をそのまま使う

### 3.3 ゲスト用ブラウザUI

既存Streamlit（app.py）の前段にトークンゲートを置く。初回アクセスでトークン入力→検証→セッション確立。トークンは `data/auth_tokens.yaml` のゲストトークン（ID付き・期限付き・失効可能）を流用し、MCPとUIで台帳を共用する。ゲストに渡すのは「URL＋トークン」の二点のみ。

デバッグ用サイドバー（コスト・設定変更）はゲストには不要かつ危険（モデル切替でコスト増）なので、ゲストトークンでは**閲覧・質問のみ**に制限する。

### 3.4 コスト統治（P-9適用）

ゲストとAIクライアントの質問は裏でLLM実行を伴う。既存のレート制限（10req/分/IP）に加え、**日次実行回数の上限**（全体・トークン別）を設ける。上限到達時は明示的なエラーメッセージで拒否する。OpenRouterアカウント上限（$1/日）が最終防壁として既に効いている。

## 4. 作業分解（M7bとしてPMへ引き渡す粒度）

| W | 内容 | 難易度 | 備考 |
|---|---|---|---|
| W-1 | Streamable HTTPトランスポート追加（`/mcp`）。SSEは互換維持 | 小 | FastMCPの`streamable_http_app()`を使用 |
| W-2 | OAuth承認画面方式への改修（D-1解消）＋クライアント非依存化 | 中 | /registerは秘密を返さない設計へ |
| W-3 | Streamlitトークンゲート＋ゲスト権限制限 | 小〜中 | auth_tokens.yaml共用 |
| W-4 | 日次実行上限（全体・トークン別） | 小 | 決定的コードで実装（P-5） |
| W-5 | 手順書全面改訂（mcp-remote-setup.md）: 正しいFunnelコマンド・三ポート構成・各クライアント別接続手順（claude.ai／ChatGPT Developer Mode／Antigravity） | 小 | 実態と乖離した現行版を置き換え |

想定2便（W-1+W-2、W-3+W-4+W-5）。LLM追加コストなし（認証・ゲートは決定的コード）。

## 5. 発注者操作（承認後・順序厳守）

1. **緊急復旧**（承認前でも実施可）: `tailscale serve reset` で全設定をクリアし、`tailscale funnel --bg --https=443 http://127.0.0.1:8787` でchat-pwaを復旧。`tailscale serve status` で `(Funnel on)` と8787への転送を確認。Pixel 10でchat-pwaの疎通確認
2. W-1/W-2納品後: `tailscale funnel --bg --https=8443 http://127.0.0.1:8766` → claude.aiカスタムコネクタ登録（URL: `https://fraine.tail204746.ts.net:8443/mcp`）→ 承認画面で本人トークン入力
3. W-3納品後: `tailscale funnel --bg --https=10000 http://127.0.0.1:8501` → ゲストURL疎通確認

## 6. 裁定事項（承認が必要な点）

1. ポート配分（§3.1）の承認
2. ゲストのブラウザ経路: **Funnel＋トークンゲート**案でよいか。代替はTailscale共有招待（公開面ゼロだがゲストにTailscaleインストールを強いる）
3. Gemini経路の解釈: 消費者向けGeminiアプリは接続不可（F-6）のため、**Antigravity等のヘッダー設定可能クライアントで「Gemini系からのアクセス」を満たす**ことでよいか
4. OAuth承認画面方式（自動承認の廃止・§2）の承認

## 改訂履歴

- v2（2026-08-16）: M7a差し戻しを受け顧問が起草。C-1棄却（Funnel三ポート対応の確認）、D-1（OAuthスタブの実質無認証）の指摘、ブラウザ要求の要件への明記、三ポート配分案
