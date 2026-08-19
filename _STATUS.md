---
version: "m7c-2-done"
badge: "M7c-2完了"
next: "次マイルストーン指示書待ち"
waiting_on: "指示書"
---

# rag-system 現在地

更新: 2026-08-19 ／ 更新者: PG

## 状態

- M1〜M7b-2 全フェーズ完了・検収済み
- Phase 2（Funnel配置変更）: 実施済み
- hotfix-3: H-Aのみ適用で完了
- M7c-1: ツール削減・docstring改訂・UI表記修正 完了
- **M7c-2: 進捗報告・永続化・フィードバック・レート制限 完了**

## M7c-2 実施結果

| W | 内容 | 結果 |
|---|---|---|
| W-3 | get_answer進捗報告（agent.py progress_cb + mcp_server.py stage/detail/hint） | 完了 ✅ |
| W-4 | 回答永続化（data/answers/YYYY-MM.jsonl + .gitignore） | 完了 ✅ |
| W-5 | report_feedback突合強化（メモリ→永続化ファイル→空の三段解決） | 完了 ✅ |
| W-6 | レート制限再設計（BF→認証→auth_idレート、60/分） | 完了 ✅ |

## PG自己テスト結果

- agent.py progress_cb後方互換: ✅（全デフォルトNone）
- mcp_server.py構文・W-4/W-5/W-6設定確認: ✅
- ゲストUI回帰: ✅（app.pyインポート正常）

## 技術スタック

- 検索: ruri-v3-310m(dense) + fugashi+BM25 → RRF → ruri-v3-reranker-310m
- エージェント: Planner → Loop → Advisor → Web照合（法令API含む） → Composer
- 公開: SSE `/sse` + Streamable HTTP `/mcp`（0.0.0.0:8766）→ Tailscale Funnel HTTPS 443
- httpツール公開: submit_question / get_answer / report_feedback の3本のみ
- **get_answer進捗: stage/detail/hintフィールド追加（W-3）**
- **回答永続化: data/answers/YYYY-MM.jsonl（W-4）**
- **レート制限: auth_idベース60/分（W-6）**
- 認証: OAuth 2.1承認画面方式（auth_tokens.yaml統合）+ Bearer直経路（既存互換）
- ブラウザUI: Streamlit（0.0.0.0:8501）→ Tailscale Funnel HTTPS 8443・トークンゲート実装
- stdio: Claude Codeローカル利用（全8ツール）
