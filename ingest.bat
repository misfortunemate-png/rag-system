@echo off
cd /d %~dp0
call .venv\Scripts\activate.bat
echo === Running ingest ===
python -m src.ingest
echo.
echo === Done. See data/chunks.jsonl ===
pause
