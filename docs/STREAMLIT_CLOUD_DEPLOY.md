# Streamlit Community Cloud 배포 (프롬프트 실험 도구)

**환경변수·시크릿 설정 없음.** API 서버 주소는 코드(`DEFAULT_BASE_URL`)에만 있고, OpenAI API Key만 사이드바에서 입력하면 됩니다.

프롬프트 실험 도구(`app_playground.py`)만 Streamlit Community Cloud에 배포하는 방법입니다.  
백엔드 API(LawChat 서버)는 **별도로** 배포한 뒤, `app_playground.py`의 `DEFAULT_BASE_URL`을 그 주소로 넣어 두면 됩니다.

## 1. 사전 준비

- **백엔드 API**를 외부에서 접근 가능한 URL로 배포해 두세요.  
  예: Render, Fly.io, Railway, AWS 등에서 `main_api`(FastAPI) 배포 후  
  `https://your-lawchat-api.onrender.com` 같은 주소 확보.
- **GitHub**에 이 저장소를 푸시해 두세요.

## 2. Streamlit Community Cloud에서 앱 만들기

1. [share.streamlit.io](https://share.streamlit.io) 에서 **Sign in with GitHub** 후 로그인.
2. **New app** 선택.
3. 설정:
   - **Repository**: `your-username/LawChat` (본인 저장소)
   - **Branch**: `main` (또는 사용 중인 브랜치)
   - **Main file path**: `app_playground.py`
   - **Advanced settings** 열기:
     - **Python version**: 3.10 또는 3.11 권장.
     - **Requirements file**: `requirements-streamlit-cloud.txt`  
       (이 파일만 사용하면 chromadb·langgraph 등 없이 빌드되어 더 빠릅니다.)

4. **Deploy** 클릭.

## 3. 사용

- **API 서버 URL**: 코드의 `DEFAULT_BASE_URL` (환경변수·시크릿 없음)
- **OpenAI API Key**: 사이드바 입력창에 입력

**연결 확인 (Health)** 버튼으로 연결 여부 확인.

## 4. 동작 확인

- **API 서버 URL**이 코드의 `DEFAULT_BASE_URL` 과 일치하는지 확인.
- **연결 확인 (Health)** 버튼으로 백엔드 `/api/v1/health` 호출이 성공하는지 확인.
- 의도 분류, 이슈 분류, 체크리스트, 결론 등 원하는 탭에서 API 호출이 되는지 테스트.

## 5. 요약

| 항목 | 값 |
|------|-----|
| Main file | `app_playground.py` |
| Requirements (Cloud 전용) | `requirements-streamlit-cloud.txt` |
| API 서버 URL | 코드 `DEFAULT_BASE_URL` 만 사용 (환경변수·시크릿 없음) |
| OpenAI API Key | 사이드바 입력창에 입력 |
| 백엔드 | 별도 호스팅 필요 (같은 앱에 포함되지 않음) |

로컬에서는 `streamlit run app_playground.py` 로 실행하고,  
Cloud에서는 위 설정으로 배포하면 동일한 프롬프트 실험 도구를 웹에서 사용할 수 있습니다.
