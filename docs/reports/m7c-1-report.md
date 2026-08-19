# M7c-1 完了報告書

作成日: 2026-08-19 ／ 作成者: PG

## 1. 実装内容の要約

### W-1: リモートツール削減（src/mcp_server.py）

`_run_http()`内で`mcp.remove_tool()`を使い、素材層ツール5本（list_documents, search_chunks, read_section, fetch_law, web_search_tool）をHTTPトランスポート起動時に除去。`tools/list`応答は submit_question / get_answer / report_feedback の3本のみとなる。stdioモードは全8ツールを維持。

### W-2: docstring改訂（src/mcp_server.py）

3ツールの説明文を指示書記載の趣旨に改訂:
- **submit_question**: 質問送信とジョブ開始、所要時間（2〜5分）、job_id控えの案内
- **get_answer**: ステータス4種、30秒以上の再確認間隔、原文転記・出典省略禁止の指示
- **report_feedback**: ユーザー判定時のフィードバック記録、自動反映なし

### W-7: ゲストUI表記修正（app.py）

`st.caption("公共建築工事標準仕様書（電気設備工事編）令和7年版")`を削除。タイトル「規程エージェント」/「規程エージェント（ゲスト）」はそのまま維持。

## 2. 完了条件の充足状況

| 条件 | 状況 |
|---|---|
| W-1, W-2, W-7が実装されていること | ✅ 実装済み |
| PG自己テスト全項合格 | ✅ 合格 |
| サーバー再起動 | ✅ start-mcp-remote.bat経由で再起動済み |
| コミット・プッシュ | ✅ 本報告と同時に実施 |
| _STATUS.md更新 | ✅ m7c-1-done |

## 3. テスト結果

### PG自己テスト

| テスト項目 | 結果 |
|---|---|
| stdioモード: 8ツール登録確認 | ✅ list_documents, search_chunks, read_section, web_search_tool, fetch_law, submit_question, get_answer, report_feedback |
| httpモード: remove_tool後3ツールのみ | ✅ submit_question, get_answer, report_feedback |
| ゲストUI: caption削除・構文検証 | ✅ 旧表記なし・AST解析合格 |

### 実機系テスト

| テスト項目 | 結果 |
|---|---|
| T-1: claude.aiコネクタでツール一覧が3本のみ | ✅ Get answer / Report feedback / Submit question の3本のみ表示確認 |
| T-2: submit_question → get_answer 完走 | ✅ status: done、answer取得（143秒、$0.005、出典4チャンク引用） |
| T-3: OAuth認可フローが正常に動作 | ✅ コネクタ再接続時にOAuth認可画面経由でトークン発行・接続成功 |

## 4. W-1ツール削減実装方式

**次点アプローチを採用。**

理由: `mcp.remove_tool(name)`がMCPServer（`mcp.server.mcpserver`）のパブリックAPIとして提供されており、内部構造への依存なく実装可能であったため。第一候補（デコレータ廃止→登録関数化）は変更量が大きく、既存の`@mcp.tool()`パターンとの乖離が生じる。次点アプローチは4行の追加で済み、既存コード構造を維持できる。

`MCPServer.remove_tool()` → `ToolManager.remove_tool()` → `del self._tools[name]`。いずれもライブラリの公開メソッドであり、コメントによる依存属性明記は不要。

## 5. 未完了・未検証の項目

なし（全項完了）

## 6. サーバー再起動・コミット・プッシュの実施状況

- サーバー再起動: start-mcp-remote.bat経由で実施済み（旧プロセス2本を停止→直接実行方式で再起動）
- コミット・プッシュ: 本報告と同時に実施
