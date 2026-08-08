# Claude Desktop への rag-system MCP サーバー登録手順

## 前提

- Claude Desktop がインストール済みであること
- rag-system のセットアップ（`setup.bat` 実行済み、`.env` に APIキー設定済み）が完了していること

## 設定ファイルの場所

Claude Desktop の MCP 設定ファイルは以下に置かれています（Windows）:

```
%APPDATA%\Claude\claude_desktop_config.json
```

エクスプローラーのアドレスバーに貼り付けてアクセスできます。

## 追加する JSON

`claude_desktop_config.json` を開き、`mcpServers` オブジェクトに以下を追加します。

```json
{
  "mcpServers": {
    "rag-system": {
      "command": "D:\\AI\\github\\rag-system\\.venv\\Scripts\\python.exe",
      "args": ["-m", "src.mcp_server"],
      "cwd": "D:\\AI\\github\\rag-system"
    }
  }
}
```

既に他のサーバーが登録されている場合は、`mcpServers` オブジェクト内に追記してください。

## 確認

Claude Desktop を再起動し、新しい会話を開いてハンマーアイコン（ツール）を確認します。
`rag-system` サーバーのツール（`list_documents` など）が表示されれば登録成功です。

## コスト上限の変更

環境変数でコスト上限を変更できます。`claude_desktop_config.json` の設定に `env` フィールドを追加します:

```json
{
  "mcpServers": {
    "rag-system": {
      "command": "D:\\AI\\github\\rag-system\\.venv\\Scripts\\python.exe",
      "args": ["-m", "src.mcp_server"],
      "cwd": "D:\\AI\\github\\rag-system",
      "env": {
        "MCP_JOB_COST_CAP": "0.20",
        "MCP_DAILY_COST_CAP": "2.00"
      }
    }
  }
}
```

| 変数 | 既定値 | 説明 |
|---|---|---|
| `MCP_JOB_COST_CAP` | `0.10` | 1ジョブあたりのコスト上限（USD） |
| `MCP_DAILY_COST_CAP` | `1.00` | 1日あたりのコスト上限（USD） |
