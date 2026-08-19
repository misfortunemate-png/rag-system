---
version: "m7c-1-done"
badge: "M7c-1完了"
next: "M7c-2指示書待ち"
waiting_on: "指示書"
---

# rag-system 現在地

更新: 2026-08-19 ／ 更新者: PG

## 状態

- M1〜M7b-2 全フェーズ完了・検収済み
- Phase 2（Funnel配置変更）: 実施済み
- hotfix-3: H-Aのみ適用で完了
- **M7c-1: ツール削減・docstring改訂・UI表記修正 完了**

## M7c-1 実施結果

| W | 内容 | 結果 |
|---|---|---|
| W-1 | httpトランスポート: tools/listを3本に限定 | 完了 ✅ |
| W-2 | submit_question / get_answer / report_feedback docstring改訂 | 完了 ✅ |
| W-7 | ゲストUI「公共建築工事標準仕様書…」表記削除 | 完了 ✅ |

## W-1 実装方式

次点アプローチ採用: `_run_http()`内で`mcp.remove_tool()`（MCPServer公開API）を使い素材層5本を除去。`@mcp.tool()`デコレータによるimport時登録は維持し、HTTPモード起動時にのみ5本を削除する方式。パブリックAPIのため内部構造への依存なし。

## PG自己テスト結果

- stdioモード: 8ツール全て登録確認 ✅
- httpモード: remove_tool後3ツールのみ（submit_question / get_answer / report_feedback）確認 ✅
- ゲストUI: caption行削除・構文検証OK ✅

## 実機系テスト（発注者に依頼）

- T-1: claude.aiのコネクタ設定でツール一覧が3本のみ表示される
- T-2: submit_question → get_answer 完走（status: done、answer取得）
- T-3: OAuth認可フローが正常に動作する

## 技術スタック

- 検索: ruri-v3-310m(dense) + fugashi+BM25 → RRF → ruri-v3-reranker-310m
- エージェント: Planner → Loop → Advisor → Web照合（法令API含む） → Composer
- 公開: SSE `/sse` + Streamable HTTP `/mcp`（0.0.0.0:8766）→ Tailscale Funnel HTTPS 443
- **httpツール公開: submit_question / get_answer / report_feedback の3本のみ**
- 認証: OAuth 2.1承認画面方式（auth_tokens.yaml統合）+ Bearer直経路（既存互換）
- ブラウザUI: Streamlit（0.0.0.0:8501）→ Tailscale Funnel HTTPS 8443・トークンゲート実装
- stdio: Claude Codeローカル利用（全8ツール）
