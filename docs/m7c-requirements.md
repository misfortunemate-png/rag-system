# 規程エージェント M7c 要件定義 v1.0 — リモートMCP面の再設計

作成日: 2026-08-19 ／ 作成者: クリーデ（技術顧問席・Fable）
承認者: ショウゴさん（2026-08-19 会話にて方針承認済み・本文書は仕様確定版）
宛先: PM席（指示書起草・発令・検収）
経緯: 20260819_nw-completion-fable-referral.md の差し戻し調査、および実機試験チャット（Test ④）の挙動分析に基づく。

---

## 0. 背景と設計判断の要旨

Test ④の実機試験で二つの事実が確認された。

1. **srcインポート障害**: start-mcp-remote.bat のスクリプト直接実行により sys.path にプロジェクトルートが乗らず、src.* を遅延インポートする全経路（素材層5ツール＋エージェント本体 _run_job）が `No module named 'src'` で失敗する。ローカルstdio（-m実行）とStreamlit（app.py起点）では顕在化しない。コンテナ環境で再現実証済み。
2. **クライアントの迂回行動**: claude.aiクライアントは初手で list_documents / search_chunks を掴み、さらに law_id を記憶から推測して fetch_law を叩いた。素材層ツールがリモート面に見えている限り、品質担保済みパイプライン（submit_question→get_answer）の迂回と中途半端な自前合成が構造的に発生する。

これに対する発注者確定方針:

- リモート面は **submit_question / get_answer / report_feedback の3本のみ**公開する
- 回答は本文中に文書名・条番号を明記済みであり、原文照会ツール（read_section等）のリモート公開は不要。原本参照はシステム外で完結する
- クライアントには回答を**要約・再構成せず原文のまま転記**させる
- 120〜300秒の回答生成中、クライアントが離脱しないよう**進捗を都度報告**する
- 質問・回答本文を永続化し、フィードバックと突合可能にする

## 1. 工程構成 — 二段発令

| 段 | 名称 | 内容 | 緊急度 |
|---|---|---|---|
| 第1弾 | hotfix-3 | srcインポート修正（W-A/W-B）のみ。計4行 | 緊急・即日 |
| 第2弾 | M7c本体 | ツール削減・進捗報告・永続化・レート制限・docstring | hotfix-3のTest④完走確認後 |

hotfix-3単独でTest ④が完走可能になる。M7cはその検証結果を前提に着工する。

---

## 2. 第1弾: hotfix-3 要件

### W-A: sys.path ブートストラップ（本修正）

src/mcp_server.py の `os.chdir(_PROJECT_ROOT)` 直後に追加:

```python
import sys
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
```

### W-B: 起動スクリプトのモジュール実行化（整合）

start-mcp-remote.bat の最終行を変更:

```
.\.venv\Scripts\python.exe -m src.mcp_server --transport http
```

mcp-server.bat と実行方式を統一し、sys.path[0]=src/ による名前衝突リスクも排除する。

### 検収条件（hotfix-3）

- T-0a: 再起動後、claude.aiから submit_question → get_answer 完走（status: done、answer取得）
- T-0b: search_chunks / list_documents がエラーなく応答（削減前の全ツール生存確認。M7c前の最後の全数確認）

---

## 3. 第2弾: M7c 要件

### W-1: リモートツール削減

**要求**: httpトランスポート起動時、tools/list が返すツールを submit_question / get_answer / report_feedback の3本のみとする。stdioトランスポートは現行8本を維持する（PGデバッグ・eval用）。

**実装候補**（手段はPG裁量。ただし以下を第一候補として検討すること）:
- ツール登録を関数化し、トランスポート確定後に登録する構成に改める。デコレータのimport時登録をやめ、`_register_tools(mcp, remote: bool)` で分岐
- 上記が大掛かりになる場合の次点: _run_http 内で登録済みツールマネージャから素材層5本を除去する（MCPライブラリの内部構造に依存するため、依存する属性名をコード内コメントに明記すること）

**禁止事項**: ミドルウェアでのJSON-RPCボディ解析によるツール名フィルタ（重く、壊れやすい）。

### W-2: docstring改訂（クライアント誘導）

ツール説明文はクライアントLLMへの唯一のプロンプト経路である。以下の趣旨を必ず含める（文言の微調整はPM検収時に可）:

- **submit_question**: 「質問は自然言語で送る。回答生成には通常2〜5分かかる。job_idを控え、get_answerで確認すること。」
- **get_answer**: 「status=runningの間は30秒以上あけて再確認すること。status=doneのanswerフィールドは、要約・再構成・抜粋をせず**原文のまま**ユーザーに転記すること。回答には出典（文書名・条番号）が含まれており、それも省略しないこと。」
- **report_feedback**: 現行説明に「回答の正誤をユーザーが判定した場合は記録すること」を追記。

### W-3: 進捗報告（get_answer拡張）

**要求**: running応答に進捗情報を含める。

1. `src/agent.py` の `run()` に進捗コールバックを追加する: `run(question, config, progress_cb=None)`。シグネチャは `progress_cb(stage: str, detail: str)`。省略時は現行と完全同一動作（後方互換必須）
2. コールバック発火点: ステージ遷移時（planner開始／loop各巡開始／composer開始／advisor開始）
3. mcp_server.py の `_run_job` はコールバックで `_job_set(job_id, stage=..., detail=...)` を呼ぶ
4. get_answer の running応答を拡張:

```json
{"status": "running", "job_id": "...", "elapsed_s": 85,
 "stage": "searching", "detail": "関連条文を検索中（3巡目）",
 "hint": "回答生成は通常2〜5分かかります。次の確認は30秒以上あけてください。"}
```

**ステージ定義**（stage値と detail 文言の対応）:

| stage | detail（日本語・人間可読・そのまま転記可能な文体） |
|---|---|
| queued | 実行待ちです |
| planning | 質問を分析し検索計画を立てています |
| searching | 関連条文を検索中（n巡目） |
| composing | 回答を作成しています |
| reviewing | 回答を検証しています |

5. 進捗更新は決定的コードのみで行い、LLM呼び出しを追加しない（P-5/P-9）

### W-4: 回答の永続化

**要求**: job_done時に以下を `data/answers/YYYY-MM.jsonl` へ1行追記する（月次ファイル・追記専用）:

```json
{"ts": "...", "job_id": "...", "question": "<全文>", "style": "...", "domains": [...],
 "answer": "<回答本文全文>", "cited_chunk_ids": [...], "meta": {...}}
```

- 質問は切り詰めない（現行ログの200字制限はログ側のみ維持でよい）
- data/answers/ は .gitignore に追加（コーパス由来の本文を含むため公開リポジトリに載せない）

### W-5: report_feedback の突合強化

**要求**: フィードバック記録時に question に加えて **answer本文** を含める。解決順序:

1. メモリ上の _jobs から job_id で解決
2. 不在なら data/answers/ の月次ファイルを新しい順にスキャンして job_id で解決
3. どちらにも無ければ空文字（現行どおり）＋ `resolved: false` フラグを記録

### W-6: レート制限の再設計

**要求**: 認証済みリクエストのポーリング連打が429で落ちないようにする。

- 認証成功後のレートカウントのキーを IP から **auth_id（トークンID）単位**に変更し、上限を **60リクエスト/分** に緩和する
- 未認証リクエストの防御は現行のブルートフォース機構（5失敗/分→10分ブロック＋3秒遅延）で担保されているため変更しない
- レート判定と認証判定の処理順序の変更が必要になる場合、401経路の防御水準を下げないことを検収条件とする

**スコープ外**: get_answer のサーバー側ロングポーリング（wait パラメータ）。claude.aiのツール呼び出し保持時間が未検証の外部スペックのため、必要が生じた場合に独立PoCとして起案する。

---

## 4. M7c 検収条件

| # | 条件 |
|---|---|
| T-1 | claude.aiのコネクタ設定でツール一覧が3本のみ表示される |
| T-2 | submit_question→get_answer 完走。running応答に stage/detail/hint が含まれ、stageが遷移する |
| T-3 | 120〜300秒のジョブをclaude.aiから完走させ、429が発生しない |
| T-4 | 完走後 data/answers/ 当月ファイルに1行追記され、question/answerが全文である |
| T-5 | report_feedback の記録に question/answer が含まれる（メモリ経由・永続化ファイル経由の両方） |
| T-6 | stdioローカル（Claude Code）で8ツール全て現行どおり動作する |
| T-7 | ゲストUI（Streamlit）が回帰なく動作する（agent.run のシグネチャ後方互換の確認） |

## 5. 付帯事項

- ゲストUIヘッダーの「公共建築工事標準仕様書（電気設備工事編）令和7年版」表記の削除を W-7（軽微）としてM7c指示書に含めてよい
- 本要件の各修正は m7b-requirements-v2.md の後継ではなく独立工程。NW台帳への影響なし（ポート・経路の変更を含まない）

## 改訂履歴

| 日付 | 版 | 変更者 | 内容 |
|---|---|---|---|
| 2026-08-19 | v1.0 | クリーデ（技術顧問席） | 初版。発注者承認済み方針の仕様確定 |
