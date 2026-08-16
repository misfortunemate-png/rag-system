---
version: "M6-1"
badge: "M6-1完了・完了報告提出中（PM検収待ち）"
next: "M6-2（Web照合 eval・品質検証）"
waiting_on: "PM検収（m6-1-completion.md）"
---

# rag-system 現在地

更新: 2026-08-16 ／ 更新者: PG

## 状態

- M1〜M5b 全フェーズ完了・検収済み
- M5c（ローカルMCPサーバー化）: 完了・検収済み
- **M6-1（Web照合ツール実装・パイプライン統合）: W-1〜W-7実施・完了報告提出中（PM検収待ち）**
- 次マイルストーン: M6-2（Web照合 eval・品質検証）— 指示書待ち

## M6-1 実施結果（疎通確認）

- web_search（DuckDuckGo）: 3件取得 ✅
- fetch_and_extract + tier判定: mlit.go.jp → tier=1 ✅
- パイプライン統合: _run_web_search_stage 動作確認・クラッシュなし ✅
- パイプラインOFF: M5b同等動作 ✅
- MCPツール web_search_tool: 疎通確認 ✅

## M6-1 追加実装

| 項目 | 内容 |
|---|---|
| W-1 | src/web_search.py (Google/DuckDuckGo/SearXNG) |
| W-2 | src/web_fetch.py (trafilatura + BS4 fallback) |
| W-3 | data/web_tiers.yaml (tier_1: go.jp系 5ドメイン) |
| W-4 | agent.py パイプライン統合（advisor conclude 発動） |
| W-5 | mcp_server.py web_search_tool |
| W-6 | トレース記録・eval JSON に web_search_used / web_results |

## 技術スタック（M6-1完了時点）

- 検索: ruri-v3-310m(dense) + fugashi+BM25 → RRF → ruri-v3-reranker-310m（top_k=5 既定）
- エージェント: Planner(domain絞り込みなし) → Execution Loop → [Mid/Post-loop Advisor] → **[Web照合]** → Composer
- Web照合: 発動条件=アドバイザーconclude+missing_coverage / バックエンド=DuckDuckGo既定（Google/SearXNG切替可）
- 三層格付け: tier_1（官公庁等）/ tier_2（技術解説系）/ tier_3（その他）
- 三部構成: 所蔵から言えること / 所蔵にないこと / 推論で補えること
- ゼロ件モード: 検索未到達告知 + 推定 + 推論（W-8）
- 空答ガード: コンポーザー空答リトライ（1回）→ 定型文フォールバック
- UI: Streamlit + domain選択チェックボックス + budget_stop表示
