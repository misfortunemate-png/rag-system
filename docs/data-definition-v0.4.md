# 規程エージェント データ定義書 v0.4

作成日: 2026-08-05 ／ 最終改訂: 2026-08-07
PM: クリーデ
対応要件定義: 統合定義書 v0.5

## 文書レジストリ（documents.yaml・新設）

複数文書を扱うため、ingest対象の台帳を置く。

| フィールド | 型 | 内容 |
|---|---|---|
| doc_slug | str | チャンクIDの接頭辞（例：`doboku-kyotsu`） |
| title | str | 正式名称・版・発行元 |
| domain | str | 系統タグ：`civil` / `electric` / `arch` / `fire` / `telecom` / `form` |
| source_url | str | 入手元（公開文書であることの証跡） |

- 横断モードの系統別検索は domain タグでフィルタする

## チャンクレコード（Chroma格納単位）

| フィールド | 型 | 内容 |
|---|---|---|
| chunk_id | str | `{doc_slug}-{連番}` |
| doc_type | str | `spec`（仕様書条文）/ `form`（帳票） |
| domain | str | documents.yamlの系統タグを継承 |
| hierarchy | str | 条文は階層パス（例：`第3編/第2章/3-2-1-2`）、帳票は`{帳票名}/{表番号}` |
| heading | str | 見出し。埋め込み対象はheading＋body連結 |
| body | str | 本文または表（Markdown表） |
| pages | str | 元PDFのページ範囲 |
| char_count | int | 分割品質の検証用 |
| source_engine | str | 採用エンジン（`plumber` / `pymupdf` / `mineru`）。突合判定の痕跡 |
| refs | list[str] | 本文中の条文間参照（「X.Y.Z「…」による」等）から決定的抽出した参照先hierarchyの一覧。空リスト可 |

## 分割ルール

- 原則、最下層の条項単位で1チャンク
- 300字未満は親階層でまとめ、2,000字超は項単位で分割（閾値は素材確定後に実物で調整し、改訂履歴に残す）
- 表はMarkdown表としてbodyに保持。整形不能なら「表あり・p.XX参照」
- 帳票は表1枚＝1チャンク
- refs抽出は正規表現による決定的処理（LLM不使用）。参照エッジの全量は`data/refs.jsonl`（from_chunk_id / to_hierarchy）にも出力し、参照グラフの検証・可視化に使えるようにする

## 評価レコード（JSONL）

**単一文書10問**（M1）

| フィールド | 内容 |
|---|---|
| question | 想定質問 |
| expected_source | 正解となる条番号 |
| retrieved | 検索で返ったchunk_id上位3件 |
| answer | エージェントの回答 |
| verdict | pass / fail と一行の理由 |

**横断シナリオ1本**（M3・新設）

| フィールド | 内容 |
|---|---|
| scenario | 質問（例：コンクリート埋込分電盤の設置） |
| expected_domains | 分解されるべき系統の集合 |
| expected_conflict | 検出されるべき要調整事項（1件以上） |
| trace | 実際の観点分解・検索・突合の記録 |
| verdict | pass / fail と一行の理由 |

- 帳票（M4）は評価対象外（抽出実演のみ）

## 設計判断の記録

- 埋め込み対象をheading連結にした理由：本文単独では「何についての規定か」が欠落し検索が外れやすい
- source_engineを持たせた理由：突合の採用判定を検証可能な痕跡として残す（検査業務の考え方）
- domainをチャンクに非正規化した理由：検索時にレジストリ結合を挟まず、Chromaのメタデータフィルタ一発で系統別検索するため
- 横断評価をexpected_conflict基準にした理由：横断デモの価値は要約でなく矛盾の発見であり、評価もそこに合わせる
- refsを持たせた理由：仕様書の条文は単独で完結せず「○○による」の参照網を成す。静的グラフを別成果物とせずチャンク属性に載せることで、エージェントがread_sectionで参照先を追跡でき、参照追跡がトレース上で実演される。将来のオントロジー構築（条文間関係の育成）の土台でもある

## 改訂履歴

- v0.1（08-04）：初版
- v0.2（08-04）：doc_type・source_engine追加
- v0.3（08-05）：documents.yaml（文書レジストリ・系統タグ）新設。chunkにdomain追加。横断シナリオ評価を新設
- v0.4（08-07）：chunkにrefs（条文間参照）追加。refs.jsonl出力を新設。抽出は決定的処理（LLM不使用）
