---
version: "M5a"
badge: "M5a 素材拡充完了・検収済・72文書13,714チャンク"
next: "M5b（ハイブリッド検索・検証拡充）"
waiting_on: none
---

# rag-system 現在地

更新: 2026-08-14 ／ 更新者: クリーデ（PM検収）

## 状態

- M1〜M5a 完了・検収済
- M5a（素材拡充）: PDF 64件 + 法令XML 8件 = 72文書 → 13,714チャンク
- documents.yaml 72エントリ、Chroma再構築済み
- 既知課題: 全PDFがgenericプロファイル（jouban検出の閾値問題・M5bスコープ候補）

## 直近の経緯

- M5a指示書発行→PG着工→完了→PM検収（2026-08-14 同日）
- ingest一般化: PDF（pdfplumber単体）+ XML（law_xml_ext新設）両対応
- スクレイピング出力に未配置の15件は発注者裁定で除外確定

## 次の見通し

- M5b: ハイブリッド検索・検証拡充（jouban検出改善を含む検討）
- M7b（リモートMCP）: 入り方の安全方針と発注者裁定待ち
