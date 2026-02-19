# -*- coding: utf-8 -*-
"""
조문 보완 및 검증 모듈 - 구조적 접근
하드코딩 없이 검색 결과의 품질을 검증하고 동적으로 보완하는 전략
"""
from typing import List, Dict, Any, Set, Optional, Tuple
from rag.store import search_by_article_numbers, search
from config import ALL_LABOR_LAW_SOURCES


def validate_search_quality(
    issue: str,
    articles: List[Dict[str, Any]],
    situation: Optional[str] = None,
) -> Dict[str, Any]:
    """
    검색 결과의 품질을 검증.
    조문의 다양성, 법률 분포, 이슈 관련성을 평가.
    
    Returns:
        {
            "quality_score": float,  # 0.0 ~ 1.0
            "law_diversity": int,  # 검색된 법률 종류 수
            "article_count": int,
            "needs_enrichment": bool,
        }
    """
    if not articles:
        return {
            "quality_score": 0.0,
            "law_diversity": 0,
            "article_count": 0,
            "needs_enrichment": True,
        }
    
    # 법률 다양성 평가
    sources = set()
    for r in articles:
        source = r.get("source", "")
        if source:
            sources.add(source)
    
    law_diversity = len(sources)
    article_count = len(articles)
    
    # 품질 점수 계산
    # - 조문 수가 충분한가 (최소 5개 이상)
    # - 법률 다양성이 있는가 (최소 1개 이상)
    quality_score = min(1.0, (article_count / 10.0) * 0.6 + (law_diversity / 3.0) * 0.4)
    
    # 보완 필요 여부 (더 적극적으로 보완)
    # 조문이 적거나, 법률 다양성이 없거나, 품질 점수가 낮으면 보완
    needs_enrichment = (
        article_count < 8 or  # 5 -> 8로 상향 (더 많은 조문 확보)
        law_diversity < 1 or
        quality_score < 0.6  # 0.5 -> 0.6으로 상향 (더 높은 품질 요구)
    )
    
    return {
        "quality_score": quality_score,
        "law_diversity": law_diversity,
        "article_count": article_count,
        "needs_enrichment": needs_enrichment,
    }


def enrich_articles_with_api_search(
    issue: str,
    articles: List[Dict[str, Any]],
    collection: Any,
    situation: Optional[str] = None,
    max_additional: int = 20,
) -> List[Dict[str, Any]]:
    """
    API를 적극 활용한 조문 확장 검색.
    벡터 검색에만 의존하지 않고 API를 통해 직접 조문을 찾습니다.
    
    전략:
    1. API를 통한 이슈 관련 조문 직접 검색 (우선순위 최상)
    2. 검색된 조문의 관련 조문 API 추적
    3. 벡터 검색은 보조적으로만 사용
    """
    enriched = list(articles)
    seen_articles = {_get_article_number(r) for r in articles if _get_article_number(r)}
    
    # 전략 1: API를 통한 이슈 관련 조문 직접 검색 (최우선)
    api_article_nums = set()
    
    # 1-1: 이슈명으로 직접 조문 검색
    try:
        from rag.api_data_loader import get_articles_from_lstrmRltJo_cache
        issue_articles = get_articles_from_lstrmRltJo_cache(issue)
        if issue_articles:
            api_article_nums.update(issue_articles[:15])  # 최대 15개
    except Exception:
        pass
    
    # 1-2: 이슈 동의어로도 조문 검색
    try:
        from rag.labor_keywords import ISSUE_SYNONYMS
        from rag.api_data_loader import get_articles_from_lstrmRltJo_cache
        synonyms = [k for k, v in ISSUE_SYNONYMS.items() if v == issue]
        for synonym in synonyms[:3]:  # 최대 3개 동의어
            try:
                syn_articles = get_articles_from_lstrmRltJo_cache(synonym)
                if syn_articles:
                    api_article_nums.update(syn_articles[:10])
            except Exception:
                pass
    except Exception:
        pass
    
    # 1-3: 상황에서 키워드 추출하여 조문 검색
    if situation:
        try:
            from rag.api_data_loader import get_articles_from_lstrmRltJo_cache
            # 상황에서 주요 키워드 추출 (간단한 방식)
            keywords = [w for w in situation.split() if len(w) >= 2][:5]  # 최대 5개 키워드
            for keyword in keywords:
                try:
                    kw_articles = get_articles_from_lstrmRltJo_cache(keyword)
                    if kw_articles:
                        api_article_nums.update(kw_articles[:5])
                except Exception:
                    pass
        except Exception:
            pass
    
    # API로 찾은 조문 번호들을 직접 검색
    if api_article_nums:
        try:
            api_results = search_by_article_numbers(
                collection, list(api_article_nums)[:20], ALL_LABOR_LAW_SOURCES
            )
            for r in api_results:
                art = _get_article_number(r)
                if art and art not in seen_articles:
                    enriched.append(r)
                    seen_articles.add(art)
        except Exception:
            pass
    
    # 전략 2: 검색된 조문의 관련 조문 API 추적
    try:
        from rag.law_json import get_related_articles_for_list
        if articles:
            # 상위 5개 조문의 관련 조문 추적
            related_nums = get_related_articles_for_list(articles[:5])
            if related_nums:
                # API로 찾은 조문도 관련 조문 추적
                if api_article_nums:
                    try:
                        api_related = get_related_articles_for_list(
                            [{"article": f"{num}"} for num in list(api_article_nums)[:5]]
                        )
                        if api_related:
                            related_nums.extend(api_related)
                    except Exception:
                        pass
                
                try:
                    related_results = search_by_article_numbers(
                        collection, list(set(related_nums))[:20], ALL_LABOR_LAW_SOURCES
                    )
                    for r in related_results:
                        art = _get_article_number(r)
                        if art and art not in seen_articles:
                            enriched.append(r)
                            seen_articles.add(art)
                            if len(enriched) >= len(articles) + max_additional:
                                break
                except Exception:
                    pass
    except Exception:
        pass
    
    # 전략 3: 벡터 검색은 보조적으로만 사용 (API로 찾지 못한 경우)
    if len(enriched) < len(articles) + 5:  # 여전히 부족하면 벡터 검색
        try:
            query = issue
            if situation:
                query = f"{issue} {situation}"
            vector_results = search(
                collection, query, top_k=max_additional,
                filter_sources=ALL_LABOR_LAW_SOURCES,
            )
            for r in vector_results:
                art = _get_article_number(r)
                if art and art not in seen_articles:
                    enriched.append(r)
                    seen_articles.add(art)
                    if len(enriched) >= len(articles) + max_additional:
                        break
        except Exception:
            pass
    
    return enriched


def _get_article_number(r: Dict[str, Any]) -> Optional[str]:
    """조문 결과에서 조문 번호 추출."""
    import re
    art = (r.get("article") or "").strip()
    if not art:
        return None
    m = re.match(r"^(제\d+(?:의\d+)?조)", art)
    return m.group(1) if m else None
