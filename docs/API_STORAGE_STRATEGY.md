# API 데이터 저장·캐시 전략

**전제**: `laws/` 폴더는 제거하고, 모든 법령·판례·해석 등은 API 기반.  
**원칙**: API 호출을 줄이기 위해 **저장 가능한 것은 주기적으로 동기화해 두고, 상담 시에는 저장된 데이터를 우선 사용**한다.

---

## 1. 저장소 구조 (laws/ 대체)

`laws/` 삭제 후 아래 디렉터리를 사용한다.

```
api_data/                    # API 기반 데이터 루트 (config에서 API_DATA_DIR 등으로 참조)
├── laws/                    # 현행법령·행정규칙 본문 (조 단위 또는 원문 JSON)
│   ├── law/                 # target=law 목록·본문
│   │   ├── list.json       # 노동 관련 법령 목록 (주기 갱신)
│   │   └── {법령ID}.json   # 본문 JSON 또는 파싱된 조 단위
│   └── admrul/
│       ├── list.json
│       └── {행정규칙ID}.json
├── bylaws/                  # 별표·서식 (licbyl, admbyl)
│   ├── licbyl_list.json
│   └── admbyl_list.json
├── terms/                   # 지능형 법령정보지식베이스 (상대적으로 정적)
│   ├── lstrmAI.json        # 법령용어 검색 결과 덤프 또는 인기 용어
│   ├── dlytrm.json         # 일상용어
│   ├── lstrmRlt.json       # 법령용어-일상용어 연계
│   ├── dlytrmRlt.json      # 일상용어-법령용어 연계
│   ├── lstrmRltJo.json     # 법령용어-조문 연계
│   └── joRltLstrm.json     # 조문-법령용어 연계
├── related/                 # 관련법령 (lsRlt) — 법령/조문별로 저장 가능
│   └── lsRlt_{법령명_조문}.json
├── precedents/              # 판례·헌재·해석·위원회 (도메인별 또는 키워드별 덤프)
│   ├── prec/               # 판례
│   │   └── by_keyword/     # 퇴직금, 해고, 임금 등 키워드별 목록+요지
│   ├── detc/
│   ├── expc/
│   ├── decc/
│   ├── nlrc/
│   ├── eiac/
│   ├── iaciac/
│   ├── ppc/
│   ├── ftc/
│   ├── moelCgmExpc/
│   ├── molegCgmExpc/
│   └── mojCgmExpc/
└── cache/                   # 온디맨드 호출 결과 캐시 (쿼리 해시 또는 ID 기준)
    ├── aiSearch/           # 지능형 검색 결과 (query 해시 → JSON)
    └── aiRltLs/            # 연관법령 API (조문 키 → JSON)
```

- **RAG/벡터 스토어**: 위 `api_data/laws/` 등에서 파싱한 텍스트를 청킹해 `vector_store/`에 적재 (기존과 동일하게 벡터 검색).
- **laws/** 에 있던 `근로기준법(법률).md` 등은 더 이상 두지 않고, **API로 수집한 내용을 api_data/laws/ 아래에 저장**한 뒤 그걸로 RAG를 구축한다.

---

## 2. 저장 vs 온디맨드 정리

| 데이터 | 저장 여부 | 갱신 주기 | 비고 |
|--------|-----------|-----------|------|
| **현행법령 목록·본문** (law) | ✅ 저장 | 일 1회 또는 주 1회 | 노동 관련만 목록 조회 후 본문 저장 |
| **행정규칙 목록·본문** (admrul) | ✅ 저장 | 일 1회 또는 주 1회 | 시행령·시행규칙 등 |
| **법령 별표·서식** (licbyl) | ✅ 저장 | 주 1회 | 목록 + 본문(형식은 제공처 따름) |
| **행정규칙 별표·서식** (admbyl) | ✅ 저장 | 주 1회 | 동일 |
| **법령용어** (lstrmAI) | ✅ 저장 | 주 1회 | 인기 용어 목록 기준 덤프 |
| **일상용어** (dlytrm) | ✅ 저장 | 주 1회 | 사용처와 맞게 일부만 덤프 가능 |
| **법령용어-일상용어 연계** (lstrmRlt) | ✅ 저장 | 주 1회 | 용어 목록 기준 덤프 |
| **일상용어-법령용어 연계** (dlytrmRlt) | ✅ 저장 | 주 1회 | 이슈 정규화용으로 자주 쓰는 표현 위주 |
| **법령용어-조문 연계** (lstrmRltJo) | ✅ 저장 | 주 1회 | 노동 관련 용어 위주 |
| **조문-법령용어 연계** (joRltLstrm) | ✅ 저장 | 주 1회 또는 조문 기준 | 저장된 법령 조문 범위 내 |
| **관련법령** (lsRlt) | ✅ 저장 | 주 1회 또는 조문 추가 시 | 저장된 법령·조문에 대해 미리 조회해 두기 |
| **판례** (prec) | ✅ 저장(덤프) | 주 1회 | 노동 도메인 키워드(퇴직금, 해고, 임금 등)별 목록 + 상위 N건 본문 |
| **헌재** (detc) | ✅ 저장(덤프) | 주 1회 | 근로·노동 등 키워드별 소량 |
| **법령해석례** (expc) | ✅ 저장(덤프) | 주 1회 | 근로기준법 등 키워드별 |
| **행정심판례** (decc) | ✅ 저장(덤프) | 주 1회 | 노동·근로 키워드별 |
| **위원회** (nlrc, eiac, iaciac, ppc, ftc) | ✅ 저장(덤프) | 주 1회 | 각 target별 키워드 검색 결과 상위 N건 |
| **부처 법령해석** (moel, moleg, moj) | ✅ 저장(덤프) | 주 1회 | 노동·근로 키워드별 목록+본문 |
| **지능형 검색** (aiSearch) | 캐시 | 쿼리별 | 첫 호출 시 cache/aiSearch/{query_hash}.json 저장, TTL(예: 7일) |
| **연관법령 API** (aiRltLs) | 캐시 | 조문별 | cache/aiRltLs/{조문키}.json, TTL |

정리하면:

- **저장**: 법령·행정규칙·별표·서식·용어·연계·판례·해석·위원회 등은 **주기 동기화 스크립트**로 `api_data/` 아래에 저장해 두고, 상담 시에는 이 저장 데이터를 읽는다.
- **캐시**: aiSearch, aiRltLs는 **온디맨드 호출**하되, 결과를 **쿼리/조문 키 기준으로 캐시**해 같은 질의 반복 시 API를 타지 않도록 한다.

---

## 3. 동기화 스크립트 역할

| 스크립트 | 역할 | 호출 API | 저장 위치 |
|----------|------|----------|-----------|
| `sync_laws.py` | 노동 관련 법령·행정규칙 목록 조회 → 본문 조회 → 조 단위 파싱 | law, admrul | api_data/laws/ |
| `sync_bylaws.py` | 별표·서식 목록·본문 수집 | licbyl, admbyl | api_data/bylaws/ |
| `sync_terms.py` | 용어·연계 데이터 덤프 | lstrmAI, dlytrm, lstrmRlt, dlytrmRlt, lstrmRltJo, joRltLstrm | api_data/terms/ |
| `sync_related.py` | 저장된 법령/조문에 대해 관련법령 조회 | lsRlt | api_data/related/ |
| `sync_precedents.py` | 판례·헌재·해석·위원회·부처해석 키워드별 목록+본문 | prec, detc, expc, decc, nlrc, eiac, iaciac, ppc, ftc, moelCgmExpc, molegCgmExpc, mojCgmExpc | api_data/precedents/ |

- 동기화 시 **요청 간 딜레이**(예: 1초) 적용해 API 부하 완화.
- 갱신 주기는 위 표(주 1회 등)에 맞춰 cron/스케줄러로 실행.

---

## 4. 상담 시 데이터 사용 순서

1. **법령·조문**: RAG는 `api_data/laws/`에서 파싱한 텍스트로 구축된 벡터 스토어 사용 (API 직접 호출 없음).
2. **이슈 정규화**: `api_data/terms/dlytrmRlt.json` 등 저장된 연계 데이터로 매핑 (없을 때만 API 호출 + 캐시 저장).
3. **판례·해석·위원회 인용**: `api_data/precedents/` 아래 키워드/이슈별 덤프에서 우선 검색; 없거나 부족할 때만 API 목록/본문 호출 후 결과를 cache 또는 precedents에 저장.
4. **용어 정의**: `api_data/terms/lstrmAI.json` 등 저장 데이터 우선; 없으면 API 호출 후 캐시.
5. **연관 조문**: `api_data/related/` 또는 `cache/aiRltLs/` 우선; 없으면 API 호출 후 캐시.
6. **지능형 검색** (aiSearch): 캐시에 있으면 사용, 없으면 1회 호출 후 cache/aiSearch/에 저장.

이렇게 하면 **상담 한 건당 API 호출은 최소화**되고, **저장할 수 있는 건 모두 api_data/와 cache/에 두어 API 의존도를 높이되 호출 빈도는 낮게** 유지할 수 있다.

---

## 5. config 설정 제안

`laws/` 제거 후 예시:

```python
# 법령/API 데이터 경로 (laws/ 제거, API 기반)
API_DATA_DIR = Path(__file__).resolve().parent / "api_data"
LAWS_DATA_DIR = API_DATA_DIR / "laws"       # 법령 본문 저장
TERMS_DATA_DIR = API_DATA_DIR / "terms"     # 용어·연계
PRECEDENTS_DATA_DIR = API_DATA_DIR / "precedents"
CACHE_DIR = API_DATA_DIR / "cache"

# 벡터 스토어는 api_data/laws 등에서 파싱한 텍스트로 구축
VECTOR_DIR = Path(__file__).resolve().parent / "vector_store"
```

- 기존 `LAWS_DIR`, `SOURCE_LAW` 등은 **api_data 기반**으로 바꾸거나, `LAWS_DATA_DIR`에서 읽은 법령명을 소스로 사용하도록 단계적으로 이전.

---

## 6. 요약

| 구분 | 내용 |
|------|------|
| **laws/ 제거** | 예정대로 삭제하고, 모든 법령·판례·해석 등은 API 유입분만 사용. |
| **저장** | 법령·행정규칙·별표·서식·용어·연계·판례·해석·위원회 → `api_data/` 아래 주기 동기화. |
| **캐시** | aiSearch, aiRltLs 등 온디맨드 호출 결과는 쿼리/조문 키 기준으로 `api_data/cache/` 저장. |
| **상담 시** | 저장·캐시 우선 사용, 부족할 때만 API 호출 후 결과 저장. |
| **의존도** | 데이터는 전부 API에서 오지만, **호출 빈도는 동기화·캐시로 낮게 유지**. |

이 전략으로 두면 API 의존도를 높이면서도 호출이 잦지 않게 할 수 있다.
