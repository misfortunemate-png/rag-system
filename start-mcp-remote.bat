@echo off
cd /d D:\AI\github\rag-system
echo [rag-system MCP] SSE HTTP mode startup check...
echo.

REM .env check
if not exist ".env" (
    echo [ERROR] .env not found. See .env.example
    pause
    exit /b 1
)

REM auth_tokens.yaml check
if not exist "data\auth_tokens.yaml" (
    echo [ERROR] data\auth_tokens.yaml not found.
    echo.
    echo  Setup:
    echo   1. copy data\auth_tokens.yaml.example data\auth_tokens.yaml
    echo   2. Generate tokens:
    echo      .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
    echo.
    pause
    exit /b 1
)

REM Show active token IDs (not tokens)
echo [rag-system MCP] Registered token IDs:
.\.venv\Scripts\python.exe -c "import yaml,sys;from pathlib import Path;from datetime import date;data=yaml.safe_load(Path('data/auth_tokens.yaml').read_text(encoding='utf-8')) or {};today=date.today();[print(f'  [{(chr(88) if (e.get(chr(101)+chr(120)+chr(112)+chr(105)+chr(114)+chr(101)+chr(115)) and date.fromisoformat(str(e.get(chr(101)+chr(120)+chr(112)+chr(105)+chr(114)+chr(101)+chr(115)))) < today else chr(79)+chr(75))}] {e.get(chr(105)+chr(100),chr(63))}') for e in data.get('tokens',[])]"

echo.
echo [rag-system MCP] Starting SSE server...

.\.venv\Scripts\python.exe src\mcp_server.py --transport sse
