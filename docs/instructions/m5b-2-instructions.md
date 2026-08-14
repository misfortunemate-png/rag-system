# 規程エージェント M5b-2作業指示書（検索層改修）

作成日: 2026-08-14 ／ PM: クリーデ ／ 対応要件: docs/m5b-requirements.md v0.1
位置づけ: M5bを二分割した後半。検索層のハイブリッド化・リランキング・UI・eval。M5b-1（ingest）と並行着工可。テストはM5b-1のデータ完成後。

## 添付マニフェスト（着工前照合・必須）

| # | パス | 種別 |
|---|---|---|
| 1 | docs/instructions/m5b-2-instructions.md | 本指示書 |
| 2 | docs/m5b-requirements.md | 要件定義 |
| 3 | docs/spec-v0.3.md | 実装仕様書（検索ツール現行仕様） |

## PG運用規律（定型）

M5b-1と同一。省略。

## 作業範囲

- **何を**: search_chunksのハイブリッド化、リランキング、domain選択UI、Planner絞り込み、eval拡充
- **なぜ**: M5b要件 R-4, R-5, R-6, R-9, R-10
- **どこで**: rag-system リポジトリ

## 作業手順

### 手順1: query.pyのハイブリッド検索化（R-4）

現行の`search_chunks`（Chroma密ベクトルのみ）を、密ベクトル＋BM25のRRF融合に改修する。

**現行シグネチャ**（spec §4）:
```python
search_chunks(query: str, domain: str | None = None, top_k: int = 3) -> list[dict]
```

**改修後シグネチャ**:
```python
search_chunks(query: str, domains: list[str] | None = None, top_k: int = 5) -> list[dict]
```

変更点:
- `domain`（単数・文字列）→ `domains`（複数・リスト）に拡張。後方互換: 文字列が渡されたらリストに変換
- `top_k` 既定値を3→5に変更（リランク後の返却数として適切）
- 内部処理:

```
1. クエリを密ベクトル化（ruri-v3-310m、クエリプレフィックス「検索クエリ: 」）
2. Chroma検索 → top 50（domainsフィルタ付き）
3. BM25検索 → top 50（domainsフィルタ: chunk_idからdomain照合）
4. RRF融合: score(d) = α/(k + rank_dense(d)) + β/(k + rank_bm25(d))
5. 融合結果 top 50 → リランカー（手順2）→ top_k を返却
```

**RRFパラメータ**: `settings.json` に以下を追加
```json
{
  "rrf_alpha": 0.5,
  "rrf_beta": 0.5,
  "rrf_k": 60,
  "rerank_candidates": 50
}
```

**BM25のdomainフィルタ**: BM25インデックスはdomain情報を持たないため、検索後にchunk_idからdocuments.yamlのdomainを逆引きしてフィルタする。あるいはbm25_index.pyでchunk_id→domain のマッピングもpickleに含める。

### 手順2: リランカー統合（R-5）

RRF融合後のtop N件をcross-encoderでスコアリングし、最終top_kに絞る。

```python
from sentence_transformers import CrossEncoder

reranker = CrossEncoder("cl-nagoya/ruri-v3-reranker-310m")

def rerank(query: str, chunks: list[dict], top_k: int = 5) -> list[dict]:
    pairs = [(f"検索クエリ: {query}", c['contextualized_text']) for c in chunks]
    scores = reranker.predict(pairs)
    ranked = sorted(zip(chunks, scores), key=lambda x: x[1], reverse=True)
    return [c for c, s in ranked[:top_k]]
```

- リランカーモデルのロードは起動時に1回（query.pyのモジュールレベルまたはシングルトン）
- M5b-1の手順0でリランカー動作確認済みを前提とする
- リランカーを無効化するオプション: `settings.json` に `"rerank_enabled": true` を追加。evalのA/B比較で使用

### 手順3: domain選択UI（R-9）

Streamlit UI（app.py）にdomain選択チェックボックスを追加する。

- 配置: チャット入力欄の上にexpander「検索対象の分野を選択」
- 選択肢（固定リスト）:

| 表示名 | フィルタ値 |
|---|---|
| 建築 | domain="建築" |
| 電気 | domain="電気" |
| 機械 | domain="機械" |
| 設計 | domain="設計" |
| 消防 | domain="消防" |
| 塗装 | domain="塗装" |
| 衛生 | domain="衛生" |
| その他 | domain="" |
| 法令 | doc_type="law" |

- 既定: 全選択
- 選択結果をst.session_stateに保持し、search_chunksの`domains`引数に渡す
- 「法令」はdomain値ではなくdoc_type値なので、フィルタ構築時に分岐が必要

### 手順4: Planner domain絞り込み（R-10）

src/agent.pyのPlannerプロンプトを改修し、domain絞り込みを組み込む。

**Plannerの現行出力**（想定）: 質問分解結果（検索クエリのリスト）

**改修後の出力**: 質問分解結果 + `relevant_domains`（関連domainのリスト）

プロンプト追加部分（例）:
```
ユーザーが選択した検索対象分野: {user_selected_domains}

質問内容から、上記の中で実際に関連する分野を判断してください。
回答の「relevant_domains」に関連分野のリストを返してください。
判断できない場合は、ユーザーが選択した全分野をそのまま返してください。
```

- Plannerの既存LLM呼び出しに統合（追加API呼び出しなし）
- Plannerの出力をJSONパースし、`relevant_domains`を取得
- 絞り込み結果はトレースに記録: `{"action": "domain_filter", "user_selected": [...], "planner_narrowed": [...]}`
- パース失敗時はユーザー選択をそのまま使用（フォールバック）

### 手順5: MCPツール改修

`src/mcp_server.py` の `submit_question` ツールに `domains` 引数を追加。

```python
@server.tool()
async def submit_question(question: str, style: str = "formal", domains: list[str] | None = None) -> str:
    # domains が指定された場合、エージェントのsearch_chunksにdomainsフィルタを渡す
    ...
```

`search_chunks` ツールも `domains` 引数を追加。

### 手順6: eval拡充（R-6）

**6a. 検証質問の追加**

eval/questions_m5b.jsonl を新設（既存のquestions.jsonlは改変しない）。
各domain代表1-2問、計10-15問を手動で作成。

質問例:
- 建築: 「コンクリートの養生期間の規定は？」
- 消防: 「屋内消火栓の設置基準は？」
- 法令: 「消防法施行令で定める防火対象物の区分は？」
- 設計: 「受変電設備の容量算定方法は？」
- 積算（空domain）: 「公共建築工事の共通費の算定方法は？」

各質問に `expected_domain`（正解のdomain）と `expected_chunks`（正解のdoc_slug）を付与。

**6b. 自動測定スクリプト**

`eval/run_retrieval_eval.py` を新設。

- 入力: questions_m5b.jsonl
- 処理: 各質問でsearch_chunks（top_k=5,10,20）を実行し、expected_chunksのdoc_slugがヒットしたかを判定
- 出力: recall@5, recall@10, recall@20, MRR を算出してeval/retrieval_results.jsonlに保存
- A/B構成: `--mode` 引数で切替
  - `dense`: Chroma密ベクトルのみ
  - `hybrid`: 密ベクトル＋BM25（RRF融合）
  - `full`: hybrid＋リランキング

```bash
python eval/run_retrieval_eval.py --mode dense
python eval/run_retrieval_eval.py --mode hybrid
python eval/run_retrieval_eval.py --mode full
```

**6c. 既存eval回帰テスト**

```bash
python eval/run_eval.py
```
合格率がM5a時点以上であることを確認。

## 禁止事項

- eval/questions.jsonl を改変しない（既存evalは触らない）
- search_chunksの戻り値の形式を変えない（フィールド追加は可、既存フィールドの削除・改名は不可）
- Plannerのdomain絞り込みでユーザー選択範囲を**広げない**（絞る方向のみ）

## テスト

- **PG自己完結分（M5b-1データ完成後に実施）**:
  - search_chunks がハイブリッド検索で動作（dense+BM25→RRF→rerank）
  - domain選択UIでチェックを外したdomainがヒットしないこと
  - Planner domain絞り込みが発動しトレースに記録されること
  - MCP submit_question(domains=["消防"]) で消防domainのみヒットすること
  - eval回帰テスト（既存questions.jsonl）合格率維持
  - retrieval eval: 三構成（dense/hybrid/full）のrecall@k・MRR比較
  - A/B結果: hybrid+rerank が dense を上回ること

## 完了条件

- query.py ハイブリッド検索化（RRF融合＋リランキング）済み
- settings.json にRRFパラメータ・rerank_enabled追加
- app.py domain選択UI実装済み
- agent.py Planner domain絞り込み実装済み
- mcp_server.py domains引数対応済み
- eval/questions_m5b.jsonl 納品
- eval/run_retrieval_eval.py 納品
- eval/retrieval_results.jsonl 三構成の比較結果
- 既存eval回帰テスト通過
- 品質レポート（docs/reports/m5b-2-completion.md）提出
- _STATUS.md更新・5W1Hコミット
- 「確認をお願いします」で完了報告
