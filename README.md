# 노동법 RAG 챗봇

한국의 모든 노동법을 RAG로 검색하여 **모든 답변을 법령 데이터에만 기반**으로 하는 노동법 상담 챗봇입니다.

## 지원 법률 범위

### 1. 개별적 근로관계법
- 근로기준법 (법률·시행령·시행규칙)
- 최저임금법
- 근로자퇴직급여 보장법
- 남녀고용평등과 일·가정 양립 지원에 관한 법률
- 기간제 및 단시간근로자 보호 등에 관한 법률

### 2. 집단적 노사관계법
- 노동조합 및 노동관계조정법
- 근로자참여 및 협력증진에 관한 법률

### 3. 노동시장 및 협력적 법률
- 산업안전보건법
- 고용보험법
- 직업안정법
- 산업재해보상보험법

- **모델**: ChatGPT 5.0-nano (`gpt-5-nano`)
- **규칙**: RAG에 없는 내용은 "해당 내용은 제공된 법령 데이터에 없습니다."로만 답변

## 파이프라인

1. **상황 입력** → RAG 기반 **이슈 분류** (멀티 이슈 감지)
2. **조항 좁히기** → 이슈별 관련 조항을 큰 카테고리로 나누고, **구분 질문** 생성
3. **체크리스트** → 걸러진 조항 기준 **정확한 숫자·요건** 검사 질문
4. **결론** → 질문·답변과 RAG 조문만으로 **법조항을 명시한 결론** 생성

## 설치

```bash
pip install -r requirements.txt
```

`.env`에 다음을 설정합니다.

```
OPENAI_API_KEY=sk-...
LAW_API_OC=your_email@example.com   # 국가법령정보 공동활용 API 인증(필수, 법령·동기화용)
# 선택: LAW_CHAT_MODEL=gpt-5-nano, LAW_EMBEDDING_MODEL=text-embedding-3-large
#       LAW_API_DELAY_SEC=1.0, LAW_API_TIMEOUT=30
```

## 법령 데이터 (API 기반)

- 법령·시행령·시행규칙은 **국가법령정보 API**에서 가져와 `api_data/laws/`에 저장합니다. `laws/` 폴더는 사용하지 않습니다.
- **최초 실행 또는 데이터 갱신 순서**
  1. **동기화**: `LAW_API_OC`를 설정한 뒤 `python scripts/sync_all.py` 또는 `run_sync.bat` 실행  
     (laws → terms → bylaws → related → precedents 순으로 API 호출 후 저장)
  2. **벡터 스토어**: 최초 실행 시 `api_data/laws/`의 본문을 파싱해 `vector_store/`(ChromaDB)를 자동 생성. 동기화 후 다시 만들려면 `python main.py --rebuild` 한 번 실행하거나, Streamlit 앱에서 **사이드바 → "벡터 스토어 재구축"** 클릭.
- 상담 시에는 `api_data/`의 저장 데이터만 사용하며, 답변에 없는 내용은 API를 실시간 호출하지 않습니다. 자세한 전략은 `docs/API_STORAGE_STRATEGY.md` 참고.

## 실행

**일상 실행 (Streamlit만)**

```bash
run.bat
```

바로 Streamlit이 뜹니다. 데이터 갱신이 필요할 때만 아래를 사용하세요.

**데이터 갱신 후 실행 (동기화 + 벡터 재구축 + Streamlit)**

```bash
run_with_sync.bat
```

`.env`의 `LAW_API_OC`로 API 동기화 → 벡터 스토어 재구축(1~2분) → Streamlit 순으로 실행됩니다.

**CLI**

```bash
python main.py
```

상황을 입력하면 이슈 분류 → 구분 질문 → 체크리스트 답변 → 결론 순으로 진행됩니다. 벡터 스토어를 처음부터 다시 만들려면 `python main.py --rebuild`를 사용하세요.

**동기화만 실행**

```bash
python scripts/sync_all.py
```

주기 실행(스케줄러)은 `scripts/run_sync_scheduled.py`를 작업 스케줄러/cron에 등록하면 됩니다. 로그는 `api_data/sync.log`에 추가됩니다.

## 자동 업데이트 (GitHub Actions)

이 저장소에는 GitHub Actions 워크플로우가 설정되어 있어 **매주 월요일 자동으로** 법령 데이터를 수집하고 갱신합니다.

### 설정 방법

1. GitHub 저장소의 **Settings → Secrets and variables → Actions**로 이동
2. 다음 Secrets를 추가:
   - `OPENAI_API_KEY`: OpenAI API 키 (벡터 임베딩용)
   - `LAW_API_OC`: 국가법령정보 공동활용 API 인증 이메일

### 워크플로우 동작

- **스케줄**: 매주 월요일 새벽 2시 (UTC) = 한국 시간 월요일 오전 11시
- **수동 실행**: GitHub Actions 탭에서 `Update Data and Vector Store` 워크플로우를 수동으로 실행 가능
- **실행 내용**:
  1. 법령 데이터 동기화 (`scripts/sync_all.py`)
  2. 벡터 스토어 재구축 (임베딩)
  3. 변경된 데이터만 자동 커밋 (벡터 스토어는 커밋하지 않음)

> **참고**: 벡터 스토어는 용량이 크고 환경별로 다를 수 있어 커밋하지 않습니다. 서비스 환경(예: Streamlit Cloud)에서는 배포 시 자동으로 재구축되도록 설정하세요.

---

## 앱 구분

- **`app_chatbot.py`**: **실제 서비스용** 대화형 챗봇. 일반 사용자에게 제공할 때 사용합니다.
- **`app.py`**: 개발·기획자용 4단계 상세 UI(이슈 분류→체크리스트→결론, 장별 둘러보기, 벡터 재구축 등). 내부 검증·기획용입니다.

## 클라우드 배포 (Streamlit Community Cloud)

무료로 웹에 올리려면 **Streamlit Community Cloud**를 쓰면 됩니다.

### 1. GitHub에 올리기

1. GitHub에서 새 저장소(Repository)를 만듭니다.
2. 프로젝트 폴더에서 Git 초기화 후 푸시합니다.

```bash
git init
git add .
git commit -m "노동법 RAG 챗봇"
git branch -M main
git remote add origin https://github.com/당신아이디/저장소이름.git
git push -u origin main
```

- `.env`와 `vector_store/`는 `.gitignore`에 있어서 올라가지 않습니다. (API 키는 클라우드에서 따로 넣습니다.)

### 2. Streamlit Cloud에 배포

1. [share.streamlit.io](https://share.streamlit.io) 에 접속 후 **Sign in with GitHub**으로 로그인합니다.
2. **New app** 클릭 후:
   - **Repository**: 방금 푸시한 저장소 선택
   - **Branch**: `main`
   - **Main file path**: 입력란에 **`app_chatbot.py`** 를 입력하세요 (서비스용 챗봇). 드롭다운에 없어도 직접 입력하면 됩니다. 개발/기획용 4단계 UI는 `app.py`를 입력하면 됩니다.
3. **Advanced settings**를 열고 **Secrets**에 아래처럼 입력합니다.

```toml
OPENAI_API_KEY = "sk-여기에_OpenAI_API_키"
```

4. **Deploy**를 누르면 빌드 후 공개 URL이 생성됩니다 (예: `https://저장소이름-main-xxx.streamlit.app`).

### 참고

- **Cold start**: 앱이 잠들었다가 깨질 때 벡터 스토어를 다시 만들기 때문에 첫 요청이 1~2분 걸릴 수 있습니다.
- **비용**: OpenAI API(임베딩·채팅) 사용량만 과금됩니다. Streamlit Cloud 자체는 무료입니다.
- 다른 클라우드(Railway, Render, Hugging Face Spaces 등)에 올릴 때는 해당 서비스 문서대로 `streamlit run app_chatbot.py`(서비스용) 또는 `streamlit run app.py`(개발/기획용)를 실행 명령으로 지정하면 됩니다.
