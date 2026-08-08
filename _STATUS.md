---
version: "M5c"
badge: "M5c MCPサーバー完了・Claude Codeから接続確認済み"
next: "M5a（内線規程PDF入手待ち）／M5b（ハイブリッド検索・検証拡充）"
waiting_on: pm_review
---

# rag-system 現在地

更新: 2026-08-08 ／ 更新者: PG（フラン）

## 状態

- M1〜M5c 完了
- M5c（stdio MCP・三層ツール・ジョブ方式・コスト記帳）実装完了
- Claude Code（プロジェクトスコープ）から全6ツール接続確認済み
- テスト表全項目合格（docs/reports/m5c-completion.md）

## 直近の経緯

- M5c指示書発行（2026-08-08）→ 当日着工・完了
- mcp 2.0.0 (MCPServer / stdio) を採用。FastMCPはv2で廃止のため上位APIを使用
- ジョブ正常系: 176.26秒・$0.012411（接続材料問・10ループ）

## 次の見通し

- M5a: 内線規程PDFが入手でき次第着工
- M5b: M5a/M5c後にハイブリッド検索・検証拡充
- M7b（リモートMCP）: 入り方の安全方針と発注者裁定待ち
