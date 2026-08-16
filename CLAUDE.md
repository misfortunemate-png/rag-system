# CLAUDE.md

## プロジェクト概要

規程エージェント — 仕様書・帳票に根拠付きで答えるエージェントのデモ（ポートフォリオ）。
M5b: 72文書13,714チャンクに対してハイブリッド検索＋リランキング＋コンテキスト付与を実装する。

## 作業指示

マイルストーンごとに docs/instructions/ に指示書が発行される。

**M5b（完了・クローズ）:**  docs/instructions/m5b-*-instructions.md 全6本 — 検収済み

**次マイルストーン:** M5c（ローカルMCPサーバー化）— 指示書発行待ち

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
