# LawChat 프롬프트 실험 도구 계획 (API 활용)

전 단계(이슈 분류 → 체크리스트 → 결론)와 **지식/계산/예외/문서** 질문까지, **입력과 프롬프트를 조합해** 결과를 나란히 비교하는 개발자 도구를 API만으로 만드는 계획입니다.

---

## 1. 목표

- **입력·프롬프트 조합 실험:** 같은 입력 + 다른 프롬프트로 출력을 비교할 수도 있고, **입력을 바꿔가며**(다른 situation, 다른 message, 다른 issue+all_qa 등) 같은 프롬프트 또는 다른 프롬프트로 여러 번 호출해 비교할 수도 있다.
- 단계별로 **입력(요청 바디)** 과 **prompt_overrides**를 자유롭게 넣어 호출하면 되므로, 별도 백엔드 없이 **기존 API만** 사용한다.

---

## 2. 활용할 API 정리

### 2.0 의도 분류(질문 유형 분류)

| 단계 | 엔드포인트 | 입력 | 변경 가능 항목 | 비교할 출력 |
|------|------------|------|----------------|-------------|
| 의도 분류 | `POST /api/v1/chat/route` (또는 동일 역할 단독 API) | message(text). **여러 개 넣어서 비교 가능** | (현재 규칙 기반이라 없음. 추후 LLM 분류 시 prompt_overrides) | question_type (knowledge / calculation / documents / exception / situation) |

- **역할:** 사용자 메시지가 지식/계산/문서/예외/상황 중 어떤 유형으로 갈지 판별. invoke가 그 다음 단계에서 이 결과를 사용함.
- **현재:** 백엔드는 `classify_question_type()`으로 **규칙·키워드 기반** 분류만 하므로 **프롬프트가 없음**. 플레이그라운드에서 “의도 분류”를 쓰려면 **message → question_type만 반환하는 단독 API(예: route)** 가 필요함. 같은 message에 대해 분류 결과를 확인·표시하는 용도로 사용.
- **추후:** 의도 분류를 LLM + prompt_overrides로 바꾸면, 같은 message·다른 프롬프트로 분류 결과를 비교하는 실험 추가 가능.

### 2.1 단계별 단독 API (classify / checklist / conclusion)

| 단계 | 엔드포인트 | 입력 | 변경 가능 항목 | 비교할 출력 |
|------|------------|------|----------------|-------------|
| 이슈 분류 | `POST /api/v1/chat/classify` | situation, top_k. **situation을 바꿔가며 여러 번 호출 가능** | prompt_overrides (system_issue_classification, user_issue_classification) | issues, articles_by_issue |
| 체크리스트 | `POST /api/v1/chat/checklist` | issue, situation, all_qa, round 등. **입력 조합을 바꿀 수 있음** | prompt_overrides (system_checklist, user_checklist, system_checklist_continuation, user_checklist_continuation) | checklist |
| 결론 | `POST /api/v1/chat/conclusion` | issue, all_qa. **다른 issue·all_qa로 여러 번 호출 가능** | prompt_overrides (system_conclusion, user_conclusion) | conclusion 텍스트, related_articles 등 |

### 2.2 지식 / 계산 / 예외 / 문서 (invoke 사용)

| 유형 | 엔드포인트 | 입력 | 변경 가능 항목 | 비교할 출력 |
|------|------------|------|----------------|-------------|
| 지식 | `POST /api/v1/chat/invoke` | message(지식 질문). **질문을 바꿔가며 여러 개 실험 가능.** 호출마다 새 thread_id | prompt_overrides (system_knowledge_qa, user_knowledge_qa) | messages 마지막 AIMessage의 c |
| 계산 | `POST /api/v1/chat/invoke` | message(계산 질문). **다른 질문으로 여러 번 호출 가능.** 호출마다 새 thread_id | prompt_overrides (system_calculation_qa, user_calculation_qa) | messages 마지막 AIMessage의 c |
| 예외 | `POST /api/v1/chat/invoke` | message(예외 질문). **입력 변경 가능.** 호출마다 새 thread_id | prompt_overrides (system_exception_qa, user_exception_qa) | messages 마지막 AIMessage의 c |
| 문서 | `POST /api/v1/chat/invoke` | message(서류·서식 질문). **입력 변경 가능.** 호출마다 새 thread_id | (현재 문서 포맷은 코드 고정. 추후 override 키 추가 시 동일 방식 적용) | messages 마지막 AIMessage의 c |

- 입력은 **고정**할 수도 있고 **여러 값으로 바꿔가며** 호출할 수 있다. (같은 입력 + 다른 프롬프트 비교 / 다른 입력 + 같은·다른 프롬프트 비교 모두 가능.)
- 지식/계산/예외/문서는 invoke 또는 단독 API 사용 시, 호출마다 **서로 다른 thread_id**를 주어 각 턴이 독립되도록 한다.
- GET /api/v1/prompts 에서 system_knowledge_qa, user_knowledge_qa, system_calculation_qa, user_calculation_qa, system_exception_qa, user_exception_qa 기본값 확인 가능.

**공통**

- 모든 LLM API: 요청 바디에 **openai_api_key** 필수.
- 기본 프롬프트 목록·플레이스홀더 확인: **GET /api/v1/prompts**.

**시나리오 수집용**

- 한 번의 상담 흐름을 재현하려면 **POST /api/v1/chat/invoke** 로 situation → checklist 답변까지 진행해, 응답에서 **situation, selected_issue, all_qa** 등을 추출해 저장.

---

## 3. 단계별 실험 플로우

### 3.0 의도 분류(질문 유형) 실험

1. **입력:** message(사용자 질문). 하나로 고정하거나 **여러 message를 넣어서** 각각 question_type 확인.
2. **실험:** (현재) route 또는 동일 API로 호출. 입력을 바꿀 때마다 또는 같은 입력에 대해(추후 LLM 분류 시) prompt_overrides만 바꿔 분류 결과 비교.
3. **비교:** question_type 표시 또는 나란히 비교.

### 3.1 이슈 분류 실험

1. **입력:** situation(문자열), top_k(선택). **situation을 고정하거나 여러 개 넣어서** 실험.
2. **실험:** 같은 입력에 prompt_overrides만 바꾼 classify N회, 또는 **입력을 바꿔가며** 같은/다른 프롬프트로 호출.
3. **비교:** 각 응답의 issues, articles_by_issue를 나란히 표시(테이블 또는 카드).

### 3.2 체크리스트 실험

1. **입력:** issue, situation, all_qa, round 등. **고정하거나 조합을 바꿔가며** 실험.
2. **실험:** 같은 입력 + 다른 prompt_overrides, 또는 **다른 입력** + 같은/다른 프롬프트로 checklist 여러 번 호출.
3. **비교:** 각 응답의 checklist(질문 목록)를 나란히 표시.

### 3.3 결론 실험

1. **입력:** issue, all_qa. **한 세트로 고정하거나 여러 세트(다른 상담 시나리오)** 로 실험.
2. **실험:** 같은 입력 + 다른 prompt_overrides, 또는 **다른 issue·all_qa** + 같은/다른 프롬프트로 conclusion 여러 번 호출.
3. **비교:** 각 응답의 conclusion 텍스트(및 related_articles 등)를 나란히 표시.

### 3.4 지식 실험

1. **입력:** message(지식 질문). **하나로 고정하거나 여러 질문**을 넣어서 실험. 호출마다 새 thread_id.
2. **실험:** 같은 message + 다른 prompt_overrides, 또는 **다른 message** + 같은/다른 프롬프트로 invoke(또는 단독 API) 여러 번 호출.
3. **비교:** 각 응답의 마지막 AIMessage의 c(내용)를 나란히 표시.

### 3.5 계산 실험

1. **입력:** message(계산 질문). **고정 또는 여러 질문**으로 실험. 호출마다 새 thread_id.
2. **실험:** 같은 message + 다른 prompt_overrides, 또는 **다른 message** + 같은/다른 프롬프트로 invoke(또는 단독 API) 여러 번 호출.
3. **비교:** 각 응답의 마지막 AIMessage의 c를 나란히 표시.

### 3.6 예외 실험

1. **입력:** message(예외 질문). **고정 또는 여러 질문**으로 실험. 호출마다 새 thread_id.
2. **실험:** 같은 message + 다른 prompt_overrides, 또는 **다른 message** + 같은/다른 프롬프트로 invoke 여러 번 호출.
3. **비교:** 각 응답의 마지막 AIMessage의 c를 나란히 표시.

### 3.7 문서(서류·서식) 실험

1. **입력:** message(서류 질문). **고정 또는 여러 질문**으로 실험. 호출마다 새 thread_id.
2. **실험:** 같은 message 또는 **다른 message**로 invoke 여러 번. (추후 문서용 override 지원 시 prompt_overrides 비교 가능.)
3. **비교:** 각 응답의 마지막 AIMessage의 c를 나란히 표시.

---

## 4. 데이터 흐름 제안

### 4.1 시나리오 캡처 (한 번만)

- **방식 A:** 프론트에서 invoke로 상담을 진행하다가, phase가 "checklist"일 때·결론 받은 직후 등에 응답을 저장.
- **방식 B:** classify → checklist → conclusion을 수동으로 한 번씩 호출하면서, 각 단계 출력을 도구에 "시나리오"로 저장.

저장 필드 예:

- **시나리오 메타:** 이름, 생성 시각.
- **1단계용:** situation.
- **2단계용:** issue, situation, all_qa(1라운드만 쓰면 빈 배열 가능), round, 필요 시 previous_rag_results.
- **3단계용:** issue, all_qa(체크리스트 답변 포함).

### 4.2 실험 실행

- 사용자가 **현재 단계**(**의도 분류** / 이슈 분류 / 체크리스트 / 결론 / 지식 / 계산 / 예외 / 문서)를 선택.
- 해당 단계의 **저장된 입력** 또는 **사용자가 넣은 여러 입력**을 사용해, **프롬프트 세트**와 조합해 호출.
- 각 프롬프트 세트마다 동일 입력 + 해당 prompt_overrides로 API 한 번씩 호출.
- 응답을 **실험 결과**로 모아서 비교 뷰에 표시.

### 4.3 프롬프트 세트 관리

- GET /api/v1/prompts 로 **기본값**을 불러와 "기본" 세트로 사용.
- 사용자가 system_* / user_* 텍스트를 수정해 "세트 A", "세트 B"처럼 이름을 붙여 저장.
- 호출 시 해당 세트를 prompt_overrides 객체로 변환해 body에 넣는다.

---

## 5. 기능 요약 (체크리스트)

- [ ] **시나리오**
  - invoke 또는 단계별 API로 situation / issue / all_qa 수집 후 저장하거나, **직접 입력을 여러 개** 정의.
  - 저장된 시나리오 또는 **입력 목록**을 선택해 각 단계의 입력으로 사용. **입력은 고정일 수도 있고, 실험마다 바꿀 수도 있음.**
- [ ] **프롬프트**
  - GET /api/v1/prompts 로 기본 프롬프트 로드.
  - 단계별로 수정 가능한 에디터, 복수 "프롬프트 세트" 저장/이름 지정.
- [ ] **단계별 실험**
  - **의도 분류:** route(또는 동일 API) 호출 → question_type 확인. **여러 message 넣어서 입력별 결과 비교 가능.**
  - 이슈 분류: classify N회. **같은 situation + 다른 프롬프트** 또는 **다른 situation** + 같은/다른 프롬프트.
  - 체크리스트: checklist N회. **입력·프롬프트 조합** 자유.
  - 결론: conclusion N회. **입력·프롬프트 조합** 자유.
  - **지식/계산/예외/문서:** invoke 또는 단독 API N회. **같은 질문 + 다른 프롬프트** 또는 **다른 질문** + 같은/다른 프롬프트.
- [ ] **비교 UI**
  - 같은 단계의 여러 결과를 나란히(열 또는 탭) 표시.
  - 선택한 실험만 비교, 복사, 내보내기(JSON/텍스트) 등.
- [ ] **설정**
  - API Base URL, openai_api_key(보안 고려해 로컬만 또는 환경변수 연동).

---

## 6. 구현 순서 제안

1. **설정·API 연동:** Base URL, API 키, GET /api/v1/prompts 호출 및 기본 프롬프트 표시.
2. **의도 분류 연동:** route(또는 question_type 반환 API) 호출로 message → question_type 확인·표시.
3. **시나리오 수집:** invoke 응답에서 situation / selected_issue / all_qa 추출해 저장하는 플로우(또는 수동 입력 폼).
4. **결론 실험:** 저장된 issue + all_qa로 conclusion 여러 번 호출, 결과 나란히 비교(가장 입력이 단순함).
5. **체크리스트 실험:** 저장된 issue, situation, all_qa로 checklist 여러 번 호출, checklist 비교.
6. **이슈 분류 실험:** situation으로 classify 여러 번 호출, issues/articles 비교.
7. **지식/계산/예외/문서 실험:** 고정 message로 invoke 여러 번(호출마다 새 thread_id), prompt_overrides만 바꿔서 마지막 AI 응답 비교.
8. **프롬프트 세트 편집·저장:** 단계별·유형별 프롬프트 에디터와 세트 이름 관리.
9. **비교 뷰 공통화:** 단계별 출력 구조가 다르므로, 단계마다 적절한 비교 레이아웃(테이블/카드/텍스트) 적용.

---

## 7. 참고

- **API 상세:** `docs/API_REFERENCE.md`
- **프롬프트 키·플레이스홀더:** GET /api/v1/prompts 응답의 prompts, placeholders.
- **invoke로 시나리오 얻기:** 같은 thread_id 유지해 체크리스트 답변까지 진행한 뒤, 응답의 selected_issue, all_qa(qa_list) 저장.
