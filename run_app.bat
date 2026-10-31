@echo off
REM Windows: double-click or run from a terminal in this folder. Creates a venv on first run.
if not exist .venv (
  py -3.11 -m venv .venv
  .venv\Scripts\pip install -r requirements.txt
)
.venv\Scripts\python -m streamlit run app.py
