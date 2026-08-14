# M5b-1 完了報告（ingest品質改善）

作成日: 2026-08-15

## 1. 作業サマリ

| 項目 | 内容 |
|---|---|
| 対象 | rag-system M5b-1（ingest品質改善） |
| 要件 | R-1（jouban検出修正）, R-2（コンテキスト付与）, R-3（BM25）, R-7（表品質）, R-8（tags転記） |
| 文書数 | 72（PDF 64 + XML 8） |
| 総チャンク数 | **9,644** |

## 2. チャンク集計

### プロファイル別

| profile | チャンク数 | 備考 |
|---|---|---|
| jouban（条番号型） | 3,083 | M5aでは0件 → 修正後に仕様書系が正しく判定 |
| generic（汎用型） | 4,541 | |
| law（法令XML） | 2,020 | 変化なし |
| **合計** | **9,644** | M5aの13,714から減少（joubanチャンキングは粒度が大きい） |

### domain別

| domain | チャンク数 |
|---|---|
| 電気 | 2,851 |
| （空文字列） | 2,571 |
| 建築 | 1,579 |
| 機械 | 759 |
| 設計 | 731 |
| 消防 | 603 |
| 塗装 | 386 |
| 衛生 | 164 |

## 3. jouban検出の修正（R-1）

### 原因

2件の不具合が重複していた:

1. `_ARTICLE_RE` が `re.MULTILINE` なしでコンパイルされていたため、`findall()` の `^` アンカーが文字列先頭にしかマッチしなかった（ページあたり最大1件）
2. 密度の分母が `total_chars`（文字数）だったため、正しくマッチしても密度値が閾値0.015に到達しなかった

### 対処

- `detect_profile` 専用の検出正規表現 `_DETECT_ARTICLE_RE` を `re.MULTILINE` + 先頭空白許容 `\s*` で新設
- 密度の分母を `total_lines`（行数）に変更。閾値0.015は据え置き
- `chunk_pages` 側の `_ARTICLE_RE` は `.match(line)` で使用するため変更不要

### 検証結果

| 文書 | profile | チャンク数 |
|---|---|---|
| kenchiku_shiyousho_R7.pdf | **jouban** | 675 |
| kikai_shiyousho_R7.pdf | **jouban** | 539 |
| mokuzou_shiyousho_R7.pdf | **jouban** | 417 |
| kaishu_kenchiku_R7.pdf | jouban | 487 |
| kaishu_denki_R7.pdf | jouban | 328 |
| kaishu_kikai_R4.pdf | jouban | 220 |

仕様書系6件がjoubanに判定。要件の3件以上を達成。

## 4. tags転記（R-8）

`gen_documents_yaml.py` を修正し、`rag_file_list.json` の `group` 値を各エントリの `tags` に転記。72件すべてにtagsが付与された。

| tag | 件数 |
|---|---|
| 消防庁_点検基準 | 38 |
| 法令_eGov | 8 |
| 国交省_設計基準 | 8 |
| 国交省_標準仕様書 | 6 |
| 国交省_積算基準 | 6 |
| 経産省_電気基準 | 2 |
| 塗装仕様書 | 2 |
| 厚労省_ビル管法 | 1 |
| 業界団体 | 1 |

## 5. コンテキスト付与（R-2）

### 実装

`src/contextualizer.py` を新設。二方式:

**(a) 決定的コンテキスト**（jouban/law）: `{doc_title}。{hierarchy}` — LLM呼び出しなし。5,103件。

**(b) LLMコンテキスト**（generic）: DeepSeek V4 Flash（OpenRouter、reasoning無効）で前後各1チャンクを参照して50〜100字の位置づけ文を生成。API障害時はdoc_titleにフォールバック。4,541件（フォールバック0件）。

### コンテキスト例

| 種別 | chunk_id | context |
|---|---|---|
| spec | kenchiku-shiyousho-r7-0001 | 公共建築工事標準仕様書（建築工事編）令和7年版。1.1.1 |
| law | law-89a-1 | 電気事業法。第一章　総則/第一条 （目的） |
| generic | setsubi-sekkei-kijun-r6-0001 | このテキストは、国土交通省が…「建築設備設計基準 令和6年版」の表紙及び前文部分である。 |

### 埋め込み対象

`contextualized_text`（context + heading + body）に切り替え。Chroma格納テキストも同様。

## 6. BM25インデックス（R-3）

`src/bm25_index.py` を新設。fugashi（UniDic Lite）で名詞・動詞・形容詞のレンマを抽出し、`rank_bm25.BM25Okapi` でインデックス構築。

### テスト結果

```
BM25 search '屋内消火栓の設置基準' → 5 hits
  setsubi-sekkei-kijun-r6-0076: score=22.84
  kikai-shiyousho-r7-0440:      score=22.50
  law-90b-33:                   score=21.77
  bepyo-02-okunai-shoukasen-0007: score=21.50
  law-90c-44:                   score=21.21
```

建築設備設計基準・仕様書・消防法施行令・別表がヒット — 適切な結果。

## 7. 表品質サンプリング（R-7）

積算系PDF（sekisan_kijun, sekisan_kijun_besshi, setsubi_suuryou_sekisan_kijun）から5チャンクをサンプリング。

| # | chunk_id | pages | 判定 |
|---|---|---|---|
| 1 | sekisan-kijun-0001 | 1 | 崩壊（表紙、表なし） |
| 2 | sekisan-kijun-0003 | 2 | 部分崩壊（工事費構成図がレイアウトスペースで維持） |
| 3 | setsubi-suuryou-sekisan-kijun-0015 | 6 | 部分崩壊（数値含む本文、表罫線なし） |
| 4 | setsubi-suuryou-sekisan-kijun-0071 | 22 | 部分崩壊（数値含む本文、表罫線なし） |
| 5 | sekisan-kijun-besshi（全10チャンク） | — | 数値含有率が低く表構造なし |

**総合判定: 部分崩壊**

pdfplumber `layout=True` のレイアウトスペースで列位置は概ね維持されているが、Markdown表としては整形されていない。`extract_tables()` の結果はページ辞書の `tables` フィールドに格納されるが、チャンク本文には統合されていない（既存の設計制約）。

## 8. 処理時間

| 工程 | 所要時間 |
|---|---|
| 抽出＋チャンキング＋コンテキスト付与 | 14,782秒（4.1時間） |
| 埋め込み（ruri-v3-310m） | 7,197秒（2.0時間） |
| Chroma格納 | 11.3秒 |
| BM25構築 | 7.0秒 |
| **合計** | **21,998秒（6.1時間）** |

※コンテキスト付与時間の大部分はDeepSeek V4 Flash API呼び出し（generic 4,541件）。

## 9. テスト結果

| テスト項目 | 結果 |
|---|---|
| jouban判定: 仕様書系6件がjouban | **OK** |
| `python -m src.ingest` 全72件正常処理 | **OK** |
| `data/bm25_index.pkl` 生成 | **OK**（7.8 MB） |
| chunks.jsonl全チャンクにcontextフィールド | **OK**（9,644/9,644） |
| BM25単体テスト: 「屋内消火栓」ヒット | **OK**（5件） |
| 表品質サンプリング3件以上 | **OK**（5件、判定: 部分崩壊） |
| documents.yaml tags転記 | **OK**（72件全件） |

## 10. 納品物一覧

| ファイル | 内容 |
|---|---|
| `src/contextualizer.py` | コンテキスト付与モジュール（決定的+LLM二方式） |
| `src/bm25_index.py` | BM25インデックス構築・検索モジュール |
| `src/chunker.py` | jouban検出修正済み（detect_profile） |
| `src/ingest.py` | コンテキスト付与＋BM25統合済み |
| `scripts/gen_documents_yaml.py` | tags転記対応 |
| `documents.yaml` | tags付き72エントリ |
| `data/chroma/` | 再構築済みChromaコレクション |
| `data/chunks.jsonl` | contextフィールド付き9,644チャンク |
| `data/bm25_index.pkl` | BM25インデックス（domain/doc_type付き） |

## 11. リランカー動作確認（着工前ゲート）

`cl-nagoya/ruri-v3-reranker-310m` がRTX 5060 Tiで正常動作を確認。スコア0.958（高関連度ペア）。M5b-2で使用可能。

## 12. 既知の課題・PM検査時の留意事項

- kenchiku_shiyousho_R7.pdf はjoubanチャンキングは正常動作するが、PDF上に「第X編」「第X章」「第X節」の見出し行が存在しないため、階層パスが条番号のみ（`1.1.1`）になる。kikai_shiyousho_R7.pdf は完全な階層パスが付く。
- 表品質は「部分崩壊」。pdfplumber `extract_tables()` の結果をチャンク本文に統合する改修は本マイルストーンのスコープ外。
- LLMコンテキスト付与のAPIコスト: DeepSeek V4 Flash × 4,541回。OpenRouterダッシュボードで実コストを確認願います。
