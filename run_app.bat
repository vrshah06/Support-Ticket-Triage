@echo off
set PYTHON_EXE=C:\Users\shahb\AppData\Local\Programs\Python\Python312\python.exe
if exist "%PYTHON_EXE%" (
    echo Launching Streamlit with Python 3.12...
    "%PYTHON_EXE%" -m streamlit run app.py
) else (
    echo Launching Streamlit with default python...
    streamlit run app.py
)
pause
