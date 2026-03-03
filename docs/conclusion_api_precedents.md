## 결론 API와 판례 상세 조회 연동 가이드

이 문서는 **결론 API 응답**에 포함된 판례 메타정보를 활용해,  
클라이언트가 **판례 상세 내용(판시사항·판결요지·본문 등)** 을 추가로 조회하는 방법을 정리한 것입니다.

---

## 1. 결론 API 응답 구조 (판례 관련)

`rag.pipeline.step3_conclusion` 기반 결론 API는 대략 아래와 같은 JSON을 반환합니다.

```jsonc
{
  "conclusion": "…결론 텍스트…",
  "related_articles": ["제24조", "제27조"],
  "law_results": [/* 조문 검색 결과 */],
  "decree_rule_results": [/* 시행령/시행규칙 결과 */],
  "validation": { /* 인용 검증 정보 */ },

  "precedents_used": {
    "source": "api",                // "api" | "cache"
    "keyword_used": "해고/징계",     // 최종 사용된 검색 키워드
    "query_used": "…",             // API 검색 쿼리 (없을 수도 있음)
    "jo_used": "근로기준법 제27조",  // 참조조문(JO)로 사용된 값 (복수면 ", "로 join)
    "count": 3,                    // 선택된 판례 개수
    "titles": [
      "해고무효확인[…]",
      "부당해고구제재심판정취소[…]",
      "부당해고구제재심판정취소[…]"
    ],
    "precedent_ids": [
      "214235",
      "228123",
      "230456"
    ]
  },

  "debug_info": { /* 선택 */ }
}
```

- **`precedents_used.precedent_ids`**
  - 각 원소는 **국가법령정보 판례 API의 `ID`(= 판례일련번호)** 에 해당한다.
  - 이 값을 사용해 **판례 본문 API를 다시 호출**할 수 있다.
- **`precedents_used.titles`**
  - 같은 순서의 **사건명 리스트**.
  - UX 상 “결론에 참고한 판례 목록”을 보여줄 때 사용하기 좋다.
- **`source`, `keyword_used`, `query_used`, `jo_used`**
  - 어떤 방식으로 판례를 찾았는지 추적/디버깅용 메타 정보.

---

## 2. 판례 상세 조회 API 설계 (서버 측 래핑)

클라이언트가 직접 국가법령정보 API를 호출하게 만들기보다,  
서버에서 **판례 상세 조회용 API** 를 하나 더 제공하는 방식을 권장한다.

### 2.1 엔드포인트 제안

- **HTTP 메서드**: `GET`
- **URL**: `/api/precedent/{id}`
- **Path 파라미터**
  - `id`: 결론 API 응답의 `precedents_used.precedent_ids` 중 하나

#### 응답 예시

```json
{
  "id": "214235",
  "case_name": "해고무효확인[근로자에 대한 계약종료통지서에 해고사유가 전혀 기재되어 있지 않았던 사건]",
  "case_number": "2017다226605",
  "decision_date": "2021.02.25",
  "court": "대법원",
  "source": "대법원",
  "type": "판결",
  "headnote": "…판시사항/판결요지 요약…",
  "statutes": "근로기준법 제27조, …",
  "body": "…판결 본문 전문 또는 앞부분 일부…"
}
```

### 2.2 내부 구현 개략

서버 내부에서는 이미 정의된 `rag.law_api_client.get_body` 를 사용해  
국가법령정보 API `lawService.do` 를 호출하면 된다.

```python
from rag.law_api_client import get_body

def get_precedent_detail(id: str) -> dict:
  """
  국가법령정보 판례 본문 API를 호출해
  판시사항/판결요지/본문 등을 정규화된 형태로 반환.
  """
  r = get_body("prec", id=id)  # 내부적으로 lawService.do 호출
  if not r.get("success") or not r.get("data"):
      # 에러 처리 (로그 + 적절한 HTTP 에러 반환 등)
      ...

  data = r["data"]
  # 실제 필드명은 응답 구조에 따라 조정
  prec = data.get("prec") or data.get("Prec") or data.get("판례") or data

  return {
      "id": id,
      "case_name": prec.get("사건명") or prec.get("사건번호"),
      "case_number": prec.get("사건번호"),
      "decision_date": prec.get("선고일자"),
      "court": prec.get("법원명"),
      "source": prec.get("데이터출처명"),
      "type": prec.get("판결유형"),
      "headnote": prec.get("판시사항") or prec.get("판결요지") or prec.get("요지"),
      "statutes": prec.get("참조조문") or prec.get("참조법령"),
      "body": prec.get("판결내용") or prec.get("본문")  # 실제 키 이름에 맞게 조정
  }
```

이 함수를 HTTP 핸들러(예: FastAPI, Django, Flask 등)에서 호출해 `/api/precedent/{id}` 응답으로 반환하면 된다.

---

## 3. 클라이언트 사용 플로우

### 3.1 결론 조회

1. **결론 API 호출**

```http
POST /api/conclusion
Content-Type: application/json

{
  "issue": "해고/징계",
  "qa_list": [...],
  "situation": "정리해고 통보받았는데 해고예고는 50일 전에 받았어요."
}
```

2. **응답에서 판례 ID 목록 추출**

```js
const used = response.precedents_used;
const ids = used.precedent_ids;   // 예: ["214235","228123","230456"]
const titles = used.titles;       // 사건명 리스트
```

3. **UI 구성**

- 결론 화면에서:
  - `titles` 리스트를 “참고 판례” 섹션으로 표시
  - 각 항목 옆에 “자세히 보기” 버튼 제공

### 3.2 판례 상세 조회

사용자가 특정 판례를 클릭했을 때:

```http
GET /api/precedent/214235
```

응답으로 받은 `headnote`·`body`·`statutes` 등을 모달/새 화면으로 렌더링한다.

---

## 4. 외부 문서에 명시해야 할 핵심 포인트

외부 API 문서(예: 공개 REST API 문서)에 아래 내용을 명확히 적어 두길 권장한다.

- **결론 API**
  - `precedents_used.precedent_ids`
    - 설명: “이 결론에서 참고한 판례들을 국가법령정보 API로 다시 조회할 수 있는 **판례 ID (law.go.kr ID)** 리스트”
    - 타입: `string[]`
  - `precedents_used.titles`
    - 설명: 위 ID 리스트와 같은 순서의 사건명 배열.

- **판례 상세 API**
  - 엔드포인트: `GET /api/precedent/{id}`
  - Path 파라미터 `{id}`: **결론 API의 `precedent_ids` 값 그대로 사용**
  - 응답 필드:
    - 최소: `id`, `case_name`, `case_number`, `decision_date`, `court`, `headnote`(판시사항/판결요지), `statutes`, `body`

이 규약만 지키면,
- 외부 서비스는 **결론 API만으로 “어떤 판례를 근거로 삼았는지”를 알고,**
- 필요할 때마다 **판례 상세 API를 통해 해당 판례의 실제 내용을 안전하게 조회**할 수 있다.

