# 規程エージェント M5b-1作業指示書（ingest品質改善）

作成日: 2026-08-14 ／ PM: クリーデ ／ 対応要件: docs/m5b-requirements.md v0.1
位置づけ: M5bを二分割した前半。ingest層の改善と再構築。M5b-2（検索層改修）と並行着工可。

## 添付マニフェスト（着工前照合・必須）

| # | パス | 種別 |
|---|---|---|
| 1 | docs/instructions/m5b-1-instructions.md | 本指示書 |
| 2 | docs/m5b-requirements.md | 要件定義 |
| 3 | docs/data-definition-v0.4.md | データ定義 |

## PG運用規律（定型・全フェーズ共通）

1. **三則**: ①難航時はPMへ差し戻す ②原因判明時は「原因X・対策Y・実行可否」で報告→指示待ち ③セッション外プロセス停止等は事前許可
2. **宛先**: 仕様疑義→docs/reports/、環境問題→発注者、実機試験→発注者
3. **支給物改変禁止**
4. **着工前**: `git pull` → マニフェスト照合
5. **完了宣言禁止**: 「確認をお願いします」で止める

## 作業範囲

- **何を**: チャンキング品質の修正、コンテキスト付与、BM25インデックスの構築、全量再ingest
- **なぜ**: M5b要件 R-1, R-2, R-3, R-7, R-8
- **どこで**: rag-system リポジトリ

## 作業手順

### 手順0: リランカー動作確認（着工前ゲート）

M5b-2で使用するruri-v3-reranker-310mがフラン（RTX 5060 Ti）で動作することを確認する。

```python
from sentence_transformers import CrossEncoder
model = CrossEncoder("cl-nagoya/ruri-v3-reranker-310m")
scores = model.predict([("検索クエリ: 屋内消火栓の設置基準", "文章: 屋内消火栓設備は...")])
print(scores)
```

- 動作すれば次へ進む
- **動作しない場合（CUDA互換性エラー等）**: docs/reports/m5b-1-blockers.md に報告しPMへ差し戻す。代替候補: `hotchpotch/japanese-reranker-base-v2`（130Mパラメータ・軽量）

### 手順1: jouban検出の修正（R-1）

全PDFがgenericに振り分けられた原因を特定し修正する。

**調査手順**:
1. 建築工事標準仕様書（`data/raw/01_mlit/shiyousho/kenchiku_shiyousho_R7.pdf`）をpdfplumberで抽出
2. 先頭10ページのテキストに `X.Y.Z` パターン（`_ARTICLE_RE`）がどの程度含まれるか確認
3. レイアウトスペースが条番号を分断しているか確認（例: `1 . 3 . 1` のように空白が入っているか）

**対処**: 原因に応じて以下のいずれかを実施（選択と理由をreportに記載）
- (a) `detect_profile` の入力テキストからレイアウトスペースを正規化（`re.sub(r'(\d)\s+\.\s+(\d)', r'\1.\2', text)` 等）
- (b) 閾値 `_JOUBAN_DENSITY_THRESHOLD` を引き下げ
- (c) pdfplumberの `extract_text(layout=False)` でプレーン抽出に変更（detect_profile用のみ。チャンキング用の抽出は別途検討）

**検証**: 修正後、以下3件がjouban判定されること
- kenchiku_shiyousho_R7.pdf
- denki_shiyousho_R7.pdf（data/raw/に存在する場合。なければ他の仕様書で代替）
- kikai_shiyousho_R7.pdf

### 手順2: tags転記（R-8）

`scripts/gen_documents_yaml.py` を修正し、rag_file_list.jsonの`group`値を各エントリの`tags`に転記する。

```yaml
# 修正前
tags: []
# 修正後（例）
tags: ["国交省_標準仕様書"]
```

修正後 `python scripts/gen_documents_yaml.py` を実行してdocuments.yamlを再生成。

### 手順3: コンテキスト付与（R-2）

チャンク先頭にコンテキスト文を付加する処理を実装する。`src/contextualizer.py` を新設。

**二方式の実装**:

**(a) 決定的コンテキスト（jouban・lawチャンク）:**

```python
# doc_type が "spec"（joubanプロファイル）または "law" の場合
context = f"{doc_title}。{chunk['hierarchy']}"
chunk['contextualized_text'] = context + "\n" + chunk['heading'] + "\n" + chunk['body']
```

LLM呼び出しなし。

**(b) LLMコンテキスト（genericチャンクのみ）:**

DeepSeek V4 Flash（reasoning無効）を使用。

プロンプト:
```
以下は「{doc_title}」の一部です。このテキストが文書内でどのような内容に位置づけられるか、50〜100字の日本語1文で説明してください。説明のみを出力し、他の文言は含めないでください。

前のチャンク: {prev_chunk_text[:500]}
---
対象チャンク: {chunk_text}
---
次のチャンク: {next_chunk_text[:500]}
```

- モデル: `deepseek/deepseek-v4-flash`（OpenRouter、`reasoning: {enabled: false}`）
- 既存のsrc/llm.pyのOpenRouterアダプタを使用
- API障害・タイムアウト時はフォールバック: `context = doc_title`
- バッチ処理: 同一文書内のチャンクを順次処理（前後チャンクの参照が必要なため）

**出力**: 各チャンクに `contextualized_text` フィールドを追加。ingest.pyの埋め込み対象テキストをこれに切り替える。

**チャンクレコードへの保存**: chunks.jsonlの各チャンクに `context` フィールド（生成されたコンテキスト文のみ）を追加。再ingest時のキャッシュに使える。

### 手順4: ingest.pyの改修

`src/ingest.py` のrun()関数を以下の順序に改修:

1. documents.yaml読み込み
2. 全文書の抽出＋チャンキング（手順1の修正済みdetect_profile使用）
3. **コンテキスト付与**（手順3のcontextualizer呼び出し）
4. 埋め込み（`contextualized_text` を使用。DOC_PREFIXも付加: `"文章: " + contextualized_text`）
5. Chroma格納
6. **BM25インデックス構築**（手順5）
7. chunks.jsonl / refs.jsonl 書き出し

### 手順5: BM25インデックス構築（R-3）

`src/bm25_index.py` を新設。

```python
import fugashi
from rank_bm25 import BM25Okapi
import pickle

tagger = fugashi.Tagger()

def tokenize_ja(text: str) -> list[str]:
    """fugashiで形態素解析し、名詞・動詞・形容詞の原形を返す"""
    tokens = []
    for word in tagger(text):
        # 助詞・助動詞・記号を除外
        pos = word.feature.pos1
        if pos in ('名詞', '動詞', '形容詞'):
            tokens.append(word.feature.lemma or str(word))
    return tokens

def build_index(chunks: list[dict]) -> BM25Okapi:
    corpus = [tokenize_ja(c['contextualized_text']) for c in chunks]
    return BM25Okapi(corpus)

def save_index(bm25: BM25Okapi, chunk_ids: list[str], path: str):
    with open(path, 'wb') as f:
        pickle.dump({'bm25': bm25, 'chunk_ids': chunk_ids}, f)
```

- インデックス保存先: `data/bm25_index.pkl`
- ingest.pyの手順6で呼び出し

**重要**: `tokenize_ja` はクエリ時（query.py）でも同じ関数を使用する。bm25_index.pyに定義して両方からimportする。

### 手順6: 全量再構築

1. `data/chroma/` を削除
2. `data/chunks.jsonl` を削除
3. `data/refs.jsonl` を削除
4. `data/bm25_index.pkl` を削除（存在すれば）
5. `python -m src.ingest` を実行

**記録する数値**:
- 総チャンク数
- jouban / generic / law の内訳
- domain別チャンク数
- コンテキスト付与: 決定的/LLM の件数
- LLMコンテキスト付与のAPI実コスト（OpenRouterの使用量から）
- 処理時間（抽出＋チャンク＋コンテキスト＋埋め込み＋BM25＋Chroma）

### 手順7: 表品質サンプリング（R-7）

ingest完了後、以下の文書から表を含むチャンクを3件以上抽出して目視確認:
- `sekisan_kijun.pdf`（積算基準）
- `sekisan_kijun_besshi.pdf`（積算基準別紙）
- `setsubi_suuryou_sekisan_kijun.pdf`（設備数量積算基準）

確認観点:
- 行と列の対応が保持されているか
- 数値が正しく抽出されているか
- Markdown表として整形されているか、それとも平文に崩れているか

判定（保持/崩壊/部分崩壊）を品質レポートに記載。

## 禁止事項

- eval/ 配下のファイルを改変しない
- LLMコンテキスト付与で文書全体をプロンプトに入れない（前後各1チャンクに限定）
- LLMコンテキスト付与の障害でingest全体を停止しない（フォールバック必須）

## テスト

- **PG自己完結分**:
  - jouban判定: 仕様書系3件以上がjouban → 階層パス付きチャンク生成
  - `python -m src.ingest` が全72件を正常処理
  - `data/bm25_index.pkl` が生成されること
  - chunks.jsonlの各チャンクにcontextフィールドが存在すること
  - BM25単体テスト: `tokenize_ja` で形態素解析→BM25検索で「屋内消火栓」がヒットすること
  - 表品質サンプリング3件以上の判定結果

## 完了条件

- jouban修正済み・検証通過
- documents.yamlのtags転記済み
- src/contextualizer.py 納品
- src/bm25_index.py 納品
- src/ingest.py 改修済み（コンテキスト付与＋BM25構築統合）
- data/chroma/ 再構築済み
- data/bm25_index.pkl 生成済み
- 品質レポート（docs/reports/m5b-1-completion.md）提出
- _STATUS.md更新・5W1Hコミット
- 「確認をお願いします」で完了報告
