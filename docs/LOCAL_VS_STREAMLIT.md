# 로컬(main.py) vs Streamlit(app.py) 실행 비교

## Streamlit Cloud 배포 시 (로컬과 UI가 다르게 보일 때)

- **Main file path**를 반드시 **`app.py`**로 설정하세요.  
  - 이 저장소에는 **`app_chatbot.py`**(채팅형 UI)도 있어, Cloud에서 Main file을 잘못 지정하면 **사이드바·추천 키워드(시나리오 버튼)가 없는 다른 화면**이 뜹니다.
- **로컬과 같은 4단계 UI**(상황 입력 → 이슈 분류 → 체크리스트 → 결론)를 쓰려면 **`app.py`**만 사용해야 합니다.
- 벡터 스토어 로드에 실패해도 이제 **사이드바와 추천 키워드는 항상 표시**되고, 로드 실패 시 사이드바에 안내 메시지가 뜹니다. Secrets에 `OPENAI_API_KEY` 설정과 저장소에 `vector_store/` 포함 여부를 확인하세요.

---

## 동일한 부분

| 항목 | 설명 |
|------|------|
| **진입 후 공통** | 둘 다 `build_vector_store()` → `step1_issue_classification` → `step2_checklist` → `step3_conclusion` 호출 |
| **step1** | 동일: `step1_issue_classification(situation, collection=collection)` |
| **step3** | 동일: `step3_conclusion(issue, qa_list, collection, narrow_answers)`. 내부에서 `_add_precedents_and_explanations` → `get_aiRltLs_cached` 등 동일 경로 |
| **캐시 경로** | config/API_DATA_DIR 등은 `Path(__file__).resolve()` 기준이라 실행 방식과 무관하게 동일 경로 사용 (수정 반영 후) |

---

## 다른 부분

### 1. Step1 직후 조문이 없을 때 보충 검색

| | main.py (로컬) | app.py (Streamlit) |
|---|----------------|---------------------|
| **대상** | `articles_by_issue.get(issue, [])`가 비었을 때만 | 이슈별로 비어 있으면 채움 |
| **검색 소스** | `filter_sources=ALL_LABOR_LAW_SOURCES` **(전체 노동법)** | `filter_sources=ALL_LABOR_LAW_SOURCES` **(동일)** |

→ **동일함.** (과거 main은 SOURCE_LAW만 사용했으나, Streamlit과 맞추기 위해 ALL_LABOR_LAW_SOURCES로 통일됨)

### 2. Step2 체크리스트 생성 시 전달 텍스트

| | main.py | app.py |
|---|---------|--------|
| **변수** | `filter_text = (situation + " " + issue)[:500]` | `filter_preview = (issue + "\n".join(Q/A...))[:400]` |
| **1차 호출 시** | 상황 + 이슈 (최대 500자) | 이슈 위주 (qa_list 비어 있으면 이슈만, 최대 400자) |

→ **로컬**은 처음부터 상황 문맥을 500자까지 넣고, **Streamlit**은 400자 제한에 Q&A가 쌓인 뒤에는 답변 반영.

### 3. Step2 호출 횟수·플로우

| | main.py | app.py |
|---|---------|--------|
| **체크리스트** | 1회 생성 후 터미널에서 답변 입력 | 1차 생성 후 네/아니요/모르겠음 선택, 필요 시 AI가 추가 질문 여부 판단해 2차·3차 생성 |
| **반복** | 없음 | `should_continue` 등으로 최대 CHECKLIST_MAX_ROUNDS까지 |

→ **Streamlit**만 체크리스트 다차례 생성·답변 누적 플로우가 있음.

### 4. Step3에 넘기는 Q&A

| | main.py | app.py |
|---|---------|--------|
| **qa_list** | 터미널 입력 한 줄 답변 (`"(미입력)"` 등 포함) | 세션의 체크리스트 답변 (네/아니요/모르겠음 + 추가 질문 답변) |
| **narrow_answers** | `"네"`, `"아니요"`, `"(미입력)"` 제외한 답변만 | 동일 규칙으로 제외 |

→ **결론 생성 로직(step3)은 동일**하나, **입력되는 qa_list·narrow_answers 내용**은 로컬은 자유 텍스트, Streamlit은 버튼 선택 위주로 다름.

---

## 요약

- **파이프라인 함수와 step3 내부(캐시 생성 포함)는 동일**하게 동작함.
- **차이**는 (1) 체크리스트용 **텍스트 길이·포함 내용**(로컬: situation+issue 500자, Streamlit: issue+Q&A 400자), (2) **체크리스트 반복·답변 수집 방식**(Streamlit만 다차례 라운드)뿐임.
- **캐시가 Streamlit에서 안 생겼던 문제**는 캐시 경로를 절대 경로로 통일한 수정으로 해소된 상태임. 동일 조건(같은 이슈·같은 조문이 상위로 나옴)이면 두 방식 모두 같은 위치에 캐시가 생성됨.
