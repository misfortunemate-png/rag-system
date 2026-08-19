---
version: "hotfix-3-done"
badge: "hotfix-3完了（H-Aのみ）"
next: "次マイルストーン指示書待ち"
waiting_on: "指示書"
---

# rag-system 現在地

更新: 2026-08-19 ／ 更新者: PG

## 状態

- M1〜M7b-2 全フェーズ完了・検収済み
- Phase 2（Funnel配置変更）: 実施済み
- **hotfix-3: H-Aのみ適用で完了（H-Bは`-m`実行がOAuth認可を破壊するため除外）**

## Phase 2 実施結果

| W | 内容 | 結果 |
|---|---|---|
| W-1 | Tailscale Funnel配置変更（443→8766/MCP、8443→8501/Streamlit、10000→10000/healthz） | 完了 ✅ |
| W-2 | .env MCP_PUBLIC_URL更新（:8443削除） | 完了 ✅ |
| W-3 | .env.example更新・commit・push | 完了 ✅ |
| W-4 | mcp-remote-setup.md URL更新・commit・push | 完了 ✅ |
| W-5 | MCPサーバー再起動 → ローカル疎通確認 | 完了 ✅ |
| W-5 | 外部疎通確認（Pixel10モバイル回線） | **発注者依頼** |

## W-5 ローカル疎通確認結果

```json
{
  "resource": "https://fraine.tail204746.ts.net",
  "authorization_servers": ["https://fraine.tail204746.ts.net"],
  "bearer_methods_supported": ["header"]
}
```

## Phase 2 Funnel構成（変更後）

| 外部ポート | 転送先 | 用途 |
|---|---|---|
| 443（Funnel） | 8766 | MCPサーバー（claude.ai・ChatGPT） |
| 8443（Funnel） | 8501 | ブラウザUI（Streamlit・ゲスト） |
| 10000（Funnel） | 10000 | 予備healthz |

## 技術スタック（Phase 2完了時点）

- 検索: ruri-v3-310m(dense) + fugashi+BM25 → RRF → ruri-v3-reranker-310m
- エージェント: Planner → Loop → Advisor → Web照合（法令API含む） → Composer
- **公開: SSE `/sse` + Streamable HTTP `/mcp`（0.0.0.0:8766）→ Tailscale Funnel HTTPS 443**
- **認証: OAuth 2.1承認画面方式（auth_tokens.yaml統合）+ Bearer直経路（既存互換）**
- **ブラウザUI: Streamlit（0.0.0.0:8501）→ Tailscale Funnel HTTPS 8443・トークンゲート実装**
- stdio: Claude Codeローカル利用として引き続き動作
