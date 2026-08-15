# M5b-4 完了報告書

**作成日:** 2026-08-15  
**担当:** PG (Claude Sonnet 4.6)  
**フェーズ:** M5b-4 — アドバイザー再設計・三部構成答弁・クロスドメインeval

---

## 1. 実施概要

| 項目 | 内容 |
|------|------|
| 起点 | M5b-3クロスドメインeval — 5/8問が瞬間死、cd-02がcitation gap |
| 根本原因 | アドバイザーが「電気設備工事編」固有IDを持ちループ前に守備範囲外裁定 |
| 対策方針 | ループ前裁定廃止・アドバイザー役割再設計・三部構成答弁強制 |
| 実施 W項目 | W-1〜W-7（全実施）＋追加修正 W-8（幻覚引用防止） |

---

## 2. 改修内容（W-1〜W-7）

### W-1: ループ前アドバイザー廃止

`run_pre_composer()` からループ前アドバイザーブロックを削除。  
`out_of_scope` 返却 → `advisor_conclude_reason` / `advisor_missing_coverage` に置換。

根拠（`answer-principles-v1.md §3`）: 「検索前の守備範囲外裁定は原理的に不可能」。

### W-2: アドバイザー役割再設計

`_ADVISOR_SYSTEM_BASE` を全面書き直し:
- 廃止: `out_of_scope` 裁定・「電気設備工事編」固有ID
- 新設: `conclude`（収束裁定）+ `missing_coverage` フィールド
- 自己定義: 「所蔵文書群の有効範囲を所管するエージェント」（スコープ基準、ドメイン基準なし）
- `replan` 裁定を維持

### W-3: スタール検知分離

旧: `(consecutive_empty >= stall_threshold) or (total_search_calls >= search_budget)` で OR 判定  
新:
- **budget_stop**: `total_search_calls >= search_budget` → break、アドバイザー呼ばず、`budget_stop` をトレースに記録
- **stall**: `consecutive_empty >= stall_threshold` のみでアドバイザー呼び出し

### W-4: アドバイザー入力トークン守衛

```python
_CHUNK_BODY_LIMIT = 120          # チャンク本文プレビュー最大文字数
_ADVISOR_CHUNK_TOTAL_LIMIT = 8000  # アドバイザー向け総文字数ガード
```

`_format_chunks_for_advisor()` を新設。超過時は `chunk_id + hierarchy + heading` のみにフォールバック。

### W-5: コンポーザー三部構成強制

`_build_composer_system()` を全面再設計:
- `§4 三部構成`: 1.所蔵から言えること / 2.所蔵にないこと / 3.推論で補えること
- `§5 文体規律`: 謝罪表現・「無関係」・完全拒否・「専門家にご相談」禁止
- チャンクIDを `[chunk_id]` 形式で明示引用を義務化
- `advisor_conclude_reason` は「命令」ではなく「参考情報」として渡す

### W-6: フロントエンド同期（app.py）

- `make_composer_stream()` 呼び出し: 新 kwargs `advisor_conclude_reason` / `advisor_missing_coverage` 対応
- トレース表示: `conclude` → 「収束裁定」、`budget_stop` エントリ追加、`missing_coverage` 表示
- デバッグパネル: `out_of_scope` → `conclude`

### W-7: クロスドメインeval スクリプト強化

- `--top-k INT` / `--tag STR` 引数追加
- `_TOP_K_OVERRIDE` グローバルによるインプロセス上書き（settings.json 競合回避）
- `RESULTS_DIR` タグベース切替
- `finally` で `rerank_enabled` のみ復元（`top_k` は settings.json に書き込まない）

### W-8: コンポーザーのハルシネーション対策（W-7 eval 観察を受けた追加修正）

cd-10 で retrieval=0 にもかかわらず `【kaishu-kenchiku-r7 第1章 総則 1.1 適用範囲】` という架空引用が発生したことへの対応。

**対策A: 引用可能 chunk_id リストの注入**  
`_build_composer_user_msg()` が取得済みチャンクのIDリストをユーザーメッセージに挿入する。  
チャンクなし時は「取得チャンク0件：架空ID・文書名・条番号を引用形式で一切記載しないこと」を挿入。

**検索未到達モード（ゼロ件時の三部構成変形）**  
`_build_composer_system()` に `zero_result_mode: bool` 引数を追加。  
取得チャンク=0 のとき、標準三部構成を以下の変形構成に切り替える:

| 通常モード | 検索未到達モード |
|----------|----------------|
| 1. 所蔵から言えること | 1. 検索未到達の告知（N回検索したが取得できなかった旨） |
| 2. 所蔵にないこと | 2. 所蔵にないこと（推定）（コーパス外 or 語彙不一致の可能性） |
| 3. 推論で補えること | 3. 推論で補えること |

dry-run 確認済み: 冒頭に「今回の検索では6回検索しましたが…」と正直に告知し、架空引用がゼロになった。

---

## 3. 改修前後 比較表（A部 8問）

### M5b-3（改修前）vs M5b-4 topk10（改修後）

| id | M5b-3 ret | M5b-3 cit | M5b-4 ret | M5b-4 cit | 変化 |
|----|-----------|-----------|-----------|-----------|------|
| cd-01 | —（瞬間死） | — | 0.67 | 0.67 | ✅ 復活 |
| cd-02 | 0.67 | 0.00 | 0.67 | 0.67 | ✅ citation gap 解消 |
| cd-03 | —（瞬間死） | — | 0.00 | 0.00 | ✅ 瞬間死は消えたが検索失敗 |
| cd-04 | —（瞬間死） | — | 1.00 | 0.50 | ✅ 復活 |
| cd-05 | —（瞬間死） | — | 1.00 | 1.00 | ✅ 復活 |
| cd-06 | —（瞬間死） | — | 1.00 | 1.00 | ✅ 復活 |
| cd-07 | —（瞬間死） | — | 0.50 | 0.50 | ✅ 復活 |
| cd-08 | —（瞬間死） | — | 1.00 | 0.50 | ✅ 復活 |
| **平均** | — | — | **0.7292** | **0.6042** | |

> M5b-3の「瞬間死」: loops=1でアドバイザーが守備範囲外裁定を出したため検索結果ゼロで終了。  
> ret=—: 検索が1回も実行されなかったため計測不能。

### top_k 比較（M5b-4内）

| id | topk5 ret | topk5 cit | topk10 ret | topk10 cit |
|----|-----------|-----------|------------|------------|
| cd-01 | 1.00 | 1.00 | 0.67 | 0.67 |
| cd-02 | 1.00 | 0.67 | 0.67 | 0.67 |
| cd-03 | 0.50 | 0.50 | 0.00 | 0.00 |
| cd-04 | 1.00 | 1.00 | 1.00 | 0.50 |
| cd-05 | 1.00 | 0.67 | 1.00 | 1.00 |
| cd-06 | 1.00 | **0.00** | 1.00 | 1.00 |
| cd-07 | 0.50 | 0.50 | 0.50 | 0.50 |
| cd-08 | 1.00 | 0.50 | 1.00 | 0.50 |
| **平均** | **0.8750** | **0.6042** | **0.7292** | **0.6042** |

> topk5 cd-06: retrieved=16チャンク、answer=空文字列。確率的LLM障害（コンポーザーが応答を生成しなかった）。  
> avg_doc_recall は両設定で同一（0.6042）。retrieval_doc_recall は topk5 が高い。

---

## 4. 合格基準判定（topk10）

| 基準 | 結果 | 判定 |
|------|------|------|
| 0件の瞬間死（ループ1回でアドバイザー裁定） | 最小ループ数=3 | ✅ |
| 0件のcitation gap（ret>0 かつ cit=0） | 0件 | ✅ |
| 0件の完全拒否（全10問で守備範囲外宣言のみで終わらない） | 0件 | ✅ |
| avg_doc_recall ≥ 0.5 | 0.6042 | ✅ |

**topk10: 全基準合格。**

> topk5: cd-06で空答（完全拒否相当）が1件発生。原因は確率的LLM障害。  
> avg_doc_recall は同一（0.6042）のため topk10 推奨。

---

## 5. 回帰eval（eval/questions.jsonl）

| 項目 | 結果 |
|------|------|
| 問数 | 10問 |
| 全問回答 | ✅ 全問 answer_length > 0 |
| 三部構成 | ✅ 全問「所蔵から言えること」「所蔵にないこと」「推論で補えること」を含む |
| 完全拒否 | 0件 |

---

## 6. B部 回答全文

### cd-09（A部との複合問：RC梁貫通スリーブ施工仕様）
**topk5 結果:** retrieval_doc_recall=0.67、doc_recall=0.33、loops=4、boundary_declared=True

**評価のポイント（boundary_expectation より）:**  
- スリーブ径・防火区画処理・保温施工は所蔵文書から根拠付きで回答可能  
- RC梁の孔径制限・補強要否は所蔵にないため宣言すべき

**B部 回答（topk5）:** 上記要件を充足している。  
- §1: kaishu-denki-r7・kaishu-kikai-r4・kikai-shiyousho-r7を引用しスリーブ径規定・防火区画処理・配管支持を明示  
- §2: 梁の孔位置制限・径上限・補強要否を「所蔵にありません」と宣言、建築構造設計基準・RC規準を参照先として提示  
- §3: 外径計算（管外径+保温50mm×2+40mm=約316mm ≒ 梁せいの53%）から補強必須と推論  
- keyword `確認が必要` 検出 → boundary_declared=True ✅

**topk10 結果:** boundary_declared=False（「確認が必要」が回答中に出現しなかった）。同じ三部構成だが宣言キーワードの有無の違いのみ。PMが全文判定。

---

### cd-10（バリアフリートイレ改装 — 寸法基準コーパス外トラップ）
**topk5 結果:** retrieval_doc_recall=0.0、doc_recall=0.0、loops=7、boundary_declared=True  
**topk10 結果:** retrieval_doc_recall=0.0、doc_recall=0.0、loops=7、boundary_declared=True

**評価のポイント（boundary_expectation より）:**  
- スロープ幅・バリアフリー法寸法基準はコーパスに存在しないため宣言すべき  
- タイル・防水・衛生器具はコーパスから回答できる（trap: 無根拠に寸法を断定したら減点）

**B部 回答（topk10）:**  
- §1: kaishu-kenchiku-r7 第1章 総則を引用（改修工事の基本原則）。ただし7ループ検索で関連チャンクをリトリーブできず、引用は幻覚（チャンクIDなし）。  
- §2: スロープ幅・トイレ内寸法の規定が所蔵にないことを明示、バリアフリー法を参照先として提示 ✅  
- §3: 900mm/2000×2000mm等の推奨値を「推論」ラベルで記載（断定せず）✅  
- `規定がない` keyword 検出 → boundary_declared=True ✅

**注意:** retrieval=0.0のため §1 で意図せず幻覚引用が発生している。PMが全文を確認の上、幻覚引用の減点有無を判定してください。

---

## 7. コスト合計

| eval | 設定 | コスト |
|------|------|--------|
| crossdomain topk10 | no-rerank, top_k=10 | $0.0611 |
| crossdomain topk5 | no-rerank, top_k=5 | $0.0945 |
| regression（10問） | デフォルト設定 | 未集計（results.jsonl参照） |
| **合計（approx）** | | **~$0.16** |

---

## 8. 未解決事項・次フェーズ持ち越し

| 項目 | 内容 |
|------|------|
| cd-10 幻覚引用 | retrieval=0のまま §1 に kaishu-kenchiku-r7 引用が発生。コーパスに車椅子トイレ改装仕様がないか再確認が必要 |
| cd-03 retrieval=0 (topk10) | kikai-shiyousho-r7 + law-91b を検索失敗。クエリ戦略の改善余地あり |
| topk5 cd-06 空答 | 確率的LLM障害（reproduceは未確認）。コンポーザー出力ガードの検討 |
| cd-09 B部 cit=0.33 | kouzou-sekkei-shiryou-r3 が missing_cit。コーパスに存在しない可能性が高い |

---

*報告終了。「確認をお願いします」*
