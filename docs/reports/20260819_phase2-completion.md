# Phase 2 完了報告 — Funnel配置変更（MCPサーバー→443）

文書種別: PG完了報告 ／ 作成日: 2026-08-19 ／ 作成者: PG（Claude Sonnet 4.6）
指示書: docs/instructions/20260819_phase2-instructions.md

---

## 完了条件の充足状況

| 条件 | 状態 |
|---|---|
| tailscale serve status が期待通り（W-1 Step 3） | ✅ 完了 |
| .env 反映済み（W-2） | ✅ 完了 |
| .env.example commit済み（W-3） | ✅ 完了 (commit: 99ede95) |
| 手順書のURL全更新 commit済み（W-4） | ✅ 完了 (commit: 99ede95) |
| ローカル疎通確認OK（W-5） | ✅ 完了 |
| 外部疎通確認OK（W-5） | ⏳ 発注者実機確認待ち |
| docs/reports/20260819_phase2-completion.md 提出 | ✅ 本文書 |
| _STATUS.md 更新 | ✅ 完了 |
| 5W1Hコミット | ✅ 完了 |

---

## W-1: Tailscale Funnel配置変更

**変更前:**
```
https://fraine.tail204746.ts.net:10000 (Funnel on) → 127.0.0.1:8501
https://fraine.tail204746.ts.net:8443  (Funnel on) → 127.0.0.1:8766
```

**変更後:**
```
https://fraine.tail204746.ts.net       (Funnel on) → 127.0.0.1:8766  # MCP
https://fraine.tail204746.ts.net:8443  (Funnel on) → 127.0.0.1:8501  # Streamlit
https://fraine.tail204746.ts.net:10000 (Funnel on) → 127.0.0.1:10000 # 予備healthz
```

8444〜8453（tailnet only）は全て残存確認済み。

---

## W-2: .env変更

```
変更前: MCP_PUBLIC_URL=https://fraine.tail204746.ts.net:8443
変更後: MCP_PUBLIC_URL=https://fraine.tail204746.ts.net
```

.env はgitignore対象のため変更のみ（コミット対象外）。

---

## W-3: .env.example更新

```
変更前: MCP_PUBLIC_URL=https://fraine.tail204746.ts.net:8443  # OAuth issuer URL
変更後: MCP_PUBLIC_URL=https://fraine.tail204746.ts.net  # OAuth issuer URL (port 443 implicit)
```

commit 99ede95 でpush済み。

---

## W-4: mcp-remote-setup.md更新

変更箇所（全てcommit 99ede95に含む）:

| 場所 | 変更内容 |
|---|---|
| §1 テーブル | MCPポート 8443→443、ゲストUIポート 10000→8443 |
| §3 Funnel設定コマンド | Phase 2構成に更新 |
| §5 claude.aiコネクタURL | `:8443/mcp` → `/mcp` |
| §6 ChatGPTコネクタURL | `:8443/mcp` → `/mcp` |
| §7 curl例 | `:8443/mcp` → `/mcp` |
| §8 ゲストUI URL | `:10000` → `:8443` |
| §9 ゲスト招待URL | `:10000` → `:8443` |
| §11 トラブルシューティング | Funnel 10000番→8443番 |

---

## W-5: MCPサーバー再起動と疎通確認

**再起動:** start-mcp-remote.bat を実行。ポート8766 LISTENING確認済み。

**ローカル疎通確認（http://localhost:8766/.well-known/oauth-protected-resource）:**

```json
{
  "resource": "https://fraine.tail204746.ts.net",
  "authorization_servers": ["https://fraine.tail204746.ts.net"],
  "bearer_methods_supported": ["header"]
}
```

`resource` と `authorization_servers` が `https://fraine.tail204746.ts.net`（ポートなし）であることを確認。

**外部疎通確認:** 発注者に依頼。

URL: `https://fraine.tail204746.ts.net/.well-known/oauth-protected-resource`
条件: Pixel 10 モバイル回線・Tailscale OFF・Wi-Fi オフ

---

## 台帳照合

指示書記載のurl_dependents:

| 依存先 | 変更 | 状態 |
|---|---|---|
| claude.aiコネクタ | `:8443/mcp` → `/mcp` | 発注者が再登録 |
| ゲストUI | `:10000` → `:8443` | 手順書更新済み（W-4） |
| chat-pwa | 変更なし | Phase 1移動済み |

台帳Funnel行のstatus/planned更新はPM側で実施。
