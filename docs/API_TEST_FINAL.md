# API 테스트 최종 결과

**OC 키**: `xognl427`  
**테스트 완료일**: 2026-02-13

## ✅ 최종 결과

| 구분 | 개수 |
|------|------|
| **총 API** | 25개 |
| **성공** | 25개 (100%) |

## 성공한 API (25개)

### 법령·행정규칙 (4개)
- ✅ 현행법령 목록 (`law`)
- ✅ 행정규칙 목록 (`admrul`)
- ✅ 법령 별표·서식 목록 (`licbyl`)
- ✅ 행정규칙 별표·서식 목록 (`admbyl`)

### 판례·해석·심판 (4개)
- ✅ 판례 목록 (`prec`)
- ✅ 헌재결정례 목록 (`detc`)
- ✅ 법령해석례 목록 (`expc`)
- ✅ 행정심판례 목록 (`decc`)

### 위원회 (5개)
- ✅ 개인정보보호위원회 (`ppc`)
- ✅ 공정거래위원회 (`ftc`)
- ✅ 노동위원회 (`nlrc`)
- ✅ 고용보험심사위원회 (`eiac`)
- ✅ 산업재해보상보험재심사위원회 (`iaciac`)

### 법령해석 (부처별) (3개)
- ✅ 고용노동부 법령해석 (`moelCgmExpc`)
- ✅ 법제처 법령해석 (`molegCgmExpc`)
- ✅ 법무부 법령해석 (`mojCgmExpc`)

### 지능형 법령정보지식베이스 (9개)
- ✅ 법령용어 조회 (`lstrmAI`)
- ✅ 일상용어 조회 (`dlytrm`)
- ✅ 관련법령 조회 (`lsRlt`)
- ✅ 지능형 검색 API (`aiSearch`)
- ✅ 연관법령 API (`aiRltLs`)
- ✅ 법령용어-일상용어 연계 (`lstrmRlt`)
- ✅ 일상용어-법령용어 연계 (`dlytrmRlt`)
- ✅ 법령용어-조문 연계 (`lstrmRltJo`)
- ✅ 조문-법령용어 연계 (`joRltLstrm`)

**참고**: 법령용어-조문 연계(`lstrmRltJo`)는 "임금"처럼 관련 조문이 매우 많은 검색어는 응답이 느릴 수 있음. 다른 용어로는 정상 작동.

## 중요 사항

### 브라우저 헤더 필요

모든 API 요청 시 브라우저 헤더를 포함해야 합니다:

```python
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'ko-KR,ko;q=0.9',
    'Referer': 'https://open.law.go.kr/',
}

response = requests.get(url, params=params, headers=headers, timeout=15)
```

**이유**: 서버가 봇으로 인식하여 접근을 거부할 수 있음

### 엔드포인트 구분

- **목록 조회**: `https://www.law.go.kr/DRF/lawSearch.do`
- **본문 조회**: `https://www.law.go.kr/DRF/lawService.do`
- **연계 API**: `lawService.do` 사용 (`lstrmRlt`, `dlytrmRlt`, `lstrmRltJo`, `joRltLstrm`)

## 결론

**25개 API 모두 정상 작동**합니다.

모든 API가 제대로 신청되어 있었고, 문제는 브라우저 헤더가 없어서 서버가 봇으로 인식한 것이었습니다.
