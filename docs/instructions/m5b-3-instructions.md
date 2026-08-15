# 規程エージェント M5b-3作業指示書（クロスドメインeval）

作成日: 2026-08-15 ／ PM: クリーデ ／ 対応要件: docs/m5b-requirements.md R-6の拡張
位置づけ: M5b検収後の残課題「eval横断化」。単独の小フェーズ。

## 添付マニフェスト（着工前照合・必須）

| # | パス | 種別 | 照合 |
|---|---|---|---|
| 1 | docs/instructions/m5b-3-instructions.md | 本指示書 | — |
| 2 | eval/questions_crossdomain.jsonl | **PM支給物・改変禁止** | SHA-256を完了報告に記載 |

## PG運用規律（定型）

M5b-1と同一。支給物（questions_crossdomain.jsonl）はdiffゼロで検収する。

## 背景（この評価の思想）

このevalは「優秀な調べ物係か」を測る。「優秀な技術者か」は測らない。

- RAGの職務は、問いに関係する規定を漏れなく集めて根拠付きで並べること（牧羊犬モデル: 判断材料の完全供給）
- 何を妥協するか等の設計判断はスコープ外。エージェントが根拠なき設計判断を語ることはむしろ減点対象
- コーパスにない基準は「ない」と正直に宣言することが正答

質問はA部（網羅性・8問）とB部（境界認識・2問）の二部構成。

## 作業範囲

- **何を**: クロスドメインevalの実行基盤を作り、10問を実行し、結果を報告する
- **なぜ**: 現行eval（電気単一文書出題）では横断検索・domainフィルタの効果を測定できないため
- **どこで**: rag-system リポジトリ

## 作業手順

### 手順1: 期待文書の事前検分（PM検分の代行実行）

eval実行の前に、各問の期待文書に実際に関連チャンクが存在するかを確認する。

各問の質問文で `search_chunks`（full mode・domainフィルタなし・top_k=20）を直接実行し、expected_docsの各doc_slugがtop-20に含まれるかを記録する。

- **含まれる**: eval実行可能
- **含まれない**: そのdoc_slugのチャンクを直接確認（chunks.jsonlをdoc_slugでgrep）し、関連する内容のチャンクが存在するか判定
  - チャンク自体が存在しない/関連内容がない → **docs/reports/に報告**。当該expected_docsはPMが修正する（支給物改変禁止のため、PGは修正せず差し戻す）
  - チャンクは存在するが検索でヒットしない → そのまま記録（それ自体がevalの発見）

特にcd-09の `kouzou-sekkei-shiryou-r3`（梁貫通の径制限の粒度）とcd-10の境界期待は、この検分の結果次第でPMが調整する。

### 手順2: 採点スクリプト作成

`eval/run_crossdomain_eval.py` を新設。

**A部（網羅性・8問）の採点:**

1. 各問を `submit_question`（エージェントパイプライン full 構成）で実行
2. トレースからsearch_chunksのヒットチャンクを収集し、引用に使われたdoc_slugを抽出
3. 指標:
   - **doc_recall** = |引用されたexpected_docs| / |expected_docs|（問ごと）
   - **retrieval_doc_recall** = |検索でヒットしたexpected_docs| / |expected_docs|（引用に至らなくても検索段でヒットしたか）
   - 集計: 全8問の平均
4. 回答テキストとトレースをeval/crossdomain_results/に問ごとに保存（PM検分用）

**B部（境界認識・2問）の採点:**

1. 同様にエージェントで実行し、回答とトレースを保存
2. 自動採点は**しない**。以下の観点メモを結果ファイルに添付してPM判定に回す:
   - expected_docsからの引用があるか（機械判定可能な部分のみ自動記録）
   - 回答に「根拠なし」「守備範囲外」「確認が必要」等の宣言が含まれるか（キーワード検出で参考情報として記録）
3. 最終判定はPMが回答全文を読んで行う

**共通:**
- 各問の実行コスト（トークン・$）を記録（P-9）
- モデルは既定構成（DeepSeek V4 Flash）

### 手順3: 実行と報告

1. 手順1の事前検分結果を報告（expected_docs修正が必要な問があれば、この時点で一旦停止してPM差し戻し）
2. 修正不要（または修正版支給後）→ 全10問を実行
3. 結果を docs/reports/m5b-3-completion.md に記載:
   - A部: 問ごとのdoc_recall / retrieval_doc_recall、全体平均
   - B部: 回答全文＋参考情報（PM判定待ちとして提出）
   - 全問の実行コスト合計
   - MISSしたexpected_docsの一覧と、検索段/引用段どちらで落ちたかの分析

## 禁止事項

- eval/questions_crossdomain.jsonl を改変しない（期待文書の修正はPMが行う）
- eval/questions.jsonl・questions_m5b.jsonl を改変しない
- B部の合否を自動判定しない（PM判定）

## テスト

- **PG自己完結分**:
  - run_crossdomain_eval.py が10問を完走すること（エラー0）
  - 結果ファイルが問ごとに保存されていること
  - A部の集計値が算出されていること

## 完了条件

- 手順1の事前検分結果報告
- eval/run_crossdomain_eval.py 納品
- eval/crossdomain_results/ に10問分の回答・トレース
- docs/reports/m5b-3-completion.md 提出
- _STATUS.md更新・5W1Hコミット
- 「確認をお願いします」で完了報告
