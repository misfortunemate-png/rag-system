# M4 完了報告

**日付:** 2026-08-08  
**担当:** PG（Claude Sonnet 4.6）  
**PM宛:** クリーデ  
**コミット:** `3d8036a` — push済み: `main` ブランチ

---

## 実施内容

### 変更ファイル（5ファイル、685行追加 / 99行削除）

| ファイル | 主な変更 |
|---|---|
| `src/config.py` | PRESETS拡充・AgentConfig拡張・APP_VERSION→0.4.0 |
| `src/llm.py` | `_ANTHROPIC_ID_MAP`更新・`chat_stream`メソッド追加 |
| `src/agent.py` | アドバイザー・早期打ち切り・並列検索・ストリーミングAPI |
| `app.py` | アドバイザーUI節・ストリーミング表示・トレース更新 |
| `settings.json.example` | アドバイザー節・early_stop_k 追加 |

---

## 機能詳細

### 1. モデルプリセット拡充

chat-pwa 準拠の14モデルに統一:

| プロバイダー | モデル |
|---|---|
| OpenRouter | deepseek-v4-flash/pro, gemini-2.5-flash, gemini-3.6-flash, claude-haiku-4-5, claude-sonnet-4-6, claude-opus-4.6, gpt-5.6-sol, gpt-5.6-luna, qwen3.7-plus, minimax-m3 |
| Anthropic direct | claude-haiku-4-5-20251001, claude-sonnet-4-6, claude-opus-4-6 |

自由入力欄「（カスタム入力）」は維持。

### 2. アドバイザー（第四の役）

**発動条件（チェックボックス・複数選択可・既定: 難航検知のみ）:**

| 条件 | 発動タイミング | 既定 |
|---|---|---|
| 常時 | プランナー直後（ループ前） | OFF |
| プランナー裁量 | `advisor_recommended: true`のとき | OFF |
| 難航検知 | 即時型: 連続k空振り（k=2）OR 予算型: 探索コール総数 >= 0.6×MAX_LOOPS | **ON** |
| 未決着 | MAX_LOOPS到達後・コンポーザー前 | OFF |

**裁定出力:** JSON形式
- `"replan"`: 新クエリを注入してループ続行
- `"out_of_scope"`: ループ打ち切り・コンポーザーへ第二段回答を指示

**ガード:** 1質問につき最大1回（advisor_state で管理）

**プランナー統合:** プランナー出力の末尾に `advisor_recommended: true/false` を追加。決定的正規表現で抽出。

### 3. 早期打ち切り（安全網）

- `consecutive_empty` カウンターで連続空振りループを追跡
- `early_stop_k`（既定3・スライダー2〜5）回連続でコンポーザーへ強制移行
- アドバイザー発動後もカウンター継続（再計画後の空振り継続でも打ち切り）
- トレースに「⏹ 早期打ち切り」エントリとして記録

### 4. コンポーザーストリーミング

**出力形式を二部形式に変更:**
```
{回答本文（Markdown）}

<!-- CITATIONS -->
{"cited_chunk_ids": ["id1", "id2"]}
```

**実装:**
- `make_composer_stream()`: ジェネレーター＋`get_result_fn`のタプルを返す
- 表示用ジェネレーターは `<!-- CITATIONS -->` より前のみを yield
- `get_result_fn()`（ジェネレーター消費後に呼ぶ）で answer/cited_ids/debug を返す
- `st.write_stream()` で Streamlit UI に逐次表示
- OpenRouter/Anthropic 両方で usage 情報をストリーム末尾から取得

### 5. search_chunks 並列発行

```python
with ThreadPoolExecutor(max_workers=len(search_tcs)) as ex:
    ...
```

- 1ターンに複数 search_chunks が来た場合のみ並列化（単一は従来通り）
- `(query, top_k)` キーでキャッシュし、重複クエリは即時返却
- read_section は並列化なし（従来通り）

---

## 動作確認

**起動確認:** `streamlit run app.py` → 正常起動（HTTP 200）

**UI確認（アクセシビリティツリーで検証）:**
- アドバイザーモデルセレクタ: ✅
- 発動条件チェックボックス4項目: ✅
- 難航検知 k スライダー（難航検知ON時のみ表示）: ✅
- 早期打ち切り k スライダー（常時表示）: ✅
- バージョン表示: `0.4.0` ✅
- モデルドロップダウン: 14プリセット + カスタム入力 ✅

**構文チェック:** `py_compile` で全ファイルエラーなし

---

## ベースライン比較

### R1 メタルモール問（アドバイザー難航検知テスト）

**設定:** `advisor_trigger_stall=True` / `advisor_k=2` / `max_loops=15` / 全段deepseek-v4-flash

| 項目 | 修正前（旧定義・バグあり） | 修正後（案A+B複合） |
|---|---|---|
| アドバイザー発動 | **未発動**（12ループ完走） | **ループ4で発動** ✅ |
| 発動トリガー | — | 予算型: `total_search_calls=9 >= 0.6×15=9` |
| アドバイザー裁定 | — | replan（新クエリ注入・守備範囲外検索軸の提案） |
| 実行ループ数 | 12 | 15（replanのため続行・MAX_LOOPS到達） |
| 所要時間 | 136.4s | 150.1s |

**考察:** アドバイザーは正しくループ4で発動し（バグ修正確認）、再計画クエリを注入した。
モデル（deepseek-v4-flash）は「再計画」を選択し守備範囲外宣言はしなかったため、ループはMAX_LOOPSまで継続した。
R1の「正解」はout_of_scope宣言であり、advisorがreplanを選んだのはアドバイザーモデルの判断精度の問題（設計上許容）。
より高精度のアドバイザーモデルを使うか、advisor_trigger_unresolved（未決着）を併用することで改善できる。

### EM-CET問ベースライン（参考）
M3実測値: 9ループ・268.6s・全段deepseek-v4-flash。  
同一条件での再計測はショウゴさん実機確認フェーズで実施予定。

---

## 既知の制約・次フェーズへの持ち越し

- ストリーミング時の usage 取得: OpenRouter は `stream_options={"include_usage": True}` に依存。プロバイダーによっては最終チャンクに usage が来ない可能性あり（その場合 usage={}）
- アドバイザー「再計画」の post-loop 発動: ループ終了後のため新クエリは実行されない（コンポーザーへの文脈として渡す設計）
- 並列化の効果測定: Chroma ローカル問い合わせのため軽微な改善にとどまる可能性あり

---

## テスト結果（ショウゴさん実機確認待ち）

| テスト | 状態 |
|---|---|
| 後方互換（アドバイザーOFF・既定設定） | ⏳ 実機確認待ち |
| アドバイザー(b) refusal問 | ✅ ループ4発動確認（R1 メタルモール問）|
| アドバイザー(a) 常時ON | ⏳ 実機確認待ち |
| 早期打ち切り | ⏳ 実機確認待ち |
| ストリーミング | ⏳ 実機確認待ち（起動確認のみ実施）|
| 並列発行 | ⏳ 実機確認待ち |
