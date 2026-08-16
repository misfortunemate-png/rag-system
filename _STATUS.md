---
version: "M6-2"
badge: "M6-2完了・完了報告提出中（PM検収待ち）"
next: "M6-3以降（PM指示書待ち）"
waiting_on: "PM検収（m6-2-completion.md）"
---

# rag-system 現在地

更新: 2026-08-16 ／ 更新者: PG

## 状態

- M1〜M5c 全フェーズ完了・検収済み
- M6-1（Web照合ツール実装・パイプライン統合）: 完了・検収済み
- **M6-2（格付けロジック改修・法令API統合）: W-1〜W-5実施・完了報告提出中（PM検収待ち）**
- 次マイルストーン: PM指示書待ち

## M6-2 実施結果

- tier判定ユニットテスト: 7/7 PASS ✅
- e-Gov法令API疎通（建築基準法 325AC0000000201）: PASS ✅
- 回帰eval（web_search_enabled=False, 10問）: 10/10 PASS ✅

## M6-2 追加実装

| 項目 | 内容 |
|---|---|
| W-1 | src/web_fetch.py 完全書き直し（URL前方一致5段階tier判定、tag/verified/category付与） |
| W-2 | fetch_law_text + LAW_ID_MAP（e-Gov法令API v1）、_run_web_search_stage に統合 |
| W-3 | _format_web_results → tag形式出力、web_rules → tag引用ルール・tier-3-2/3-4追加 |
| W-4 | mcp_server.py: web_search_tool にtag/verified/category追加、fetch_law ツール新設 |
| W-5 | 検証eval（tier unit 7/7、法令API疎通、回帰10/10） |

## 技術スタック（M6-2完了時点）

- 検索: ruri-v3-310m(dense) + fugashi+BM25 → RRF → ruri-v3-reranker-310m（top_k=5 既定）
- エージェント: Planner → Execution Loop → [Advisor] → **[Web照合 + 法令API]** → Composer
- Web照合: 発動条件=アドバイザーconclude+missing_coverage / バックエンド=DuckDuckGo既定
- 法令API: e-Gov法令API v1、法令名マッチで自動呼び出し（最大2件・1秒インターバル）
- 格付け: web_tiers.yaml準拠（negative_examples → go.jp → tier_2前方一致 → tier_3前方一致 → 未分類）
- 三部構成: 所蔵から言えること / 所蔵にないこと / 推論で補えること
- ゼロ件モード・空答ガード・UI: M6-1から継続
