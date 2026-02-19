# -*- coding: utf-8 -*-
"""
사법정보공개포털(판례 검색) 검색어 생성.
이슈·조문을 포털 검색 문법에 맞게 변환해, 유사 판례 검색 시 참고용으로 사용.

[포털 검색 문법 요약]
- 검색어: 판시사항, 판결요지, 전문에서 검색
  - "부동산" : 단어 존재
  - "부동산 & 채권" : 두 단어 동시 존재
  - "부동산 + 채권" : 둘 중 하나 이상 존재
  - "부동산 ! 채권" : 부동산 있음, 채권 없음
- 사건번호: 99도12345 등
- 사건명: 사건명 필드 검색
- 참조조문: "민법 제100조", "근로기준법 제34조" 등 (형태 무관)
  - "민법 제100조 & 민법 제200조" : 둘 다 참조
  - "민법 제100조 + 민법 제200조" : 둘 중 하나 참조
- 고급: 포함하는 단어, 제외하는 단어, 인접하는 단어(형태소 거리)

참고: https://portal.scourt.go.kr/pgp/index.on?m=PGP1011M01&l=N&c=900
"""
from typing import List, Optional

# 검색어 연산자
OP_AND = " & "   # 동시 존재
OP_OR = " + "    # 하나 이상 존재
OP_NOT = " ! "   # 앞은 있음, 뒤는 없음


def _normalize_article_for_ref(article: str) -> str:
    """'제34조' -> '근로기준법 제34조', '제36조(금품 청산)' -> '근로기준법 제36조'"""
    import re
    s = (article or "").strip()
    m = re.match(r"(제\d+(?:의\d+)?조)", s)
    num = m.group(1) if m else s
    if not num:
        return ""
    if "근로기준법" in s or "법" in s:
        return s.split("(")[0].strip()
    return f"근로기준법 {num}"


def build_precedent_search_keywords(
    issue: str,
    related_terms: Optional[List[str]] = None,
    mode: str = "and",
    max_terms: int = 5,
) -> str:
    """
    이슈 + 관련어로 '검색어' 필드용 문자열 생성.
    - mode "and": 이슈와 핵심 관련어를 & 로 연결 (정밀 검색)
    - mode "or": 이슈 + 관련어를 + 로 연결 (넓은 검색)
    """
    terms = [t for t in [issue.strip()] if t]
    if related_terms:
        # 2글자 이상, 이슈와 중복 제외
        seen = set(terms)
        for t in related_terms:
            t = (t or "").strip()
            if len(t) >= 2 and t not in seen and len(terms) < max_terms:
                terms.append(t)
                seen.add(t)
    if not terms:
        return ""
    if mode == "and" and len(terms) > 1:
        return OP_AND.join(terms[: max_terms])
    if mode == "or" and len(terms) > 1:
        return OP_OR.join(terms[: max_terms])
    return terms[0] if terms else ""


def build_precedent_ref_articles(
    article_numbers: List[str],
    law_name: str = "근로기준법",
) -> List[str]:
    """
    조문 번호 리스트를 참조조문 검색용 문자열로 변환.
    "민법 제100조", "근로기준법 제34조" 등 어떤 형태든 가능하다고 안내됨.
    """
    import re
    out = []
    seen = set()
    for a in article_numbers or []:
        s = (a or "").strip()
        m = re.match(r"(제\d+(?:의\d+)?조)", s)
        num = m.group(1) if m else s
        if not num or num in seen:
            continue
        seen.add(num)
        ref = f"{law_name} {num}"
        out.append(ref)
    return out


def build_precedent_queries(
    issue: str,
    article_numbers: Optional[List[str]] = None,
    situation: Optional[str] = None,
    include_words: Optional[List[str]] = None,
    exclude_words: Optional[List[str]] = None,
    related_terms: Optional[List[str]] = None,
    keyword_mode: str = "and",
) -> dict:
    """
    이슈·조문·상황을 넣으면 판례 포털 검색에 쓸 수 있는 쿼리 dict 반환.

    반환 예:
      {
        "검색어": "퇴직금 & 평균임금 & 금품",
        "참조조문": ["근로기준법 제34조", "근로기준법 제36조"],
        "포함하는_단어": " ",
        "제외하는_단어": " ",
      }
    """
    if related_terms is None and issue:
        try:
            from rag.law_json import get_related_terms_for_issue
            related_terms = list(get_related_terms_for_issue(issue))[:8]
        except Exception:
            related_terms = []
    kw = build_precedent_search_keywords(
        issue or "",
        related_terms=related_terms,
        mode=keyword_mode,
        max_terms=5,
    )
    # 상황 문장에서 핵심 명사만 추출해 보조로 쓰고 싶다면 여기서 파싱 가능
    if situation and not kw:
        kw = situation.strip()[:50]
    refs = build_precedent_ref_articles(article_numbers or [], law_name="근로기준법")
    include_str = " ".join((include_words or []))
    exclude_str = " ".join((exclude_words or []))
    return {
        "검색어": kw,
        "참조조문": refs,
        "포함하는_단어": include_str,
        "제외하는_단어": exclude_str,
    }
