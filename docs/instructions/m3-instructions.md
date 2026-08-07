# 規程エージェント M3 作業指示書 — 設定・デバッグ・三役モデル構成

作成日: 2026-08-07 ／ PM: クリーデ（Opus席）
対応仕様: docs/spec-v0.3.md（本指示書が§8として追補される内容を先行定義）
前提: M2完了（Streamlit UI稼働）

## 背景と目的

M1 evalの失敗2問（Q4金属管曲げ半径・Q8 SPD電圧防護レベル）は多ホップ条件比較での
非収束が原因。モデル・ループ数・推論構成の調整を予測し、設定・デバッグ機能を
最優先プロセスとして実装する（devスキル共通機能ガイド準拠）。
外部RAG理論との突合済み（末尾の出典参照）。

## スコープ概要

1. 三役モデル構成（プランナー／実行ループ／コンポーザー）
2. 設定画面（サイドバー常設・settings.json永続化）
3. 引用宣言方式＋決定的引用検証
4. 回答スタイル三段階
5. デバッグパネル

M2で「原則触らない」としたsrc/配下の改修を本指示書で解禁する。

## 1. 三役モデル構成

エージェントを三役に分離する（decomposer-retriever-decider型の中央集権構成。出典[1][2]）。

| 役 | 職務 | 呼び出し回数 | コスト方針 |
|---|---|---|---|
| プランナー | 質問を分解し検索計画を立てる | 1回 | 高級モデル可 |
| 実行ループ | search_chunks / read_section を回して素材収集 | 複数回 | 安いモデルに寄せる |
| コンポーザー | 素材を突き合わせて最終回答＋引用宣言 | 1回 | 高級モデル可 |

- 各役に独立したprovider/model設定を持たせる（三スロット）
- **既定値は三役とも現行モデル（deepseek/deepseek-v4-flash）**。既定のままなら
  現行の単一モデル動作と等価であること（後方互換・比較実験の基準）
- プランナー段はON/OFF可。OFF時は質問をそのまま実行ループに渡す（現行動作）
- インターフェース改訂: `run(question)` → `run(question, config)`。
  configはUIの設定値を保持するdataclassまたはdict

### プランナーのプロンプト方針

- 可否を問う質問（〜を使ってよいか等）では、個別の言及例の収集より
  **権威ソース（規定表・一覧表）の特定を優先**する検索計画を立てさせる

### コンポーザーのプロンプト方針（根拠不足の明言・出典[5][6]）

- 集めた素材で回答に足りない場合は「根拠不足」と明言させる。もっともらしい
  条番号で穴を埋めることを明示的に禁止する
- 可否の質問は、権威ソースを引用できた場合のみ断定する

## 2. 設定画面（st.sidebar常設）

| 項目 | UI | 既定値 |
|---|---|---|
| プランナー ON/OFF | トグル | OFF |
| プランナー model | プリセット選択＋自由入力 | deepseek/deepseek-v4-flash |
| 実行ループ model | 同上 | 同上 |
| コンポーザー model | 同上 | 同上 |
| MAX_LOOPS | スライダー 5〜30 | 15 |
| search_chunks top_k | スライダー 3〜15 | 現行値 |
| 回答スタイル | ラジオ（結論のみ／標準／詳細） | 標準 |

- プリセット: deepseek/deepseek-v4-flash, google/gemini-2.5-flash,
  anthropic/claude-haiku-4-5（provider=anthropicの場合はclaude-haiku-4-5-20251001）
- 設定は `settings.json` に保存し次回起動時に復元（.gitignore対象に追加）。
  **.envは秘密（APIキー）専用**とし、モデル選択等の非秘密は settings.json に分離
- 設定変更は再起動不要で次の質問から反映

## 3. 引用宣言方式＋決定的引用検証

- コンポーザーの出力を構造化: `{"answer": str, "cited_chunk_ids": [str]}`
  （JSON出力。パース失敗時は全文をanswerとして扱いcitedは空）
- **決定的検証（出典[3][4]）**: cited_chunk_ids の各IDが実行ループの検索結果
  集合に実在するかをPythonコードで照合。実在しないIDは黙って捨てず、
  デバッグログに `invalid_citation` として記録した上で表示から除外
- UI改修: 根拠パネルは**引用されたチャンクのみ**を既定表示。
  「検索した全チャンク」は折りたたみ（st.expander）に退避

## 4. 回答スタイル三段階

コンポーザーのプロンプトで制御する。

- **結論のみ**: 結論＋根拠条番号の一〜二文
- **標準**: 結論＋根拠条文の要点（既定）
- **詳細**: 引用付き解説・関連条文への言及を含む

## 5. デバッグパネル（設定画面と同居・st.expander区分）

| 機能 | 内容 |
|---|---|
| バージョン表示 | アプリ版・三役の使用モデル・設定値スナップショット |
| 生トレース表示 | 直近質問のLLM往復（リクエスト/レスポンス）をJSON展開 |
| トークン・コスト・時間表示 | 段ごと（プランナー／実行／コンポーザー）のトークン内訳＋概算コスト＋**所要時間（秒）**＋合計。速度改善の計測基盤を兼ねる |
| invalid_citation ログ | §3の検証で弾いた引用の一覧 |
| eval質問ワンクリック投入 | eval/questions.jsonl の10問をボタンで質問欄に投入 |
| 設定リセット | settings.json を既定値に戻す（confirm付き） |

## テスト

| テスト | 方法 | 合格条件 |
|---|---|---|
| 後方互換 | 既定設定（三役同一・プランナーOFF）でeval実行 | M1と同等の8/10以上 |
| 三役動作 | プランナーON＋コンポーザーを別モデルにして失敗2問（Q4・Q8）を実行 | トレースに三役の呼び分けが記録される（正答は合格条件にしない。改善実験はM3検収後） |
| 引用検証 | VVF可否質問を実行 | 根拠パネルに引用チャンクのみ表示・全チャンクは折りたたみ |
| スタイル切替 | 同一質問を三スタイルで実行 | 回答の長さ・詳細度が明確に変わる |
| 設定永続化 | 設定変更→アプリ再起動 | settings.jsonから復元される |

## 禁止事項

- ショウゴさんにPowerShellコマンドを叩かせること（R-015）
- 新規pip依存の追加（現行requirements.txtの範囲で実装可能なはず。
  必要と判断した場合は着工前にdocs/reports/で相談）
- eval/questions.jsonl の改変（PM支給物）

## 完了条件

- start.bat ダブルクリック起動で全機能動作
- テスト表の全項目合格
- settings.json.example（既定値見本）を同梱
- push済み・docs/reports/ に完了報告

## スコープ外（M4候補として記帳）

- ハイブリッド検索（BM25＋密埋め込みのRRF融合）: VVF等の固有語・条番号の
  完全一致に有効（出典[7]）。ingest改修を伴うためM3に含めない
- クエリ複雑度による従来型／エージェント型の振り分けルーター（出典[2]）
- groundedness判定による回答ゲート＋再検索ループ（出典[8]）
- 速度改善: コンポーザー出力のストリーミング表示（体感速度・M4筆頭候補）
- 速度改善: 1ターン内の複数search_chunks並列発行（逐次往復の圧縮・実装軽量）
- 速度改善: ファンアウト構成——プランナーが分解可能と判定した質問をサブタスク別の
  並列実行ループで処理しコンポーザーが統合（出典[1]の分散型。並列度上限と
  合計予算ガード必須=P-9。分解可能性判定が前提。M5候補）

## 出典（外部RAG理論との突合・2026-08-07実施）

[1] Towards Agentic RAG with Deep Reasoning: A Survey of RAG-Reasoning Systems in LLMs
    (arXiv:2507.09477) — decomposer-retriever-decider型の中央集権マルチエージェント構成、
    異なるモデル能力の役割別割り当て
[2] Agentic RAG Patterns 2026: Multi-Step Reasoning Guide (digitalapplied.com) —
    エージェント型は従来型の3〜10倍のトークン消費、反復予算の有界化、
    複雑度ルーティング
[3] CiteFix: Enhancing RAG Accuracy Through Post-Processing Citation Correction
    (arXiv:2504.15629) — 生成検索エンジンの引用精度は74%程度、後処理訂正の有効性
[4] AI Document Retrieval RAG: Citations & Confidence (buzzi.ai) — パッセージIDに
    限定した引用強制、ドラフト→検証→引用付き最終回答の二段生成
[5] Retrieval Improvements Do Not Guarantee Better Answers: A Study of RAG for
    AI Policy QA (arXiv:2603.24580) — 検索強化が確信的幻覚を増やしうる
[6] Why RAG over a document dump fails regulated work (ansvar.eu) — 規制文書では
    根拠不能の明示（unresolved）を幻覚より優先する設計
[7] RAG Architecture 2026: Patterns, Code, and Eval (futureagi.com) — BM25＋密埋め込み
    RRF融合が単独方式を上回る（BEIR/MTEB等）
[8] Agentic RAG in 2026: Patterns, Code, Observability (futureagi.com) —
    faithfulness判定による回答ゲート、失敗時再検索
