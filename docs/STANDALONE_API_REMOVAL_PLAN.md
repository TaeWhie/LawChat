# 단독 API 삭제 계획

invoke 한 경로로 통일하기 위해, **invoke와 역할이 겹치는 단독 엔드포인트**를 제거하는 계획입니다.

---

## 1. 대상 엔드포인트 정리

| 엔드포인트 | invoke로 대체 가능 여부 | 삭제 시 영향 |
|------------|--------------------------|--------------|
| **POST /api/v1/chat/route** | ✅ 질문 유형만 필요하면 invoke 1회로 동작은 재현 가능. | **프롬프트 플레이그라운드**에서 **의도 분류(질문 유형)** 확인용으로 사용. message → question_type만 반환하는 API가 필요하므로 **유지 권장**. |
| **POST /api/v1/chat/classify** | ⚠️ 가능하지만, **같은 situation + 다른 프롬프트**로 이슈만 여러 번 비교하려면 단독 호출이 유리함. | **프롬프트 플레이그라운드**에서 단계별 실험에 사용 중 |
| **POST /api/v1/chat/checklist** | ⚠️ 위와 동일. 같은 입력으로 체크리스트만 여러 프롬프트 비교 시 단독이 유리함. | **프롬프트 플레이그라운드**에서 사용 |
| **POST /api/v1/chat/conclusion** | ⚠️ 위와 동일. 같은 issue+all_qa로 결론만 여러 프롬프트 비교 시 단독이 유리함. | **프롬프트 플레이그라운드**에서 사용 |
| **POST /api/v1/chat/qa/knowledge** | ✅ invoke가 지식 질문이면 바로 답변. prompt_overrides도 invoke에서 가능. | 단독 호출만 쓰는 코드/문서 제거 |
| **POST /api/v1/chat/qa/calculation** | ✅ invoke가 계산 질문이면 바로 답변. prompt_overrides도 invoke에서 가능. | 단독 호출만 쓰는 코드/문서 제거 |
| **POST /api/v1/chat/qa/documents** | ✅ invoke가 서류 질문이면 documents 경로로 답변. 단, LLM 미사용·LAW_API_OC 사용. | 제거 시 서류 전용 클라이언트는 invoke로 대체 |

---

## 2. 삭제 단계 제안

### 2-1. 1단계: invoke와 완전 중복 (우선 삭제 권장)

- **POST /api/v1/chat/qa/knowledge**
- **POST /api/v1/chat/qa/calculation**

→ **route는 유지.** 플레이그라운드에서 의도 분류(질문 유형) 확인용으로 사용.  
→ 지식/계산은 invoke가 처리하므로 위 두 단독 경로만 제거해도 됨.

### 2-2. 2단계: classify / checklist / conclusion (삭제 시 플레이그라운드 영향)

- **POST /api/v1/chat/classify**
- **POST /api/v1/chat/checklist**
- **POST /api/v1/chat/conclusion**

→ **삭제하면:** 프롬프트 플레이그라운드에서 “같은 입력, 다른 프롬프트로 단계별 결과만 비교”가 불가능해짐.  
→ **유지하면:** invoke는 “전체 상담용”, classify/checklist/conclusion은 “단계별 실험·비교용”으로 역할이 나뉨.

**선택지**

- **A)** 2단계는 **유지**하고, 1단계만 삭제해 API 면을 단순화.
- **B)** 2단계까지 **전부 삭제**하고, 플레이그라운드는 “invoke만 여러 번 + prompt_overrides 변경”으로 재설계(같은 단계를 여러 번 돌리려면 invoke를 여러 번 호출해야 해서 비용·시간 증가).

### 2-3. 3단계: qa/documents (선택)

- **POST /api/v1/chat/qa/documents**

→ 서류·서식 전용. invoke 안에서도 동일 로직 호출됨. 단독 삭제 시 서류만 쓰는 클라이언트는 invoke로 대체 가능.

---

## 3. 삭제 시 수정 대상 목록

### 3-1. 백엔드 (main_api.py)

- 해당 `@app.post(...)` 라우트 및 핸들러 함수 삭제.
- 사용하는 Request 모델이 다른 곳에서만 쓰이면 유지, 더 이상 안 쓰이면 제거  
  (예: `QARequest`는 qa/knowledge, qa/calculation, qa/documents에서만 사용 → 3개 다 제거 시 QARequest 삭제 검토).
- `ClassifyRequest`, `ChecklistRequest`, `ConclusionRequest`는 해당 단독 API에서만 사용 → 해당 API 제거 시 모델도 제거 검토.

### 3-2. 문서

| 문서 | 수정 내용 |
|------|-----------|
| `docs/API_PROMPT_FOR_OTHER_AI.md` | LLM 사용 엔드포인트 목록에서 삭제된 경로 제거. invoke만 남기거나, 유지하는 단독만 명시. |
| `docs/API_REFERENCE.md` | 삭제된 엔드포인트 섹션 제거, prompt_overrides 설명은 invoke 중심으로 정리. |
| `docs/API_USAGE.md` | 삭제된 URL·예시 제거, invoke 사용법으로 통일. |
| `docs/API_사용방법_전체.md` | 삭제된 API 설명 제거. |
| `docs/RENDER_DEPLOY.md` | 배포 체크 목록에서 삭제된 엔드포인트 제거. |
| `docs/PROMPT_PLAYGROUND_PLAN.md` | classify/checklist/conclusion 삭제 시 “invoke만 사용” 방식으로 수정. 유지 시 변경 없음. |
| `docs/API_흐름도_시작부터_결론까지.md` | 단독 classify→checklist→conclusion 흐름 삭제 시, “invoke 권장” 흐름으로 수정. |
| `docs/체크리스트_검토_준비.md` | 삭제된 API 언급 제거 또는 invoke만 언급. |

### 3-3. 스크립트

| 스크립트 | 수정 내용 |
|----------|-----------|
| `scripts/test_all_endpoints.py` | 삭제된 엔드포인트 호출 제거 또는 skip 처리. |
| `scripts/test_api_v1.py` | 삭제된 엔드포인트 테스트 제거. |
| `scripts/test_production_render.py` | classify, qa/knowledge 등 삭제된 경로 제거. |
| `scripts/check_deployed_api.py` | 삭제된 엔드포인트 체크 제거. |
| `scripts/test_checklist_improvements.py` | classify, checklist 단독 호출 사용 시 → invoke 기반 테스트로 변경하거나, 해당 단독 API 유지 시 그대로 두기. |

---

## 4. 권장 실행 순서

1. **1단계만 삭제**  
   - main_api.py에서 `route`, `qa/knowledge`, `qa/calculation` 제거.  
   - 위 문서·스크립트에서 해당 3개만 반영.

2. **플레이그라운드 유지 여부 결정**  
   - 단계별 프롬프트 비교를 계속할지 결정.  
   - 할 거면 **classify, checklist, conclusion은 유지**.  
   - 안 할 거면 **2단계 삭제** 진행 후 PROMPT_PLAYGROUND_PLAN을 invoke 중심으로 수정.

3. **qa/documents**  
   - 서류 전용 클라이언트가 없으면 3단계로 삭제 검토.

4. **문서·스크립트 일괄 점검**  
   - 삭제한 경로가 남아 있는지 grep으로 확인 후 정리.

---

## 5. 삭제 후 남는 LLM·챗 관련 엔드포인트 (1단계만 삭제 시)

- **POST /api/v1/chat/invoke** — 상담 전체(이슈·체크리스트·결론·지식·계산·서류)  
- **POST /api/v1/chat/invoke/batch** — 배치 invoke  
- **POST /api/v1/chat/route** — 의도 분류(질문 유형) 단독 (플레이그라운드용)  
- **POST /api/v1/chat/classify** — 이슈 분류 단독 (플레이그라운드용)  
- **POST /api/v1/chat/checklist** — 체크리스트 단독 (플레이그라운드용)  
- **POST /api/v1/chat/conclusion** — 결론 단독 (플레이그라운드용)  
- **GET /api/v1/prompts** — 기본 프롬프트 조회  

(2단계까지 삭제하면 classify, checklist, conclusion도 제거되고, invoke·invoke/batch·route·prompts만 남음.)
