---
version: "M5b-2"
badge: "M5b-2 検索層改修（コード実装完了・M5b-1データ完成後テスト）"
next: "M5b-1完了後にテスト実行・eval計測"
waiting_on: "M5b-1（ingest品質改善・BM25インデックス構築）"
---

# rag-system 現在地

更新: 2026-08-14 ／ 更新者: PG（M5b-2実装）

## 状態

- M1〜M5a 完了・検収済
- M5b-2（検索層改修）: コード実装完了
  - search_chunks ハイブリッド化（密ベクトル＋BM25＋RRF融合＋リランキング）
  - settings.json に RRFパラメータ・rerank_enabled 追加
  - domain選択UI（Streamlit expander・9分野チェックボックス）
  - Planner domain絞り込み（R-10: relevant_domains出力・トレース記録）
  - MCP submit_question / search_chunks に domains 引数追加
  - eval/questions_m5b.jsonl（13問）・eval/run_retrieval_eval.py 納品
- M5b-1（ingest品質改善）: 並行作業中・BM25インデックス未構築

## 直近の経緯

- M5b要件定義・指示書発行（2026-08-14）
- M5b-2 コード実装着工・完了（同日）
- テスト実行はM5b-1のBM25インデックス構築完了後

## 次の見通し

- M5b-1完了後: BM25インデックス構築 → テスト実行 → eval計測（dense/hybrid/full A/B比較）
- 品質レポート提出 → PM検収
