---
version: "M5b-1"
badge: "M5b-1 ingest品質改善完了・9,644チャンク・BM25構築済み"
next: "M5b-2テスト実行・eval計測"
waiting_on: "PM検収"
---

# rag-system 現在地

更新: 2026-08-15 ／ 更新者: PG（M5b-1完了報告）

## 状態

- M1〜M5a 完了・検収済
- M5b-1（ingest品質改善）: **実装完了・確認待ち**
  - jouban検出修正: 仕様書系6件がjouban判定（M5aでは全件generic）
  - コンテキスト付与: 決定的5,103件 + LLM(DeepSeek V4 Flash)4,541件 = 全9,644件
  - BM25インデックス構築: fugashi + rank_bm25、data/bm25_index.pkl生成
  - tags転記: documents.yaml全72件にgroup値を転記
  - 全量再構築: 9,644チャンク（jouban 3,083 / generic 4,541 / law 2,020）
  - 表品質サンプリング: 部分崩壊（layout=Trueスペースで列位置維持、Markdown表なし）
- M5b-2（検索層改修）: コード実装完了（別セッション）
  - テスト実行はM5b-1検収後

## 直近の経緯

- M5b-1指示書発行→PG着工（2026-08-14）
- リランカー動作確認OK（ruri-v3-reranker-310m、RTX 5060 Ti）
- jouban検出修正・tags転記・contextualizer新設・BM25新設
- .env のOPENROUTER_API_KEY読み込み修正（dotenv.load_dotenv()追加）
- 全量再構築完了（6.1時間、LLM API 4,541回含む）→ 2026-08-15

## 次の見通し

- M5b-1 PM検収
- M5b-2テスト実行: BM25インデックス構築完了済み → eval計測（dense/hybrid/full A/B比較）
- M7b（リモートMCP）: 入り方の安全方針と発注者裁定待ち
