# M4.5 完了報告 — 文書投入基盤（受信箱・ツリー選択）

作成日: 2026-08-08  
実装担当: PG (Claude Sonnet 4.6)  
PM: クリーデ（Opus席）

---

## 実装スコープ

| 項目 | 状態 |
|---|---|
| 受信箱intake（intake.bat + scripts/intake.py） | ✅ |
| フォルダツリー分類（domain/tags自動付与） | ✅ |
| UI 文書スコープ選択（サイドバーツリー＋タグ絞り込み） | ✅ |
| チャンク方式プロファイル（jouban/generic）— M4で完了済 | ✅ |
| 既存チャンク遡及登録（doc_id Chromaマイグレーション） | ✅ |
| documents.yaml 遡及登録（公共建築工事標準仕様書） | ✅ |

---

## 主要変更ファイル

| ファイル | 変更内容 |
|---|---|
| `src/config.py` | `selected_doc_ids: list \| None = None` 追加（None=全文書、[]=全除外）、`load_documents_yaml()` 追加 |
| `src/tools.py` | `search_chunks()` に `doc_ids` パラメータ追加、Chroma `$in` フィルタ実装 |
| `src/agent.py` | `_build_scope_docs_text()` 追加、planner/loop/composer システムプロンプト動的化、doc_ids をパイプライン全段に伝播 |
| `src/chunker.py` | `chunk_generic()` / `detect_profile()` / `chunk_by_profile()` / `append_jsonl()` 追加（M4.5前半で完了済） |
| `app.py` | 文書セクション（ツリー選択・タグ絞り込み・全選択/全解除）、メタフッターにスコープ件数追記 |
| `scripts/intake.py` | 新規: SHA-256 dedup・domain/tags推定・extract/chunk/embed/Chroma・raw/移動・yaml登録・既存chunk遡及マイグレーション |
| `intake.bat` | 新規: ASCII/CRLF、ダブルクリック一発実行（R-015準拠） |
| `data/inbox/.gitkeep` | 新規: 受信箱ディレクトリ |
| `documents.yaml` | 公共建築工事標準仕様書の遡及登録（SHA-256付き） |
| `settings.json.example` | `selected_doc_ids: null` 追加 |

---

## 設計決定事項

### selected_doc_ids の仕様
- `None`（デフォルト）: 全文書対象（Chroma フィルタなし）
- `[]`（全解除）: 検索結果0件（エラーにならずに空応答）
- `["id1", "id2"]`: 指定文書のみ対象

### Chroma doc_id マイグレーション
- 既存644チャンクに `doc_id=denki-setsubi` を `col.update()` で遡及付与
- intake.py 起動時に毎回自動実行（冪等）
- 再ingest禁止制約を厳守

### フォルダツリー分類ルール
- `inbox/<第1階層>/file.pdf` → `domain=<第1階層>`
- `inbox/<第1階層>/<第2階層以降>/file.pdf` → `tags=[<第2階層以降>]`
- inbox直下に直置きの場合 → `domain=未分類`

### システムプロンプトの動的スコープ
- planner/loop/composer の全段でスコープ内文書一覧を `documents.yaml` から動的生成
- "プロンプトは彫り込まない" 原則に従い、文書名・domain・tags の事実のみ提示

---

## テスト項目検証

| テスト | 方法 | 結果 |
|---|---|---|
| 遡及登録 | documents.yaml 確認 + Chroma doc_id フィルタ動作確認 | ✅ 644件マイグレーション済み、`doc_ids=['denki-setsubi']` で正常検索 |
| スコープ（doc_ids=None） | `search_chunks('ケーブル', top_k=2, doc_ids=None)` | ✅ 2件返却 |
| スコープ（doc_ids=[]） | `search_chunks('ケーブル', top_k=2, doc_ids=[])` | ✅ 0件返却（エラーなし） |
| スコープ（doc_ids=['denki-setsubi']） | `search_chunks('ケーブル', top_k=2, doc_ids=['denki-setsubi'])` | ✅ 2件返却 |
| UI表示 | app.py 構文チェック + Streamlit起動確認 | ✅ |
| intake.bat 文字コード | ASCII/CRLF確認 | ✅ |

新規投入テスト（PDF1冊→intake.bat→UI表示）、冪等テスト、衝突テストは発注者実機確認項目。

---

## 残課題（次フェーズ）

- M5: マルチ文書での回答品質検証・プランナーへのdoc選択連携チューニング
- `read_section` のスコープガード（現在はLLM任せ）
- generic プロファイルのチューニング（品質の追い込みはM5指示書で）
