# rag-system ネットワーク作業完了・技術顧問差し戻し報告

文書種別: PM報告 ／ 作成日: 2026-08-19 ／ 作成者: クリーデ（PM）
宛先: 技術顧問（Fable席）
経緯: M7a（08-16）→ M7b hotfix-2（08-18）→ Funnel配置変更（08-19）

---

## 1. 完了事項

### 1.1 ネットワーク基盤

| 項目 | 結果 |
|---|---|
| Funnel配置変更 | 完了。443=MCP / 8443=ゲストUI / 10000=予備 |
| Serveポート10枠 | 8444〜8453 全疎通確認済み |
| chat-pwa移動 | 443→8446（serve only） |
| NW台帳 | v2.2（ai-family-memory ops/state/network.yaml） |
| 配線指針 | v1.0 確立 |
| 配置変更計画書 | ai-family-ops docs/20260818_port-migration-plan.md |

### 1.2 確立した制約

| ID | 内容 |
|---|---|
| C-CLAUDE-443 | claude.aiカスタムコネクタは443限定。非標準ポートはサイレントTCPリセット |
| C-PWA-SAME-HOST | 同一Tailscaleホスト名ではPWA 1つのみ。ブックマーク運用で決着 |
| C-SERVE-OFF-SYNTAX | tailscale serve --https=PORT off が正しい構文 |

### 1.3 実機テスト結果

| テスト | 結果 | 備考 |
|---|---|---|
| ① Funnel疎通 | PASS | Pixel 10モバイル回線から443到達確認 |
| ② 承認画面 | PASS | ③に統合。OAuth発見フロー→DCR→認可画面 全通過 |
| ③ claude.aiコネクタ接続 | PASS | ツール8個認識。M7aからの懸案解決 |
| ④ ツール実行 | 部分PASS | 経路正常。ジョブ管理系3ツール動作。実行系5ツールがsrcインポートエラー |
| ⑤ ゲストUI | PASS | Streamlit（:8443）からの質問・回答確認済み |

### 1.4 M7b hotfix-2（RFC 9728対応）

| 修正 | 内容 | 状態 |
|---|---|---|
| W-1 | /.well-known/oauth-protected-resource エンドポイント新設 | 検収合格 |
| W-2 | 401レスポンスにWWW-Authenticateヘッダー追加 | 検収合格 |
| W-3 | _OAUTH_PATHS追加 | 検収合格 |
| W-4 | 手順書URL変更（/sse→/mcp） | 差し戻し後再検収合格 |

---

## 2. 技術顧問への差し戻し事項

### 2.1 srcインポートエラー（Test ④ 不完走）

claude.aiからのツール呼び出しでPythonコードを実行する5ツールが同一エラーで失敗。

```
No module named 'src'
```

**症状の整理:**

| ツール | 結果 |
|---|---|
| submit_question | ⚠️ job_id発行成功（キュー投入は通る） |
| get_answer | ✅ 正常応答（ポーリング機構は生存） |
| report_feedback | ✅ accepted: true |
| list_documents | ❌ No module named 'src' |
| search_chunks | ❌ No module named 'src' |
| fetch_law | ❌ No module named 'src' |
| read_section | ❌ No module named 'src' |
| web_search_tool | ❌ No module named 'src' |

**PM所見:**
- ネットワーク経路は完全に正常。claude.ai→Funnel→MCPサーバー→ツール呼び出しまで到達している
- ジョブ管理系（FastAPIのエンドポイント処理）は動作し、ワーカー側（実際のPython実行）で失敗している
- ゲストUI（Streamlit）は同じバックエンドで正常動作しているため、MCPツール経由のワーカー起動パスが異なる可能性がある
- start-mcp-remote.batの起動ディレクトリとPythonのインポートパス解決の問題が疑われる
- M7bの実装範囲（OAuth・Funnel）とは無関係の、元からあるかもしれない問題

**顧問に期待する判断:**
1. インポートパス問題の原因特定と修正方針（仕様変更か実装バグか）
2. MCPツールのワーカーがsrcモジュールを解決する前提条件の確認（sys.path、作業ディレクトリ、__init__.py）
3. ゲストUI（Streamlit）とMCPツールでインポート経路が異なる理由の調査

### 2.2 ゲストUI表記の修正

ゲストUIヘッダーに「公共建築工事標準仕様書（電気設備工事編）令和7年版」の表記がある。
発注者から不要と指摘。次回改修で修正。

---

## 3. 教訓

| # | 内容 |
|---|---|
| 教訓 | claude.aiカスタムコネクタは443限定。公式ドキュメントに明記されておらず、デバッグガイド（個人ブログ）とGitHub issue（#85, #373）でのみ確認可能。要件定義時に外部スペックの実機検証を怠ると、ローカルテスト全PASSでも実機で全滅する |
| 教訓 | 軽微な修正の軽微な間違いは軽微でない（発注者の言葉）。PM検収で不備を見つけたら、自分で直さず差し戻すのが筋 |
| 教訓 | NW台帳の先着登記と工程0（依存行の検証）は配線変更の事故を防ぐ。Phase 1→Phase 2の二段階変更が安全に成立した |

---

## 4. 引き継ぎ資料

| 資料 | 場所 |
|---|---|
| NW台帳 v2.2 | ai-family-memory main ops/state/network.yaml |
| 配線指針 v1.0 | ai-family-ops main docs/20260817_nw-wiring_guideline_v1.0.md |
| 配置変更計画書 | ai-family-ops main docs/20260818_port-migration-plan.md |
| M7b要件定義 v2 | rag-system main docs/m7b-requirements-v2.md |
| M7b hotfix-2指示書 | rag-system main docs/instructions/m7b-hotfix2-instructions.md |
| Phase 2指示書 | rag-system main docs/instructions/20260819_phase2-instructions.md |
| 手順書（改訂済み） | rag-system main docs/mcp-remote-setup.md |
| _STATUS.md | rag-system main _STATUS.md |
