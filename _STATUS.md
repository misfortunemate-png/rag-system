---
version: "M5a"
badge: "M5a 素材拡充完了・72文書13,714チャンク・PM検査待ち"
next: "M5b（ハイブリッド検索・検証拡充）"
waiting_on: pm_review
---

# rag-system 現在地

更新: 2026-08-14 ／ 更新者: PG（フラン）

## 状態

- M1〜M5a 完了
- M5a（素材拡充）: PDF 64件 + 法令XML 8件 = 72文書 → 13,714チャンク
- documents.yaml 72エントリ、Chroma再構築済み
- search_chunks 動作確認済み（消防domain等がヒット）
- 品質レポート提出済み（docs/reports/m5a-completion.md）

## 直近の経緯

- M5a指示書発行（2026-08-14）→ 当日着工・完了
- スクレイピング出力72件で実施（tfd 13件・denki 1件・nohmi 1件は出力未配置のため発注者了承で除外）
- ingest一般化: PDF（pdfplumber単体）+ XML（law_xml_ext新設）両対応
- query.pyのCOLLECTION_NAME不整合（jusetu_spec→kitei_spec）を修正

## 次の見通し

- M5b: ハイブリッド検索・検証拡充
- M7b（リモートMCP）: 入り方の安全方針と発注者裁定待ち
