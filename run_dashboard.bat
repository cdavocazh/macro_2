@echo off
REM Quick start script for the Macro Indicators Dashboard (Windows)

echo ======================================
echo Macro Indicators Dashboard
echo ======================================
echo.

REM Check if virtual environment exists
if exist "venv\Scripts\activate.bat" (
    echo Activating virtual environment...
    call venv\Scripts\activate.bat
)

REM Check if requirements are installed
echo Checking dependencies...
python -c "import streamlit" 2>nul
if errorlevel 1 (
    echo Installing required packages...
    pip install -r requirements.txt
)

REM Run the dashboard
echo.
echo Starting Streamlit dashboard...
echo The dashboard will open in your browser at http://localhost:8501
echo.
echo Press Ctrl+C to stop the dashboard
echo.

streamlit run app.py
