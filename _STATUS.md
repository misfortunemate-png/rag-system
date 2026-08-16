---
version: "M7a"
badge: "M7a完了・完了報告提出中（PM検収待ち）"
next: "M7b以降（PM指示書待ち）"
waiting_on: "PM検収（m7a-completion.md）"
---

# rag-system 現在地

更新: 2026-08-16 ／ 更新者: PG

## 状態

- M1〜M6-2 全フェーズ完了・検収済み
- **M7a（MCP HTTP化・認証・Tailscale Funnel）: W-1〜W-5実施・完了報告提出中（PM検収待ち）**
- 次マイルストーン: PM指示書待ち

## M7a 実施結果

- SSE接続（有効トークン）: PASS ✅
- 認証失敗（401）・ブロック（403）・レート制限（429）: PASS ✅
- sleep(3)遅延: PASS (elapsed=3.0s) ✅
- 入力サイズ打ち切り・doc_slugバリデーション: PASS ✅
- stdio回帰: PASS ✅
- Tailscale Funnel疎通: 発注者操作が必要（手順書 docs/mcp-remote-setup.md に記載）

## M7a 追加実装

| 項目 | 内容 |
|---|---|
| W-1 | mcp_server.py: --transport sse 引数、SSE ASGIアプリ、uvicorn起動 |
| W-2 | _AuthRateLimitMiddleware（Bearer認証・レート制限・ブルートフォース抑止）、入力truncation、doc_slugバリデーション |
| W-3 | start-mcp-remote.bat、data/auth_tokens.yaml.example、.env.example/.gitignore更新 |
| W-4 | docs/mcp-remote-setup.md（Tailscale Funnel・claude.ai・ゲスト管理・ローテーション手順） |
| W-5 | HTTP疎通確認（9項目全PASS） |

## 技術スタック（M7a完了時点）

- 検索: ruri-v3-310m(dense) + fugashi+BM25 → RRF → ruri-v3-reranker-310m
- エージェント: Planner → Loop → Advisor → Web照合（法令API含む） → Composer
- **公開: SSE HTTP（0.0.0.0:8766）→ Tailscale Funnel → claude.ai カスタムコネクタ**
- **認証: Bearer token（data/auth_tokens.yaml）・レート制限・ブルートフォース抑止**
- stdio: Claude Codeローカル利用として引き続き動作
