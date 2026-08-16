# 規程エージェント M6-2作業指示書（格付けロジック改修・法令API統合・eval）

作成日: 2026-08-16 ／ PM: クリーデ
位置づけ: data/web_tiers.yaml が調査プロジェクト成果物で更新された。M6-1の仮設計（ドメイン末尾一致三層）を実データに合わせて改修する。

## 背景

M6-1ではドメイン末尾一致（go.jp→tier_1等）の仮ロジックで疎通確認した。調査プロジェクトの成果物（web_tiers.yaml更新済み）は以下の構造を持つ:

1. **tier_1**: e-Gov法令APIのエンドポイント定義（法令原文XML/JSONを直接取得可）
2. **tier_2**: メーカー仕様書の個別URL登録（丸一鋼管・吉野石膏・フジクラ・能美防災・TOTO・LIXIL・パナソニック）。content/note/verified付き
3. **tier_3**: 専門家コンテンツの個別URL登録（electric-facilities.jp・JEEA・建築設備ラボ）
4. **negative_examples**: 引用禁止（tier-3-2：引用列挙のみ）・要注意（tier-3-4：過度の一般化リスクあり）のURL・判定根拠

M6-1のドメイン末尾一致ロジックではこの構造を読めない。改修が必要。

## 作業項目

### W-1: tier判定ロジックの改修（web_fetch.py）

現行のドメイン末尾一致を、以下の複合判定に改修する:

#### 判定順序（先にマッチした方が優先）

1. **negative_examples**: URLの前方一致。マッチしたらそのエントリのtagを返す（「tier-3-2」または「tier-3-4」）。tier値は3。
2. **tier_1**: URLのドメインがgo.jp末尾一致（従来ロジック維持。APIエンドポイントはW-2で別経路対応）
3. **tier_2**: URLの前方一致（各エントリのurl値）。マッチしたらtier=2、tag=そのエントリのtag値
4. **tier_3**: URLの前方一致。マッチしたらtier=3、tag=そのエントリのtag値
5. **該当なし**: tier=3、tag="【tier-3：未分類】"

#### 実装方針

- web_tiers.yamlの読み込み時に全URLエントリをコンパイルし、メモリ上にルックアップテーブルを保持する
- エントリの `verified: false` のものは判定リストに含めるが、fetch_and_extractの返値に `verified: false` フラグを付与する（LIXIL等）
- エントリの `access_restriction` があるものは、fetchを試みるがタイムアウト/ブロック時にログに記録する

#### 返値の拡張

fetch_and_extractの返値に以下を追加:
- `tag`: タグ文字列（例: "【tier-2：仕様書】"、"【tier-3-2：引用列挙のみ】"）
- `verified`: bool（web_tiers.yamlのverifiedフィールド。該当なしの場合はfalse）
- `category`: str | None（web_tiers.yamlのcategoryフィールド）

### W-2: e-Gov法令API統合（web_search.py または新設）

web_tiers.yamlのtier_1にはe-Gov法令APIのエンドポイントが定義されている。Web検索（DuckDuckGo等）とは別経路で、条文を直接取得する機能を追加する。

```python
def fetch_law_text(law_id: str) -> dict:
    """
    e-Gov法令API v1 から法令XMLを取得し、テキストに変換して返す。
    返値: {"law_id": str, "title": str, "text": str, "tier": 1, "tag": "【tier-1：法令原文】", "source": "e-gov-law-api"}
    """
```

- エンドポイント: `https://laws.e-gov.go.jp/api/1/lawdata/{law_id}`
- XMLレスポンスから条文テキストを抽出（全文は巨大なので、指定された条・項のみ抽出する仕組みが望ましい。最低限は全文取得→3,000字打ち切り）
- レート制限遵守: 1件ずつインターバル（1秒以上）を設けること
- 主要法令IDはweb_tiers.yamlに記載済み（建築基準法: 325AC0000000201 等）

#### パイプラインへの統合

_run_web_search_stage内で、missing_coverageに法令名（「建築基準法」「消防法」等）が含まれる場合、Web検索に加えてfetch_law_textを呼び出す。法令名→法令IDのマッピングはweb_tiers.yamlのdescriptionから構築する。

法令APIの結果もコンポーザーへのWeb照合素材ブロックに含める（tier=1、tag=【tier-1：法令原文】）。

### W-3: コンポーザーへのtag伝達

_format_web_resultsを改修し、tagフィールドを出力に含める:

```
[【tier-2：仕様書】 https://www.maruichikokan.co.jp/products/349/]
鋼製電線管（G管・C管・E管）の規格・寸法表...
```

negative_examples該当の場合:
```
[【tier-3-2：引用列挙のみ】 https://kenshoku-bank.com/column/1596/]
（引用禁止。参考情報としてのみ言及可）
```

コンポーザー厳守事項に以下を追加:
- 【tier-3-2：引用列挙のみ】のWeb素材は根拠引用不可。参考としても言及を最小限に
- 【tier-3-4：過度の一般化リスクあり】のWeb素材は引用時に「確認を要する」旨を付記すること
- 回答にWebソースを引用する場合はtag文字列を必ず併記すること（例:「能美防災公式（【tier-2：仕様書】）によれば…」）

### W-4: MCPツール拡張

mcp_server.pyに法令API用ツールを追加:

```python
@mcp.tool()
def fetch_law(law_id: str) -> dict:
    """e-Gov法令APIから法令条文を取得する。"""
```

web_search_toolの返値にもtag/verified/categoryを追加。

### W-5: 検証eval

以下の検証を実施する:

#### A. tier判定テスト（決定的・ユニットテスト相当）

web_tiers.yamlの全URLについてtier判定を実行し、期待するtier/tagが返ることを確認:

| URL | 期待tier | 期待tag |
|---|---|---|
| https://laws.e-gov.go.jp/... | 1 | 【tier-1：法令原文】 |
| https://www.mlit.go.jp/... | 1 | （go.jp一致） |
| https://www.maruichikokan.co.jp/products/349/ | 2 | 【tier-2：仕様書】 |
| https://electric-facilities.jp/denki4/haikan.html | 3 | 【tier-3：独自知見】 |
| https://kenshoku-bank.com/column/1596/ | 3 | 【tier-3-2：引用列挙のみ】 |
| https://progress-company.jp/blog/20260318/ | 3 | 【tier-3-4：過度の一般化リスクあり】 |
| https://example.com/unknown | 3 | 【tier-3：未分類】 |

#### B. 法令API疎通

fetch_law_text("325AC0000000201")（建築基準法）を呼び出し、条文テキストが返ることを確認。

#### C. パイプラインeval

クロスドメインeval（questions_crossdomain.jsonl）をweb_search_enabled=Trueで実行し:
- Web照合が発動した問でtag付き引用が回答に含まれること
- negative_examplesに該当するURLがtier-3-2/tier-3-4として正しくタグ付けされること
- Web照合OFF時との比較（三部構成§2の不足領域がWeb補完で埋まっているか）

#### D. 回帰

web_search_enabled=Falseで既存eval（questions.jsonl）を実行し、全問回答を確認。

結果を docs/reports/m6-2-completion.md に記載する。

## 禁止事項

- data/web_tiers.yaml を改変しない（発注者支給物）
- 既存の検索層を変更しない
- e-Gov法令APIへの短時間大量アクセス（1件ずつインターバル）

## 完了条件

- W-1〜W-4の実装
- W-5の検証結果
- docs/reports/m6-2-completion.md 提出
- _STATUS.md・CLAUDE.md更新
- 「確認をお願いします」で完了報告
