# 노동법 RAG 챗봇

근로기준법(법률·시행령·시행규칙)을 RAG로 검색하여 **모든 답변을 법령 데이터에만 기반**으로 하는 노동법 상담 챗봇입니다.

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

`.env`에 OpenAI API 키 설정:

```
OPENAI_API_KEY=sk-...
# 선택: LAW_CHAT_MODEL=gpt-5-nano, LAW_EMBEDDING_MODEL=text-embedding-3-small
```

## 법령 데이터

- `laws/` 폴더에 근로기준법(법률), 시행령, 시행규칙 마크다운(`.md`)을 두면 조(條) 단위로 청킹되어 벡터 스토어에 적재됩니다.
- 최초 실행 시 `vector_store/`에 ChromaDB가 생성됩니다. 법령 파일을 바꾼 뒤 다시 쌓으려면 `vector_store` 폴더를 삭제하거나, 코드에서 `build_vector_store(force_rebuild=True)`로 재구축하세요.

## 실행

**Streamlit (웹 UI)**

```bash
streamlit run app.py
```

브라우저에서 상황 입력 → 이슈 선택 → 조항 구분 질문 → 체크리스트 → 결론 순으로 진행됩니다.

**CLI**

```bash
python main.py
```

상황을 입력하면 이슈 분류 → 구분 질문 → 체크리스트 답변 → 결론 순으로 진행됩니다.

---

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
   - **Main file path**: `app.py`
3. **Advanced settings**를 열고 **Secrets**에 아래처럼 입력합니다.

```toml
OPENAI_API_KEY = "sk-여기에_OpenAI_API_키"
```

4. **Deploy**를 누르면 빌드 후 공개 URL이 생성됩니다 (예: `https://저장소이름-main-xxx.streamlit.app`).

### 참고

- **Cold start**: 앱이 잠들었다가 깨질 때 벡터 스토어를 다시 만들기 때문에 첫 요청이 1~2분 걸릴 수 있습니다.
- **비용**: OpenAI API(임베딩·채팅) 사용량만 과금됩니다. Streamlit Cloud 자체는 무료입니다.
- 다른 클라우드(Railway, Render, Hugging Face Spaces 등)에 올릴 때는 해당 서비스 문서대로 `streamlit run app.py`를 실행 명령으로 지정하면 됩니다.
