# 規程エージェント M1 作業指示書

作成日: 2026-08-07 ／ PM: クリーデ（Opus席）
対応仕様: docs/spec-v0.3.md ／ 対応データ定義: docs/data-definition-v0.4.md
スコープ: M1（単一文書ingest＋agent query CLI）

## マニフェスト（着工前照合）

以下がリポジトリに存在すること。欠けたら着工せずPMに報告。

| # | パス | 種別 |
|---|---|---|
| 1 | docs/spec-v0.3.md | 仕様書 |
| 2 | docs/data-definition-v0.4.md | データ定義 |
| 3 | docs/requirements-v0.5.md | 統合定義書 |
| 4 | eval/questions.jsonl | 評価質問（PM支給・10問） |
| 5 | data/raw/ 配下にPDF1点 | 素材 |

## PG運用規律

1. 難航時はdocs/reports/にpushしてPMへ差し戻す
2. 環境・インフラの問題は発注者に直接聞いてよい
3. eval/questions.jsonlは改変しない
4. 着工前に `git pull` してマニフェスト照合
5. 仕様の疑義はPMへ（docs/reports/）。自己判断で仕様を拡張しない

## 作業範囲

単一文書（電気設備工事編）のingest→agent query→evalをCLIで一気通貫させる。UIは含まない（M2）。

成果物: src/配下の全モジュール＋eval結果＋中間データ

## 技術情報（PM調査済み）

### PDF条文構造

```
第N編 > 第M章 > 第K節 > X.Y.Z 条名
  (1) 項
    (ｱ) 号（全角カタカナ括弧）
      (a) 細目
```

条番号パターン: `\d+\.\d+\.\d+`（例: 1.1.1, 2.13.14）
編見出し: `第\d+編`、章見出し: `第\d+章`、節見出し: `第\d+節`
表: `表\d+\.\d+\.\d+` の形で出現

### hierarchyの構築

上位の編・章・節を追跡して結合する。
例: `第2編/第1章/第3節/1.3.1`

### 条文間参照パターン（refs抽出）

本文中に頻出する参照パターン:
- `\d+\.\d+\.\d+「.+?」`（例: `1.7.3「キャビネット」(1)による`）
- `第\d+編第\d+章`
- `表\d+\.\d+\.\d+`

正規表現で決定的抽出する。LLM不使用。全エッジをdata/refs.jsonlに出力。

### ruri-v3-310m プレフィックス

HuggingFaceモデルカード（cl-nagoya/ruri-v3-310m）を正として照合すること。
文書側・クエリ側のプレフィックスが異なる場合があるため、付け忘れ防止のユニットテストを必ず書く。

### LLMバックエンド（spec §3.1）

環境変数:
- `LLM_PROVIDER`：`openrouter`（既定）／`anthropic`
- `LLM_MODEL`：モデルID
- `OPENROUTER_API_KEY`／`ANTHROPIC_API_KEY`

src/llm.pyにアダプタ2実装。ツール定義はプロバイダ非依存の内部形式で持ち、アダプタが各API形式に変換する。既定モデルはOpenRouter上でツール使用対応かつコスト最適なものをPGが確認して仮置きし、選定根拠をREADMEに記載。

## 作業手順

### Phase A: 基盤構築

1. **ディレクトリ・依存関係**: spec §2のファイル構成に従い骨格を作成。requirements.txtに主要パッケージを記載（pdfplumber, pymupdf, llama-index, chromadb, sentence-transformers, openai, anthropic, streamlit）

2. **documents.yaml**: 電気設備工事編1件のレジストリ

3. **src/llm.py**: OpenRouter（OpenAI互換）とAnthropic直の2アダプタ。ツール定義の内部形式→API形式変換。ストリーミングは不要（CLIなのでブロッキング呼出で可）

### Phase B: 抽出・分割

4. **src/extract/plumber.py**: pdfplumberでページ単位テキスト抽出

5. **src/extract/pymupdf.py**: PyMuPDFでページ単位テキスト抽出

6. **src/extract/arbiter.py**: 同一ページの2エンジン結果を比較。判定基準は文字化け率（U+FFFD・制御文字）＋行断片化度。採用エンジンと理由をログ出力

7. **src/chunker.py**: 条番号正規表現で条単位分割。上位階層追跡→hierarchy構築。refs抽出（決定的正規表現）。閾値ルール（300字/2000字）。出力: data/chunks.jsonl（中間検査用）＋data/refs.jsonl（参照エッジ全量）

### Phase C: 格納・検索

8. **src/ingest.py**: documents.yaml読み込み→抽出→分割→ruri-v3-310m埋め込み→Chroma格納。collection名: `kitei_spec`。metadataにchunk_id, hierarchy, domain, pages, source_engine, refsを付与

9. **src/tools.py**: 2ツール実装
   - `search_chunks(query, domain=None, top_k=3)`: Chromaベクトル検索。domainフィルタ可
   - `read_section(doc_slug, hierarchy)`: chunks.jsonlからhierarchy完全一致でbody全文を返す

### Phase D: エージェント・評価

10. **src/agent.py**: llm.pyを使うツール使用ループ。最大10ループ。システムプロンプト要点: 出典必須／根拠なしは「該当なし」／refsがあれば参照先をread_sectionで追跡。全ツール呼出と引数をトレース記録（リスト形式で保持、eval・UI両方から参照可能）

11. **eval/run_eval.py**: questions.jsonlの10問を順次実行。results.jsonlを出力（question, expected_source, retrieved, answer, verdict欄は空）。トレースも併せて保存

12. **CLIエントリポイント**: `python src/agent.py "質問文"` で回答＋トレースをターミナル表示

## Phase完了の確認

Phase B完了時: data/chunks.jsonlとdata/refs.jsonlが存在し、chunks.jsonlのchar_count分布が妥当であること。refsが空でないこと（電気設備工事仕様書は参照が豊富にある）。この時点でPGはサーバー再起動不要。

Phase D完了時: `python eval/run_eval.py` が10問分のresults.jsonlを出力すること。

## テスト

| テスト | 方法 | 合格条件 |
|---|---|---|
| プレフィックス | ユニットテスト | クエリ側・文書側の両方に正しく付与 |
| 分割品質 | chunks.jsonlのchar_count分布 | 300未満・2000超が説明可能な範囲 |
| refs抽出 | refs.jsonlの件数と目視 | 参照が拾えている（0件は不合格） |
| ビルド | requirements.txt install + 全モジュールimport | エラーなし |
| E2E | eval/run_eval.py | results.jsonlが10問分出力される |

## 禁止事項

- APIキーをコードやコミットに含めない
- questions.jsonlを改変しない
- 精度チューニングのための試行錯誤は不要（7問passを狙うが、未達分は失敗分析としてREADMEに書く）
- UIの実装（M2の領域）

## 完了条件

- 全モジュールが動作し、ingest→agent query→evalの一連が通ること
- results.jsonlが10問分出力されること（verdict判定は発注者）
- chunks.jsonl、refs.jsonlが目視検査可能な形で存在すること
- push済み

## サーバー再起動指示

このプロジェクトにサーバーコンポーネントはない（M1はCLIのみ）。再起動不要。
