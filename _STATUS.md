---
version: "M7b-1"
badge: "M7b-1完了・確認待ち"
next: "M7b-2（W-3+W-4+W-5）"
waiting_on: "PM検収（m7b-1-completion.md）"
---

# rag-system 現在地

更新: 2026-08-17 ／ 更新者: PG

## 状態

- M1〜M7a 全フェーズ完了・検収済み
- **M7b-1（Streamable HTTP化・OAuth承認画面方式）: 実施・確認待ち**
- 次マイルストーン: M7b-2（W-3+W-4+W-5）

## M7b-1 実施結果

| テスト | 結果 |
|---|---|
| メタデータ（token_endpoint_auth_methods_supported=["none"]） | PASS ✅ |
| /register（client_secret返さない） | PASS ✅ |
| GET /authorize → HTML承認画面 | PASS ✅ |
| POST /authorize 無効トークン → エラー再表示+3s遅延 | PASS ✅ |
| POST /authorize 有効トークン → 302リダイレクト+code | PASS ✅ |
| POST /token → access_token（token_idから取得） | PASS ✅ |
| SSE接続（Bearer） | PASS ✅ |
| Streamable HTTP /mcp（Bearer） | PASS ✅ |
| stdio回帰（--transport {stdio,http}） | PASS ✅ |
| 実機系（Tailscale・claude.ai） | 発注者依頼 |

## M7b-1 実装内容

| W | 内容 |
|---|---|
| W-1 | Streamable HTTP `/mcp` 追加（anyio lifespan fanout対応） |
| W-2 | OAuth承認画面方式（D-1解消）: /authorize GET→HTML/POST→検証, /register client_secret除去, /token token_id対応 |

## 技術スタック（M7b-1完了時点）

- 検索: ruri-v3-310m(dense) + fugashi+BM25 → RRF → ruri-v3-reranker-310m
- エージェント: Planner → Loop → Advisor → Web照合（法令API含む） → Composer
- **公開: SSE `/sse` + Streamable HTTP `/mcp`（0.0.0.0:8766）→ Tailscale Funnel**
- **認証: OAuth 2.1承認画面方式（auth_tokens.yaml統合）+ Bearer直経路（既存互換）**
- stdio: Claude Codeローカル利用として引き続き動作
