@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo 노동법 RAG 챗봇 - 동기화 후 실행
echo.

echo [1/3] api_data 동기화 중...
python scripts/sync_all.py
echo.

echo [2/3] 벡터 스토어 재구축 중... (1~2분 소요)
python scripts/rebuild_vector_store.py
echo.

echo [3/3] Streamlit 실행 중...
streamlit run app.py

pause
