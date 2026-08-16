# CLAUDE.md

## プロジェクト概要

規程エージェント — 仕様書・帳票に根拠付きで答えるエージェントのデモ（ポートフォリオ）。
M6-1: Web照合ツール（三種切替）・三層格付け基盤・パイプライン統合を実装。

## 作業指示

マイルストーンごとに docs/instructions/ に指示書が発行される。

**M5b〜M6-1（完了・クローズ）:** 各指示書 — 検収済み

**次マイルストーン:** M6-2（Web照合 eval・品質検証）— 指示書待ち

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
