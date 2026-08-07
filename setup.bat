@echo off
cd /d %~dp0
echo === jusetu-kogyo setup ===
if not exist .venv (
    echo Creating venv...
    python -m venv .venv
)
call .venv\Scripts\activate.bat
echo Installing dependencies...
pip install -r requirements.txt
echo.
echo === Setup complete ===
echo Next: copy .env.example to .env and fill in your API key, then run start.bat
pause
