# LawChat API — 시작부터 결론까지 흐름도

API를 사용해 **상황 입력 → 이슈 분류 → 체크리스트 → 결론**까지 가는 흐름을 그림으로 정리했습니다.  
Mermaid를 지원하는 뷰어(VS Code 확장, GitHub, [Mermaid Live Editor](https://mermaid.live))에서 다이어그램이 렌더링됩니다.

---

## 1. 권장: invoke 한 엔드포인트 (2회 호출로 결론까지)

클라이언트가 **POST /api/v1/chat/invoke**만 사용할 때의 흐름입니다.  
**1차 요청**으로 체크리스트를 받고, **2차 요청**에 체크리스트 답변을 담아 보내면 결론을 받습니다.  
(현재 그래프는 체크리스트 1라운드만 지원 → 2차 요청 시 무조건 결론으로 직행)

```mermaid
sequenceDiagram
    participant Client as 클라이언트
    participant API as POST /api/v1/chat/invoke
    participant Graph as LangGraph
    participant Step1 as step1 이슈분류
    participant Step2 as step2 체크리스트
    participant Step3 as step3 결론

    Note over Client,Step3: 【1차 요청】상황 메시지
    Client->>+API: message="월급을 3개월째 못 받았어요", thread_id, openai_api_key
    API->>+Graph: invoke(state)
    Graph->>Graph: 질문 유형 분기 (지식/계산/상황/서류/예외)
    Graph->>Step1: 이슈 분류 + 조문 검색
    Graph->>Step2: step2_checklist (1차, qa_list=[])
    Step2-->>Graph: checklist[], rag_results
    Graph-->>API: phase="checklist", checklist, messages
    API-->>-Client: status, phase="checklist", checklist[], selected_issue, messages

    Note over Client,Step3: 사용자가 체크리스트에 네/아니요/모르겠음 선택

    Note over Client,Step3: 【2차 요청】체크리스트 답변을 메시지로 전달
    Client->>+API: message="질문1: 네\n질문2: 아니요\n...", thread_id (동일)
    API->>+Graph: invoke(state) — phase=checklist, 기존 checklist 유지
    Graph->>Graph: intent = answer_checklist (답변 파싱)
    Graph->>Step3: step3_conclusion(issue, qa_list)
    Step3-->>Graph: conclusion, related_articles
    Graph-->>API: phase="conclusion", messages (결론 텍스트)
    API-->>-Client: status, phase="conclusion", messages (결론)
```

---

## 2. 단계별 API (classify → checklist → conclusion)

**POST /api/v1/chat/classify** → **POST /api/v1/chat/checklist** (필요 시 반복) → **POST /api/v1/chat/conclusion** 순서로 호출하는 흐름입니다.  
체크리스트 **다음 라운드**는 `/checklist`의 `should_continue`로 판단합니다.

```mermaid
flowchart TB
    Start([클라이언트: 시작]) --> A["POST /api/v1/chat/classify"]
    A --> AReq["요청: situation, openai_api_key"]
    AReq --> ARes["응답: selected_issue, issues, articles_by_issue"]
    ARes --> B["POST /api/v1/chat/checklist"]
    B --> BReq["요청: issue, situation, all_qa"]
    BReq --> BLogic[step2_checklist 내부]
    BLogic --> BRetry{"컨텍스트 없음? 또는 checklist 0개?"}
    BRetry -->|예| BRetryDo["재시도: 확장 검색 또는 LLM 재호출"]
    BRetryDo --> BOut
    BRetry -->|아니오| BOut["응답: checklist, should_continue, rag_results"]
    BOut --> BDec{"should_continue? 새 checklist 있음?"}
    BDec -->|예, 라운드 3 미만| ShowCheck["체크리스트 표시, 사용자 답변 수집"]
    ShowCheck --> B2["POST /api/v1/chat/checklist 다시 호출"]
    B2 --> BReq
    BDec -->|아니오| C["POST /api/v1/chat/conclusion"]
    C --> CReq["요청: issue, all_qa"]
    CReq --> CRes["응답: conclusion, related_articles, usage"]
    CRes --> End([클라이언트: 결론 표시])
```

---

## 3. 전체 흐름 한눈에 (엔드포인트 기준)

```mermaid
flowchart LR
    subgraph Invoke["invoke 방식 (권장)"]
        I1["1️⃣ invoke\n(상황 메시지)"]
        I2["2️⃣ invoke\n(체크리스트 답변 메시지)"]
        I1 --> I2
        I2 --> IEnd["결론"]
    end

    subgraph StepByStep["단계별 방식"]
        S1["classify"]
        S2["checklist\n(1차)"]
        S2R["checklist\n(2차, 선택)"]
        S3["conclusion"]
        S1 --> S2
        S2 --> S2R
        S2R --> S2R
        S2R --> S3
        S2 --> S3
      end

    Client([클라이언트]) --> Invoke
    Client --> StepByStep
```

---

## 4. 서버 내부 (invoke 시 그래프 노드 흐름)

invoke 한 번이 호출될 때, **그래프가 내부에서 어떻게 단계를 타는지** 요약입니다.

```mermaid
flowchart TB
    subgraph inv1["1차 요청: 상황 메시지"]
        M1[메시지 수신] --> RT[route: 질문 유형]
        RT --> T1{유형?}
        T1 -->|situation| S1[step1: 이슈 분류 + 조문]
        T1 -->|knowledge 등| Other[지식/계산/서류/예외 처리]
        S1 --> S2[step2: 체크리스트 생성]
        S2 --> R1["반환: phase=checklist, messages"]
    end

    subgraph inv2["2차 요청: 체크리스트 답변"]
        M2["메시지 수신, phase=checklist"] --> Parse[답변 파싱 Q: A 형식]
        Parse --> S3[step3: 결론 생성]
        S3 --> R2["반환: phase=conclusion, 결론"]
    end
```

---

## 5. 참고

- **invoke**: 상태는 `thread_id` + 서버 메모리(또는 체크포인트)로 유지됩니다. 2차 요청 시 같은 `thread_id`와 이전에 받은 `checklist`/`phase`를 서버가 state로 사용합니다.
- **단계별 API**: 상태는 전부 **클라이언트**가 관리합니다. `classify` 결과와 `checklist` 호출 시마다 받은 `all_qa`를 누적해 `conclusion`에 넘깁니다.
- **체크리스트 0개·컨텍스트 없음 재시도**: 모두 **step2_checklist** 내부에서 이루어지며, `/checklist` 또는 invoke(그래프)를 통해 API로 호출될 때 자동으로 적용됩니다.

이 문서를 열어두고 위 Mermaid 블록을 지원하는 뷰어에서 보시면, API로 시작부터 결론까지의 흐름을 그림으로 확인하실 수 있습니다.
