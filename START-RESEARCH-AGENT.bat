@echo off
setlocal
cd /d "%~dp0"
title JARVIS Local Research Agent
where py >nul 2>nul
if %errorlevel%==0 (set "PY=py") else (set "PY=python")
if not exist ".research-venv\Scripts\python.exe" (
  echo [JARVIS] Menyiapkan environment Python...
  %PY% -m venv .research-venv
  if errorlevel 1 goto failed
)
call ".research-venv\Scripts\activate.bat"
echo [JARVIS] Memasang dependensi...
python -m pip install --upgrade pip
python -m pip install -r requirements-research.txt
if errorlevel 1 goto failed
echo [JARVIS] Memastikan Chromium tersedia...
python -m playwright install chromium
if errorlevel 1 goto failed
echo.
echo [JARVIS] Research Agent berjalan di http://127.0.0.1:8765
echo Jangan tutup jendela ini selama riset berlangsung.
python research_agent.py
goto end
:failed
echo.
echo GAGAL. Pastikan Python 3.10+ sudah terpasang dan masuk PATH.
pause
:end
endlocal
