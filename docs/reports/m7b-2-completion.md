# M7b-2 完了報告

報告日: 2026-08-17 ／ PG → PM（クリーデ）

## 実施内容

W-3・W-4・W-5をすべて実装しました。確認をお願いします。

---

## W-3: Streamlitトークンゲート＋ゲスト権限制限

### 変更ファイル
- `app.py`

### 実装概要

- 未認証時: タイトルとトークン入力欄（password型）・ログインボタンのみ表示。認証成功時に `st.rerun()`
- トークン検証: `src/mcp_server.py` の `_load_auth_tokens()` をインポートして使用。期限切れの場合は YAML を二次確認してエラーメッセージを区別
- ゲストモード（`auth_id` が `guest-` で始まる場合）: サイドバーコンテンツを描画しない、コスト・デバッグ・エージェントトレースを非表示、タイトルに「（ゲスト）」付記
- 管理者モード: 従来動作と同一
- ログアウト: 管理者はサイドバー下部、ゲストはヘッダー横に配置
- `st.set_page_config(initial_sidebar_state="collapsed")` に変更

---

## W-4: 日次実行上限

### 変更ファイル
- `src/mcp_server.py` — `DAILY_QUERY_LIMIT` 定数・`_daily_query_count()` 関数・`submit_question` 冒頭チェック追加
- `app.py` — `_daily_query_count()`・`_log_job_submitted()` 追加、チャット送信冒頭チェック追加
- `.env.example` — `MCP_DAILY_QUERY_LIMIT=50` 追記

### 実装概要

- 上限値: 環境変数 `MCP_DAILY_QUERY_LIMIT`（既定: 50）
- カウント基準: `logs/{YYYY-MM-DD}.log` の `job_submitted` イベント数（MCP側・Streamlit側の両方が同一ログに記録）
- MCP側: `submit_question` の冒頭で上限チェック。到達時は `{"error": "daily_limit", ...}` を返す
- Streamlit側: チャット送信の冒頭で上限チェック。到達時は `st.warning(...)` を表示
- Streamlit起点のクエリも `_log_job_submitted()` で `job_submitted` イベントを記録し、MCP側と合算カウントされる

---

## W-5: 手順書全面改訂

### 変更ファイル
- `docs/mcp-remote-setup.md`

### 実装概要

三ポート構成（MCP 8443・ゲストUI 10000・chat-pwa 443）を正として全面書き直し。以下の章立てに整備:

1. 概要（三経路一覧）
2. 前提（Tailscale・auth_tokens.yaml）
3. Tailscale Funnel 設定（三ポート一発設定）
4. サーバー起動手順
5. MCP接続手順 — claude.ai
6. MCP接続手順 — ChatGPT
7. MCP接続手順 — CLIクライアント
8. ブラウザUI（ゲスト向け）
9. ゲスト招待手順
10. トークン管理（追加・失効・ローテーション）
11. トラブルシューティング

---

## その他変更

- `start.bat`: `--server.port 8501` を追加
- `_STATUS.md`: M7b-2完了状態に更新
- `CLAUDE.md`: 次マイルストーン欄を更新

---

## テスト結果

| # | テスト内容 | 結果 |
|---|---|---|
| 1 | 未認証時ログイン画面のみ表示 | PASS ✅ |
| 2 | 管理者トークン入力 → サイドバー付き通常UI | PASS ✅ |
| 3 | guest-プレフィクスのトークン → ゲストモード（サイドバー非表示） | PASS ✅ |
| 4 | 無効トークン → エラーメッセージ・再試行可能 | PASS ✅ |
| 5 | 期限切れトークン（expires=2024-01-01） → 専用エラーメッセージ | PASS ✅ |
| 6 | MCP_DAILY_QUERY_LIMIT=2 での3回目拒否（MCP側・Streamlit側の両方） | PASS ✅ |
| 7 | stdio回帰（import・シグネチャ・daily_limit実装確認） | PASS ✅ |
| 実機1 | Funnel疎通・モバイル回線からゲストUI表示 | 発注者依頼 |
| 実機2 | ゲストトークンでログイン → 質問 → 回答表示 | 発注者依頼 |

---

以上、テスト項目1〜7の自己確認が完了しました。実機系（Funnel疎通・モバイル）は発注者にお願いします。確認をお願いします。
