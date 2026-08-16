# M6-2 完了レポート — 格付けロジック改修・法令API統合

作成日: 2026-08-16 / 担当: エージェント

## 概要

M6-1の仮設計（ドメイン末尾一致三層）を `data/web_tiers.yaml`（発注者支給物）の実データ構造に合わせて改修した。
e-Gov法令API統合、コンポーザーへのtag伝達、MCPツール拡張を実施。

---

## 実施内容

### W-1: tier判定ロジック改修（`src/web_fetch.py` 完全書き直し）

- `_build_lookup()`: web_tiers.yaml の全エントリをモジュール起動時にメモリ上のルックアップテーブルに変換
- `_classify_tier_and_meta(url)`: 5段階優先順位で判定
  1. `negative_examples` URL前方一致 → negative tag（tier-3-2 / tier-3-4）
  2. go.jp ドメイン末尾一致 → tier=1（従来ロジック維持）
  3. `tier_2` URL前方一致 → tier=2、tag/verified/category/access_restriction を付与
  4. `tier_3` URL前方一致 → tier=3、tag を付与
  5. 該当なし → tier=3、"【tier-3：未分類】"
- `fetch_and_extract()` 返値に `tag`, `verified`, `category` を追加
- `access_restriction` エントリは fetch 試行 + ログ記録（LIXIL等）

### W-2: e-Gov法令API統合（`src/web_fetch.py` + `src/agent.py`）

- `fetch_law_text(law_id)`: e-Gov法令API v1 からXML取得・テキスト変換（3,000字打ち切り、エラー時 text="" で継続）
- `LAW_ID_MAP`: 8法令のID定数（建築基準法・建築基準法施行令・消防法・電気事業法・労働安全衛生法・省エネ法・水道法・下水道法）
- `_run_web_search_stage` に法令API呼び出しを統合:
  - `question + missing_coverage` に法令名が含まれる場合に自動呼び出し
  - 最大2件・1秒インターバル（レート制限遵守）
  - 法令API結果をWeb検索結果の前に挿入（tier=1優先）

### W-3: コンポーザーへのtag伝達（`src/agent.py`）

- `_format_web_results()` 改修:
  - `[tier N: url]` → `[{tag} url]` 形式に変更
  - negative_examples（tier-3-2/tier-3-4）は `（引用禁止。参考情報としてのみ言及可）` を付記し本文非掲載
- `_build_composer_system()` の `web_rules` 改修:
  - tag文字列を回答中に必ず併記する要件を追加
  - 【tier-3-2】引用禁止ルール追加
  - 【tier-3-4】「確認を要する」付記ルール追加

### W-4: MCPツール拡張（`src/mcp_server.py`）

- `web_search_tool`: 返値に `tag`, `verified`, `category` を追加
- `fetch_law` ツール新設: `fetch_law_text(law_id)` を直接呼び出す

---

## 検証結果（W-5）

### A. tier判定ユニットテスト: **7/7 PASS**

| URL | 期待tier | 期待tag | 結果 |
|---|---|---|---|
| https://laws.e-gov.go.jp/.../325AC0000000201 | 1 | 【tier-1：法令原文】 | OK |
| https://www.mlit.go.jp/... | 1 | 【tier-1：法令原文】 | OK |
| https://www.maruichikokan.co.jp/products/349/ | 2 | 【tier-2：仕様書】 | OK |
| https://electric-facilities.jp/denki4/haikan.html | 3 | 【tier-3：独自知見】 | OK |
| https://kenshoku-bank.com/column/1596/ | 3 | 【tier-3-2：引用列挙のみ】 | OK |
| https://progress-company.jp/blog/20260318/ | 3 | 【tier-3-4：過度の一般化リスクあり】 | OK |
| https://example.com/unknown | 3 | 【tier-3：未分類】 | OK |

### B. e-Gov法令API疎通: **PASS**

```
law_id  : 325AC0000000201
title   : '建築基準法'
tier    : 1
tag     : 【tier-1：法令原文】
source  : e-gov-law-api
verified: True
text_len: 3000
```

### C. パイプラインeval（Web照合発火時）

Web照合は「advisor conclude + missing_coverage」時のみ発火（M6-1設計通り）。
スモークテスト（防火区画 × 消防設備）では所蔵文書で回答完結→Webステージ非発火=正常動作。
Web照合発火する問（advisor 難航）での tag 伝達はコード確認済み（`_format_web_results` tag付与・コンポーザー rules 更新）。

### D. 回帰eval（web_search_enabled=False, questions.jsonl 10問）: **10/10 PASS**

全問回答生成確認。既存機能への影響なし。

---

## 禁止事項の遵守

- `data/web_tiers.yaml`: 改変なし（発注者支給物）
- 既存検索層: 変更なし
- e-Gov法令API: 1件ずつ1秒インターバル実装

---

## 変更ファイル一覧

| ファイル | 変更内容 |
|---|---|
| `src/web_fetch.py` | 完全書き直し（W-1, W-2） |
| `src/agent.py` | `_format_web_results`, `_run_web_search_stage`, `web_rules` 改修（W-2, W-3） |
| `src/mcp_server.py` | `web_search_tool` 更新, `fetch_law` 追加（W-4） |
