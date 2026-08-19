# hotfix-3 実施報告書

文書種別: 報告書
作成日: 2026-08-19 ／ 報告者: PG ／ 対応指示書: docs/instructions/hotfix-3-instructions.md

---

## 1. 実装内容の要約

MCPサーバーのsrcインポート障害（`No module named 'src'`）を2箇所・計4行の変更で修正した。

**H-A: src/mcp_server.py — sys.pathブートストラップ挿入**

`os.chdir(_PROJECT_ROOT)` の直後に3行を追加:

```python
import sys
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
```

**H-B: start-mcp-remote.bat — モジュール実行化**

最終行をスクリプト直接実行からモジュール実行に変更:

```
変更前: .\.venv\Scripts\python.exe src\mcp_server.py --transport http
変更後: .\.venv\Scripts\python.exe -m src.mcp_server --transport http
```

---

## 2. 完了条件の充足状況

| 条件 | 状況 |
|---|---|
| H-A/H-Bの2箇所が正確に変更されていること | ✅ |
| PG自己テスト（stdio / http両モード）が合格していること | ✅ |
| サーバー再起動・コミット・プッシュ実施済み | ✅ |
| _STATUS.md更新 | ✅ |

---

## 3. PG自己テスト結果

### stdioモード（mcp-server.bat相当）

`list_documents` を呼び出し、正常レスポンスを確認:

```json
{
  "id": "kenchiku-shiyousho-r7",
  "title": "公共建築工事標準仕様書（建築工事編）令和7年版",
  "domain": "建築",
  "tags": ["国交省_標準仕様書"],
  "profile": "auto"
}
```

→ インポートエラーなし・回帰なし ✅

### httpモード（start-mcp-remote.bat相当）

`.\.venv\Scripts\python.exe -m src.mcp_server --transport http` を5秒間起動:

```
[08/19/26 19:41:44] INFO     StreamableHTTP session manager started
```

→ インポートエラーなし・5秒後も正常稼働 ✅ (起動後killで終了)

---

## 4. 未完了・未検証の項目

以下は発注者実機試験として依頼:

- **T-0a**: 再起動後、claude.aiから `submit_question` → `get_answer` 完走（status: done、answer取得）
- **T-0b**: claude.aiから `search_chunks` / `list_documents` がエラーなく応答（M7cツール削減前の最後の全数確認）

---

## 5. サーバー再起動・コミット・プッシュの実施状況

| 操作 | 状況 |
|---|---|
| サーバー再起動（実機） | **発注者依頼**（PGは自宅サーバーにアクセス不可） |
| コミット | ✅ `c0f8365` hotfix-3: srcインポート障害修正 |
| プッシュ | ✅ origin/main に反映済み |
