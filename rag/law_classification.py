# -*- coding: utf-8 -*-
"""
이슈별 법률 구분 모듈
API를 활용하여 이슈가 어떤 법률에 속하는지 동적으로 판단
"""
from typing import List, Dict, Set, Optional, Any
from rag.store import search_by_article_numbers
from config import ALL_LABOR_LAW_SOURCES


def classify_laws_for_issue(
    issue: str,
    situation: Optional[str] = None,
    collection: Optional[Any] = None,
) -> List[str]:
    """
    이슈가 어떤 법률에 속하는지 API를 통해 동적으로 판단.
    
    전략:
    1. 이슈명으로 API에서 관련 조문 번호 찾기
    2. 조문 번호로 벡터 스토어에서 source(법률) 확인
    3. 이슈 동의어로도 조문 찾아서 법률 확인
    4. 상황 키워드로도 조문 찾아서 법률 확인
    
    Returns:
        법률 소스 리스트 (예: ["최저임금법(법률)", "근로기준법(법률)"])
    """
    if collection is None:
        from rag.store import build_vector_store
        collection, _ = build_vector_store()
    
    law_sources: Set[str] = set()
    article_nums_found: Set[str] = set()
    
    # 전략 1: 이슈명으로 직접 조문 검색
    try:
        from rag.api_data_loader import get_articles_from_lstrmRltJo_cache
        issue_articles = get_articles_from_lstrmRltJo_cache(issue)
        if issue_articles:
            article_nums_found.update(issue_articles[:20])  # 최대 20개
    except Exception:
        pass
    
    # 전략 2: 이슈 동의어로도 조문 검색
    try:
        from rag.labor_keywords import ISSUE_SYNONYMS
        from rag.api_data_loader import get_articles_from_lstrmRltJo_cache
        synonyms = [k for k, v in ISSUE_SYNONYMS.items() if v == issue]
        for synonym in synonyms[:5]:  # 최대 5개 동의어
            try:
                syn_articles = get_articles_from_lstrmRltJo_cache(synonym)
                if syn_articles:
                    article_nums_found.update(syn_articles[:10])
            except Exception:
                pass
    except Exception:
        pass
    
    # 전략 3: 상황에서 키워드 추출하여 조문 검색
    if situation:
        try:
            from rag.api_data_loader import get_articles_from_lstrmRltJo_cache
            # 상황에서 주요 키워드 추출
            keywords = [w for w in situation.split() if len(w) >= 2][:5]
            for keyword in keywords:
                try:
                    kw_articles = get_articles_from_lstrmRltJo_cache(keyword)
                    if kw_articles:
                        article_nums_found.update(kw_articles[:5])
                except Exception:
                    pass
        except Exception:
            pass
    
    # 찾은 조문 번호들로 법률 소스 확인
    if article_nums_found:
        try:
            # 조문 번호로 벡터 스토어에서 검색하여 source 확인
            results = search_by_article_numbers(
                collection, list(article_nums_found)[:30], ALL_LABOR_LAW_SOURCES
            )
            for r in results:
                source = r.get("source", "")
                if source and source in ALL_LABOR_LAW_SOURCES:
                    law_sources.add(source)
        except Exception:
            pass
    # 전략 4: 기존 매핑도 항상 참고 (이슈별 특화 법률은 항상 우선 포함)
    mapping_sources = []
    try:
        from rag.pipeline import ISSUE_TO_LAW_MAPPING
        mapping_sources = ISSUE_TO_LAW_MAPPING.get(issue, [])
        if mapping_sources:
            # 매핑된 법률을 항상 포함 (API 결과와 합산)
            law_sources.update(mapping_sources)
    except Exception:
        pass
    
    # 기본적으로 근로기준법은 항상 포함 (fallback)
    if not law_sources:
        from config import SOURCE_LAW
        law_sources.add(SOURCE_LAW)
    
    # 이슈별 특화 법률을 앞에 배치 (우선 검색을 위해)
    ordered = list(mapping_sources)
    for s in law_sources:
        if s not in ordered:
            ordered.append(s)
    return ordered


def get_primary_law_for_issue(
    issue: str,
    situation: Optional[str] = None,
    collection: Optional[Any] = None,
) -> Optional[str]:
    """
    이슈의 주요 법률 1개를 반환 (우선순위가 가장 높은 법률).
    
    Returns:
        법률 소스 문자열 (예: "최저임금법(법률)") 또는 None
    """
    laws = classify_laws_for_issue(issue, situation, collection)
    if not laws:
        return None
    
    # 우선순위: 특수법 > 근로기준법
    # 근로기준법이 아닌 법률이 있으면 그것을 우선
    from config import SOURCE_LAW
    non_basic_laws = [law for law in laws if law != SOURCE_LAW]
    if non_basic_laws:
        return non_basic_laws[0]
    
    return laws[0] if laws else None
