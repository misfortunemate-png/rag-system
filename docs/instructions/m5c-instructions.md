# 規程エージェント M5c 作業指示書 — MCPサーバー化（stdio型・ローカル完結）

作成日: 2026-08-08 ／ PM: クリーデ
前提: M4.5完了（文書投入基盤・文書スコープ選択）。ロードマップv1のM7a設計をM5cに前倒し
対応ロードマップ: docs/roadmap-v1.md M7a（v1.1でM5cに再配置）

## 目的

規程エージェントを外部LLMクライアント（Claude Code / Claude Desktop / Gemini CLI等の
MCP対応クライアント）から利用可能にする。業務用途の必要条件である「他ツールからの
呼び出し」の可否を最短で実証する。リモート公開はしない（M7b・発注者裁定待ち）。

## スコープ概要

1. stdio型MCPサーバー（公式Python SDK使用）
2. 三層ツール（素材層・エージェント層・フィードバック層）
3. 非同期ジョブ方式（submit→ポーリング）＋実行ガード（P-9）
4. コスト記帳（chat-pwa互換JSONL）
5. Claude Codeへの登録と動作確認（登録作業はPGが実施・R-015）

## 1. サーバー本体

- `src/mcp_server.py` を新設。公式MCP Python SDK（`mcp` パッケージ・FastMCP）で
  stdioサーバーを実装
- 既存パイプライン（src/agent.py・src/tools.py・src/config.py）を呼び出すラッパーに
  徹する。**パイプライン本体のロジック変更は禁止**
- settings.json（selected_doc_ids・モデル構成等）を尊重する。Streamlit UIと同じ
  設定を読む（設定の二重管理をしない）
- 起動用 `mcp-server.bat`（ASCII・CRLF）を同梱。ただし通常はクライアントが
  spawnするため、batは疎通確認用

## 2. ツール定義（三層）

| 層 | ツール | 引数 | 応答 |
|---|---|---|---|
| 素材層 | list_documents() | なし | documents.yamlのactive文書一覧（id・title・domain・tags・profile） |
| 素材層 | search_chunks(query, top_k=3) | 検索語・件数 | 同期・チャンクリスト（chunk_id・hierarchy・heading・body・pages） |
| 素材層 | read_section(doc_slug, hierarchy) | スラッグ・条番号 | 同期・条文全文 |
| エージェント層 | submit_question(question, style="standard") | 質問・回答スタイル | job_id（即時返却） |
| エージェント層 | get_answer(job_id) | ジョブID | running{loop数・経過秒} / done{回答＋引用＋メタフッター相当} / error{理由} |
| フィードバック層 | report_feedback(job_id, verdict, correction="", evidence="") | 裁定・訂正・根拠 | 受理確認 |

- 素材層は既存 search_chunks / read_section を直接呼ぶ（selected_doc_idsスコープ適用）
- ツールのdescriptionは事実の記述に留める（文書ごとの解釈指示を書かない。
  roadmap「プロンプトは彫り込まない」に従う）

## 3. ジョブ方式とガード（P-9）

- submit_question はバックグラウンドスレッドで実行。**同時実行1・待機キュー2**。
  超過時はエラー応答（受け付けない理由を明記して返す）
- ジョブ状態はプロセス内メモリ管理で可（stdioサーバーの寿命＝クライアント
  セッション）。完了ジョブは最新20件保持
- **ジョブ単価上限**: 既定 $0.10。実行中に累計推定コスト（既存estimate_cost利用）が
  超過したら中断し、error{cost_cap_exceeded}を返す
- **日次上限**: 既定 $1.00。当日ログの合計が超過していたら新規submitを拒否
- 上限値は環境変数（MCP_JOB_COST_CAP / MCP_DAILY_COST_CAP）で変更可

## 4. コスト記帳（chat-pwa互換JSONL）

- `logs/YYYY-MM-DD.log` にJSONL追記。chat-pwaと同形式:
  `{"ts": ISO8601, "event": ..., "model": ..., "usage": {"input_tokens": N, "output_tokens": N}, ...}`
- 記録イベント: job_submitted / job_done（ステージ別usage・推定コスト・所要秒）/
  job_error / feedback_received
- Streamlit側（app.py経由の実行）への記帳追加は**本指示のスコープ外**（別途M5bで検討）

## 5. フィードバック受信箱

- `data/feedback/inbox.jsonl`（追記専用）: ts / source_client / job_id / question /
  verdict(correct|incorrect|incomplete) / correction / evidence
- **自動反映禁止**: 受信箱への追記のみ。eval追加・正誤表ingestへの昇格は
  発注者とPMの検分を経る（実装しない）

## 6. 登録と動作確認

- フラン上のClaude Codeに登録（プロジェクトスコープ `.mcp.json` をリポジトリ直下に
  同梱し、これが正）。登録・疎通確認はPGが実施（R-015）
- Claude Desktopへの登録手順は docs/ にMarkdownで納品（発注者が試す場合の参照用。
  設定ファイルの場所とJSON片を記載）

## 依存

- 新規pip依存は `mcp`（公式SDK）のみ許可。requirements.txtに追記。
  それ以外が必要なら着工前にdocs/reports/で相談

## テスト

| テスト | 方法 | 合格条件 |
|---|---|---|
| 疎通 | Claude Codeからlist_documents呼び出し | active文書一覧が返る |
| 素材層 | search_chunks("ケーブル") / read_section既知条番号 | 既存Streamlit経由と同一内容 |
| スコープ | settings.jsonでselected_doc_ids=[]にして検索 | 0件応答（エラーで落ちない） |
| ジョブ正常系 | submit_question(R2相当問)→ポーリング→done | 回答・引用・メタ情報が返る |
| ジョブ多重 | 実行中に4件目submit | キュー超過エラーが返る（クラッシュしない） |
| コスト記帳 | job_done後にlogs/当日ファイル確認 | JSONL形式・usage/コストが記録されている |
| 日次上限 | MCP_DAILY_COST_CAP=0.0001で新規submit | 拒否応答が返る |
| フィードバック | report_feedback呼び出し | inbox.jsonlに1行追記される |

## 禁止事項

- ショウゴさんにコンソール操作をさせること（R-015。MCP登録作業もPGが実施）
- リモート公開・ポート開放・トンネル設定（M7b・発注者裁定待ち）
- 既存パイプライン（agent.py三役ロジック）の変更
- 既存チャンクデータの再生成
- eval支給物の改変

## 完了条件

- テスト表全項目合格
- .mcp.json／mcp-server.bat／Claude Desktop登録手順書の同梱
- docs/reports/ に完了報告（実測のジョブ所要秒・コスト実績を含む）・push済み
