# 規程エージェント hotfix-3 作業指示書（srcインポート障害修正）
文書種別: 権威文書

作成日: 2026-08-19 ／ PM: クリーデ ／ 対応仕様: docs/m7c-requirements.md v1.0 §2 ／ 本書一枚で完結（追補なし）

## 添付マニフェスト（着工前照合・必須）

以下がすべて交換所（リポジトリ）に存在すること。**1つでも欠けたら着工せず docs/reports/ に報告。**

| # | パス | 種別 | SHA-256（支給物のみ） |
|---|---|---|---|
| 1 | docs/m7c-requirements.md | 要件定義 | — |

## PG運用規律（定型・全フェーズ共通）

1. **停止条件**: 仕様にない判断が必要／仕様どおりだと問題が生じる／技術的に実現困難または難航／セッション外プロセスの停止等の副作用がある操作。原因判明時は「原因X・対策Y・実行可否」で報告し指示を待つ
2. **支給物改変禁止**: PM支給物はdiffゼロで検収される。技術的整合の調整もPMへ差し戻す
3. **発注者指示による仕様外修正**: 発注者から直接指示を受けた修正は実施・効果確認してよい。報告時に「発注者の指示により実装/修正」と明記する。権威文書は書き換えない
4. **着工前**: `git pull` → inspect実行（マニフェスト照合・版確認）。緑でなければ着工しない

## 作業範囲

- 何を: MCPサーバーのsrcインポート障害の修正（2箇所・計4行の変更）
- なぜ: start-mcp-remote.batのスクリプト直接実行により`sys.path`にプロジェクトルートが乗らず、src.*を遅延インポートする全経路が`No module named 'src'`で失敗する（m7c-requirements.md §0背景1、§2）
- どこで: misfortunemate-png/rag-system（D:\AI\github\rag-system）

## 作業手順

### H-A: sys.pathブートストラップ（src/mcp_server.py）

32行目 `os.chdir(_PROJECT_ROOT)` の直後（33行目の空行の位置）に以下3行を挿入する:

```python
import sys
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
```

挿入後の30〜37行目が以下になること:

```python
# ── CWD = project root (parent of this file's src/ directory) ────────────────
_PROJECT_ROOT = Path(__file__).parent.parent
os.chdir(_PROJECT_ROOT)
import sys
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ── .env ──────────────────────────────────────────────────────────────────────
```

### H-B: 起動スクリプトのモジュール実行化（start-mcp-remote.bat）

最終行を変更する:

変更前:
```
.\.venv\Scripts\python.exe src\mcp_server.py --transport http
```

変更後:
```
.\.venv\Scripts\python.exe -m src.mcp_server --transport http
```

ファイル全体がASCII・CRLFであることを確認する。

## 禁止事項

- 上記2箇所以外のファイルを変更しない（M7c本体はhotfix-3検収後に別途発令する）

## テスト

- PG自己完結分:
  - mcp-server.bat（stdioモード）で `list_documents` が応答すること（回帰なし）
  - start-mcp-remote.bat（httpモード）でサーバーが起動し、ログにインポートエラーが出ないこと
- **実機系（発注者に依頼）**:
  - T-0a: 再起動後、claude.aiから submit_question → get_answer 完走（status: done、answer取得）
  - T-0b: claude.aiから search_chunks / list_documents がエラーなく応答（M7cツール削減前の最後の全数確認）

## 完了条件

- H-A/H-Bの2箇所が正確に変更されていること
- PG自己テスト（stdio / http両モード）が合格していること
- サーバー再起動・コミット・プッシュ実施済み
- _STATUS.md更新

## 報告基準

報告は docs/reports/ に置く。コンテキスト圧縮後もこのセクションを読み返してから報告すること。

1. 実装内容の要約
2. 完了条件の各項に対する充足状況
3. PG自己テストの結果（stdioモード・httpモード各1回の出力抜粋）
4. 未完了・未検証の項目があれば列挙
5. サーバー再起動・コミット・プッシュの実施状況
