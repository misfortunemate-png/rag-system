# 規程エージェント M7b-2 作業指示書（ゲストUI・日次上限・手順書）

文書種別: 権威文書

作成日: 2026-08-16 ／ PM: クリーデ ／ 対応要件: docs/m7b-requirements-v2.md v2.1 ／ 本書一枚で完結（追補なし）

## 添付マニフェスト（着工前照合・必須）

以下がすべて交換所（リポジトリ）に存在すること。**1つでも欠けたら着工せず docs/reports/ に報告。**

| # | パス | 種別 | SHA-256 |
|---|---|---|---|
| 1 | docs/m7b-requirements-v2.md | 要件定義書 | — |
| 2 | docs/instructions/m7b-1-instructions.md | 前便指示書 | — |
| 3 | docs/reports/m7b-1-completion.md | 前便完了報告 | — |

前便（M7b-1）の検収完了後に着工すること。

## PG運用規律（定型・全フェーズ共通）

1. **三則**: ①難航時はPMへ差し戻す ②原因判明時は「原因X・対策Y・実行可否」で報告→指示待ち ③セッション外プロセス停止等は事前許可
2. **宛先**:
   - **仕様の疑義・技術判断** → docs/reports/ にpushしてPMへ
   - **環境・インフラの問題** → 発注者に直接聞いてよい
   - **実機試験の依頼・承認** → 発注者
3. **支給物改変禁止**: PM支給物はdiffゼロで検収される
4. **発注者指示による仕様外修正**: 実施してよい。報告時に「発注者の指示により実装/修正」と明記する
5. **着工前**: `git pull` → マニフェスト照合・版確認。不一致なら着工しない
6. **完了宣言禁止**: テスト結果を添えて「確認をお願いします」で止める

## 作業範囲

- 何を: (W-3) Streamlitトークンゲート＋ゲスト権限制限、(W-4) 日次実行上限、(W-5) 手順書全面改訂
- なぜ: ゲストのブラウザアクセスを実現し、コストを統治し、実態に合った手順書を整備するため
- どこで: misfortunemate-png/rag-system

## W-3: Streamlitトークンゲート＋ゲスト権限制限

### 目的

既存のStreamlit UI（app.py）にトークン認証を追加し、ゲストが安全にブラウザから利用できるようにする。ゲストにはサイドバーの設定変更（モデル切替等）を見せない。

### 実装

1. `st.session_state` に `authenticated` フラグと `auth_id` を持つ
2. 未認証時は以下のみ表示する:
   - 「規程エージェント」タイトル
   - テキスト入力欄（type="password"・placeholder="アクセストークンを入力"）
   - 「ログイン」ボタン
3. 送信されたトークンを `data/auth_tokens.yaml` で検証する:
   - **トークン読み込みは `src/mcp_server.py` の `_load_auth_tokens()` 関数を `import` して使う**（ロジックの二重実装を避ける）。ただし `_load_auth_tokens` がモジュールレベル変数に書き込む副作用を持つ場合は、純粋関数としてのラッパーを切り出すこと
   - 有効 → `st.session_state.authenticated = True` / `st.session_state.auth_id = token_id` でリロード
   - 無効 → `st.error("トークンが無効です")` 表示。ブルートフォース保護はStreamlit側では不要（リクエストレートがUI操作で律速されるため）
   - 期限切れ → `st.error("トークンの有効期限が切れています")` 表示
4. 認証済みの場合:
   - `auth_id` がゲストトークン（IDが `guest-` で始まる）の場合は**ゲストモード**:
     - サイドバーを非表示にする（`st.set_page_config(initial_sidebar_state="collapsed")` は既にセットされているため、ゲスト時はサイドバーコンテンツを描画しない）
     - チャット入力と回答表示のみ
     - モデル選択・設定変更・コスト表示・デバッグ情報を非表示
     - ページタイトルに「（ゲスト）」を付記
   - それ以外は**管理者モード**（現行動作と同一）
5. ログアウト機能: ヘッダーまたはサイドバー下部に「ログアウト」ボタン → `st.session_state` をクリアしてリロード

### ポート

Streamlitのデフォルトポートは 8501。起動コマンドは `streamlit run app.py --server.port 8501`。このポートは `start.bat` に既に反映されているか確認し、必要なら更新する。

### 制約

- StreamlitのUI構造（左チャット＋右根拠パネル）は変更しない
- 管理者モードの既存機能を削らない
- `data/auth_tokens.yaml` のフォーマットを変更しない

## W-4: 日次実行上限

### 目的

MCP経由（W-1/W-2）とStreamlit UI経由（W-3）の両方に共通する日次実行回数上限を設ける。OpenRouterアカウント上限（$1/日）が最終防壁だが、到達前にユーザーに明示的にエラーを返す。

### 実装

1. 環境変数 `MCP_DAILY_QUERY_LIMIT`（既定: 50）で日次上限を設定する
2. カウントは `logs/{YYYY-MM-DD}.log` の `job_submitted` イベント数で算出する（既存のログ基盤を流用。新しいストアを作らない）
3. 上限チェックの挿入箇所:
   - **MCP側**: `submit_question` ツール関数の冒頭。上限到達時は `"error": "daily_limit"` を含むdictを返す
   - **Streamlit側**: チャット送信ハンドラの冒頭。上限到達時は `st.warning("本日の実行上限（{n}回）に達しました。明日以降にお試しください。")` を表示
4. トークンID別の上限は**今回は実装しない**（全体上限で十分。要求があれば次便で追加）
5. `.env.example` に `MCP_DAILY_QUERY_LIMIT=50` を追記する

### 制約

- 日次リセットはログファイルの日付に依存（決定的コード。LLM不使用）
- 既存のコスト上限（`MCP_JOB_COST_CAP` / `MCP_DAILY_COST_CAP`）を削除しない（回数上限との併存）

## W-5: 手順書全面改訂

### 目的

`docs/mcp-remote-setup.md` を実態に合わせて全面改訂する。M7a時点の手順書はTailscale Funnel部分が実態と乖離している。

### 改訂内容

以下の構成で書き直す:

1. **概要**: rag-systemの三つのアクセス経路（MCP・ブラウザUI・stdioローカル）
2. **前提**: フラン・Tailscale・auth_tokens.yamlのセットアップ
3. **Tailscale Funnel設定**（三ポート構成）:
   ```
   tailscale funnel --bg --https=443 http://127.0.0.1:8787    # chat-pwa（既存）
   tailscale funnel --bg --https=8443 http://127.0.0.1:8766   # MCP
   tailscale funnel --bg --https=10000 http://127.0.0.1:8501  # ゲストUI
   ```
   - `tailscale serve status` で三ポートすべてが `(Funnel on)` であることを確認
   - 注意: `serve` と `funnel` を同一ポートに混在させない。`funnel` コマンド一発で設定する
4. **MCP接続手順 — claude.ai**:
   - 設定 → コネクタ → カスタムコネクタ追加
   - URL: `https://fraine.tail204746.ts.net:8443/sse`
   - ブラウザが開く → アクセストークンを入力 → 接続完了
5. **MCP接続手順 — ChatGPT**:
   - Developer Mode有効化（設定 → Apps → Advanced settings → Developer Mode ON）
   - 設定 → Connectors → Create → URL: `https://fraine.tail204746.ts.net:8443/sse`（または `/mcp`）
   - OAuth承認画面でトークン入力
6. **MCP接続手順 — Antigravity CLI / ローカルクライアント**:
   - Bearerトークンをヘッダーに直接設定
   - `Authorization: Bearer {token}`
7. **ブラウザUI（ゲスト向け）**:
   - URL: `https://fraine.tail204746.ts.net:10000`
   - トークン入力でログイン
8. **ゲスト招待手順**:
   - トークン生成: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
   - `data/auth_tokens.yaml` に `guest-{名前}` IDで追記（`expires` 設定推奨）
   - サーバー再起動
   - ゲストに渡すもの: URL＋トークン
9. **トークン管理**: 生成・追加・失効・ローテーション手順
10. **トラブルシューティング**: よくある問題と対処

### 制約

- 日本語で記述する
- ASCIIアート・Mermaidは使わない（Markdownの表とコードブロックのみ）

## 禁止事項

- 既存のstdioトランスポートを削除しない
- `data/auth_tokens.yaml` のフォーマット（id/token/expires構造）を変更しない
- Streamlitの既存の管理者向け機能を削除しない
- 認証なしでStreamlit UIにアクセス可能にしない
- LLMを認証・上限チェックに使わない（決定的コードで実装）

## テスト

### PG自己完結分

1. **トークンゲート**: Streamlit起動 → 未認証時にログイン画面のみ表示される
2. **有効トークン**: 管理者トークン入力 → サイドバー付きの通常UI
3. **ゲストトークン**: `guest-` IDのトークン入力 → サイドバーなし・チャットのみ
4. **無効トークン**: 誤入力 → エラーメッセージ・再試行可能
5. **期限切れ**: `expires` が過去日のゲストトークンで拒否される
6. **日次上限**: `MCP_DAILY_QUERY_LIMIT=2` に設定し、3回目の実行が拒否される（MCP側・Streamlit側の両方）
7. **回帰**: `--transport stdio` でClaude Codeから利用可能

### 実機系（発注者に依頼）

1. **Funnel疎通**: `tailscale funnel --bg --https=10000 http://127.0.0.1:8501` 後、Pixel 10のモバイル回線から `https://fraine.tail204746.ts.net:10000` にアクセスしてログイン画面が表示される
2. **ゲスト体験**: ゲストトークンでログイン → 質問 → 回答が表示される

## 完了条件

- W-3・W-4・W-5の実装
- テスト項目1〜7の結果
- `start.bat` にStreamlitのポート指定が含まれていること（`--server.port 8501`）
- `.env.example` に `MCP_DAILY_QUERY_LIMIT=50` が追記されていること
- docs/reports/m7b-2-completion.md 提出
- _STATUS.md・CLAUDE.md更新（フロントマター含む）
- 5W1Hコミット
- 「確認をお願いします」で完了報告
