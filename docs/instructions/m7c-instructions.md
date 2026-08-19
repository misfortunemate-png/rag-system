# 規程エージェント M7c 作業指示書（リモートMCP面の再設計）
文書種別: 権威文書

作成日: 2026-08-19 ／ PM: クリーデ ／ 対応仕様: docs/m7c-requirements.md v1.0 §3 ／ 本書一枚で完結（追補なし）
着工条件: hotfix-3のT-0a（submit_question→get_answer完走）がPASS済みであること

## 添付マニフェスト（着工前照合・必須）

以下がすべて交換所（リポジトリ）に存在すること。**1つでも欠けたら着工せず docs/reports/ に報告。**

| # | パス | 種別 | SHA-256（支給物のみ） |
|---|---|---|---|
| 1 | docs/m7c-requirements.md | 要件定義 | — |
| 2 | docs/instructions/hotfix-3-instructions.md | 前段指示書 | — |

## PG運用規律（定型・全フェーズ共通）

1. **停止条件**: 仕様にない判断が必要／仕様どおりだと問題が生じる／技術的に実現困難または難航／セッション外プロセスの停止等の副作用がある操作。原因判明時は「原因X・対策Y・実行可否」で報告し指示を待つ
2. **支給物改変禁止**: PM支給物はdiffゼロで検収される。技術的整合の調整もPMへ差し戻す
3. **発注者指示による仕様外修正**: 発注者から直接指示を受けた修正は実施・効果確認してよい。報告時に「発注者の指示により実装/修正」と明記する。権威文書は書き換えない
4. **着工前**: `git pull` → inspect実行（マニフェスト照合・版確認）。緑でなければ着工しない

## 作業範囲

- 何を: リモートMCP面のツール削減・進捗報告・回答永続化・フィードバック突合強化・レート制限再設計・docstring改訂・ゲストUI表記修正
- なぜ: Test④でクライアントの素材層迂回行動が確認され、品質担保済みパイプラインの迂回を構造的に排除する（m7c-requirements.md §0・§3）
- どこで: misfortunemate-png/rag-system（D:\AI\github\rag-system）

## 作業手順

### W-1: リモートツール削減（src/mcp_server.py）

httpトランスポート起動時、`tools/list`が返すツールを **submit_question / get_answer / report_feedback の3本のみ**とする。stdioトランスポートは現行8本を維持する。

実装の第一候補: ツール登録を関数化し、トランスポート確定後に登録する構成に改める。現行の`@mcp.tool()`デコレータによるimport時登録をやめ、明示的な登録関数（例: `_register_tools(mcp, remote: bool)`）で分岐する。

次点: `_run_http`内で登録済みツールマネージャから素材層5本（list_documents / search_chunks / read_section / fetch_law / web_search_tool）を除去する。MCPライブラリの内部構造に依存する場合、依存する属性名をコード内コメントに明記すること。

### W-2: docstring改訂（src/mcp_server.py）

3ツールの説明文を以下の趣旨に改訂する。文言の微調整はPM検収時に許容する。

**submit_question**:
```
質問を自然言語で送信し、回答生成ジョブを開始する。
回答生成には通常2〜5分かかる。返却されたjob_idを控え、get_answerで結果を確認すること。
```

**get_answer**:
```
ジョブ状態を返す。status: running / done / error / not_found。
status=runningの間は30秒以上あけて再確認すること。
status=doneのanswerフィールドは、要約・再構成・抜粋をせず原文のままユーザーに転記すること。
回答には出典（文書名・条番号）が含まれており、それも省略しないこと。
```

**report_feedback**:
```
回答の正誤をユーザーが判定した場合にフィードバックを記録する（自動反映なし）。
verdict: correct / incorrect / incomplete。
```

### W-3: 進捗報告（src/agent.py + src/mcp_server.py）

#### W-3a: agent.py — コールバック追加

`run()` と `run_pre_composer()` のシグネチャに `progress_cb=None` を追加する。

```python
def run(question: str, config: AgentConfig | None = None, progress_cb=None) -> dict:
def run_pre_composer(question: str, config: AgentConfig | None = None, progress_cb=None) -> dict:
```

`progress_cb` のシグネチャ: `progress_cb(stage: str, detail: str)`。省略時（None）は現行と完全同一動作（後方互換必須）。

以下のタイミングで `progress_cb` を呼び出す（Noneチェック付き）:

| 呼び出し箇所 | stage値 | detail文言 |
|---|---|---|
| `run_pre_composer` 冒頭（planner呼び出し前） | `"planning"` | `"質問を分析し検索計画を立てています"` |
| `_run_loop` の各巡回冒頭（ループカウンタ参照） | `"searching"` | `f"関連条文を検索中（{n}巡目）"` |
| `run` 内の `_run_composer` 呼び出し前 | `"composing"` | `"回答を作成しています"` |
| advisor呼び出し前（mid-loop advisor含む） | `"reviewing"` | `"回答を検証しています"` |

`_run_loop` は `progress_cb` を引数として受け取る必要がある。シグネチャの変更は内部関数であるため影響範囲はrun_pre_composerのみ。

進捗更新にLLM呼び出しを追加しない（P-5/P-9）。

#### W-3b: mcp_server.py — _run_jobからのコールバック接続

`_run_job` 内で `agent_run` を呼ぶ際に `progress_cb` を渡す:

```python
def _progress(stage: str, detail: str) -> None:
    _job_set(job_id, stage=stage, detail=detail)

result = agent_run(question, config, progress_cb=_progress)
```

`_run_job` のジョブ初期化（status="running"設定時）に `stage="queued"`, `detail="実行待ちです"` を追加する。

#### W-3c: mcp_server.py — get_answer応答拡張

running応答を以下の形式に拡張する:

```python
if status in ("queued", "running"):
    elapsed = round(time.time() - job.get("submitted_at", time.time()), 1)
    return {
        "status": "running",
        "job_id": job_id,
        "elapsed_s": elapsed,
        "stage": job.get("stage", "queued"),
        "detail": job.get("detail", "実行待ちです"),
        "hint": "回答生成は通常2〜5分かかります。次の確認は30秒以上あけてください。",
    }
```

### W-4: 回答の永続化（src/mcp_server.py）

`_run_job` 内のjob_done処理（_job_set(job_id, status="done", ...)の直後、_job_mark_doneの前）で、`data/answers/YYYY-MM.jsonl` へ1行追記する。

```python
_persist_answer(job_id, question, style, domains, job_result)
```

新規関数 `_persist_answer` を追加:

```python
def _persist_answer(job_id: str, question: str, style: str, domains: list[str] | None, result: dict) -> None:
    answers_dir = _PROJECT_ROOT / "data" / "answers"
    answers_dir.mkdir(parents=True, exist_ok=True)
    month_file = answers_dir / f"{datetime.now(timezone.utc).strftime('%Y-%m')}.jsonl"
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "job_id": job_id,
        "question": question,   # 全文・切り詰めない
        "style": style,
        "domains": domains,
        "answer": result.get("answer", ""),
        "cited_chunk_ids": result.get("cited_chunk_ids", []),
        "meta": result.get("meta", {}),
    }
    with open(month_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
```

`.gitignore` に `data/answers/` を追加する。

### W-5: report_feedback突合強化（src/mcp_server.py）

`report_feedback` のquestion解決を以下の三段に拡張する。answerも同時に解決する:

1. メモリ上の `_jobs` から `job_id` で解決（現行ロジック）
2. 不在なら `data/answers/` の月次ファイルを新しい順にスキャンし、`job_id` 一致行から解決
3. どちらにも無ければ空文字＋ `"resolved": false` フラグ

記録エントリに `answer` フィールドと `resolved` フラグを追加:

```python
entry = {
    "ts": datetime.now(timezone.utc).isoformat(),
    "source_client": "mcp",
    "job_id": job_id,
    "question": question,
    "answer": answer,           # 追加
    "verdict": verdict,
    "correction": correction,
    "evidence": evidence,
    "resolved": resolved,       # 追加（True/False）
}
```

メモリからの解決時: `question = job.get("question", "")` に加え `answer = job.get("result", {}).get("answer", "")`。
永続化ファイルからの解決時: jsonl行をパースし `question` と `answer` を取得。

### W-6: レート制限の再設計（src/mcp_server.py）

`_AuthRateLimitMiddleware` のレートカウントを以下のように変更する:

1. 認証成功後のレートカウントキーを **IP → auth_id** に変更する
2. 認証成功時の上限を **60リクエスト/分** に緩和する
3. 未認証リクエストのブルートフォース防御（5失敗/分→10分ブロック＋3秒遅延）は変更しない

実装方針: ミドルウェアの処理順序を「BFチェック → 認証 → レートカウント」に変更する（現行は「BFチェック → レートカウント → 認証」）。認証成功時は `auth_id` をキーに60/分でカウントし、認証失敗時はレートカウントを行わない（BF機構が担保するため）。

```
RATE_LIMIT = 60      # 認証済みリクエストの上限（変更: 10→60）
```

検収時の確認ポイント: 認証失敗時に既存のBF機構（3秒遅延・5失敗→10分ブロック・401＋WWW-Authenticateヘッダー）が従来どおり機能していること。

### W-7: ゲストUI表記修正（app.py）

ヘッダーまたはタイトルに含まれる「公共建築工事標準仕様書（電気設備工事編）令和7年版」の表記を削除する。システムは複数分野の文書を収容しており、単一仕様書名の表示は不正確である。代替表記はPG裁量（例: 「規程エージェント」「建築設備規程検索」等）。

## 禁止事項

- ミドルウェアでのJSON-RPCボディ解析によるツール名フィルタ（W-1。重く壊れやすい）
- 進捗更新へのLLM呼び出し追加（W-3。P-5/P-9違反）
- data/answers/*.jsonlのリポジトリへのコミット（W-4。コーパス由来本文を含む）
- submit_question内のジョブ辞書への`question`フィールドの格納方法の変更。report_feedbackのメモリ解決がこれに依存する

## テスト

- PG自己完結分:
  - stdioモード: 8ツール全て現行どおり動作（W-1回帰確認）
  - httpモード: `tools/list` が3本のみ返却（W-1）
  - httpモード: submit_question → get_answer のrunning応答に stage/detail/hint が含まれること（W-3）
  - ジョブ完走後 `data/answers/` に当月ファイルが生成され、question/answerが全文であること（W-4）
  - report_feedback がメモリ上のジョブからquestion/answerを含めて記録すること（W-5）
  - ゲストUI（Streamlit）が回帰なく動作すること（agent.run のシグネチャ後方互換）

- **実機系（発注者に依頼）**:
  - T-1: claude.aiのコネクタ設定でツール一覧が3本のみ表示される
  - T-2: submit_question → get_answer 完走。running応答でstageが遷移する
  - T-3: 120〜300秒のジョブをclaude.aiから完走させ、429が発生しない
  - T-5: report_feedback 実施後の `data/feedback/inbox.jsonl` にquestion/answerが含まれる

## 完了条件

- W-1〜W-7の全項が実装されていること
- PG自己テスト全項合格
- `.gitignore` に `data/answers/` が追加されていること
- サーバー再起動・コミット・プッシュ実施済み
- _STATUS.md更新

## 報告基準

報告は docs/reports/ に置く。コンテキスト圧縮後もこのセクションを読み返してから報告すること。

1. 実装内容の要約（W-1〜W-7の各項の実装方式）
2. 完了条件の各項に対する充足状況
3. PG自己テスト結果（stdioモード8ツール・httpモード3ツール・進捗報告・永続化・フィードバック・ゲストUI）
4. inspect結果（緑/赤と出力の添付）
5. 未完了・未検証の項目があれば列挙
6. W-1のツール削減実装方式（第一候補/次点のどちらを採用したか、理由）
7. W-6のレート制限変更で処理順序を変更した場合、認証失敗時のBF機構動作確認結果
8. サーバー再起動・コミット・プッシュの実施状況
