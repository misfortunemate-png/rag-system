# 規程エージェント（jusetu-kogyo）

仕様書・帳票に根拠付きで答えるエージェントのケーススタディ。
公共建築工事標準仕様書（電気設備工事編・令和7年版）を素材に、検索→精読→照合→参照追跡の動作をトレース付きで実演する。

（デモGIF: M2完了後にここへ掲載）

## なにを見せるものか

ベクトル検索で条文を引くだけのRAGは、仕様書の下限しか返せない。実際の施工判断には条文間の関係（「○○による」の参照網）と現場知識が必要になる。本プロジェクトは、その第一歩として

- 2エンジン突合によるPDF抽出（採用判定の痕跡を残す）
- 条文構造に基づくルールベース分割（ドメイン知識）
- ツール2本だけの自前エージェントループ（挙動の説明可能性）
- 条文間参照の決定的抽出と、エージェントによる参照追跡
- 複数仕様の横断突合（整合／要調整の発見）

を、設計判断の記録とともに展示する。

## 技術構成

| 工程 | 採用 |
|---|---|
| PDF抽出 | pdfplumber + PyMuPDF 突合（帳票はMinerU） |
| チャンク分割 | 条番号正規表現（ルールベース） |
| 検索層 | LlamaIndex + Chroma |
| 埋め込み | ruri-v3-310m |
| エージェント | 自前ツール使用ループ（search_chunks / read_section） |
| LLM | OpenRouter／Anthropic切替式 |
| UI | Streamlit |

設計判断・棄却リスト・失敗分析は実装の進行に合わせて本READMEに追記する。

## マイルストーン

- M1: 単一文書ingest＋agent query（CLI）
- M2: Streamlit UI（トレース・根拠パネル）
- M3: 複数文書ingest＋横断モード
- M4: MinerU帳票ingest

## セットアップ

```bash
pip install -r requirements.txt
```

**注意：埋め込みモデル（ruri-v3-310m）はGPU推奨（CPU動作は644チャンクで約5時間）。**

## 実行フロー（M1）

```bash
# 1. 取り込み
python -m src.ingest

# 2. エージェント検索
python src/agent.py "分電盤の保護等級は屋内形と屋外形でそれぞれ何か？"

# 3. 一括評価（10問）
python eval/run_eval.py
# → eval/results.jsonl に出力（verdict欄は人間が記入）
```

## ファイル構成

```
src/extract/
  plumber.py      pdfplumber抽出
  pymupdf_ext.py  PyMuPDF抽出
  arbiter.py      突合判定（採用エンジン選択）
src/
  llm.py          LLMアダプタ（OpenRouter / Anthropic）
  chunker.py      条番号正規表現・分割ルール・refs抽出
  ingest.py       抽出→分割→埋め込み→Chroma格納
  tools.py        search_chunks / read_section
  agent.py        ツール使用ループ・トレース記録
eval/
  questions.jsonl 想定質問10問（PM支給・改変禁止）
  run_eval.py     一括評価実行
  results.jsonl   評価結果（実行後に生成）
tests/
  test_prefix.py  プレフィックスユニットテスト
  test_arbiter.py arbiterユニットテスト
  test_chunker.py chunkerユニットテスト
data/
  chunks.jsonl    中間チャンク（ingest後に生成・目視検査用）
  refs.jsonl      条文間参照エッジ（ingest後に生成）
  chroma/         Chromaベクトルストア（ingest後に生成）
documents.yaml    文書レジストリ
```

---

## 設計判断

### PDF抽出：pdfplumber＋PyMuPDF突合

単一エンジンでは「テーブル抽出精度（pdfplumber有利）」と「本文読み順（PyMuPDF有利）」のトレードオフが生じる。
arbiter.pyがページ単位で2エンジンの結果を比較し、**文字化け率（weight 0.6）+ 行断片化度（weight 0.4）** のスコアが低い方を採用。採用エンジンはchunk metadataの `source_engine` フィールドに痕跡として残す。

### チャンク分割：条番号正規表現

- 条（X.Y.Z）単位で1チャンク
- 300字未満 → 同じ節の隣接条文と統合（断片防止）
- 2,000字超 → 項（(1)(2)...）単位で分割（コンテキスト長制限への対応）
- 本文中の条文参照（`\d+\.\d+\.\d+「.+?」` 等）を決定的抽出してrefsフィールドに格納

### 埋め込みモデル：ruri-v3-310m

日本語検索精度（JMTEB）で現行最良クラスのローカルモデル。GPU推奨。
プレフィックスが異なる（文書側: `文章: ` / クエリ側: `クエリ: `）点が最大の既知の罠。
付与漏れをユニットテスト（`tests/test_prefix.py`）で検査する。

### LLMバックエンド：OpenRouter / Anthropic 切替式

`LLM_PROVIDER` 環境変数で切替。ツール定義は内部形式で保持しアダプタが各API形式に変換。

### エージェント：自前ツール使用ループ

LlamaIndex Agent等フレームワーク不使用。ループ制御・トレース記録を自前実装することで挙動の透明性を確保。
最大10ループ。全ツール呼出と引数をリストで保持し、eval・UIから参照可能。

---

## 棄却リスト

| 候補 | 棄却理由 |
|---|---|
| tesseract | 日本語精度で実用不達（実試行済み） |
| Docling | 日本語の漢数字・長音記号の誤抽出報告あり |
| YomiToku | 精度最高クラスだがCC BY-NC-SA。商用ライセンス別途必要 |
| ハイブリッド検索 | 10問規模に過剰。将来改善候補 |
| RAGAS | 評価の最終責任を機械に渡さない設計方針と相容れない |
| multilingual-e5-small | ruri-v3-310mの日本語精度に劣る（初期案から変更） |
| LlamaIndex Agent | ループ制御とトレース記録を自前実装して透明性を優先 |

---

## 将来構想

条文間参照グラフを土台に、実務者のフィードバック（横断突合で検出された「要調整」への人間の裁定）を関係として蓄積し、仕様書のテキストに書かれていない判断知識をオントロジーとして育成するループを構想している。詳細は実装後に記述する。

---

## 評価結果（eval/results.jsonl）

`python eval/run_eval.py` 実行後に生成される。verdict欄はショウゴさんが記入。
7問以上passを目標とするが、未達の場合は以下で分析：
- chunk境界が条文の途中で切れていないか（chunks.jsonlで目視確認）
- 検索でヒットしたchunk_idがexpected_sourceの条番号を含むか
- エージェントがrefs経由の参照追跡を実行しているか

---

## テスト実行

```bash
python -m pytest tests/ -v
```

| テスト | 確認内容 |
|---|---|
| test_prefix.py | クエリ・文書両側のプレフィックス付与 |
| test_arbiter.py | 文字化け・断片化スコアリング、エンジン選択 |
| test_chunker.py | 分割フィールド・階層構造・条番号抽出 |
