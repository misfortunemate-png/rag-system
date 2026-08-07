@echo off
cd /d %~dp0
call .venv\Scripts\activate.bat
for /f "usebackq tokens=1,* delims==" %%a in (".env") do set "%%a=%%b"
echo === Running eval ===
python eval/run_eval.py
echo.
echo === Done. See eval/results.jsonl ===
pause
