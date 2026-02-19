# 국가법령정보 공동활용 API 스펙

## 기본 정보

- **API 키**: OC (사용자 이메일의 ID 부분)
  - 예: 이메일이 `g4c@korea.kr`이면 OC = `g4c`
  - 마이페이지에서 변경 가능: https://open.law.go.kr/LSO/usr/usrOcInfoMod.do

## 엔드포인트

- **목록 조회**: `https://www.law.go.kr/DRF/lawSearch.do`
- **본문 조회**: `https://www.law.go.kr/DRF/lawService.do`

## 공통 파라미터

| 파라미터 | 필수 | 설명 | 예시 |
|----------|------|------|------|
| OC | ✅ | 사용자 이메일의 ID 부분 | `g4c` |
| target | ✅ | 서비스 대상 (API 종류 코드) | `lstrmAI`, `prec`, `ftc` 등 |
| type | ✅ | 출력 형태 | `XML`, `JSON`, `HTML` |
| query | | 검색어 | `퇴직금` |
| display | | 결과 개수 (기본 20, 최대 100) | `50` |
| page | | 페이지 번호 (기본 1) | `1` |
| ID | (본문 조회 시) | 일련번호 | `228541` |

## 주요 API target 값

### 법령
- **현행법령(공포일) 목록**: `law` ✅
- **현행법령 본문**: `law` ✅
- **현행법령(시행일) 목록**: `eflaw` ✅
- **현행법령(시행일) 본문**: `eflaw` ✅
- **행정규칙 목록**: `admrul` ✅ (또는 `school`/`public`/`pi` 학칙/공단/공공기관)
- **행정규칙 본문**: `admrul` ✅ (또는 `school`/`public`/`pi`)
- **법령 별표·서식 목록**: `licbyl` ✅
- **행정규칙 별표·서식 목록**: `admbyl` ✅

### 판례·해석·심판
- **판례 목록**: `prec` ✅
- **판례 본문**: `prec` ✅
- **헌재결정례 목록**: `detc` ✅
- **헌재결정례 본문**: `detc` ✅
- **법령해석례 목록**: `expc` ✅
- **법령해석례 본문**: `expc` ✅
- **행정심판례 목록**: `decc` ✅
- **행정심판례 본문**: `decc` ✅

### 위원회 결정문
- **공정거래위원회**: `ftc` ✅
- **국민권익위원회**: `acr` ✅
- **개인정보보호위원회**: `ppc` ✅
- **노동위원회**: `nlrc` ✅
- **고용보험심사위원회**: `eiac` ✅
- **산업재해보상보험재심사위원회**: `iaciac` ✅

### 법령해석 (부처별)
- **고용노동부 목록**: `moelCgmExpc` ✅
- **고용노동부 본문**: `moelCgmExpc` ✅
- **법제처 목록**: `molegCgmExpc` ✅
- **법제처 본문**: `molegCgmExpc` ✅
- **법무부 목록**: `mojCgmExpc` ✅
- **법무부 본문**: `mojCgmExpc` ✅

### 지능형 법령정보지식베이스
- **법령용어 조회**: `lstrmAI` ✅
- **일상용어 조회**: `dlytrm` ✅
- **법령용어-일상용어 연계**: `lstrmRlt` ✅
- **일상용어-법령용어 연계**: `dlytrmRlt` ✅
- **법령용어-조문 연계**: `lstrmRltJo` ✅
- **조문-법령용어 연계**: `joRltLstrm` ✅
- **관련법령 조회**: `lsRlt` ✅
- **지능형 검색 API**: `aiSearch` ✅
- **연관법령 API**: `aiRltLs` ✅

## 샘플 요청

### 현행법령(공포일) 목록 조회 (JSON)
```
https://www.law.go.kr/DRF/lawSearch.do?OC=test&target=law&type=JSON&query=근로기준법
```

### 판례 목록 조회 (JSON)
```
https://www.law.go.kr/DRF/lawSearch.do?OC=test&target=prec&type=JSON&query=퇴직금
```

### 판례 본문 조회 (JSON)
```
https://www.law.go.kr/DRF/lawService.do?OC=test&target=prec&ID=228541&type=JSON
```

### 법제처 법령해석 목록 조회 (JSON)
```
https://www.law.go.kr/DRF/lawSearch.do?OC=test&target=molegCgmExpc&type=JSON&query=근로기준법
```

### 법제처 법령해석 본문 조회 (JSON)
```
https://www.law.go.kr/DRF/lawService.do?OC=test&target=molegCgmExpc&ID=427778&type=JSON
```

### 법령해석례 목록 조회 (JSON)
```
https://www.law.go.kr/DRF/lawSearch.do?OC=test&target=expc&type=JSON&query=근로기준법
```

### 법령해석례 본문 조회 (JSON)
```
https://www.law.go.kr/DRF/lawService.do?OC=test&target=expc&ID=330471&type=JSON
```

### 위원회 결정문 본문 조회 (XML)
```
https://www.law.go.kr/DRF/lawService.do?OC=test&target=ftc&ID=331&type=XML
```

### 법령용어 조회 (JSON)
```
https://www.law.go.kr/DRF/lawSearch.do?OC=test&target=lstrmAI&type=JSON&query=임금
```

## 응답 형식

- **JSON**: `type=JSON` 지정 시 JSON 응답
- **XML**: `type=XML` 지정 시 XML 응답
- **HTML**: `type=HTML` 지정 시 HTML 응답 (일부 API만 지원)

## API별 상세 스펙

### 1. 현행법령(공포일) 목록 조회 API

**요청 URL**: `http://www.law.go.kr/DRF/lawSearch.do?target=law`

**요청변수**:
| 요청변수 | 필수 | 설명 |
|---------|------|------|
| OC | ✅ | 사용자 이메일의 ID |
| target | ✅ | `law` |
| type | ✅ | `HTML`/`XML`/`JSON` |
| search | | 검색범위 (1: 법령명 기본, 2: 본문검색) |
| query | | 검색어 |
| display | | 결과 개수 (기본 20, 최대 100) |
| page | | 페이지 번호 (기본 1) |
| sort | | 정렬옵션 (lasc/ldes/dasc/ddes/nasc/ndes/efasc/efdes) |
| date | | 공포일자 검색 |
| efYd | | 시행일자 범위 검색 (20090101~20090130) |
| ancYd | | 공포일자 범위 검색 (20090101~20090130) |
| ancNo | | 공포번호 범위 검색 (306~400) |
| rrClsCd | | 법령 제개정 종류 (300201-제정, 300202-일부개정 등) |
| nb | | 공포번호 검색 |
| org | | 소관부처별 검색 (소관부처코드) |
| knd | | 법령종류 (코드제공) |
| lsChapNo | | 법령분류 (01-제1편, 02-제2편 등) |
| gana | | 사전식 검색 (ga,na,da 등) |
| popYn | | 팝업창 여부 (`Y` 지정 시) |

**출력 필드**:
- target, 키워드, section, totalCnt, page, law id
- 법령일련번호, 현행연혁코드, 법령명한글, 법령약칭명, 법령ID
- 공포일자, 공포번호, 제개정구분명, 소관부처명, 소관부처코드
- 법령구분명, 공동부령구분, 시행일자, 자법타법여부, 법령상세링크

---

### 2. 판례 목록 조회 API

**요청 URL**: `http://www.law.go.kr/DRF/lawSearch.do?target=prec`

**요청변수**:
| 요청변수 | 필수 | 설명 |
|---------|------|------|
| OC | ✅ | 사용자 이메일의 ID |
| target | ✅ | `prec` |
| type | ✅ | `HTML`/`XML`/`JSON` |
| search | | 검색범위 (1: 판례명 기본, 2: 본문검색) |
| query | | 검색어 |
| display | | 결과 개수 (기본 20, 최대 100) |
| page | | 페이지 번호 (기본 1) |
| org | | 법원종류 (대법원:400201, 하위법원:400202) |
| curt | | 법원명 (대법원, 서울고등법원 등) |
| JO | | 참조법령명 (형법, 민법 등) |
| gana | | 사전식 검색 |
| sort | | 정렬옵션 (lasc/ldes/dasc/ddes/nasc/ndes) |
| date | | 선고일자 |
| prncYd | | 선고일자 범위 검색 (20090101~20090130) |
| nb | | 사건번호 |
| datSrcNm | | 데이터출처명 (국세법령정보시스템, 근로복지공단산재판례, 대법원 등) |
| popYn | | 팝업창 여부 |

**출력 필드**:
- target, 공포번호, 키워드, section, totalCnt, page, prec id
- 판례일련번호, 사건명, 사건번호, 선고일자, 법원명, 법원종류코드
- 사건종류명, 사건종류코드, 판결유형, 선고, 데이터출처명, 판례상세링크

---

### 3. 법제처 법령해석 목록 조회 API

**요청 URL**: `http://www.law.go.kr/DRF/lawSearch.do?target=molegCgmExpc`

**요청변수**:
| 요청변수 | 필수 | 설명 |
|---------|------|------|
| OC | ✅ | 사용자 이메일의 ID |
| target | ✅ | `molegCgmExpc` |
| type | ✅ | `HTML`/`XML`/`JSON` |
| search | | 검색범위 (1: 법령해석명 기본, 2: 본문검색) |
| query | | 검색어 |
| display | | 결과 개수 (기본 20, 최대 100) |
| page | | 페이지 번호 (기본 1) |
| inq | | 질의기관코드 |
| rpl | | 해석기관코드 |
| gana | | 사전식 검색 |
| itmno | | 안건번호 (지정 시 query 무시) |
| explYd | | 해석일자 검색 (20090101~20090130) |
| sort | | 정렬옵션 (lasc/ldes/dasc/ddes/nasc/ndes) |
| popYn | | 팝업창 여부 |
| fields | | 응답항목 옵션 (HTML일 경우 적용 불가) |

**출력 필드**:
- target, 키워드, section, totalCnt, page, id
- 법령해석일련번호, 안건명, 안건번호, 질의기관코드, 질의기관명
- 해석기관코드, 해석기관명, 해석일자, 데이터기준일시, 법령해석상세링크

---

### 3-1. 판례 본문 조회 API

**요청 URL**: `http://www.law.go.kr/DRF/lawService.do?target=prec`

**요청변수**:
| 요청변수 | 필수 | 설명 |
|---------|------|------|
| OC | ✅ | 사용자 이메일의 ID |
| target | ✅ | `prec` |
| type | ✅ | `HTML`/`XML`/`JSON` (국세청 판례는 HTML만 가능) |
| ID | ✅ | 판례 일련번호 |
| LM | | 판례명 |

**출력 필드**:
- 판례정보일련번호, 사건명, 사건번호, 선고일자, 선고, 법원명, 법원종류코드
- 사건종류명, 사건종류코드, 판결유형, 판시사항, 판결요지
- 참조조문, 참조판례, 판례내용

---

### 3-2. 법제처 법령해석 본문 조회 API

**요청 URL**: `http://www.law.go.kr/DRF/lawService.do?target=molegCgmExpc`

**요청변수**:
| 요청변수 | 필수 | 설명 |
|---------|------|------|
| OC | ✅ | 사용자 이메일의 ID |
| target | ✅ | `molegCgmExpc` |
| type | ✅ | `HTML`/`XML`/`JSON` |
| ID | ✅ | 법령해석일련번호 |
| LM | | 법령해석명 |
| fields | | 응답항목 옵션 (HTML일 경우 적용 불가) |

**출력 필드**:
- 법령해석일련번호, 안건명, 안건번호, 해석일자, 해석기관코드, 해석기관명
- 질의기관코드, 질의기관명, 관리기관코드, 등록일시
- 질의요지, 회답, 이유, 관련법령, 데이터기준일시

---

### 4. 행정규칙(학칙공단공공기관) 목록 조회 API

**요청 URL**: `http://www.law.go.kr/DRF/lawSearch.do?target=school` (또는 `public`, `pi`)

**요청변수**:
| 요청변수 | 필수 | 설명 |
|---------|------|------|
| OC | ✅ | 사용자 이메일의 ID |
| target | ✅ | `school`(대학) / `public`(지방공사공단) / `pi`(공공기관) |
| type | ✅ | `HTML`/`XML`/`JSON` |
| nw | | 현행/연혁 (1: 현행, 2: 연혁, 기본값: 현행) |
| search | | 검색범위 (1: 규정명 기본, 2: 본문검색) |
| query | | 검색어 |
| display | | 결과 개수 (기본 20, 최대 100) |
| page | | 페이지 번호 (기본 1) |
| knd | | 학칙공단 종류별 검색 (1: 학칙, 2: 학교규정 등) |
| rrClsCd | | 제정·개정 구분 (200401: 제정, 200402: 전부개정 등) |
| date | | 발령일자 검색 |
| prmlYd | | 발령일자 범위 검색 |
| nb | | 발령번호 검색 |
| gana | | 사전식 검색 |
| sort | | 정렬옵션 (lasc/ldes/dasc/ddes/nasc/ndes) |
| popYn | | 팝업창 여부 |

**출력 필드**:
- target, 키워드, section, totalCnt, page, numOfRows, resultCode, resultMsg, admrul id
- 행정규칙일련번호, 행정규칙명, 행정규칙종류, 발령일자, 발령번호
- 소관부처명, 현행연혁구분, 제개정구분코드, 제개정구분명
- 법령분류코드, 법령분류명, 행정규칙ID, 행정규칙상세링크, 시행일자, 생성일자

---

### 5. 행정규칙(학칙공단공공기관) 본문 조회 API

**요청 URL**: `http://www.law.go.kr/DRF/lawService.do?target=school` (또는 `public`, `pi`)

**요청변수**:
| 요청변수 | 필수 | 설명 |
|---------|------|------|
| OC | ✅ | 사용자 이메일의 ID |
| target | ✅ | `school` / `public` / `pi` |
| type | ✅ | `HTML`/`XML`/`JSON` |
| ID | | 행정규칙 일련번호 |
| LID | | 행정규칙 ID |
| LM | | 행정규칙명 (정확한 이름 입력) |

**출력 필드**:
- 행정규칙일련번호, 행정규칙명, 행정규칙종류, 행정규칙종류코드
- 발령일자, 발령번호, 제개정구분명, 제개정구분코드, 조문형식여부
- 행정규칙ID, 소관부처명, 소관부처코드, 담당부서기관코드, 담당부서기관명
- 담당자명, 전화번호, 현행여부, 생성일자, 조문내용
- 부칙공포일자, 부칙공포번호, 부칙내용
- 별표단위 별표키, 별표번호, 별표가지번호, 별표구분, 별표제목, 별표서식파일링크
- 개정문내용, 제개정이유내용

---

### 6. 행정규칙 목록 조회 API

**요청 URL**: `http://www.law.go.kr/DRF/lawSearch.do?target=admrul`

**요청변수**:
| 요청변수 | 필수 | 설명 |
|---------|------|------|
| OC | ✅ | 사용자 이메일의 ID |
| target | ✅ | `admrul` |
| type | ✅ | `HTML`/`XML`/`JSON` |
| nw | | 현행/연혁 (1: 현행, 2: 연혁, 기본값: 현행) |
| search | | 검색범위 (1: 행정규칙명 기본, 2: 본문검색) |
| query | | 검색어 |
| display | | 결과 개수 (기본 20, 최대 100) |
| page | | 페이지 번호 (기본 1) |
| org | | 소관부처별 검색 (코드별도제공) |
| knd | | 행정규칙 종류별 검색 (1=훈령/2=예규/3=고시/4=공고/5=지침/6=기타) |
| gana | | 사전식 검색 |
| sort | | 정렬옵션 (lasc/ldes/dasc/ddes/nasc/ndes/efasc/efdes) |
| date | | 발령일자 검색 |
| prmlYd | | 발령일자 기간검색 (20090101~20090130) |
| modYd | | 수정일자 기간검색 (20090101~20090130) |
| nb | | 발령번호 검색 (예: 제2023-8호 검색 시 nb=20238) |
| popYn | | 팝업창 여부 |

**출력 필드**:
- target, 키워드, section, totalCnt, page, admrul id
- 행정규칙일련번호, 행정규칙명, 행정규칙종류, 발령일자, 발령번호
- 소관부처명, 현행연혁구분, 제개정구분코드, 제개정구분명
- 행정규칙ID, 행정규칙상세링크, 시행일자, 생성일자

---

### 7. 행정규칙 본문 조회 API

**요청 URL**: `http://www.law.go.kr/DRF/lawService.do?target=admrul`

**요청변수**:
| 요청변수 | 필수 | 설명 |
|---------|------|------|
| OC | ✅ | 사용자 이메일의 ID |
| target | ✅ | `admrul` |
| type | ✅ | `HTML`/`XML`/`JSON` |
| ID | | 행정규칙 일련번호 |
| LID | | 행정규칙 ID |
| LM | | 행정규칙명 (정확한 이름 입력) |

**출력 필드**:
- 행정규칙일련번호, 행정규칙명, 행정규칙종류, 행정규칙종류코드
- 발령일자, 발령번호, 제개정구분명, 제개정구분코드, 조문형식여부
- 행정규칙ID, 소관부처명, 소관부처코드, 상위부처명
- 담당부서기관코드, 담당부서기관명, 담당자명, 전화번호
- 현행여부, 시행일자, 생성일자, 조문내용
- 부칙, 부칙공포일자, 부칙공포번호, 부칙내용
- 별표, 별표번호, 별표가지번호, 별표구분, 별표제목
- 별표서식파일링크, 별표서식PDF파일링크, 별표내용

---

### 8. 헌재결정례 목록 조회 API

**요청 URL**: `http://www.law.go.kr/DRF/lawSearch.do?target=detc`

**요청변수**:
| 요청변수 | 필수 | 설명 |
|---------|------|------|
| OC | ✅ | 사용자 이메일의 ID |
| target | ✅ | `detc` |
| type | ✅ | `HTML`/`XML`/`JSON` |
| search | | 검색범위 (1: 헌재결정례명 기본, 2: 본문검색) |
| query | | 검색어 |
| display | | 결과 개수 (기본 20, 최대 100) |
| page | | 페이지 번호 (기본 1) |
| gana | | 사전식 검색 |
| sort | | 정렬옵션 (lasc/ldes/dasc/ddes/nasc/ndes/efasc/efdes) |
| date | | 종국일자 |
| edYd | | 종국일자 기간 검색 |
| nb | | 사건번호 |
| popYn | | 팝업창 여부 |

**출력 필드**:
- target, 키워드, section, totalCnt, page, detc id
- 헌재결정례일련번호, 종국일자, 사건번호, 사건명, 헌재결정례상세링크

---

### 9. 헌재결정례 본문 조회 API

**요청 URL**: `http://www.law.go.kr/DRF/lawService.do?target=detc`

**요청변수**:
| 요청변수 | 필수 | 설명 |
|---------|------|------|
| OC | ✅ | 사용자 이메일의 ID |
| target | ✅ | `detc` |
| type | ✅ | `HTML`/`XML`/`JSON` |
| ID | ✅ | 헌재결정례 일련번호 |
| LM | | 헌재결정례명 |

**출력 필드**:
- 헌재결정례일련번호, 종국일자, 사건번호, 사건명, 사건종류명, 사건종류코드
- 재판부구분코드 (전원재판부:430201, 지정재판부:430202)
- 판시사항, 결정요지, 전문, 참조조문, 참조판례, 심판대상조문

---

### 10. 법령해석례 목록 조회 API

**요청 URL**: `http://www.law.go.kr/DRF/lawSearch.do?target=expc`

**요청변수**:
| 요청변수 | 필수 | 설명 |
|---------|------|------|
| OC | ✅ | 사용자 이메일의 ID |
| target | ✅ | `expc` |
| type | ✅ | `HTML`/`XML`/`JSON` |
| search | | 검색범위 (1: 법령해석례명 기본, 2: 본문검색) |
| query | | 검색어 |
| display | | 결과 개수 (기본 20, 최대 100) |
| page | | 페이지 번호 (기본 1) |
| inq | | 질의기관 |
| rpl | | 회신기관 |
| gana | | 사전식 검색 |
| itmno | | 안건번호 (예: 13-0217 검색 시 itmno=130217) |
| regYd | | 등록일자 검색 (20090101~20090130) |
| explYd | | 해석일자 검색 (20090101~20090130) |
| sort | | 정렬옵션 (lasc/ldes/dasc/ddes/nasc/ndes) |
| popYn | | 팝업창 여부 |

**출력 필드**:
- target, 키워드, section, totalCnt, page, expc id
- 법령해석례일련번호, 안건명, 안건번호
- 질의기관코드, 질의기관명, 회신기관코드, 회신기관명, 회신일자
- 법령해석례상세링크

---

### 11. 법령해석례 본문 조회 API

**요청 URL**: `http://www.law.go.kr/DRF/lawService.do?target=expc`

**요청변수**:
| 요청변수 | 필수 | 설명 |
|---------|------|------|
| OC | ✅ | 사용자 이메일의 ID |
| target | ✅ | `expc` |
| type | ✅ | `HTML`/`XML`/`JSON` |
| ID | ✅ | 법령해석례 일련번호 |
| LM | | 법령해석례명 |

**출력 필드**:
- 법령해석례일련번호, 안건명, 안건번호, 해석일자
- 해석기관코드, 해석기관명, 질의기관코드, 질의기관명
- 관리기관코드, 등록일시
- 질의요지, 회답, 이유

---

## 확인 완료 항목 (체크한 항목만)

### 현행법령 본문 조회 API ✅

**요청 URL**: `http://www.law.go.kr/DRF/lawService.do?target=law`

**요청변수**:
| 요청변수 | 필수 | 설명 |
|---------|------|------|
| OC | ✅ | 사용자 이메일의 ID |
| target | ✅ | `law` |
| type | ✅ | `HTML`/`XML`/`JSON` |
| ID | | 법령 ID (ID 또는 MST 중 하나 필수) |
| MST | | 법령 마스터 번호 (ID 또는 MST 중 하나 필수) |
| LM | | 법령명 |
| LD | | 공포일자 |
| LN | | 공포번호 |
| JO | | 조번호 (생략 시 모든 조 표시, 6자리: 조번호4자리+조가지번호2자리) |
| LANG | | 원문/한글 여부 (KO: 한글, ORI: 원문) |

**출력 필드**: 법령ID, 공포일자, 공포번호, 법령명_한글, 법령명_한자, 법령명약칭, 소관부처명, 소관부처코드, 시행일자, 조문번호, 조문가지번호, 조문제목, 조문내용, 항번호, 항내용, 호번호, 호내용, 목번호, 목내용, 부칙내용, 별표번호, 별표내용 등

---

### 노동위원회 결정문 목록 조회 API ✅

**요청 URL**: `http://www.law.go.kr/DRF/lawSearch.do?target=nlrc`

**요청변수**:
| 요청변수 | 필수 | 설명 |
|---------|------|------|
| OC | ✅ | 사용자 이메일의 ID |
| target | ✅ | `nlrc` |
| type | ✅ | `HTML`/`XML`/`JSON` |
| search | | 검색범위 (1: 제목 기본, 2: 본문검색) |
| query | | 검색어 |
| display | | 결과 개수 (기본 20, 최대 100) |
| page | | 페이지 번호 (기본 1) |
| gana | | 사전식 검색 |
| sort | | 정렬옵션 (lasc/ldes/dasc/ddes/nasc/ndes) |
| popYn | | 팝업창 여부 |

**출력 필드**: target, 키워드, section, totalCnt, page, 기관명, nlrc id, 결정문일련번호, 제목, 사건번호, 등록일, 결정문상세링크

---

### 노동위원회 결정문 본문 조회 API ✅

**요청 URL**: `http://www.law.go.kr/DRF/lawService.do?target=nlrc`

**요청변수**: `OC`, `target`, `type`, `ID` (결정문 일련번호)

---

### 고용보험심사위원회 결정문 목록 조회 API ✅

**요청 URL**: `http://www.law.go.kr/DRF/lawSearch.do?target=eiac`

**요청변수**:
| 요청변수 | 필수 | 설명 |
|---------|------|------|
| OC | ✅ | 사용자 이메일의 ID |
| target | ✅ | `eiac` |
| type | ✅ | `HTML`/`XML`/`JSON` |
| search | | 검색범위 (1: 사건명 기본, 2: 본문검색) |
| query | | 검색어 |
| display | | 결과 개수 (기본 20, 최대 100) |
| page | | 페이지 번호 (기본 1) |
| gana | | 사전식 검색 |
| sort | | 정렬옵션 (lasc/ldes/dasc/ddes/nasc/ndes) |
| popYn | | 팝업창 여부 |

**출력 필드**: target, 키워드, section, totalCnt, page, 기관명, eiac id, 결정문일련번호, 사건명, 사건번호, 의결일자, 결정문상세링크

---

### 고용보험심사위원회 결정문 본문 조회 API ✅

**요청 URL**: `http://www.law.go.kr/DRF/lawService.do?target=eiac`

**요청변수**: `OC`, `target`, `type`, `ID` (결정문 일련번호)

---

### 산업재해보상보험재심사위원회 결정문 목록 조회 API ✅

**요청 URL**: `http://www.law.go.kr/DRF/lawSearch.do?target=iaciac`

**요청변수**:
| 요청변수 | 필수 | 설명 |
|---------|------|------|
| OC | ✅ | 사용자 이메일의 ID |
| target | ✅ | `iaciac` |
| type | ✅ | `HTML`/`XML`/`JSON` |
| search | | 검색범위 (1: 사건 기본, 2: 본문검색) |
| query | | 검색어 |
| display | | 결과 개수 (기본 20, 최대 100) |
| page | | 페이지 번호 (기본 1) |
| gana | | 사전식 검색 |
| sort | | 정렬옵션 (lasc/ldes/dasc/ddes/nasc/ndes) |
| popYn | | 팝업창 여부 |

**출력 필드**: target, 키워드, section, totalCnt, page, 기관명, iaciac id, 결정문일련번호, 사건, 사건번호, 의결일자, 결정문상세링크

---

### 산업재해보상보험재심사위원회 결정문 본문 조회 API ✅

**요청 URL**: `http://www.law.go.kr/DRF/lawService.do?target=iaciac`

**요청변수**: `OC`, `target`, `type`, `ID` (결정문 일련번호)

---

### 고용노동부 법령해석 목록 조회 API ✅

**요청 URL**: `http://www.law.go.kr/DRF/lawSearch.do?target=moelCgmExpc`

**요청변수**:
| 요청변수 | 필수 | 설명 |
|---------|------|------|
| OC | ✅ | 사용자 이메일의 ID |
| target | ✅ | `moelCgmExpc` |
| type | ✅ | `HTML`/`XML`/`JSON` |
| search | | 검색범위 (1: 법령해석명 기본, 2: 본문검색) |
| query | | 검색어 |
| display | | 결과 개수 (기본 20, 최대 100) |
| page | | 페이지 번호 (기본 1) |
| inq | | 질의기관코드 |
| rpl | | 해석기관코드 |
| gana | | 사전식 검색 |
| itmno | | 안건번호 (지정 시 query 무시) |
| explYd | | 해석일자 검색 (20090101~20090130) |
| sort | | 정렬옵션 (lasc/ldes/dasc/ddes/nasc/ndes) |
| popYn | | 팝업창 여부 |
| fields | | 응답항목 옵션 (HTML일 경우 적용 불가) |

**출력 필드**: target, 키워드, section, totalCnt, page, id, 법령해석일련번호, 안건명, 안건번호, 질의기관코드, 질의기관명, 해석기관코드, 해석기관명, 해석일자, 데이터기준일시, 법령해석상세링크

---

### 고용노동부 법령해석 본문 조회 API ✅

**요청 URL**: `http://www.law.go.kr/DRF/lawService.do?target=moelCgmExpc`

**요청변수**: `OC`, `target`, `type`, `ID` (법령해석일련번호), `LM`, `fields`

---

### 법무부 법령해석 목록 조회 API ✅

**요청 URL**: `http://www.law.go.kr/DRF/lawSearch.do?target=mojCgmExpc`

**요청변수**: 고용노동부와 동일 (target만 `mojCgmExpc`)

**출력 필드**: 고용노동부와 동일

---

### 법무부 법령해석 본문 조회 API ✅

**요청 URL**: `http://www.law.go.kr/DRF/lawService.do?target=mojCgmExpc`

**요청변수**: `OC`, `target`, `type`, `ID` (법령해석일련번호), `LM`, `fields`

---

### 행정심판례 목록 조회 API ✅

**요청 URL**: `http://www.law.go.kr/DRF/lawSearch.do?target=decc`

**요청변수**:
| 요청변수 | 필수 | 설명 |
|---------|------|------|
| OC | ✅ | 사용자 이메일의 ID |
| target | ✅ | `decc` |
| type | ✅ | `HTML`/`XML`/`JSON` |
| search | | 검색범위 (1: 행정심판례명 기본, 2: 본문검색) |
| query | | 검색어 |
| display | | 결과 개수 (기본 20, 최대 100) |
| page | | 페이지 번호 (기본 1) |
| cls | | 재결례유형 (재결구분코드) |
| gana | | 사전식 검색 |
| date | | 의결일자 |
| dpaYd | | 처분일자 검색 (20090101~20090130) |
| rslYd | | 의결일자 검색 (20090101~20090130) |
| sort | | 정렬옵션 (lasc/ldes/dasc/ddes/nasc/ndes) |
| popYn | | 팝업창 여부 |

**출력 필드**: target, 키워드, section, totalCnt, page, decc id, 행정심판재결례일련번호, 사건명, 사건번호, 처분일자, 의결일자, 처분청, 재결청, 재결구분명, 재결구분코드, 행정심판례상세링크

---

### 행정심판례 본문 조회 API ✅

**요청 URL**: `http://www.law.go.kr/DRF/lawService.do?target=decc`

**요청변수**: `OC`, `target`, `type`, `ID` (행정심판재결례 일련번호)

---

### 법령 별표·서식 목록 조회 API ✅

**요청 URL**: `http://www.law.go.kr/DRF/lawSearch.do?target=licbyl`

**요청변수**:
| 요청변수 | 필수 | 설명 |
|---------|------|------|
| OC | ✅ | 사용자 이메일의 ID |
| target | ✅ | `licbyl` |
| type | ✅ | `HTML`/`XML`/`JSON` |
| search | | 검색범위 (1: 별표서식명 기본, 2: 해당법령검색, 3: 별표본문검색) |
| query | | 검색어 (default=*) |
| display | | 결과 개수 (기본 20, 최대 100) |
| page | | 페이지 번호 (기본 1) |
| sort | | 정렬옵션 (lasc/ldes) |
| org | | 소관부처별 검색 (소관부처코드, 2개 이상 가능, ","로 구분) |
| mulOrg | | 소관부처 다중 검색 조건 (OR: OR검색 기본, AND: AND검색) |
| knd | | 별표종류 (1: 별표, 2: 서식, 3: 별지, 4: 별도, 5: 부록) |
| gana | | 사전식 검색 |
| popYn | | 팝업창 여부 |

**출력 필드**: target, 키워드, section, totalCnt, page, licbyl id, 별표일련번호, 관련법령일련번호, 관련법령ID, 별표명, 관련법령명, 별표번호, 별표종류, 소관부처명, 공포일자, 공포번호, 제개정구분명, 법령종류, 별표서식파일링크, 별표서식PDF파일링크, 별표법령상세링크

---

### 행정규칙 별표·서식 목록 조회 API ✅

**요청 URL**: `http://www.law.go.kr/DRF/lawSearch.do?target=admbyl`

**요청변수**:
| 요청변수 | 필수 | 설명 |
|---------|------|------|
| OC | ✅ | 사용자 이메일의 ID |
| target | ✅ | `admbyl` |
| type | ✅ | `HTML`/`XML`/`JSON` |
| search | | 검색범위 (1: 별표서식명 기본, 2: 해당법령검색, 3: 별표본문검색) |
| query | | 검색어 (default=*) |
| display | | 결과 개수 (기본 20, 최대 100) |
| page | | 페이지 번호 (기본 1) |
| sort | | 정렬옵션 (lasc/ldes) |
| org | | 소관부처별 검색 (소관부처코드) |
| knd | | 별표종류 (1: 별표, 2: 서식, 3: 별지) |
| gana | | 사전식 검색 |
| popYn | | 팝업창 여부 |

**출력 필드**: target, 키워드, section, totalCnt, page, admrulbyl id, 별표일련번호, 관련행정규칙일련번호, 별표명, 관련행정규칙명, 별표번호, 별표종류, 소관부처명, 발령일자, 발령번호, 관련법령ID, 행정규칙종류, 별표서식파일링크, 별표행정규칙상세링크

### 지능형 법령정보지식베이스 ✅ (모두 확인 완료)

#### 일상용어 조회 API ✅

**요청 URL**: `https://www.law.go.kr/DRF/lawSearch.do?target=dlytrm`

**요청변수**:
| 요청변수 | 필수 | 설명 |
|---------|------|------|
| OC | ✅ | 사용자 이메일의 ID |
| target | ✅ | `dlytrm` |
| type | ✅ | `XML`/`JSON` (HTML 미지원) |
| query | | 일상용어명 검색어 |
| display | | 결과 개수 (기본 20, 최대 100) |
| page | | 페이지 번호 (기본 1) |

**출력 필드**: target, 키워드, 검색결과개수, section, page, numOfRows, 일상용어 id, 일상용어명, 출처, 용어간관계링크

---

#### 법령용어-일상용어 연계 API ✅

**요청 URL**: `https://www.law.go.kr/DRF/lawService.do?target=lstrmRlt`

**요청변수**:
| 요청변수 | 필수 | 설명 |
|---------|------|------|
| OC | ✅ | 사용자 이메일의 ID |
| target | ✅ | `lstrmRlt` |
| type | ✅ | `XML`/`JSON` |
| query | | 법령용어명 (query 또는 MST 중 하나 필수) |
| MST | | 법령용어명 일련번호 (query 또는 MST 중 하나 필수) |
| trmRltCd | | 용어관계 코드 (140301: 동의어, 140302: 반의어, 140303: 상위어, 140304: 하위어, 140305: 연관어) |

**출력 필드**: target, 키워드, 검색결과개수, 법령용어 id, 법령용어명, 비고, 연계용어 id, 일상용어명, 용어관계코드, 용어관계, 일상용어조회링크, 용어간관계링크

---

#### 일상용어-법령용어 연계 API ✅

**요청 URL**: `https://www.law.go.kr/DRF/lawService.do?target=dlytrmRlt`

**요청변수**:
| 요청변수 | 필수 | 설명 |
|---------|------|------|
| OC | ✅ | 사용자 이메일의 ID |
| target | ✅ | `dlytrmRlt` |
| type | ✅ | `XML`/`JSON` |
| query | | 일상용어명 (query 또는 MST 중 하나 필수) |
| MST | | 일상용어명 일련번호 (query 또는 MST 중 하나 필수) |
| trmRltCd | | 용어관계 코드 (동의어/반의어/상위어/하위어/연관어) |

**출력 필드**: target, 키워드, 검색결과개수, 일상용어명, 출처, 연계용어 id, 법령용어명, 비고, 용어관계코드, 용어관계, 용어간관계링크, 조문간관계링크

---

#### 법령용어-조문 연계 API ✅

**요청 URL**: `https://www.law.go.kr/DRF/lawService.do?target=lstrmRltJo`

**요청변수**:
| 요청변수 | 필수 | 설명 |
|---------|------|------|
| OC | ✅ | 사용자 이메일의 ID |
| target | ✅ | `lstrmRltJo` |
| type | ✅ | `XML`/`JSON` |
| query | ✅ | 법령용어명 |

**출력 필드**: target, 키워드, 검색결과개수, 법령용어 id, 법령용어명, 비고, 용어간관계링크, 연계법령 id, 법령명, 조번호, 조가지번호, 조문내용, 용어구분코드, 용어구분, 조문연계용어링크

---

#### 조문-법령용어 연계 API ✅

**요청 URL**: `https://www.law.go.kr/DRF/lawService.do?target=joRltLstrm`

**요청변수**:
| 요청변수 | 필수 | 설명 |
|---------|------|------|
| OC | ✅ | 사용자 이메일의 ID |
| target | ✅ | `joRltLstrm` |
| type | ✅ | `XML`/`JSON` |
| query | | 법령명 (query 또는 ID 중 하나 필수) |
| ID | | 법령 ID (query 또는 ID 중 하나 필수) |
| JO | ✅ | 조번호 (6자리: 조번호4자리+조가지번호2자리, 예: 000200=2조, 000202=제2조의2) |

**출력 필드**: target, 키워드, 검색결과개수, 법령조문 id, 법령명, 조번호, 조가지번호, 조문내용, 연계용어 id, 법령용어명, 비고, 용어구분코드, 용어구분, 용어간관계링크, 용어연계조문링크

---

#### 관련법령 조회 API ✅

**요청 URL**: `https://www.law.go.kr/DRF/lawSearch.do?target=lsRlt`

**요청변수**:
| 요청변수 | 필수 | 설명 |
|---------|------|------|
| OC | ✅ | 사용자 이메일의 ID |
| target | ✅ | `lsRlt` |
| type | ✅ | `XML`/`JSON` |
| query | | 기준법령명 |
| ID | | 법령 ID |
| lsRltCd | | 법령 간 관계 코드 |

**출력 필드**: target, 키워드, 검색결과개수, 기준법령ID, 기준법령명, 기준법령상세링크, 관련법령 id, 관련법령ID, 관련법령명, 법령간관계코드, 법령간관계, 관련법령상세링크, 관련법령조회링크

---

#### 지능형 검색 API ✅

**요청 URL**: `https://www.law.go.kr/DRF/lawSearch.do?target=aiSearch`

**요청변수**:
| 요청변수 | 필수 | 설명 |
|---------|------|------|
| OC | ✅ | 사용자 이메일의 ID |
| target | ✅ | `aiSearch` |
| type | ✅ | `XML`/`JSON` (HTML 미지원) |
| search | | 법령분류 (0: 법령조문, 1: 법령별표·서식, 2: 행정규칙조문, 3: 행정규칙별표·서식) |
| query | | 검색어 |
| display | | 결과 개수 (기본 20) |
| page | | 페이지 번호 (기본 1) |

**출력 필드**: target, 키워드, 검색결과개수, 법령조문ID, 법령ID, 법령일련번호, 법령명, 시행일자, 공포일자, 공포번호, 소관부처코드, 소관부처명, 법령종류명, 제개정구분명, 법령편장절관코드, 조문일련번호, 조문번호, 조문가지번호, 조문제목, 조문내용, 법령별표서식ID, 별표서식일련번호, 별표서식번호, 별표서식가지번호, 별표서식제목, 별표서식구분코드, 별표서식구분명, 행정규칙조문ID, 행정규칙일련번호, 행정규칙ID, 행정규칙명, 발령일자, 발령번호, 시행일자, 발령기관명, 행정규칙종류명, 제개정구분명, 조문일련번호, 조문번호, 조문가지번호, 조문제목, 조문내용, 행정규칙별표서식ID, 별표서식일련번호, 별표서식번호, 별표서식가지번호, 별표서식제목, 별표서식구분코드, 별표서식구분명

---

#### 연관법령 API ✅

**요청 URL**: `https://www.law.go.kr/DRF/lawSearch.do?target=aiRltLs`

**요청변수**:
| 요청변수 | 필수 | 설명 |
|---------|------|------|
| OC | ✅ | 사용자 이메일의 ID |
| target | ✅ | `aiRltLs` |
| type | ✅ | `XML`/`JSON` (HTML 미지원) |
| search | | 법령분류 (0: 법령조문, 1: 행정규칙조문) |
| query | | 검색어 |

**출력 필드**: target, 키워드, 검색결과개수, 법령조문ID, 법령ID, 법령명, 시행일자, 공포일자, 공포번호, 조문번호, 조문가지번호, 조문제목, 행정규칙조문ID, 행정규칙ID, 행정규칙명, 발령일자, 발령번호, 조문번호, 조문가지번호, 조문제목

---

## 참고

- 각 API의 정확한 `target` 값과 상세 파라미터는 각 API의 상세 가이드 페이지에서 확인 필요.
- 상세 가이드: https://open.law.go.kr/LSO/openApi/guideList.do?p_target=law&p_gubun=search
- 각 API 항목 클릭 시 `guideResult.do?htmlName=...` 형태의 상세 페이지로 이동.
- 본문 조회 API는 대부분 `lawService.do` 엔드포인트 사용, `ID` 또는 `LID` 파라미터로 조회.
