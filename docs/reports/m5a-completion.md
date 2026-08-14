# M5a 完了報告（素材拡充）

作成日: 2026-08-14

## 1. ファイル集計

| 項目 | 数量 |
|---|---|
| 投入ファイル数（PDF） | 64 |
| 投入ファイル数（XML） | 8 |
| 投入ファイル数（合計） | 72 |
| documents.yaml エントリ数 | 72 |

**注記**: 指示書上の目標90件に対し72件。rag_file_list.json記載の15件（東京消防庁tfd 13件、denki_shiyousho 1件、nohmi_shouka_shiryou 1件）がスクレイピング出力に存在しなかったため、発注者確認のうえ除外。

## 2. チャンク集計

| 区分 | チャンク数 |
|---|---|
| **総チャンク数** | **13,714** |

### domain別

| domain | チャンク数 |
|---|---|
| 建築 | 3,364 |
| 電気 | 2,964 |
| （空文字列） | 2,571 |
| 設計 | 1,845 |
| 機械 | 1,817 |
| 消防 | 603 |
| 塗装 | 386 |
| 衛生 | 164 |

### doc_type別（≒profile別）

| doc_type | チャンク数 |
|---|---|
| generic（PDF由来） | 11,694 |
| law（法令XML由来） | 2,020 |

## 3. 品質指標

| 指標 | 値 |
|---|---|
| char_count = 0（テキスト抽出失敗疑い） | 0 |
| char_count < 50 | 136 |
| char_count > 5,000 | 14 |
| 平均 char_count | 735 |
| 中央値 char_count | 779 |
| 最小 char_count | 2 |
| 最大 char_count | 8,270 |

## 4. 処理時間

| 工程 | 所要時間 |
|---|---|
| 抽出＋チャンキング | 196.2秒（3.3分） |
| 埋め込み（ruri-v3-310m） | 5,343.6秒（89.1分） |
| Chroma格納 | 14.7秒 |
| **合計** | **5,554.5秒（92.6分）** |

## 5. エラー一覧

処理失敗ファイル: **なし**（全72件正常完了）

## 6. テスト結果

| テスト項目 | 結果 |
|---|---|
| `python -m src.ingest` 全72件正常処理 | OK |
| `data/chunks.jsonl` チャンク数 ≥ 3,000 | OK（13,714） |
| documents.yaml エントリ数 = 72 | OK |
| 全8 domain にチャンク存在 | OK（建築・電気・機械・設計・消防・塗装・衛生・空文字列） |
| search_chunks 応答確認 | OK（「屋内消火栓の設置基準」→ 消防法施行令・施行規則・別表がヒット） |
| Chroma コレクション件数 | 13,714 |

## 7. 納品物一覧

| ファイル | 内容 |
|---|---|
| `data/raw/` （72件） | RAW素材ファイル |
| `documents.yaml` | 文書レジストリ（72エントリ） |
| `scripts/gen_documents_yaml.py` | documents.yaml生成スクリプト |
| `src/extract/law_xml_ext.py` | XML法令抽出器 |
| `src/ingest.py` | 一般化済みingestパイプライン |
| `data/chroma/` | Chromaコレクション |
| `data/chunks.jsonl` | チャンクデータ |
| `data/refs.jsonl` | 参照エッジ |

## 8. 既知の課題・PM検査時の留意事項

- PDF由来の全チャンクが `generic` profile。jouban（条番号型）検出密度が閾値未満のため。pdfplumber の `layout=True` 抽出でレイアウトスペースが入る影響の可能性あり。品質検査で条番号型PDFのチャンク構造を確認願います。
- `query.py` の `COLLECTION_NAME` が `jusetu_spec` になっていたため `kitei_spec` に修正済み。
