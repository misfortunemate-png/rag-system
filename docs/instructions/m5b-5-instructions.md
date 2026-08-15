# 規程エージェント M5b-5作業指示書（検索到達性の改修＋検収再eval）

作成日: 2026-08-16 ／ PM: クリーデ ／ 根拠文書: docs/answer-principles-v1.md（既読前提）
位置づけ: M5b-4で判明した検索到達性の問題と、W-8適用後の検収再evalを一括で実施する。

## 背景

M5b-4でアドバイザー再設計・三部構成を実装し、瞬間死・citation gap・全面拒否の三指標はゼロになった。しかしcd-10（ret=0.0・topk5/topk10ともに一貫）とcd-03（topk10でret=0.0）は検索段で期待文書に到達できていない。cd-10はバリアフリートイレ改装という質問に対し、7ループ検索しても所蔵チャンクを1件も取得できなかった。質問語彙（「多機能トイレ」「車椅子」）とチャンク語彙のミスマッチが主因と推定される。

また、W-8（幻覚引用防止）はM5b-4のeval後に実装されており、最終コードでの再走が未了。

## 作業範囲

- **何を**: domain自動絞り込みの既定OFF、ツールレベルの安全策、トレース記録の拡充、検収再eval
- **なぜ**: 不要な複雑性の除去、検索失敗時の可視性向上、W-8を含む最終コードの検証
- **触らない**: 検索エンジン（RRF重み・リランカー・BM25・ingest・チャンキング）、アドバイザー/コンポーザー/プランナーのプロンプト本文

## 作業項目

### W-1: domain自動絞り込みの既定OFF（発注者裁定済み）

- config.pyの `planner_enabled` は現行 False のまま維持（プランナーそのものの有効/無効はこのフェーズでは変えない）
- プランナープロンプトから `relevant_domains` の出力指示と `domain_section`（ユーザー選択分野の提示）を削除する
- `_parse_relevant_domains()` 関数は残置し、呼び出し元のdomain narrowingブロック（R-10・740-750行付近）を無効化する（コメントアウト＋ログに「R-10 disabled (M5b-5)」出力）
- UIのdomain選択プルダウンは残す（selected_domainsがユーザー手動選択由来の場合は引き続きフィルタに使う）

### W-2: ツールレベルのdomain引数の除去

search_chunksのツールスキーマ（TOOLSリスト）から `domain` パラメータを削除する。ループLLMが任意にdomainフィルタを渡す経路を断つ。

search_chunks関数のPythonシグネチャ上の `domain` / `domains` 引数は残す（UIや将来のAPI呼び出しで使うため）。削除するのはLLMに公開するツールスキーマのみ。

### W-3: ゼロ件セーフティ（決定的コード）

search_chunks関数内に以下のフォールバックを追加する:

1. フィルタ付き検索（`allowed_domains` または `doc_ids` がある場合）で dense + BM25 の統合結果が 0件のとき、同一クエリでフィルタなし再検索を1回だけ自動実行する
2. フォールバック発動時はログに `filter_fallback: domains=... -> unfiltered` を出力する
3. 返却するチャンクの各要素に `"filter_fallback": true` フラグを付与する（トレースから追跡可能に）

W-2でLLM経由のdomain指定は断たれるため、このセーフティはUI由来のユーザー手動フィルタに対するフェールオープンとして機能する。

### W-4: トレース記録の拡充

M5b-4のevalではtraceが空リストで記録されており、tool call引数の事後分析ができなかった。evalスクリプト（run_crossdomain_eval.py）が結果JSONにトレースを保存する経路を確認し、以下の情報が記録されることを保証する:

- 各ループのtool_calls: `name`, `input`（query・domain・doc_ids等すべて）, ヒット件数
- アドバイザー裁定: decision, reason, missing_coverage
- budget_stop / early_stop の有無

run(question, config) の返却値の中にtraceが含まれているはず（agent.pyの返却構造を確認のこと）。evalスクリプト側で結果JSONに格納する処理が欠落している場合は追加する。

### W-5: 検収再eval

**W-1〜W-4の実装後**、以下を実行する:

#### A. クロスドメインeval
- eval/questions_crossdomain.jsonl（改変禁止）の10問をtopk5/topk10両構成で再実行
- **domain絞り込みOFF**で実施（W-1の結果として自然にそうなる）
- cd-06の空答再現性確認: topk5で2回実行し、2回とも回答が生成されることを確認（1回でも空答なら報告）

#### B. 回帰eval
- eval/questions.jsonl（既存10問）をデフォルト設定で再実行。全問回答生成を確認

#### C. 記録
以下の項目を docs/reports/m5b-5-completion.md に記載する:

1. M5b-3→M5b-4→M5b-5の三時点比較表（A部8問: ret / cit / loops）
2. cd-10のトレース（W-4で拡充済み。何を検索し何がヒットし何がヒットしなかったか）
3. B部回答全文（cd-09・cd-10、topk10のみ）
4. 回帰eval結果（全問回答/三部構成の有無）
5. コスト合計

#### D. 受入目安

| 項目 | 目標 |
|---|---|
| 瞬間死（loops=1型） | 0問 |
| citation gap（ret>0 かつ cit=0） | 0問 |
| 全面拒否 | 0問 |
| 空答（answer長=0） | 0問 |
| 回帰 | 全問回答 |
| cd-10幻覚引用（架空chunk_idの引用形式使用） | 0件 |

avg_doc_recallの数値目標は設けない。cd-10はトラップ問（バリアフリー法の寸法基準は所蔵外）であり、検索未到達は正当な可能性がある。到達性の改善は検索エンジン層のスコープ（M6以降）で扱う。**このフェーズの目的は不要な複雑性の除去、失敗時の正直な振る舞い、トレースの可視化である。**

## 禁止事項

- eval/questions_crossdomain.jsonl・questions.jsonl を改変しない
- プロンプト本文（アドバイザー・コンポーザー・プランナー・ループ）を変更しない（W-1のプランナーからのrelevant_domains出力削除のみ例外）
- 検索層を改修しない

## 完了条件

- W-1〜W-4の実装
- W-5の再eval結果
- docs/reports/m5b-5-completion.md 提出
- _STATUS.md更新・5W1Hコミット
- 「確認をお願いします」で完了報告
