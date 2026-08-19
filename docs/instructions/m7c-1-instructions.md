# 規程エージェント M7c-1 作業指示書（ツール削減・docstring・UI表記）
文書種別: 権威文書

作成日: 2026-08-19 ／ PM: クリーデ ／ 対応仕様: docs/m7c-requirements.md v1.0 §3（W-1, W-2, W-7） ／ 本書一枚で完結（追補なし）
着工条件: hotfix-3完了済み（H-Aのみ適用・claude.ai接続確認済み）
旧版: docs/instructions/m7c-instructions.md を本書＋m7c-2-instructions.md に分割・廃止

## 添付マニフェスト（着工前照合・必須）

以下がすべて交換所（リポジトリ）に存在すること。**1つでも欠けたら着工せず docs/reports/ に報告。**

| # | パス | 種別 | SHA-256（支給物のみ） |
|---|---|---|---|
| 1 | docs/m7c-requirements.md | 要件定義 | — |

## PG運用規律（定型・全フェーズ共通）

1. **停止条件**: 仕様にない判断が必要／仕様どおりだと問題が生じる／技術的に実現困難または難航／セッション外プロセスの停止等の副作用がある操作。原因判明時は「原因X・対策Y・実行可否」で報告し指示を待つ
2. **支給物改変禁止**: PM支給物はdiffゼロで検収される。技術的整合の調整もPMへ差し戻す
3. **発注者指示による仕様外修正**: 発注者から直接指示を受けた修正は実施・効果確認してよい。報告時に「発注者の指示により実装/修正」と明記する。権威文書は書き換えない
4. **着工前**: `git pull` → inspect実行（マニフェスト照合・版確認）。緑でなければ着工しない

## 作業範囲

- 何を: リモートMCP面のツール削減、docstring改訂、ゲストUI表記修正
- なぜ: Test④でクライアントの素材層迂回行動が確認され、品質担保済みパイプラインの迂回を構造的に排除する（m7c-requirements.md §0・§3 W-1/W-2/W-7）
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

### W-7: ゲストUI表記修正（app.py）

ヘッダーまたはタイトルに含まれる「公共建築工事標準仕様書（電気設備工事編）令和7年版」の表記を削除する。システムは複数分野の文書を収容しており、単一仕様書名の表示は不正確である。代替表記はPG裁量（例: 「規程エージェント」「建築設備規程検索」等）。

## 禁止事項

- ミドルウェアでのJSON-RPCボディ解析によるツール名フィルタ（W-1。重く壊れやすい）
- start-mcp-remote.batの`-m src.mcp_server`への変更（hotfix-3教訓: `-m`実行は`src/__init__.py`を先に実行しOAuth初期化を破壊する）
- ミドルウェア（_AuthRateLimitMiddleware）の変更（M7c-2のスコープ）
- agent.pyの変更（M7c-2のスコープ）

## テスト

- PG自己完結分:
  - stdioモード: 8ツール全て現行どおり動作（W-1回帰確認）
  - httpモード: `tools/list`応答が3本のみ
  - ゲストUI（Streamlit）が回帰なく動作
- **実機系（発注者に依頼）**:
  - T-1: claude.aiのコネクタ設定でツール一覧が3本のみ表示される
  - T-2: submit_question → get_answer 完走（status: done、answer取得）
  - T-3: OAuth認可フローが正常に動作する（hotfix-3教訓の回帰確認）

## 完了条件

- W-1, W-2, W-7が実装されていること
- PG自己テスト全項合格
- サーバー再起動・コミット・プッシュ実施済み
- _STATUS.md更新

## 報告基準

報告は docs/reports/ に置く。コンテキスト圧縮後もこのセクションを読み返してから報告すること。

1. 実装内容の要約（W-1, W-2, W-7の各項の実装方式）
2. 完了条件の各項に対する充足状況
3. PG自己テスト結果（stdioモード8ツール・httpモード3ツール・ゲストUI）
4. W-1のツール削減実装方式（第一候補/次点のどちらを採用したか、理由）
5. 未完了・未検証の項目があれば列挙
6. サーバー再起動・コミット・プッシュの実施状況
