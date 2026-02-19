# -*- coding: utf-8 -*-
"""
조문·이슈 유틸리티. API·labor_keywords 전용 (근로기준법_분류.json 미사용).

- 장/조문 목록: rag/api_chapters.py (API 본문)
- 이슈·동의어·관련어: rag/labor_keywords.py (PRIMARY_ISSUES, ISSUE_SYNONYMS)
- 이슈 관련도 필터: 조문 원문 + labor_keywords 관련어만 사용
"""
import re
from typing import List, Dict, Any, Optional
from functools import lru_cache

# 시나리오 바로가기 (label: 버튼문구, situation: 입력창에 넣을 텍스트)
SCENARIO_QUICK = [
    {"label": "퇴직금", "situation": "퇴직금을 받지 못했어요", "issue": "퇴직금 미지급"},
    {"label": "해고", "situation": "회사에서 해고당했어요", "issue": "해고 예고"},
    {"label": "연차·휴가", "situation": "연차휴가를 받지 못했어요", "issue": "연차휴가"},
    {"label": "임금 체불", "situation": "월급을 받지 못했어요", "issue": "임금 체불"},
    {"label": "근로시간", "situation": "야근이 너무 많아요", "issue": "근로시간"},
    {"label": "근로계약", "situation": "근로계약서에 대해 알고 싶어요", "issue": "근로계약"},
]


def _normalize_article(article_str: str) -> str:
    """'제36조(금품 청산)' -> '제36조', '제43조의2(체불사업주)' -> '제43조의2'"""
    if not article_str:
        return ""
    m = re.match(r"(제\d+(?:의\d+)?조)", article_str)
    return m.group(1) if m else article_str


def get_related_terms_for_issue(issue: str) -> set:
    """
    이슈(primary)에 대해 JSON에서 추론한 관련어 집합.
    get_related_terms_and_definition_terms 캐시를 사용.
    """
    t, _ = get_related_terms_and_definition_terms(issue)
    return set(t)


@lru_cache(maxsize=128)
def get_related_terms_and_definition_terms(issue: str) -> tuple:
    """관련어 전체 집합과, 총칙(제1장)에서만 추출한 용어 집합을 함께 반환. 이슈별 캐시."""
    terms, def_terms = _get_related_terms_impl(issue)
    return (tuple(sorted(terms)), tuple(sorted(def_terms)))  # tuple로 반환해 lru_cache 가능


def _get_related_terms_impl(issue: str) -> tuple:
    """이슈별 관련어·정의용어. labor_keywords만 사용 (API 전용)."""
    if not (issue or issue.strip()):
        return set(), set()
    key = (issue or "").strip()
    terms = set()
    terms.add(key)
    try:
        from rag.labor_keywords import ISSUE_SYNONYMS, PRIMARY_ISSUES
        for syn, primary in ISSUE_SYNONYMS.items():
            if primary == key and syn and len(syn) >= 2:
                terms.add(syn)
        for p in PRIMARY_ISSUES:
            if p and len(p) >= 2:
                terms.add(p)
    except Exception:
        pass
    def_terms = set()
    return terms, def_terms


def rerank_definition_results(
    articles: List[Dict[str, Any]],
    def_terms: Any,
    top_terms: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    정의 전용 검색 결과 재랭킹: 제목/본문에 정의 관련어(정의, 평균임금 등)가 있으면 앞으로.
    def_terms: set 또는 iterable. top_terms가 있으면 그 단어 우선 가산.
    """
    if not articles or not def_terms:
        return articles
    terms_set = set(def_terms)
    if top_terms:
        terms_set = terms_set | set(top_terms)
    def _boost(r: Dict[str, Any]) -> float:
        text = ((r.get("text") or r.get("article") or "") + " " + (r.get("original_text") or "")).strip()
        if not text:
            return 0.0
        score = 0.0
        for t in terms_set:
            if t and t in text:
                score += 1.0
        return score
    return sorted(articles, key=lambda r: (-_boost(r), r.get("article", "")))


def _score_article_relevance_for_issue(
    info: Optional[Dict],
    issue: str,
    related_terms: set,
    raw_text: str = "",
) -> float:
    """
    조문이 이슈와 얼마나 관련 있는지 점수.
    2.0=primary 일치, 1.5=키워드에 관련어 포함, 1.0=제목/요약 등에 관련어 포함, 0.5=원문에 관련어만, 0=무관.
    info가 없으면 폴백: raw_text에 이슈·관련어 포함 여부로 1.0/0.5 (조문이 적게 나오는 것 방지).
    """
    key = (issue or "").strip()
    if not key:
        return 0.0
    if not info:
        if not raw_text:
            return 0.0
        if key in raw_text:
            return 1.0
        for t in (related_terms or set()):
            if t and len(t) >= 2 and t in raw_text:
                return 0.5
        return 0.0
    pc = (info.get("primary_category") or "").strip()
    if pc == key:
        return 2.0
    title = (info.get("title") or "").strip()
    kws = list(info.get("keywords") or [])
    summary = (info.get("summary") or "").strip()
    text = " ".join([title, (info.get("secondary_category") or ""), summary]) + " " + " ".join(kws)
    kws_set = set(str(x).strip() for x in kws if str(x).strip())
    match_in_kw = 0
    match_in_rest = 0
    for t in related_terms:
        if t in kws_set or t in title:
            match_in_kw += 1
        elif t in text:
            match_in_rest += 1
    if match_in_kw:
        return 1.5
    if match_in_rest:
        return 1.0
    if raw_text and key in raw_text:
        return 1.0
    return 0.0


def filter_and_rank_articles_by_issue(
    issue: str,
    articles: List[Dict[str, Any]],
    top_k: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    검색된 조문을 이슈와의 관련도로 필터·정렬.
    API 전용: 근로기준법_분류.json 사용하지 않음. 조문 원문(raw_text)과
    labor_keywords 기반 관련어만으로 점수(1.0=이슈 포함, 0.5=관련어 포함) 후 top_k개 반환.
    """
    try:
        from config import RAG_FILTER_TOP_K
    except ImportError:
        RAG_FILTER_TOP_K = 15
    k = top_k if top_k is not None else RAG_FILTER_TOP_K
    if not (issue or issue.strip()) or not articles:
        return articles
    related_terms = get_related_terms_for_issue(issue)
    scored = []
    for r in articles:
        raw = (r.get("text") or r.get("original_text") or "").strip()
        # 원문·관련어만으로 점수 (labor_keywords 기반)
        score = _score_article_relevance_for_issue(None, issue, related_terms, raw_text=raw)
        if score >= 0.5:
            scored.append((score, r))
    scored.sort(key=lambda x: (-x[0], x[1].get("article", "")))
    combined = [r for _, r in scored]
    return combined[:k]


def get_related_articles(article_str: str) -> List[str]:
    """관련 조문 번호 리스트. 특정 조문 검색 시 함께 검토해야 할 조문들을 반환."""
    # 숫자와 가지번호만 추출 (예: '제23조' -> '23', '제43조의2' -> '43의2')
    import re
    match = re.search(r'제(\d+(?:의\d+)?)조', article_str)
    if not match:
        return []
    
    art_num = match.group(1)
    
    # 주요 조문 관계 매핑
    RELATIONS = {
        # 해고 관련: 제한, 경영상 해고, 예고, 서면통지, 구제신청
        "23": ["24", "26", "27", "28"],
        "24": ["23", "26", "27", "28"],
        "26": ["23", "27", "28"],
        "27": ["23", "26", "28"],
        "28": ["23", "27", "30"],
        "30": ["23", "28"],
        
        # 임금 관련: 금품청산, 임금지급, 도급, 시효
        "36": ["43", "44", "49"],
        "43": ["36", "43의2", "44", "49"],
        "49": ["36", "43"],
        
        # 근로시간 및 휴식: 시간, 휴게, 연장근로, 가산임금, 휴일
        "50": ["53", "54", "56"],
        "53": ["50", "56", "59"],
        "54": ["50"],
        "56": ["50", "53", "55"],
        "55": ["56", "60"],
        
        # 휴가: 연차, 사용촉진, 대체
        "60": ["61", "62", "55"],
        "61": ["60"],
        "62": ["60"],
        
        # 직장 내 괴롭힘
        "76의2": ["76의3"],
        "76의3": ["76의2"],
        
        # 모성보호 (남녀고용평등법 조항과 매칭 필요하나 우선 근기법 내)
        "74": ["74의2"],
        
        # 산업안전보건법 (작업중지 등)
        "51": ["52", "53"],
        "52": ["51", "53", "54"],
        "53": ["51", "52", "54"],
        
        # 노동조합 및 노동관계조정법 (부당노동행위 등)
        "81": ["82", "83", "84", "85", "86"],
        "82": ["81", "83", "84", "85", "86"]
    }
    
    related = RELATIONS.get(art_num, [])
    return [f"제{r}조" for r in related]


def get_related_articles_for_list(articles: List[Dict[str, Any]]) -> List[str]:
    """RAG 검색 결과 리스트에서 관련 조문 수집 (중복 제거)"""
    seen = set()
    out = []
    for r in articles:
        art = r.get("article", "")
        for rel in get_related_articles(art):
            if rel not in seen:
                seen.add(rel)
                out.append(rel)
    return out


def get_search_questions_for_issue(issue: str, limit: int = 5) -> List[str]:
    """이슈 관련 추천 질문. API 전용: 분류 JSON 미사용 → 빈 리스트."""
    return []


def get_search_questions_for_articles(articles: List[Dict[str, Any]], limit: int = 5) -> List[str]:
    """검색된 조문 기준 추천 질문. API 전용: 분류 JSON 미사용 → 빈 리스트."""
    return []


def get_primary_categories_list() -> List[str]:
    """허용 primary 이슈 목록. labor_keywords.PRIMARY_ISSUES 사용."""
    from rag.labor_keywords import PRIMARY_ISSUES
    return list(PRIMARY_ISSUES)


@lru_cache(maxsize=1)
def _issue_phrase_to_primary_from_labor_keywords() -> Dict[str, str]:
    """labor_keywords.ISSUE_SYNONYMS + PRIMARY_ISSUES로 문구 → primary 맵 생성."""
    out = {}
    try:
        from rag.labor_keywords import ISSUE_SYNONYMS, PRIMARY_ISSUES
        for syn, primary in ISSUE_SYNONYMS.items():
            if syn and primary:
                out[syn] = primary
        for p in PRIMARY_ISSUES:
            if p:
                out[p] = p
    except Exception:
        pass
    return out


def normalize_issue_to_primary(issue: str) -> str:
    """
    이슈 문자열을 primary(정규화된 이슈) 하나로 정규화.
    labor_keywords.PRIMARY_ISSUES, ISSUE_SYNONYMS만 사용.
    """
    if not (issue or issue.strip()):
        return issue or ""
    s = (issue or "").strip()
    allowed = set(get_primary_categories_list())
    if s in allowed:
        return s
    phrase_map = _issue_phrase_to_primary_from_labor_keywords()
    if s in phrase_map:
        return phrase_map[s]
    for phrase, pc in sorted(phrase_map.items(), key=lambda x: -len(x[0])):
        if (phrase in s or s in phrase) and pc:
            return pc
    from rag.labor_keywords import ISSUE_SYNONYMS
    if s in ISSUE_SYNONYMS:
        return ISSUE_SYNONYMS[s]
    for syn, pc in sorted(ISSUE_SYNONYMS.items(), key=lambda x: -len(x[0])):
        if (syn in s or s in syn) and pc:
            return pc
    return s


def get_categories_for_issue(issue: str) -> List[str]:
    """이슈/상황에 해당하는 primary 리스트. labor_keywords.ISSUE_SYNONYMS 사용.
    핵심 키워드(육아휴직, 산재, 노조, 산업안전, 최저임금 등)를 우선적으로 매칭."""
    from rag.labor_keywords import ISSUE_SYNONYMS, PRIMARY_ISSUES
    issue_norm = (issue or "").strip()
    matched = []
    
    # 핵심 키워드 우선 매칭 (직접 언급된 경우)
    priority_keywords = {
        "육아휴직": "육아휴직",
        "산재": "산재",
        "산업재해": "산재",
        "업무상재해": "산재",
        "노조": "노조",
        "노동조합": "노조",
        "산업안전": "산업안전",
        "작업중지": "산업안전",
        "작업중지권": "산업안전",
        "작업 거부": "산업안전",
        "작업거부": "산업안전",
        "위험": "산업안전",
        "최저임금": "최저임금",
        "수습": "최저임금",
        "수습기간": "최저임금",
        "수습사원": "최저임금",
        "남녀고용평등": "남녀고용평등",
        "성차별": "남녀고용평등",
        "퇴사": "퇴직금",
        "퇴직": "퇴직금",
    }
    
    # 우선 키워드 먼저 확인
    for keyword, primary in priority_keywords.items():
        if keyword in issue_norm and primary not in matched:
            matched.append(primary)
    
    # 나머지 키워드 매칭
    phrase_map = _issue_phrase_to_primary_from_labor_keywords()
    for phrase, pc in sorted(phrase_map.items(), key=lambda x: -len(x[0])):
        if (phrase in issue_norm or issue_norm in phrase) and pc and pc not in matched:
            matched.append(pc)
    for syn, pc in sorted(ISSUE_SYNONYMS.items(), key=lambda x: -len(x[0])):
        if (syn in issue_norm or issue_norm in syn) and pc and pc not in matched:
            matched.append(pc)
    
    return matched


def get_laws() -> List[Dict[str, Any]]:
    """법률 둘러보기용 법령 목록. API 동기화된 law/*.json 기준. [{id, name}, ...]."""
    try:
        from rag.api_chapters import get_laws_from_api
        return get_laws_from_api()
    except Exception as e:
        import sys
        print(f"[get_laws] API 본문에서 법령 목록을 불러올 수 없습니다: {e}", file=sys.stderr)
        return []


def get_chapters(law_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """장(章) 목록. law_id 지정 시 해당 법령, 없으면 근로기준법 등 첫 법령."""
    try:
        from rag.api_chapters import get_chapters_from_api
        api_chapters = get_chapters_from_api(law_id)
        return api_chapters if api_chapters else []
    except Exception as e:
        import sys
        print(f"[get_chapters] API 본문에서 장 목록을 불러올 수 없습니다: {e}", file=sys.stderr)
        return []


def get_articles_by_chapter(chapter_number: str, law_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """장 번호로 해당 조문 목록. law_id 지정 시 해당 법령, 없으면 근로기준법 등."""
    try:
        from rag.api_chapters import get_articles_by_chapter_from_api
        api_articles = get_articles_by_chapter_from_api(chapter_number, law_id)
        return api_articles if api_articles is not None else []
    except Exception as e:
        import sys
        print(f"[get_articles_by_chapter] API 본문에서 조문 목록을 불러올 수 없습니다 (장: {chapter_number}): {e}", file=sys.stderr)
        return []


def get_chunk_enrichment(chunk: Dict[str, Any], source: str) -> Optional[Dict[str, Any]]:
    """
    법률 청크 임베딩 보강. API 전용: 분류 JSON 미사용 → 항상 None.
    """
    return None


def get_embedding_enhanced_text(chunk: Dict[str, Any], source: str) -> Optional[str]:
    """get_chunk_enrichment의 embedding_text만 반환 (기존 호환)"""
    en = get_chunk_enrichment(chunk, source)
    return en.get("embedding_text") if en else None
