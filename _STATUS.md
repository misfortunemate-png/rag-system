---
version: "M7b-hotfix2"
badge: "hotfix-2完了・確認待ち"
next: "—"
waiting_on: "発注者実機試験（コネクタ再登録→承認画面確認）"
---

# rag-system 現在地

更新: 2026-08-17 ／ 更新者: PG

## 状態

- M1〜M7b-1 全フェーズ完了・検収済み
- **M7b-2（W-3+W-4+W-5）: 実施・確認待ち**

## M7b-2 実施結果

| テスト | 結果 |
|---|---|
| 未認証時ログイン画面のみ表示 | PASS ✅ |
| 管理者トークンでサイドバー付きUI | PASS ✅ |
| guest-プレフィクスでゲストモード（サイドバー非表示） | PASS ✅ |
| 無効トークン → エラー・再試行可能 | PASS ✅ |
| 期限切れトークン → エラーメッセージ区別 | PASS ✅ |
| MCP_DAILY_QUERY_LIMIT=2 で3回目拒否（MCP側） | PASS ✅ |
| MCP_DAILY_QUERY_LIMIT=2 で3回目拒否（Streamlit側） | PASS ✅ |
| stdio回帰（--transport stdio） | PASS ✅ |
| 実機系（Funnel・モバイル） | 発注者依頼 |

## M7b-2 実装内容

| W | 内容 |
|---|---|
| W-3 | Streamlitトークンゲート・ゲストモード（サイドバー・コスト・デバッグ非表示） |
| W-4 | 日次実行上限（MCP_DAILY_QUERY_LIMIT・MCP側＋Streamlit側の両方） |
| W-5 | mcp-remote-setup.md 全面改訂（三ポート構成・ゲストUI手順追加） |

## 技術スタック（M7b-2完了時点）

- 検索: ruri-v3-310m(dense) + fugashi+BM25 → RRF → ruri-v3-reranker-310m
- エージェント: Planner → Loop → Advisor → Web照合（法令API含む） → Composer
- **公開: SSE `/sse` + Streamable HTTP `/mcp`（0.0.0.0:8766）→ Tailscale Funnel HTTPS 8443**
- **認証: OAuth 2.1承認画面方式（auth_tokens.yaml統合）+ Bearer直経路（既存互換）**
- **ブラウザUI: Streamlit（0.0.0.0:8501）→ Tailscale Funnel HTTPS 10000・トークンゲート実装**
- stdio: Claude Codeローカル利用として引き続き動作
