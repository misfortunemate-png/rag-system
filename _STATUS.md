---
version: "M5b"
badge: "M5b-4完了・クロスドメインeval実施・PM検収待ち"
next: "cd-10幻覚引用確認 / cd-03検索失敗の原因分析 / CUDA PyTorch導入"
waiting_on: "PM検収（m5b-4-completion.md）"
---

# rag-system 現在地

更新: 2026-08-15 ／ 更新者: PG

## 状態

- M1〜M5b 完了・検収済
- M5b-1（ingest品質改善）: jouban修正（6件判定）、コンテキスト付与（決定的5,103+LLM4,541、$0.36）、BM25構築、tags転記
- M5b-2（検索層改修）: ハイブリッド検索（dense+BM25+RRF）、リランキング、domain選択UI（9分野）、Planner絞り込み、eval A/B比較
- M5b-3（eval横断化）: クロスドメイン10問実施・完了報告提出・検収済
- **M5b-4（アドバイザー再設計・三部構成）: W-1〜W-7実施・完了報告提出中（PM検収待ち）**

## M5b-4 結果サマリ（topk10）

- A部（8問）: avg_retrieval_doc_recall=0.7292、avg_doc_recall=0.6042
- B部（2問）: cd-09 boundary宣言なし、cd-10 boundary宣言あり（PM全文判定待ち）
- 実行コスト: topk10=$0.0611、topk5=$0.0945
- 主要成果: M5b-3での5問瞬間死→0件、cd-02 citation gap→解消
- 合格基準: 瞬間死0件✅ / citation gap 0件✅ / 完全拒否0件✅ / avg_doc_recall≥0.5✅

## 直近の経緯

- M5b-3→ループ前アドバイザー守備範囲外裁定が根本原因と特定（2026-08-15）
- M5b-4: W-1〜W-7実施 — ループ前裁定廃止・アドバイザー役割再設計・三部構成強制・スタール検知分離
- 単体テスト16件通過・dry-run正常・topk5/topk10/回帰eval全実施

## 次の見通し

- cd-10 幻覚引用（retrieval=0なのに §1 で kaishu-kenchiku-r7 を引用）の原因確認
- cd-03 kikai-shiyousho-r7 検索失敗の分析
- CUDA対応PyTorch導入 → リランキング有効化・フル比較計測
- M7b（リモートMCP）: 安全方針と発注者裁定待ち

## 技術スタック（M5b-4時点）

- 検索: ruri-v3-310m(dense) + fugashi+BM25 → RRF → ruri-v3-reranker-310m
- エージェント: Planner → Execution Loop → [Mid/Post-loop Advisor(replan/conclude)] → Composer
- 三部構成: 所蔵から言えること / 所蔵にないこと / 推論で補えること
- UI: Streamlit + domain選択チェックボックス + budget_stop表示
