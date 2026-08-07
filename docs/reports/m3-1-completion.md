# M3.1 完了報告 — 回答メタデータの常時表示

**日付:** 2026-08-08  
**担当:** PG（Claude Sonnet 4.6）  
**PM宛:** クリーデ

---

## 実施内容

### 変更ファイル

- `app.py` のみ（1ファイル、70行追加 / 38行削除）

### 実装詳細

1. **`_build_meta(debug, t_total) → dict`**  
   `result["debug"]` と計測済み `t_total` からフッター用データを抽出して辞書に格納。

2. **`_render_meta_footer(meta) → None`**  
   2行の `st.caption` でフッターを描画:
   - 行1: `合計 Xs　🗺 Xs (in/outtok)　🔄×N Xs (in/outtok)　✍ Xs (in/outtok)`  
   - 行2: `≈$X.XXXX　planner=... / loop=... / composer=...`
   - プランナーOFF時は🗺行を省略。コスト推計できないモデルは「―」表示。

3. **ライブ回答への適用**  
   `if result:` ブロック内で `_build_meta()` → `_render_meta_footer()` を呼び出し。

4. **履歴保持**  
   `session_state.history` の各アイテムに `"meta"` キーで保存。  
   履歴表示ループ内でも `_render_meta_footer(item.get("meta"))` を呼び出し。

5. **デバッグパネルの整理**  
   撤去: トークン・コスト・時間の集計表示（`_render_usage_row` 呼び出し群）  
   残存: MAX_LOOPS警告 / プランナー生出力 expander / コンポーザー生出力 expander /  
   invalid_citation ログ / eval投入ボタン / 設定リセット

---

## 動作確認

- テスト質問: 「公共工事でVVFを使ってよいか」（プランナーON）
- 表示結果:
  ```
  合計 90.8s　🗺 7.8s (202/637tok)　🔄×3 69.3s (60,453/2,198tok)　✍ 13.7s (14,802/1,119tok)
  ≈$0.0064　planner=deepseek-v4-flash / loop=deepseek-v4-flash / composer=deepseek-v4-flash
  ```
- 回答本文の可読性に影響なし（`st.caption` で控えめ表示）

---

## コミット

`9a75425` — `feat(ui): M3.1 — 各回答末尾にメタデータフッターを常時表示`  
push済み: `main` ブランチ
