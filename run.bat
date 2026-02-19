@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo 노동법 RAG 챗봇
echo.
echo Streamlit 실행 중... (데이터 갱신이 필요하면 먼저 python scripts/sync_all.py 실행)
echo.
streamlit run app.py

pause
