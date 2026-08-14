# 規程エージェント M5a作業指示書（素材拡充）

作成日: 2026-08-14 ／ PM: クリーデ ／ 対応仕様: docs/data-definition-v0.4.md・docs/roadmap-v1.md
位置づけ: 本書一枚でこのフェーズの全指示が完結する（追補なし・R-014）

## 添付マニフェスト（着工前照合・必須）

以下がすべて交換所（リポジトリ）に存在すること。**1つでも欠けたら着工せず docs/reports/ に報告。**

| # | パス | 種別 | SHA-256（支給物のみ） |
|---|---|---|---|
| 1 | docs/instructions/m5a-instructions.md | 指示書 | — |
| 2 | docs/data-definition-v0.4.md | 仕様書 | — |
| 3 | docs/roadmap-v1.md | ロードマップ | — |

ローカル前提ファイル（リポジトリ外・フラン上）:

| # | パス | 確認方法 |
|---|---|---|
| A | `D:\AI\github\rag-system\0814scraping_plan\output\` | ディレクトリ存在確認 |
| B | `D:\AI\github\rag-system\0814scraping_plan\rag_file_list.json` | ファイル存在確認 |

**A・Bが見つからなければ発注者に確認。**

## PG運用規律（定型・全フェーズ共通）

1. **三則**: ①難航時はPMへ差し戻す ②原因判明時は「原因X・対策Y・実行可否」で報告→指示待ち ③セッション外プロセス停止等は事前許可
2. **宛先**:
   - **仕様の疑義・技術判断** → docs/reports/ にpushしてPMへ
   - **環境・インフラの問題**（ファイルが見つからない、権限、起動不能等）→ 発注者に直接聞いてよい
   - **実機試験の依頼・承認** → 発注者
3. **支給物改変禁止**: PM支給物はdiffゼロで検収される。技術的整合の調整もPMへ差し戻す
4. **着工前**: `git pull` → マニフェスト照合。緑でなければ着工しない
5. **完了宣言禁止**: 「確認をお願いします」で止める

## 作業範囲

- **何を**: RAG素材を1件→90件に拡充する（PDF 82件 + 法令XML 8件）
- **なぜ**: M5a（素材拡充）。横断検索の実用性と検証基盤の前提
- **どこで**: rag-system リポジトリ（D:\AI\github\rag-system）

## 作業手順

### 手順1: ファイル配置

`0814scraping_plan/output/` 配下のファイルを `data/raw/` にコピーする。フォルダ構造は保持。

対象:
- `01_mlit/` 以下の全PDF（13件）
- `02_denki/` 以下の全PDF（2件）
- `03_shobo/` 以下の全PDF（42件）
- `05_tosou/` 以下の全PDF（2件）
- `07_mhlw/` 以下の全PDF（1件）
- `08_gyoukai/` 以下の全PDF（1件）
- `09_maker/` 以下の全PDF（1件）
- `10_hourei/` 以下の **XMLファイルのみ**（8件）

**除外:**
- `10_hourei/*.txt`（XMLと重複。XMLを優先）
- `11_scraped/`（L3スクレイピング結果・対象外）

既存の `data/raw/公共建築工事標準仕様書（電気設備工事編）令和７年版.pdf` は削除してよい（スクレイピング出力の `01_mlit/shiyousho/denki_shiyousho_R7.pdf` が同一ファイル）。

コピー後、対象ファイル数が90件であることをカウントして確認。

### 手順2: documents.yaml 生成

`rag_file_list.json` を入力として、`documents.yaml` を生成するスクリプト `scripts/gen_documents_yaml.py` を作成・実行する。

各エントリの構成:

```yaml
- id: "{doc_slug}"
  doc_slug: "{doc_slug}"
  title: "{rag_file_list.jsonのtitle}"
  domain: "{下表による}"
  tags: []
  profile: "auto"   # PDF: ingest時にdetect_profileで判定。XML: "hourei"固定
  file_path: "data/raw/{rag_file_list.jsonのpath}"
  ingest_at: "2026-08-14"
  status: active
```

**doc_slug生成規則:**
- ファイル名の拡張子を除いた部分を使用
- 大文字→小文字、アンダースコア→ハイフン、日本語部分は除去
- 例: `kenchiku_shiyousho_R7.pdf` → `kenchiku-shiyousho-r7`
- 例: `bepyo_01_shoukaki.pdf` → `bepyo-01-shoukaki`
- 例: `law-89a_電気事業法.xml` → `law-89a`（最初のアンダースコアまで）
- slug重複が発生した場合は末尾に `-2`, `-3` を付与

**domain割り当て規則:**

| パスパターン | domain |
|---|---|
| `01_mlit/shiyousho/*kenchiku*` | 建築 |
| `01_mlit/shiyousho/*mokuzou*` | 建築 |
| `01_mlit/shiyousho/*denki*` | 電気 |
| `01_mlit/shiyousho/*kikai*` | 機械 |
| `01_mlit/sekkei/*` | 設計 |
| `01_mlit/sekisan/*` | （空文字列） |
| `02_denki/*` | 電気 |
| `03_shobo/*` | 消防 |
| `05_tosou/*` | 塗装 |
| `07_mhlw/*` | 衛生 |
| `08_gyoukai/*` | （空文字列） |
| `09_maker/*` | （空文字列） |
| `10_hourei/*` | （空文字列） |

パターンに一致しない場合は空文字列。

### 手順3: XML法令抽出器の新設

`src/extract/law_xml_ext.py` を新設する。

**入力**: 法令XML（e-Gov API形式）のファイルパス
**出力**: チャンクのリスト（data-definition-v0.4.md のチャンクレコード形式に準拠）

処理:
1. XMLをパースし、`Article`（条）要素を走査する
2. 各条を1チャンクとする
3. 階層パス（hierarchy）は XML構造から構築: `{編名}/{章名}/{節名}/{条番号} {条名}`
4. heading = 条の見出し（`ArticleCaption`）
5. body = 条文の全テキスト（全項・号を含む平文）
6. refs = 空リスト（法令XMLの参照抽出は今回スコープ外）
7. source_engine = `"law_xml"`
8. doc_type = `"law"`

**XMLの典型構造**（参考）:
```xml
<Law>
  <LawBody>
    <MainProvision>
      <Part Title="第一編 ...">
        <Chapter Title="第一章 ...">
          <Section Title="第一節 ...">
            <Article Num="1">
              <ArticleCaption>（目的）</ArticleCaption>
              <Paragraph Num="1">
                <ParagraphSentence>
                  <Sentence>この法律は...</Sentence>
                </ParagraphSentence>
              </Paragraph>
            </Article>
          </Section>
        </Chapter>
      </Part>
    </MainProvision>
    <SupplementaryProvisions>...</SupplementaryProvisions>
  </LawBody>
</Law>
```

**注意**: 実際のXML構造はファイルによって異なる場合がある（Part/Chapter/Sectionの有無、附則の構造等）。先頭1ファイル（`law-90a_消防法.xml`）で動作確認してから全件に適用すること。構造が想定と大きく異なる場合は docs/reports/ に報告。

### 手順4: ingest.pyの一般化

現行の `ingest.py` は `pdf_path` 固定で plumber+pymupdf の二重抽出→仲裁を行っている。以下のように一般化する。

1. `documents.yaml` のフィールド名を `pdf_path` → `file_path` に変更対応（後方互換: `pdf_path` があれば `file_path` として読む）
2. ファイル拡張子による処理分岐:
   - `.pdf` → 既存のpdfplumber抽出（arbiterは使わない。intake.pyと同じpdfplumber単体方式）→ `detect_profile` → `chunk_by_profile`
   - `.xml` → `law_xml_ext` で直接チャンク生成（抽出とチャンキングが一体）
3. チャンクは全文書分を `all_chunks` に集約し、一括で embed → Chroma格納（既存のフローと同じ）

**arbiter（plumber+pymupdf二重抽出）を使わない理由**: 82件のPDFに対して二重抽出は時間がかかりすぎる。intake.pyのpdfplumber単体方式で十分な品質が出る。品質問題が判明した個別ファイルについては、後で arbiter経由の再ingestを検討する。

### 手順5: 全量再構築

1. `data/chroma/` を削除（Chromaをクリア）
2. `data/chunks.jsonl` を削除（再生成するため）
3. `data/refs.jsonl` を削除（再生成するため）
4. `python -m src.ingest` を実行
5. 完了後、以下を記録:
   - 総チャンク数
   - domain別チャンク数
   - 処理時間
   - エラーが出たファイル（あれば）

### 手順6: 品質レポート

以下をdocs/reports/m5a-completion.mdに記載する:

1. **ファイル集計**: 投入ファイル数（PDF/XML別）、documents.yamlのエントリ数
2. **チャンク集計**: domain別チャンク数、profile別（jouban/generic/hourei）チャンク数
3. **品質指標**:
   - char_count = 0 のチャンク数（テキスト抽出失敗の疑い = スキャンPDF候補）
   - char_count < 50 のチャンク数
   - char_count > 5000 のチャンク数
4. **処理時間**: 抽出・チャンキング・埋め込み・Chroma格納の各所要時間
5. **エラー一覧**: 処理に失敗したファイルがあれば、ファイル名とエラー内容

## 禁止事項

- eval/ 配下のファイルを改変しない
- 法令TXTファイル（`10_hourei/*.txt`）をingest対象に含めない
- `11_scraped/` 配下のファイルをingest対象に含めない
- arbiter（二重抽出）をデフォルトの処理パスにしない（手順4に記載の通り）
- `0814scraping_plan/` 配下のスクリプト（`l1_download.py`等）を実行・改変しない（参照のみ可）

## テスト

- **PG自己完結分**:
  - `python -m src.ingest` が全90件を正常に処理すること
  - `data/chunks.jsonl` のチャンク数が3,000以上であること（推定6,000-10,000）
  - documents.yamlのエントリ数が90であること
  - 各domainについて少なくとも1件のチャンクが存在すること（建築・電気・機械・設計・消防・塗装・衛生・空文字列の8種）
  - MCPサーバー（`python -m src.mcp_server`）が新しいChromaで起動し、search_chunksが応答すること
  - submit_questionで1問投げて回答が返ること（質問例: 「屋内消火栓の設置基準は？」— 消防domainのチャンクがヒットすること）
- **PM検査で確認する項目（PGは実施不要）**:
  - チャンク品質のサンプリング検査（domain代表1件ずつ）
  - eval回帰テスト（既存questions.jsonlの合格率が維持されること）

## 完了条件

- `data/raw/` に90件のファイルが配置されていること
- `documents.yaml` に90エントリが登録されていること
- `data/chroma/` にChromaコレクションが構築されていること
- `data/chunks.jsonl` が再生成されていること
- `scripts/gen_documents_yaml.py` が納品されていること
- `src/extract/law_xml_ext.py` が納品されていること
- `src/ingest.py` がPDF/XML両対応に一般化されていること
- 品質レポート（docs/reports/m5a-completion.md）が提出されていること
- _STATUS.md更新（フロントマター含む）・5W1Hコミット
- 「確認をお願いします」で完了報告
