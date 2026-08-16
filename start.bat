@echo off
cd /d %~dp0
call .venv\Scripts\activate.bat
for /f "usebackq tokens=1,* delims==" %%a in (".env") do set "%%a=%%b"
streamlit run app.py --server.port 8501
