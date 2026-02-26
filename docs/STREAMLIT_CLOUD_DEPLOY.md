# Streamlit Community Cloud 배포 (프롬프트 실험 도구)

프롬프트 실험 도구(`app_playground.py`)만 Streamlit Community Cloud에 배포하는 방법입니다.  
백엔드 API(LawChat 서버)는 **별도로** 배포한 뒤, Cloud 앱에서 그 URL로 연결합니다.

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

## 3. Secrets 설정 (API 주소·API 키)

배포된 앱의 **Settings → Secrets** 에서 아래처럼 넣습니다.

```toml
[api]
base_url = "https://your-lawchat-api.onrender.com"
openai_api_key = "sk-..."
```

- **base_url**: LawChat **API 서버 URL** (끝의 `/` 제거). 예: `https://your-lawchat-api.onrender.com`
- **openai_api_key**: (선택) 기본으로 넣어 둘 OpenAI API 키.  
  비워두면 앱 사이드바에서 매번 입력해야 합니다.

저장하면 앱이 재시작되며, 사이드바의 **API 서버 URL** / **OpenAI API Key** 기본값이 위 값으로 채워집니다. (사용자가 UI에서 덮어쓸 수 있습니다.)

## 4. 동작 확인

- 앱에서 **API 서버 URL**이 Secrets의 `base_url`로 설정돼 있는지 확인.
- **연결 확인 (Health)** 버튼으로 백엔드 `/api/v1/health` 호출이 성공하는지 확인.
- 의도 분류, 이슈 분류, 체크리스트, 결론 등 원하는 탭에서 API 호출이 되는지 테스트.

## 5. 요약

| 항목 | 값 |
|------|-----|
| Main file | `app_playground.py` |
| Requirements (Cloud 전용) | `requirements-streamlit-cloud.txt` |
| Secrets 예시 | `[api]` 아래 `base_url`, `openai_api_key` |
| 백엔드 | 별도 호스팅 필요 (같은 앱에 포함되지 않음) |

로컬에서는 `streamlit run app_playground.py` 로 실행하고,  
Cloud에서는 위 설정으로 배포하면 동일한 프롬프트 실험 도구를 웹에서 사용할 수 있습니다.
