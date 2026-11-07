@echo off
cd /d "%~dp0"
if not exist .venv py -3 -m venv .venv
call .venv\Scripts\activate
python -c "import dash, plotly, pandas, numpy, duckdb" >nul 2>&1
if errorlevel 1 (
  python -m pip install --upgrade pip
  pip install -r requirements.txt
)
python app.py
pause
