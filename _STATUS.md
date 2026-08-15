---
version: "M5b"
badge: "M5b-3完了・クロスドメインeval実施・PM検収待ち"
next: "early-stop/引用ロジック改善 / CUDA PyTorch導入 / M5b数値目標再評価"
waiting_on: "PM検収（m5b-3-completion.md）"
---

# rag-system 現在地

更新: 2026-08-15 ／ 更新者: PG

## 状態

- M1〜M5b 完了・検収済
- M5b-1（ingest品質改善）: jouban修正（6件判定）、コンテキスト付与（決定的5,103+LLM4,541、$0.36）、BM25構築、tags転記
- M5b-2（検索層改修）: ハイブリッド検索（dense+BM25+RRF）、リランキング、domain選択UI（9分野）、Planner絞り込み、eval A/B比較
- **M5b-3（eval横断化）: クロスドメイン10問実施・完了報告提出中（PM検収待ち）**
- 72文書・9,644チャンク、hybrid MRR +28%（dense比）

## M5b-3 結果サマリ

- A部（8問）: avg_retrieval_doc_recall=0.375、avg_doc_recall=0.25
- B部（2問）: cd-09/cd-10 ともに守備範囲外宣言あり（PM判定待ち）
- 実行コスト: $0.0270 USD
- 主要発見: 5問で loops=1 の早期終了によりコーパス内の docs を検索未実施（検索段ギャップ）; cd-02 では全 expected_docs を取得したが引用ゼロ（引用段ギャップ）

## 直近の経緯

- M5b要件定義→顧問検証→M5b-1/M5b-2並行発令（2026-08-14）→翌日完了・検収
- リランカー入力をheading+bodyに修正（contextualized_textのコンテキスト接頭辞がcross-encoderを撹乱）
- 「その他」domain変換バグ修正済み
- 受入基準の数値目標（recall@10≥0.80, MRR≥0.70）は未達だが、eval横断化後も低値（avg doc_recall=0.25）
- early-stop 精度と引用ロジックが次の改善候補

## 次の見通し

- early-stop / 引用ロジック改善（M5b-3発見の主要課題）
- CUDA対応PyTorch導入 → full mode完全計測 + リランキング速度改善
- M7b（リモートMCP）: 安全方針と発注者裁定待ち
- M8b（積算支援・構想）: 表品質は部分崩壊と確認済み、歩掛表の構造化抽出が前提

## 技術スタック（M5b時点）

- 検索: ruri-v3-310m(dense) + fugashi+BM25 → RRF → ruri-v3-reranker-310m
- ingest: pdfplumber(PDF) + law_xml_ext(XML) → jouban/generic/law auto → contextualizer(決定的+DeepSeek) → embed+Chroma+BM25
- エージェント: Planner(domain絞り込み) → Advisor → Execution Loop → Composer
- UI: Streamlit + domain選択チェックボックス
