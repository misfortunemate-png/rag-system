# M5c 完了報告 — MCPサーバー化（stdio型・ローカル完結）

作成日: 2026-08-08 ／ PG: フラン

## 実装概要

`src/mcp_server.py` を新設し、公式 Python SDK（mcp 2.0.0 / MCPServer）で
stdio型MCPサーバーを実装した。既存パイプライン（agent.py / tools.py / config.py）
のロジックは無変更。

## テスト結果

| テスト | 方法 | 結果 |
|---|---|---|
| 疎通 | claude mcp list + list_documents呼び出し | ✅ Connected / active文書1件返却 |
| 素材層 search_chunks | search_chunks("ケーブル", top_k=2) | ✅ チャンクリスト返却 |
| 素材層 read_section | read_section("denki-setsubi", "1.1.1") | ✅ 768文字の条文全文返却 |
| スコープ | selected_doc_ids=[] でsearch_chunks | ✅ 0件（エラーなし） |
| ジョブ正常系 | submit_question(接続材料問)→ポーリング→done | ✅ 回答・引用・メタ情報返却 |
| ジョブ多重 | _pending_count=3で4件目submit | ✅ queue_fullエラー（クラッシュなし） |
| コスト記帳 | job_done後にlogs/当日ファイル確認 | ✅ JSONL・usage/cost/elapsed記録済み |
| 日次上限 | _daily_cost()→9999でsubmit | ✅ daily_cost_cap_exceededエラー |
| フィードバック | report_feedback呼び出し | ✅ inbox.jsonlに1行追記 |

## 実測値（正常系ジョブ：接続材料問）

- **質問**: 絶縁電線の心線の接続に使用できるものを教えてください
- **ジョブ所要時間**: 176.26秒（10ループ + advisor1回 + planner + composer）
- **総コスト**: $0.012411
  - planner (deepseek-v4-flash): $0.000122（275 in / 366 out）
  - loop (deepseek-v4-flash): $0.010614（128,277 in / 5,839 out）
  - composer (deepseek-v4-flash): $0.000605（8,324 in / 81 out）
  - advisor (deepseek-v4-pro): $0.001070（1,014 in / 1,687 out）
- **回答**: 圧着スリーブ・電線コネクタ・圧着端子等（根拠：2.1.1(4)）
- **引用チャンク**: denki-setsubi-0153

## 備考

- ジョブ単価上限（$0.10）はジョブ完了後チェック方式。パイプライン本体への
  割り込みフックを追加しないため、実行中断ではなく完了後コスト超過エラー扱いとなる。
  これはパイプライン変更禁止（M5c指示書）に従った設計判断。
- search_chunksのtop_k引数はMCPプロトコル経由でも正常に機能する
  （スコープテスト・空スコープ返却ともに確認済み）
- 日本語テキストのJSONL記録はensure_ascii=Falseで正常出力

## 納品物

| ファイル | 説明 |
|---|---|
| src/mcp_server.py | MCPサーバー本体（6ツール・ジョブ方式・コスト記帳） |
| .mcp.json | Claude Code プロジェクトスコープ登録ファイル |
| mcp-server.bat | 起動用バッチ（ASCII・CRLF） |
| docs/mcp-claude-desktop.md | Claude Desktop登録手順書 |
| requirements.txt | mcp>=2.0.0 追記 |
| logs/.gitkeep | ログディレクトリ |
| data/feedback/.gitkeep | フィードバック受信箱ディレクトリ |
