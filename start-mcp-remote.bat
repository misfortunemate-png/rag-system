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

REM Show active token IDs
echo [rag-system MCP] Registered token IDs:
.\.venv\Scripts\python.exe scripts\show_token_ids.py

echo.
echo [rag-system MCP] Starting SSE server...

.\.venv\Scripts\python.exe src\mcp_server.py --transport sse
