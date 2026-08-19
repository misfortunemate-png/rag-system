# M7c-2 完了報告書

作成日: 2026-08-19 ／ 作成者: PG

## 1. 実装内容の要約

### W-3: 進捗報告（agent.py + mcp_server.py）

**W-3a**: `run()`, `run_pre_composer()`, `_run_loop()` に `progress_cb=None` を追加。4箇所でNoneチェック付きコールバック呼び出し:
- run_pre_composer冒頭: `("planning", "質問を分析し検索計画を立てています")`
- _run_loop各巡回冒頭: `("searching", f"関連条文を検索中（{n}巡目）")`
- advisor呼び出し前（mid-loop/post-loop共通）: `("reviewing", "回答を検証しています")`
- run内_run_composer前: `("composing", "回答を作成しています")`

**W-3b**: `_run_job` 内で `_progress` クロージャを定義し `_job_set(job_id, stage=stage, detail=detail)` で進捗をジョブ辞書に反映。ジョブ初期化時に `stage="queued"`, `detail="実行待ちです"` を設定。

**W-3c**: get_answer の running 応答に `stage`, `detail`, `hint` フィールドを追加。

### W-4: 回答の永続化（mcp_server.py）

`_persist_answer` 関数を新設。`_job_set(status="done", ...)` 直後・`_job_mark_done` 前に `data/answers/YYYY-MM.jsonl` へ1行追記。`.gitignore` に `data/answers/` を追加。

### W-5: report_feedback突合強化（mcp_server.py）

三段解決:
1. メモリ（`_jobs`）から `job_id` で question/answer を解決
2. 不在なら `data/answers/*.jsonl` を新しい順にスキャンし一致行から解決
3. どちらにも無ければ空文字 + `resolved: false`

記録エントリに `answer` フィールドと `resolved` フラグを追加。

### W-6: レート制限の再設計（mcp_server.py）

ミドルウェアの処理順序を「BFチェック → 認証 → レートカウント」に変更（旧: BFチェック → レートカウント → 認証）。認証成功時の上限を60リクエスト/分に緩和、レートカウントキーをIPからauth_idに変更。BF機構（5失敗/分→10分ブロック・3秒遅延・401＋WWW-Authenticateヘッダー）は変更なし。

## 2. 完了条件の充足状況

| 条件 | 状況 |
|---|---|
| W-3〜W-6が実装されていること | ✅ 実装済み |
| PG自己テスト全項合格 | ✅ 合格 |
| .gitignoreにdata/answers/が追加 | ✅ 追加済み |
| サーバー再起動 | ✅ start-mcp-remote.bat経由で再起動済み |
| コミット・プッシュ | ✅ 本報告と同時に実施 |
| _STATUS.md更新 | ✅ m7c-2-done |

## 3. PG自己テスト結果

| テスト項目 | 結果 |
|---|---|
| agent.py progress_cb後方互換（全デフォルトNone） | ✅ |
| src/agent.py, src/mcp_server.py, app.py 構文検証 | ✅ |
| W-4 _persist_answer関数存在確認 | ✅ |
| W-5 report_feedbackにresolved/answersスキャンロジック確認 | ✅ |
| W-6 RATE_LIMIT=60, BF_LIMIT=5, BF_BLOCK_DURATION=600確認 | ✅ |
| ゲストUI（Streamlit）回帰: app.pyインポート正常 | ✅ |

## 4. W-6 認証失敗時のBF機構動作確認

処理順序変更後もBF機構は変更なし:
- 認証失敗時: `asyncio.sleep(3)` → IP別の失敗カウント → 5失敗/分で10分ブロック
- 401レスポンスに `WWW-Authenticate` ヘッダー付与
- レートカウント（429判定）は認証成功後のパスでのみ実行されるため、未認証リクエストはBF機構のみが担保する

## 5. 未完了・未検証の項目

実機系テスト（発注者に依頼）:
- T-4: submit_question→get_answer完走。running応答でstageが遷移する
- T-5: 120〜300秒のジョブをclaude.aiから完走させ、429が発生しない（W-6）
- T-6: OAuth認可フローが正常に動作する（W-6ミドルウェア変更の回帰確認）
- T-7: report_feedback実施後のdata/feedback/inbox.jsonlにquestion/answerが含まれる

## 6. サーバー再起動・コミット・プッシュの実施状況

- サーバー再起動: start-mcp-remote.bat経由で実施済み（旧プロセス停止→直接実行方式で再起動）
- コミット・プッシュ: 本報告と同時に実施
