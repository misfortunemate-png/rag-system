# CLAUDE.md

## プロジェクト概要

規程エージェント — 仕様書・帳票に根拠付きで答えるエージェントのデモ（ポートフォリオ）。
M5b: 72文書13,714チャンクに対してハイブリッド検索＋リランキング＋コンテキスト付与を実装する。

## 作業指示

マイルストーンごとに docs/instructions/ に指示書が発行される。
**現行の指示書（並行2本）:**
- **docs/instructions/m5b-1-instructions.md** — ingest品質改善（先に着工・GPU処理あり）
- **docs/instructions/m5b-2-instructions.md** — 検索層改修（並行着工可・テストはM5b-1完了後）

現行の指示書を読んでから着工すること。指示書がない場合は着工せず待機。

## 正典文書

- docs/requirements-v0.5.md（統合定義書）
- docs/m5b-requirements.md（M5b要件定義書）
- docs/data-definition-v0.4.md（データ定義書）
- docs/spec-v0.3.md（実装仕様書）
- docs/roadmap-v1.md（ロードマップ）

## 環境

- Python 3.10+
- LLMバックエンド切替式（spec §3.1）
- 全マイルストーンを自宅デスクトップ（RTX 5060 Ti 16GB）で実施

## 素材

data/raw/ に配置。documents.yaml がレジストリ（72エントリ）。

## 運用規律

- 難航時はdocs/reports/にpushしてPMへ差し戻す
- 環境問題は発注者に直接聞いてよい
- eval/questions.jsonlは改変しない（PM支給物）
