# 規程エージェント M5c作業指示書（ローカルMCPサーバー環境整備・疎通確認）

作成日: 2026-08-16 ／ PM: クリーデ ／ 根拠: ロードマップv1 M5c/M7a節
位置づけ: src/mcp_server.pyは三層フル実装済み。本フェーズは環境整備・納品物作成・疎通確認のみ。

## 背景

mcp_server.pyは素材層（list_documents・search_chunks・read_section）、エージェント層（submit_question・get_answer）、フィードバック層（report_feedback）の三層ツールとP-9ガード（同時1・待機2・ジョブ$0.10・日次$1.00）を既に実装している。未着手なのはフラン上での実際の起動・接続・疎通確認と、発注者が手を動かさずに使える納品物一式。

## 作業項目

### W-1: 依存関係の確認と整備

- mcp_server.pyが `from mcp.server.mcpserver import MCPServer` を使用している。フラン上にこのパッケージがインストール済みか確認する
- 未インストールの場合はインストールし、requirements.txt（または pyproject.toml）に追加する
- 既存の依存関係（ruri-v3、chromadb、fugashi等）と競合しないことを確認する

### W-2: 起動スクリプトの作成

以下の納品物を作成する（R-015: 発注者にコンソール操作をさせない）:

1. **start-mcp.bat**（Windows・ASCII・CRLF）: mcp_server.pyをstdioモードで起動するバッチファイル。.envの存在確認、Python仮想環境の有効化（あれば）、`python src/mcp_server.py` の実行。エラー時はpauseで停止
2. **.env.example**: MCP固有の環境変数（MCP_JOB_COST_CAP、MCP_DAILY_COST_CAP）を既定値付きで記載。既存の.env.example（あれば）にマージ

### W-3: Claude Desktop / Claude Code用MCP設定例

docs/mcp-setup.md に以下を記載する:

1. Claude Desktop用の claude_desktop_config.json のスニペット例（command・args・cwd）
2. Claude Code用の .mcp.json のスニペット例
3. 接続確認の手順（list_documentsを呼んで文書一覧が返ることを確認）

パスはフランの作業ディレクトリ（D:\AI\github\rag-system）を前提とする。

### W-4: 疎通確認

フラン上で以下の疎通確認を実施する:

1. **素材層**: search_chunks(query="メタルモール 配線") を呼び、チャンクが返ることを確認
2. **素材層**: read_section(doc_slug="denki-shiyousho-r7", hierarchy="1.7.3") を呼び、条文が返ることを確認
3. **エージェント層**: submit_question(question="メタルモールで配線してよい場所は？") → job_id取得 → get_answer(job_id) のポーリングで回答が返ることを確認
4. **フィードバック層**: report_feedback(job_id=上記, verdict="correct") を呼び、data/feedback/inbox.jsonl にエントリが追記されることを確認
5. **ガード確認**: 日次コスト集計（logs/YYYY-MM-DD.log）にjob_doneエントリが記録されることを確認

疎通の実施方法は任意（Claude Code MCPクライアント、Python直接呼び出し、mcp inspectorのいずれでも可）。

### W-5: _STATUS.md・CLAUDE.md更新

- _STATUS.mdをM5c完了に更新
- CLAUDE.mdにMCPサーバーの起動方法と利用可能ツール一覧を追記

## 禁止事項

- mcp_server.pyの機能（ツール定義・ガード・ジョブ管理）を変更しない（バグ修正は例外）
- agent.py・tools.py・config.pyを変更しない

## 完了条件

- W-1〜W-3の納品物
- W-4の疎通確認結果（各ツールの入出力サンプルを添付）
- docs/reports/m5c-completion.md 提出
- W-5の更新
- 「確認をお願いします」で完了報告
