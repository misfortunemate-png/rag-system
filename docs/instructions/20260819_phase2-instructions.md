# Phase 2 指示書 — Funnel配置変更（MCPサーバー→443）

文書種別: PG指示書 ／ 作成日: 2026-08-19 ／ 作成者: クリーデ（PM）
前提: Phase 1完了（chat-pwaが8446に移動、443が空いている）
計画書: ai-family-ops docs/20260818_port-migration-plan.md
台帳: ai-family-memory ops/state/network.yaml v2.1

## 背景

claude.aiカスタムコネクタはポート443でしか外部通信しない（C-CLAUDE-443）。
Phase 1で443を空けた。rag-system MCPサーバーを443に移動する。

## 作業内容

### W-1: Tailscale Funnel配置変更

配線指針§4に従い、三手順（状態記録→スクリプト実行→差分確認）で行う。

**Step 1: 状態記録**
```powershell
tailscale serve status > D:\AI\funnel-before-phase2.txt
```

**Step 2: 設定変更**
以下を順に実行する。

```powershell
# 旧設定を解除
tailscale funnel --https=8443 off
tailscale funnel --https=10000 off

# 新設定を投入
tailscale funnel --bg --https=443 http://127.0.0.1:8766
tailscale funnel --bg --https=8443 http://127.0.0.1:8501
tailscale funnel --bg --https=10000 http://127.0.0.1:10000
```

10000は予備としてFunnel ONを維持する。port-healthz.pyの10000ポートが応答する。

**Step 3: 差分確認**
```powershell
tailscale serve status
```

期待する出力:
```
https://fraine.tail204746.ts.net (Funnel on)
|-- / proxy http://127.0.0.1:8766
https://fraine.tail204746.ts.net:8443 (Funnel on)
|-- / proxy http://127.0.0.1:8501
https://fraine.tail204746.ts.net:10000 (Funnel on)
|-- / proxy http://127.0.0.1:10000
```

+ 既存のserveポート（8444〜8453）が全て残っていること。

### W-2: .env変更

`D:\AI\github\rag-system\.env` の以下の行を変更する:

```
変更前: MCP_PUBLIC_URL=https://fraine.tail204746.ts.net:8443
変更後: MCP_PUBLIC_URL=https://fraine.tail204746.ts.net
```

ポート443は暗黙なのでURLに含めない。

### W-3: .env.example更新

リポジトリの `.env.example` の同じ行を変更してcommit・push。

```
変更前: MCP_PUBLIC_URL=https://fraine.tail204746.ts.net:8443  # OAuth issuer URL
変更後: MCP_PUBLIC_URL=https://fraine.tail204746.ts.net  # OAuth issuer URL (port 443 implicit)
```

### W-4: 手順書URL変更

`docs/mcp-remote-setup.md` 内の全URLを変更する。

検索対象: `fraine.tail204746.ts.net:8443`
置換先: `fraine.tail204746.ts.net`（ポートなし）

ただし以下は除外:
- ゲストUI（§7等）のURL → `:8443` のまま（ゲストUIが8443に移動するため）
- 変更履歴セクション内の過去の記述

具体的な変更箇所:
- §5 claude.aiコネクタURL: `https://fraine.tail204746.ts.net/mcp`
- §6 ChatGPTコネクタURL: `https://fraine.tail204746.ts.net/mcp`
- §7 curl例: `https://fraine.tail204746.ts.net/mcp`
- ゲストUI URL: `https://fraine.tail204746.ts.net:10000/` → `https://fraine.tail204746.ts.net:8443/`

### W-5: MCPサーバー再起動と疎通確認

1. MCPサーバーを停止→再起動（start-mcp-remote.bat）
2. 起動ログで `OAuth endpoints enabled (issuer: https://fraine.tail204746.ts.net)` を確認
3. ローカル疎通確認:

```powershell
Invoke-WebRequest -Uri "http://localhost:8766/.well-known/oauth-protected-resource" -UseBasicParsing
```

JSONの`resource`と`authorization_servers`が `https://fraine.tail204746.ts.net` であること。

4. 外部疎通確認（Pixel 10モバイル回線・Tailscale OFF・Wi-Fiオフ）:

```
https://fraine.tail204746.ts.net/.well-known/oauth-protected-resource
```

## 台帳との照合

NW台帳v2.1のurl_dependents:
- claude.aiコネクタ: `:8443/mcp` → `/mcp` — Phase 2完了後に発注者が再登録
- ゲストUI: `:10000` → `:8443` — 手順書更新で対応（W-4）
- chat-pwa: 変更なし（Phase 1で移動済み）

台帳のFunnel行のstatus/planned更新はPM側で行う。

## 完了条件

- tailscale serve statusが期待通り（W-1 Step 3）
- .env反映済み（W-2）
- .env.example commit済み（W-3）
- 手順書のURL全更新 commit済み（W-4）
- ローカル＋外部疎通確認OK（W-5）
- docs/reports/20260819_phase2-completion.md 提出
- _STATUS.md更新
- 5W1Hコミット
