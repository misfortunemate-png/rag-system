# CLAUDE.md

## プロジェクト概要

規程エージェント — 仕様書・帳票に根拠付きで答えるエージェントのデモ（ポートフォリオ）。
単一文書デモの素材は公共建築工事標準仕様書（電気設備工事編）令和7年版。

## 作業指示

マイルストーン（M1〜M4）ごとに docs/instructions/ に指示書が発行される。
現行の指示書を読んでから着工すること。指示書がない場合は着工せず待機。

## 正典文書

- docs/requirements-v0.5.md（統合定義書）
- docs/data-definition-v0.4.md（データ定義書）
- docs/spec-v0.3.md（実装仕様書）

## 環境

- Python 3.10+
- LLMバックエンド切替式（spec §3.1）:
  - `LLM_PROVIDER`=`openrouter`（既定）／`anthropic`
  - `LLM_MODEL`=モデルID
  - `OPENROUTER_API_KEY` または `ANTHROPIC_API_KEY`
- 全マイルストーンを自宅デスクトップ（RTX 5060 Ti 16GB）で実施

## 素材PDF

data/raw/ に配置:
https://www.mlit.go.jp/gobuild/content/001888825.pdf

## 運用規律

- 難航時はdocs/reports/にpushしてPMへ差し戻す
- 環境問題は発注者に直接聞いてよい
- eval/questions.jsonlは改変しない（PM支給物）
