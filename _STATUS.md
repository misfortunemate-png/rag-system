---
version: "M5b"
badge: "M5b完了・クローズ・PM検収待ち"
next: "M5c（ローカルMCPサーバー化）— 指示書発行待ち"
waiting_on: "PM検収（m5b-6-completion.md）"
---

# rag-system 現在地

更新: 2026-08-16 ／ 更新者: PG

## 状態

- M1〜M5b 全フェーズ完了・検収済み
- **M5b-6（空答対処・M5bクローズ）: W-1〜W-3実施・完了報告提出中（PM検収待ち）**
- 次マイルストーン: M5c（ローカルMCPサーバー化）— 指示書待ち

## M5b 最終結果（M5b-6 topk5）

- A部（8問）: avg_retrieval_doc_recall=0.7917、avg_doc_recall=0.7292
- 空答: 0問 ✅（W-1 リトライ実地確認、cd-06 / 回帰 Q1 で発動）
- citation gap（ret>0 かつ cit=0）: 0問 ✅
- 回帰: 10/10 ✅

## M5b 全フェーズ通し主要成果

| フェーズ | 主要成果 |
|----------|---------|
| M5b-3 | クロスドメイン eval 整備・瞬間死発覚 |
| M5b-4 | アドバイザー再設計・三部構成・瞬間死ゼロ |
| M5b-5 | domain絞り込み無効化・cd-03 到達回復・cd-10 幻覚引用ゼロ |
| M5b-6 | 空答リトライ（W-1）・topk=5 既定・空答ゼロ |

## 技術スタック（M5b完了時点）

- 検索: ruri-v3-310m(dense) + fugashi+BM25 → RRF → ruri-v3-reranker-310m（top_k=5 既定）
- エージェント: Planner(domain絞り込みなし) → Execution Loop → [Mid/Post-loop Advisor] → Composer
- 三部構成: 所蔵から言えること / 所蔵にないこと / 推論で補えること
- ゼロ件モード: 検索未到達告知 + 推定 + 推論（W-8）
- 空答ガード: コンポーザー空答リトライ（1回）→ 定型文フォールバック
- UI: Streamlit + domain選択チェックボックス + budget_stop表示
