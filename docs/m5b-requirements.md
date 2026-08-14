# 規程エージェント M5b要件定義書 — 検索品質向上

作成日: 2026-08-14 ／ PM: クリーデ ／ 承認: ショウゴさん（承認待ち）
前提: M5a完了（72文書13,714チャンク・Chroma稼働中）、顧問検証済み

## 目的

検索層を商用RAGの標準水準に引き上げる。現状（密ベクトル単体・genericチャンキング）では条番号指定クエリや専門用語の完全一致が外れやすく、デモ品質として不十分。Anthropicの Contextual Retrieval 研究に基づく三層（コンテキスト付与＋ハイブリッド検索＋リランキング）を実装し、検索失敗率を現状比で50%以上削減する。

現スコープは施工管理基準の一問一答だが、将来は調査業務・入札積算にも拡張する。本M5bの検索基盤はそれらの用途と共通であり、積算における歩掛コード・工種名・規格番号の完全一致はBM25が直接効く領域である。

## 技術選定

| 技術 | 採用理由 |
|---|---|
| fugashi + unidic-lite | 日本語BM25の形態素解析器。SudachiPyと比較して辞書サイズが小さく導入が軽い。デフォルトのスペース分割では日本語BM25が機能しないため必須 |
| rank_bm25 | BM25実装。Pythonで完結、外部サーバー不要。Chromaとは別建てでインデックスを持つ |
| ruri-v3-reranker-310m (cl-nagoya) | 日本語cross-encoderリランカー。JaCWIRベンチマーク最上位帯（map@10: 0.9463）。埋め込みモデル（ruri-v3-310m）と同系列でsentence-transformers経路を共有。RTX 5060 Ti 16GBで動作 |
| DeepSeek V4 Flash (non-reasoning) | LLMコンテキスト付与用。OpenRouter経由、$0.08/1M入力・$0.17/1M出力 |

棄却:
- Cohere Rerank: API課金。ローカル実行でコスト$0にできる本件では不採用
- bge-reranker-v2-m3: 日本語特化ベンチで ruri-reranker に劣る
- japanese-reranker-v2 (tiny/xsmall): 精度が ruri-reranker-310m より低い。速度優先の用途向け

## 機能要件

### R-1: jouban検出の修正

M5aで全PDFがgenericプロファイルに振り分けられた問題を修正する。

原因候補: pdfplumberの`layout=True`抽出でレイアウトスペースが挿入され、条番号パターン`X.Y.Z`の密度が閾値（0.015）を下回った。

対処方針: 以下のいずれか（PGが原因を特定して選択し報告）。
- (a) 抽出テキストからレイアウトスペースを正規化してからdetect_profileを実行
- (b) 閾値を引き下げる
- (c) pdfplumberのlayoutオプションを変更する

受入基準: 国交省標準仕様書（建築・電気・機械の3件）がjoubanと判定され、条項単位の階層パス（`第N編/第M章/X.Y.Z`）を持つチャンクが生成されること。

### R-2: コンテキスト付与（Contextual Retrieval）

各チャンクの先頭に、そのチャンクの文書内での位置づけを示すコンテキスト文を付加する。コンテキスト付きテキストで埋め込みとBM25インデックスの両方を構築する。

二方式の使い分け:
- **決定的コンテキスト（jouban・lawチャンク）**: `{文書タイトル}。{hierarchy}` を決定的コードでチャンク先頭に付加。LLM不使用（P-5）
- **LLMコンテキスト（genericチャンクのみ）**: DeepSeek V4 Flash（reasoning無効）で、チャンクの文書内での位置づけを50-100字で生成し付加

LLMコンテキスト生成の設計制約:
- LLMに渡すコンテキストは「文書タイトル＋前後各1チャンクのテキスト＋当該チャンク」に限定する。文書全体を渡さない（P-9: コスト有界）
- LLMの出力は50-100字の日本語テキスト1文。指示以外の出力（謝辞・装飾・マークダウン等）を返さないようプロンプトで制御
- 失敗時（API障害・タイムアウト）は決定的フォールバック（文書タイトルのみ付加）で継続。LLM障害でingest全体が止まらない設計
- コンテキスト付与結果はchunks.jsonlの`context`フィールドに保存。再ingest時にキャッシュとして再利用可能な設計が望ましいが、必須ではない

### R-3: BM25インデックス構築

コンテキスト付きチャンクテキストに対して、日本語形態素解析済みのBM25インデックスを構築する。

- トークナイザ: fugashi（MeCab）+ unidic-lite辞書
- インデックス形式: rank_bm25のBM25Okapiを使用。シリアライズしてdata/bm25_index.pkl等に永続化
- クエリ時も同じトークナイザで形態素解析してからBM25検索

### R-4: ハイブリッド検索（RRF融合）

search_chunksツールの内部を密ベクトル＋BM25のハイブリッドに置き換える。

- 密ベクトル検索: Chroma（既存）→ top_k=50
- BM25検索: rank_bm25 → top_k=50
- 融合: Reciprocal Rank Fusion。`RRF(d) = α/(k + rank_dense(d)) + β/(k + rank_bm25(d))`
- パラメータ: α=0.5, β=0.5, k=60 を初期値とする。evalの結果に基づいて調整可能な設計（settings.jsonまたは環境変数）
- 融合後のtop_nをリランカーに渡す（R-5）

### R-5: cross-encoderリランキング

RRF融合後の候補をcross-encoderでスコアリングし、最終的なtop_kに絞る。

- モデル: cl-nagoya/ruri-v3-reranker-310m
- 入力: RRF融合後のtop 50件（クエリ×チャンクのペア）
- 出力: スコア順に並べ替え、top 5-10 をエージェントに返す
- 返却数: search_chunksのtop_k引数に従う（既定3 → 5に変更推奨。指示書で具体化）
- Blackwellリスク: RTX 5060 Tiでのruri-v3-reranker-310mの動作を着工前に確認する。動作しない場合はdocs/reports/に報告してPMへ差し戻す

### R-6: eval拡充と自動測定

- 既存のeval/questions.jsonlの回帰テスト（合格率維持）
- 新domain対応の検証質問を追加（各domain代表1-2問、計10-15問）
- recall@k（k=5, 10, 20）とMRR（Mean Reciprocal Rank）の自動計算スクリプト
- ハイブリッド検索の有無・リランキングの有無・RRF重みを変えたA/B比較が実行可能な設計
- 結果はeval/results_m5b.jsonlに出力

### R-7: 表チャンクの品質サンプリング（顧問追加項目）

積算基準・別紙PDFのチャンクから表を含むものを3件以上サンプリングし、行と列の対応が保持されているかを報告する。判定結果（保持/崩壊/部分崩壊）を品質レポートに記載。

目的: 将来の積算用途（歩掛表・単価表の検索と引用）に向けた実態把握。表抽出の実装自体はM5bのスコープ外（実態を見てから後続を判断する）。

### R-8: tags へのgroup情報転記（顧問追加項目）

documents.yamlの各エントリのtagsフィールドに、rag_file_list.jsonのgroup値を転記する。gen_documents_yaml.pyを修正。検索挙動は変更しない（将来のメタデータフィルタ拡張への備え）。

### R-9: domain選択UI（チェックボックス）

Streamlit UIに検索対象domainの選択チェックボックスを設置する。

- 選択肢: 建築 / 電気 / 機械 / 設計 / 消防 / 塗装 / 衛生 / その他（domain空文字列の文書群） / 法令（doc_type=law）
- 既定: 全選択
- 選択結果はsearch_chunksのdomainフィルタとしてChroma/BM25の両方に適用する
- MCP経由（submit_question）でも`domains`引数（文字列リスト）でdomain指定を受け付ける。省略時は全domain

### R-10: 前工程domain絞り込み（Pre-retrieval filtering）

ユーザーがdomainを広く選択していても、検索前にLLMが質問内容から関連domainを判定し、検索空間を絞る。

- タイミング: Plannerの質問分解ステップの中で実行（Plannerプロンプトにdomain判定の指示を追加）
- モデル: エージェントのPlannerと同じLLMを使用（追加API呼び出しを避ける。Plannerの出力に`relevant_domains`フィールドを追加する形）
- ユーザーが選択したdomain範囲を**広げることはしない**（絞る方向のみ。ユーザー選択 ∩ LLM判定 = 実行時フィルタ）
- 絞り込み結果はトレースに記録する（「質問内容から消防・法令に絞り込み」等）
- LLMが判定に失敗した場合（パース不能等）はユーザー選択をそのまま使用（フォールバック）
- コスト: Plannerの既存呼び出しに統合するため追加コスト実質$0

## 処理パイプライン（全体像）

```
ingest時:
  文書 → テキスト抽出 → チャンキング（jouban/generic/law 自動判定）
       → コンテキスト付与（R-2: 決定的 or LLM）
       → 密ベクトル埋め込み（ruri-v3-310m・コンテキスト付きテキスト）
       → Chroma格納
       → BM25インデックス構築（R-3: fugashi形態素解析済みテキスト）

検索時:
  UI: domain選択（R-9）
    ↓
  Planner: 質問分解 + domain絞り込み（R-10: ユーザー選択 ∩ LLM判定）
    ↓
  クエリ → 密ベクトル検索 top-50（domainフィルタ付き）─┐
         → BM25検索 top-50（domainフィルタ付き）     ─┤→ RRF融合（R-4）→ リランク top-5（R-5）→ エージェント
```

## 工程順序（依存関係）

1. **リランカー動作確認**（着工前ゲート）: RTX 5060 Tiでruri-v3-reranker-310mが動作することを確認
2. **R-1 jouban修正** → 再チャンク: チャンクの切れ目が変わるため、以降の全工程はこの結果に依存
3. **R-8 tags転記** → documents.yaml更新（R-1と並行可）
4. **R-2 コンテキスト付与**: R-1完了後のチャンクに対して実行
5. **再埋め込み＋Chroma再構築＋R-3 BM25構築**: R-2完了後のコンテキスト付きテキストで一括
6. **R-4 RRF融合＋R-5 リランカー＋R-9 domain選択UI＋R-10 Planner絞り込み**: 検索側の改修（一括）
7. **R-6 eval拡充＋A/B測定**: R-4〜R-10完了後に測定（domain絞り込みの有無も比較項目に追加）
8. **R-7 表品質サンプリング**: R-1完了後いつでも可（並行）

## コスト見積もり

| 項目 | コスト |
|---|---|
| LLMコンテキスト付与（genericチャンクのみ・DeepSeek V4 Flash） | ~$1 |
| ローカル計算（再埋め込み90分＋BM25構築＋リランカーロード） | $0（電気代のみ） |
| eval質問追加（DeepSeek V4 Flash） | ~$0.1 |
| **合計LLMコスト** | **~$1.1** |

## テスト方針

| テスト | 方法 | 合格条件 |
|---|---|---|
| jouban検出 | 建築・電気・機械の3件がjouban判定されること | 3/3 jouban |
| 既存eval回帰 | eval/questions.jsonlの全問実行 | 合格率が M5a時点以上 |
| recall@k | Golden Set（既存10問＋新規10-15問）で自動計測 | recall@10 ≥ 0.80 |
| MRR | 同上 | MRR ≥ 0.70 |
| A/B比較 | dense単体 vs hybrid vs hybrid+rerank の三構成で上記指標を比較 | hybrid+rerank が dense単体を上回ること |
| 表品質 | 積算基準・別紙のチャンク3件以上を目視 | 判定結果の報告（合否判定はPM） |
| domain選択UI | チェックボックスで特定domain選択→該当domainのみヒット | フィルタ動作 |
| domain絞り込み | 広域選択＋専門的質問→Plannerが関連domainに絞り込み、トレースに記録 | 絞り込み発動・トレース記載 |
| MCP domains引数 | submit_question(domains=["消防","法令"])で絞り込み動作 | フィルタ動作 |
| MCP動作 | search_chunks・submit_question が新しい検索構成で動作 | 応答返却 |

## 受入基準

1. search_chunksがハイブリッド検索＋リランキングで動作すること
2. 仕様書系PDFがjoubanプロファイルでチャンク化されていること
3. eval回帰テストが合格率維持していること
4. recall@10 ≥ 0.80, MRR ≥ 0.70 を達成していること
5. A/B比較結果が品質レポートに記載されていること
6. 表品質サンプリング結果が品質レポートに記載されていること
7. RRFパラメータ（α, β）が設定ファイルで変更可能であること
8. UIにdomain選択チェックボックスがあり、選択結果が検索フィルタに反映されること
9. Plannerがdomain絞り込みを行い、結果がトレースに記録されること
10. MCP submit_questionがdomains引数を受け付けること

## ロードマップ更新（記帳のみ・実装はM5bスコープ外）

roadmap-v1.mdに以下を追記する:

### M8b: 積算支援（構想）
- 歩掛表・単価表の構造化抽出（pdfplumberのextract_tables → Markdown表 → 行列対応付き検索）
- 数量×歩掛の計算ツール（エージェントの「電卓」）
- 入札特記仕様書読解との接続

## 追加依存パッケージ

| パッケージ | 用途 |
|---|---|
| fugashi | MeCab形態素解析器（Python binding） |
| unidic-lite | MeCab辞書（軽量版） |
| rank_bm25 | BM25実装 |

ruri-v3-reranker-310mはsentence-transformers経由でロード（既存依存で動作）。

## 改訂履歴

- v0.1（2026-08-14）: 初版。PM提案＋顧問検証（コスト修正・トークナイザ補足・リランカー指名・工程順序修正）＋将来スコープ反映（表品質調査・tags転記・M8b記帳）＋R-9 domain選択UI・R-10前工程domain絞り込み追加（発注者裁定）
