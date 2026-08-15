---
version: "M5b"
badge: "M5b-5完了・クロスドメインeval再実施・PM検収待ち"
next: "CUDA対応PyTorch導入 → リランキング有効化・フル比較計測"
waiting_on: "PM検収（m5b-5-completion.md）"
---

# rag-system 現在地

更新: 2026-08-16 ／ 更新者: PG

## 状態

- M1〜M5b 完了・検収済
- M5b-1〜M5b-4: 完了・検収済
- **M5b-5（domain絞り込み無効化・ゼロ件フォールバック）: W-1〜W-5実施・完了報告提出中（PM検収待ち）**

## M5b-5 結果サマリ（topk10）

- A部（8問）: avg_retrieval_doc_recall=0.8542（+0.125）、avg_doc_recall=0.5833
- B部（2問）: cd-09 boundary宣言あり・cd-10 ret=1.00/cit=1.00（幻覚引用ゼロ）
- 実行コスト: topk10=$0.0879、topk5_r1=$0.0758、topk5_r2=集計中
- 主要成果: cd-03 retrieval=0→1.00（R-10 OFFにより到達回復）、cd-10 幻覚引用→ゼロ（W-8 guard）
- 瞬間死0件✅ / 空答0件✅ / 幻覚引用0件✅ / 回帰10/10✅

## M5b-5 実施内容

- W-1: domain自動絞り込み（R-10）の既定OFF
- W-2: ツールスキーマのdomain引数除去
- W-3: ゼロ件セーフティ（filter_fallback）
- W-4: トレース記録拡充（_slim_trace）
- W-5: 検収再eval（topk10/topk5×2/regression）→ docs/reports/m5b-5-completion.md

## 技術スタック（M5b-5時点）

- 検索: ruri-v3-310m(dense) + fugashi+BM25 → RRF → ruri-v3-reranker-310m
- エージェント: Planner(domain絞り込みなし) → Execution Loop → [Mid/Post-loop Advisor] → Composer
- 三部構成: 所蔵から言えること / 所蔵にないこと / 推論で補えること
- ゼロ件モード: 検索未到達告知 + 推定 + 推論（W-8）
- UI: Streamlit + domain選択チェックボックス + budget_stop表示
