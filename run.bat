@echo off
if "%DEEPSEEK_API_KEY%"=="" (
    echo [ERROR] Please set DEEPSEEK_API_KEY first.
    pause
    exit /b 1
)
python app.py
pause
