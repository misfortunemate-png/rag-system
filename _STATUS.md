---
version: "M5b-2"
badge: "M5b-2 検索層改修完了・hybrid+rerank実装済み"
next: "CUDA PyTorch導入→full mode完全計測"
waiting_on: "PM検収"
---

# rag-system 現在地

更新: 2026-08-15 ／ 更新者: PG（M5b-2完了報告）

## 状態

- M1〜M5a 完了・検収済
- M5b-1（ingest品質改善）: **実装完了・PM検収待ち**
- M5b-2（検索層改修）: **実装完了・PM検収待ち**
  - ハイブリッド検索: dense(ruri-v3-310m) + BM25(fugashi) + RRF融合
  - リランカー: ruri-v3-reranker-310m（heading+body入力、2000文字切り詰め）
  - domain選択UI: 9分野チェックボックス（建築/電気/機械/設計/消防/塗装/衛生/その他/法令）
  - Planner domain絞り込み: relevant_domains出力 × ユーザー選択の積集合
  - MCPツール: domains引数追加
  - retrieval eval: hybrid MRR +28%改善（0.4641→0.5946）、rerank スポット検証で改善確認
  - 回帰テスト: 10問パイプライン正常動作（5正答/5守備範囲外/0エラー）

## 直近の経緯

- M5b-1完了（2026-08-15）: 9,644チャンク・BM25構築済み
- M5b-2実装・テスト（2026-08-15）:
  - hybrid検索・リランカー・domain UI・Planner絞り込み・MCPツール改修
  - 「その他」→""変換追加（tools.py + bm25_index.py）
  - リランカー入力をcontextualized_text→heading+bodyに修正（品質改善）
  - retrieval eval A/B比較: dense/hybrid 完了、full スポット検証
  - 回帰テスト: 10問完走・正常動作確認

## 次の見通し

- M5b-1 + M5b-2 PM検収
- CUDA対応PyTorch導入 → full mode retrieval eval完全計測
- M7b（リモートMCP）: 入り方の安全方針と発注者裁定待ち
