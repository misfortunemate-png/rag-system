@echo off
cd /d D:\AI\github\rag-system
chcp 65001 > nul
echo [rag-system MCP] SSE HTTP mode startup check...
echo.

REM .env check
if not exist ".env" (
    echo [ERROR] .env が見つかりません。.env.example を参考に作成してください。
    pause
    exit /b 1
)

REM auth_tokens.yaml check
if not exist "data\auth_tokens.yaml" (
    echo [ERROR] data\auth_tokens.yaml が見つかりません。
    echo.
    echo  作成手順:
    echo   1. data\auth_tokens.yaml.example をコピーして data\auth_tokens.yaml を作成
    echo   2. 各トークンを以下のコマンドで生成して置き換える:
    echo      .venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
    echo.
    pause
    exit /b 1
)

REM Show active token IDs (not tokens)
echo [rag-system MCP] 登録済みトークンID:
.venv\Scripts\python.exe -c "
import yaml, sys
from pathlib import Path
from datetime import date
data = yaml.safe_load(Path('data/auth_tokens.yaml').read_text(encoding='utf-8')) or {}
today = date.today()
for e in data.get('tokens', []):
    tid = e.get('id','')
    exp = e.get('expires')
    if exp and date.fromisoformat(str(exp)) < today:
        status = '[期限切れ]'
    else:
        status = '[有効]'
    print(f'  {status} {tid}')
"

echo.
echo [rag-system MCP] 起動中...

REM Start the server
.venv\Scripts\python.exe src\mcp_server.py --transport sse
