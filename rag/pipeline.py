# RAG 기반 노동법 상담 파이프라인
#
# [실제 구현 흐름]
#
# **Streamlit 앱(app.py) 기준 (현재 메인 흐름):**
#   1. step1_issue_classification: 상황 → [경로A] 이슈 후보(키워드 매칭) 또는 [경로B] 1차검색+LLM 분류 → 이슈별 검색으로 조문 수집 → (issues, articles_by_issue) 반환
#   2. 앱은 step1 반환값 articles_by_issue 사용 (없는 이슈만 검색으로 보완)
#   3. step2_checklist: 이슈 + remaining_articles(걸러진 조문) → "당신의 상황·사실" 확인용 질문 리스트 생성
#   4. (선택) "다음 확인으로" 시 답변 반영 검색 후 step2 재호출 (최대 N차)
#   5. step3_conclusion: 체크리스트 Q&A + 조문 → 법적 결론
#
# **구현된 step 함수:**
#   - step1_issue_classification: 이슈 분류
#   - step2_checklist: 체크리스트 생성
#   - step3_conclusion: 결론 생성
import os
import re
import sys
import concurrent.futures
from typing import List, Dict, Any, Optional, Tuple

# 디버깅 모드. 환경변수 LAW_DEBUG=1 일 때만 stderr 출력
DEBUG = os.getenv("LAW_DEBUG", "0") == "1"

from rag.store import build_vector_store, search, search_by_article_numbers
from rag.prompts import (
    system_issue_classification,
    user_issue_classification,
    system_checklist,
    user_checklist,
    system_checklist_continuation,
    user_checklist_continuation,
    system_conclusion,
    user_conclusion,
)
from rag.llm import chat, chat_json, chat_json_fast
from config import (
    SOURCE_LAW, SOURCE_DECREE, SOURCE_RULE,
    SOURCE_MIN_WAGE_LAW,
    SOURCE_RETIREMENT_LAW,
    SOURCE_GENDER_EQUALITY_LAW,
    SOURCE_SAFETY_LAW,
    SOURCE_INDUSTRIAL_ACCIDENT_LAW,
    SOURCE_UNION_LAW,
    ALL_LABOR_LAW_SOURCES,
    INDIVIDUAL_LABOR_LAW_SOURCES,
    COLLECTIVE_LABOR_LAW_SOURCES,
    LABOR_MARKET_LAW_SOURCES,
)

# 이슈별 관련 법률 매핑 (우선 검색용)
ISSUE_TO_LAW_MAPPING = {
    "최저임금": [SOURCE_MIN_WAGE_LAW, SOURCE_LAW],
    "산재": [SOURCE_INDUSTRIAL_ACCIDENT_LAW, SOURCE_SAFETY_LAW, SOURCE_LAW],
    "산업안전": [SOURCE_SAFETY_LAW, SOURCE_INDUSTRIAL_ACCIDENT_LAW],
    "노조": [SOURCE_UNION_LAW],
    "남녀고용평등": [SOURCE_GENDER_EQUALITY_LAW, SOURCE_LAW],
    "육아휴직": [SOURCE_GENDER_EQUALITY_LAW, SOURCE_LAW],
    "퇴직금": [SOURCE_RETIREMENT_LAW, SOURCE_LAW],
    "고용보험": [SOURCE_LAW],
    "임금": [SOURCE_LAW],
    "근로시간": [SOURCE_LAW],
    "괴롭힘": [SOURCE_LAW],
    "해고/징계": [SOURCE_LAW],
    "휴일/휴가": [SOURCE_LAW],
    "근로계약": [SOURCE_LAW],
}

# 한 사이클: 본칙으로 조항 확정 후 벌칙·부칙 확인. 법률 검색 시 본칙만 사용.
EXCLUDE_SECTIONS_MAIN = ["벌칙", "부칙"]
# 제1장 총칙은 정의와 개념 설명이므로 구체 조항 검색에서 제외
EXCLUDE_CHAPTERS_MAIN = ["제1장 총칙"]


def _rag_context(search_results: List[Dict[str, Any]], max_length: int = 5000) -> str:
    """RAG 검색 결과를 컨텍스트 문자열로 변환. 장 정보와 법률명도 포함. max_length로 길이 제한."""
    parts = []
    total_length = 0
    for r in search_results:
        text = r.get("text", "")
        chapter = r.get("chapter", "")
        article = r.get("article", "")
        source = r.get("source", "")
        
        # 법률명 추출 (source에서 "(법률)" 제거)
        law_name = ""
        if source:
            # "근로기준법(법률)" -> "근로기준법"
            law_name = source.replace("(법률)", "").replace("(시행령)", "").replace("(시행규칙)", "").strip()
        
        # 장 정보와 법률명이 있으면 함께 표시
        # 예: "[근로기준법] [제3장 임금] 제36조(임금의 지급)"
        header_parts = []
        if law_name:
            header_parts.append(f"[{law_name}]")
        if chapter:
            header_parts.append(f"[{chapter}]")
        if header_parts:
            part = " ".join(header_parts) + f" {article}\n{text}"
        else:
            part = f"{article}\n{text}"
        
        # 길이 제한: 각 조문을 추가해도 max_length를 넘지 않도록
        if total_length + len(part) > max_length and parts:
            break
        parts.append(part)
        total_length += len(part)
    return "\n\n---\n\n".join(parts)


def _cap_articles_by_source_diversity(articles: List[Dict[str, Any]], max_n: int) -> List[Dict[str, Any]]:
    """조문 목록을 최대 max_n개로 줄이되, 법률(source)별로 고르게 포함. 두 개 이상 법률이 있으면 한쪽만 몰리지 않도록 함."""
    if not articles or len(articles) <= max_n:
        return list(articles)
    by_source: Dict[str, List[Dict[str, Any]]] = {}
    for r in articles:
        src = r.get("source", "") or ""
        if src not in by_source:
            by_source[src] = []
        by_source[src].append(r)
    n_sources = len(by_source)
    if n_sources <= 1:
        return articles[:max_n]
    per_source = max(1, (max_n + n_sources - 1) // n_sources)
    out = []
    for src in by_source:
        out.extend(by_source[src][:per_source])
    if len(out) > max_n:
        out = out[:max_n]
    return out


def _debug_print(*args, **kwargs):
    """디버그 출력 헬퍼 함수"""
    if DEBUG:
        print(*args, **kwargs, file=sys.stderr)


def filter_articles_by_issue_relevance(
    issue: str,
    articles: List[Dict[str, Any]],
    top_k: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """검색된 조문을 이슈와의 관련도로 필터·정렬."""
    try:
        from rag.law_json import filter_and_rank_articles_by_issue
        k = top_k if top_k is not None else 15
        return filter_and_rank_articles_by_issue(issue, articles, top_k=k)
    except Exception:
        return articles[:top_k] if top_k else articles


def _expand_query_for_search(situation: str) -> str:
    """쿼리 확장을 한 곳에서 처리하고 로깅. 카테고리, 법령용어, 관련법령 등 추가."""
    query = situation
    expansions = []
    
    # 1. 카테고리 추가
    try:
        from rag.law_json import get_categories_for_issue
        cats = get_categories_for_issue(situation)
        if cats:
            query = query + " " + " ".join(cats)
            expansions.append(f"카테고리: {cats}")
    except Exception as e:
        _debug_print(f"[쿼리 확장] 카테고리 추가 실패: {e}")
    
    # 2. 일상용어 → 법령용어 (dlytrmRlt)
    try:
        from rag.api_data_loader import get_law_terms_from_dlytrmRlt_cache
        law_terms = get_law_terms_from_dlytrmRlt_cache(situation)
        if law_terms:
            query = (query or situation) + " " + " ".join(law_terms)
            expansions.append(f"법령용어(dlytrmRlt): {law_terms[:3]}")
    except Exception as e:
        _debug_print(f"[쿼리 확장] 법령용어(dlytrmRlt) 추가 실패: {e}")
    
    # 3. 법령용어 → 일상용어 역방향 확장 (lstrmRlt) - 법령용어에서 일상용어 찾아 추가
    try:
        from rag.api_data_loader import get_daily_terms_from_lstrmRlt_cache
        # 이미 찾은 법령용어에서 일상용어 역추적
        if law_terms:
            for term in law_terms[:3]:  # 상위 3개만
                daily_terms = get_daily_terms_from_lstrmRlt_cache(term)
                if daily_terms:
                    query = query + " " + " ".join(daily_terms[:2])  # 각 용어당 최대 2개
                    expansions.append(f"일상용어(lstrmRlt): {daily_terms[:2]}")
    except Exception as e:
        _debug_print(f"[쿼리 확장] 일상용어(lstrmRlt) 추가 실패: {e}")
    
    # 4. 일상용어 직접 조회 (dlytrm) - dlytrmRlt와 유사하지만 다른 방식
    try:
        from rag.api_data_loader import get_dlytrm_from_cache
        dlytrm_terms = get_dlytrm_from_cache(situation)
        if dlytrm_terms:
            query = query + " " + " ".join(dlytrm_terms)
            expansions.append(f"법령용어(dlytrm): {dlytrm_terms[:2]}")
    except Exception as e:
        _debug_print(f"[쿼리 확장] 법령용어(dlytrm) 추가 실패: {e}")
    
    # 5. 관련법령 추가 (lsRlt)
    try:
        from rag.api_data_loader import get_related_laws_from_lsRlt_cache
        related_laws = get_related_laws_from_lsRlt_cache("근로기준법")
        if related_laws:
            query = query + " " + " ".join(related_laws[:2])  # 상위 2개만
            expansions.append(f"관련법령(lsRlt): {related_laws[:2]}")
    except Exception as e:
        _debug_print(f"[쿼리 확장] 관련법령(lsRlt) 추가 실패: {e}")
    
    # 6. 지능형 검색 (aiSearch) - 더 정교한 검색어 확장
    try:
        from rag.api_cache import get_aiSearch_cached
        ai_result = get_aiSearch_cached(situation)
        if ai_result.get("success") and ai_result.get("data"):
            # aiSearch 결과에서 키워드 추출 (간단히 쿼리에 추가)
            data = ai_result["data"]
            # 결과가 있으면 쿼리 확장에 활용 (구체적인 키워드 추출은 생략하고 쿼리만 사용)
            expansions.append("지능형검색(aiSearch) 활용")
    except Exception as e:
        _debug_print(f"[쿼리 확장] 지능형검색(aiSearch) 추가 실패: {e}")
    
    if expansions:
        _debug_print(f"[쿼리 확장] {', '.join(expansions)}")
    return query


def _validate_issues_with_articles(issues: List[str], articles_by_issue: Dict[str, List[Dict[str, Any]]]) -> bool:
    """이슈와 조문이 유효한지 검증. 최소 1개 이슈에 조문이 있어야 함."""
    if not issues:
        return False
    for issue in issues:
        if articles_by_issue.get(issue):
            return True
    return False


def _collect_articles_by_issue(
    collection: Any,
    issues: List[str],
    situation: Optional[str] = None,
    initial_list: Optional[List[Dict[str, Any]]] = None,
    top_k_per_issue: int = 15,
) -> Dict[str, List[Dict[str, Any]]]:
    """이슈 리스트에 대해 각 이슈별로 조문 검색 후 수집. 이슈별 관련 법률 우선 검색.
    검색 후 품질 검증 및 동적 보완 단계를 거침."""
    articles_by_issue: Dict[str, List[Dict[str, Any]]] = {}
    base = initial_list or []
    # (source, article) 기준으로 중복 제거 → 같은 조문 번호라도 법률이 다르면 둘 다 포함
    seen_keys = {(r.get("source", ""), r.get("article", "")) for r in base if r.get("article")}
    for issue in issues:
        issue_list = []
        query = issue
        if situation:
            query = situation + " " + issue
        
        # 단계 1: 이슈별 법률 구분 (API 기반 동적 판단)
        try:
            from rag.law_classification import classify_laws_for_issue
            api_detected_sources = classify_laws_for_issue(issue, situation, collection)
            if api_detected_sources:
                _debug_print(f"[법률 구분] {issue}: API로 감지된 법률 {len(api_detected_sources)}개 - {api_detected_sources}")
                preferred_sources = api_detected_sources
            else:
                # API로 찾지 못하면 기존 매핑 사용
                preferred_sources = ISSUE_TO_LAW_MAPPING.get(issue, None)
        except Exception as e:
            _debug_print(f"[법률 구분] {issue}: API 기반 구분 실패 ({e}), 기존 매핑 사용")
            preferred_sources = ISSUE_TO_LAW_MAPPING.get(issue, None)
        if preferred_sources:
            # 법률이 2개 이상이면 법률별로 나눠 검색해 조문이 한쪽 법률에만 몰리지 않도록 함
            if len(preferred_sources) >= 2:
                k_per_law = max(3, (top_k_per_issue + len(preferred_sources) - 1) // len(preferred_sources))
                for src in preferred_sources:
                    res_one = search(
                        collection, query, top_k=k_per_law,
                        filter_sources=[src], exclude_sections=EXCLUDE_SECTIONS_MAIN,
                        exclude_chapters=EXCLUDE_CHAPTERS_MAIN,
                    )
                    for r in res_one:
                        art = r.get("article", "")
                        src_key = r.get("source", "")
                        if art and (src_key, art) not in seen_keys:
                            issue_list.append(r)
                            seen_keys.add((src_key, art))
            else:
                res_preferred = search(
                    collection, query, top_k=top_k_per_issue,
                    filter_sources=preferred_sources, exclude_sections=EXCLUDE_SECTIONS_MAIN,
                    exclude_chapters=EXCLUDE_CHAPTERS_MAIN,
                )
                for r in res_preferred:
                    art = r.get("article", "")
                    src_key = r.get("source", "")
                    if art and (src_key, art) not in seen_keys:
                        issue_list.append(r)
                        seen_keys.add((src_key, art))
            # 부족하면 전체 법률에서 추가 검색
            if len(issue_list) < top_k_per_issue // 2:
                res_all = search(
                    collection, query, top_k=top_k_per_issue - len(issue_list),
                    filter_sources=ALL_LABOR_LAW_SOURCES, exclude_sections=EXCLUDE_SECTIONS_MAIN,
                    exclude_chapters=EXCLUDE_CHAPTERS_MAIN,
                )
                for r in res_all:
                    art = r.get("article", "")
                    src_key = r.get("source", "")
                    if art and (src_key, art) not in seen_keys:
                        issue_list.append(r)
                        seen_keys.add((src_key, art))
        else:
            # 매핑이 없으면 전체 법률에서 검색
            res = search(
                collection, query, top_k=top_k_per_issue,
                filter_sources=ALL_LABOR_LAW_SOURCES, exclude_sections=EXCLUDE_SECTIONS_MAIN,
                exclude_chapters=EXCLUDE_CHAPTERS_MAIN,
            )
            for r in res:
                art = r.get("article", "")
                src_key = r.get("source", "")
                if art and (src_key, art) not in seen_keys:
                    issue_list.append(r)
                    seen_keys.add((src_key, art))
        
        if issue_list:
            # 검색 품질 검증 및 동적 보완
            try:
                from rag.article_enrichment import validate_search_quality, enrich_articles_with_api_search
                quality = validate_search_quality(issue, issue_list, situation)
                _debug_print(f"[조문 검증] {issue}: 품질 점수 {quality['quality_score']:.2f}, 법률 다양성 {quality['law_diversity']}")
                
                if quality["needs_enrichment"]:
                    _debug_print(f"[조문 보완] {issue}: API 기반 검색으로 보완 시도")
                    from rag.article_enrichment import enrich_articles_with_api_search
                    issue_list = enrich_articles_with_api_search(
                        issue, issue_list, collection, situation, max_additional=20
                    )
                    _debug_print(f"[조문 보완] {issue}: 보완 후 {len(issue_list)}개 조문")
            except Exception as e:
                _debug_print(f"[조문 보완] 실패 ({issue}): {e}")
            
            articles_by_issue[issue] = issue_list
        else:
            articles_by_issue[issue] = list(base)
    return articles_by_issue


def _classify_with_llm(
    situation: str,
    collection: Any,
    top_k: int,
) -> Tuple[List[str], Dict[str, List[Dict[str, Any]]], str]:
    """LLM을 사용한 이슈 분류 (경로 B)."""
    query = _expand_query_for_search(situation)
    
    _debug_print(f"\n[조항 검색] 쿼리: {query}, top_k: {top_k}")
    # 모든 노동법에서 검색 (개별적/집단적/노동시장 법률 모두 포함)
    results = search(
        collection, query, top_k=top_k,
        filter_sources=ALL_LABOR_LAW_SOURCES, exclude_sections=EXCLUDE_SECTIONS_MAIN,
        exclude_chapters=EXCLUDE_CHAPTERS_MAIN,
    )
    _debug_print(f"[검색 결과] {len(results)}개 조항 발견")
    
    if not results:
        _debug_print("[이슈 분류 완료] 검색 결과 없음")
        return ([], {}, "llm")
    
    context = _rag_context(results)
    if not (context and context.strip()):
        _debug_print("[이슈 분류 완료] 컨텍스트 없음")
        return ([], {}, "llm")
    
    _debug_print(f"\n[LLM 이슈 분류] 컨텍스트 길이: {len(context)}자")
    try:
        from rag.law_json import get_primary_categories_list
        allowed = get_primary_categories_list()
    except Exception:
        allowed = None
    
    out = chat_json(
        system_issue_classification(),
        user_issue_classification(situation, context, allowed_primaries=allowed),
    )
    _debug_print(f"[LLM 원시 응답] 타입={type(out).__name__}, 값={out}")
    
    raw_issues = []
    if isinstance(out, list):
        raw_issues = [x for x in out if isinstance(x, str)]
    elif isinstance(out, dict) and "issues" in out:
        raw_issues = out["issues"]
    _debug_print(f"[LLM 파싱] raw_issues ({len(raw_issues)}개): {raw_issues}")
    
    # 이슈 정규화 및 검증
    try:
        from rag.law_json import normalize_issue_to_primary, get_primary_categories_list
        allowed_set = set(get_primary_categories_list())
        seen = []
        issues = []
        for x in raw_issues:
            raw_str = (x or "").strip()
            if not raw_str:
                continue
            norm = normalize_issue_to_primary(raw_str)
            if not norm:
                _debug_print(f"[이슈 정규화 실패] '{raw_str}' → 정규화 결과 없음")
                continue
            if norm not in allowed_set:
                _debug_print(f"[이슈 정규화 실패] '{raw_str}' → '{norm}' 허용 목록에 없음")
                continue
            if norm not in seen:
                seen.append(norm)
                issues.append(norm)
    except Exception as e:
        _debug_print(f"[이슈 정규화] 예외 발생: {e}, raw_issues 사용")
        issues = raw_issues
    
    _debug_print(f"[이슈 분류 결과] 최종 {len(issues)}개 이슈: {issues}")
    
    if not issues:
        return ([], {}, "llm")
    
    articles_by_issue = _collect_articles_by_issue(
        collection, issues, situation=None, initial_list=results, top_k_per_issue=15
    )
    _debug_print(f"\n[이슈 분류 완료] 이슈 {len(issues)}개, 이슈별 조문 반환")
    return (issues, articles_by_issue, "llm")


def step1_issue_classification(
    situation: str,
    collection=None,
    top_k: int = 22,
) -> Tuple[List[str], Dict[str, List[Dict[str, Any]]], str]:
    """사용자 상황 → 이슈 후보(키워드 매칭) 또는 1차검색+LLM 분류 → 이슈별 조문 수집.
    반환: (issues, articles_by_issue, source). source는 "keyword" 또는 "llm"."""
    _debug_print("\n" + "="*80)
    _debug_print(f"[이슈 분류 시작] 상황: {situation}")
    _debug_print("="*80)
    
    if collection is None:
        collection, _ = build_vector_store()
    
    try:
        from config import STEP1_ISSUE_SEARCH_TOP_N
        top_n = STEP1_ISSUE_SEARCH_TOP_N
    except Exception:
        top_n = 3
    
    # ---------- 경로 A: 키워드 매칭 먼저 시도 ----------
    try:
        from rag.law_json import get_categories_for_issue
        candidate_issues = get_categories_for_issue(situation)
    except Exception as e:
        _debug_print(f"[키워드 매칭] 실패: {e}")
        candidate_issues = []
    
    if candidate_issues:
        seen_order = []
        for x in candidate_issues:
            if x and (x not in seen_order):
                seen_order.append(x)
        issues = seen_order
        _debug_print(f"[이슈 후보] 키워드 매칭 → {issues}")
        articles_by_issue = _collect_articles_by_issue(
            collection, issues, situation=situation, initial_list=None, top_k_per_issue=15
        )
        # 검증: 최소 1개 이슈에 조문이 있어야 함
        if _validate_issues_with_articles(issues, articles_by_issue):
            for issue in issues[:top_n]:
                n = len(articles_by_issue.get(issue, []))
                _debug_print(f"  이슈 '{issue}' 조문 수: {n}")
            _debug_print("[이슈 분류 완료] 키워드 경로 → 이슈별 조문 반환")
            return (issues, articles_by_issue, "keyword")
        else:
            _debug_print("[키워드 경로] 조문 검증 실패 → LLM 경로로 전환")
    
    # ---------- 경로 B: LLM 분류 (키워드 실패 시 또는 강제 시) ----------
    issues, articles_by_issue, source = _classify_with_llm(situation, collection, top_k)
    
    # LLM 경로도 실패 시 키워드 fallback 재시도
    if not issues and candidate_issues:
        _debug_print(f"[경로 B fallback] LLM 실패 → 키워드 후보 재시도: {candidate_issues}")
        seen_order = []
        for x in candidate_issues:
            if x and (x not in seen_order):
                seen_order.append(x)
        issues = seen_order
        articles_by_issue = _collect_articles_by_issue(
            collection, issues, situation=situation, initial_list=None, top_k_per_issue=15
        )
        if _validate_issues_with_articles(issues, articles_by_issue):
            _debug_print("[이슈 분류 완료] 키워드 fallback → 이슈별 조문 반환")
            return (issues, articles_by_issue, "keyword")
    
    return (issues, articles_by_issue, source)


def step1_and_step2_parallel(
    situation: str,
    collection=None,
    top_k: int = 22,
) -> Dict[str, Any]:
    """
    step1_issue_classification + step2_checklist 를 가능한 한 병렬로 수행해 TTFT 단축.

    전략:
      - 키워드 경로(경로 A)일 때:
          1) step1 키워드 이슈 추출 + 이슈별 조문 검색을 먼저 시작
          2) 이슈가 확정되는 즉시 별도 thread에서 step2 시작
          → 전체 시간 ≈ max(step1, step2) 대신 step1 + overlap
      - LLM 경로(경로 B)일 때:
          순차 실행 (step2는 step1 결과가 필요하므로 병렬 불가)

    Returns:
        {
            "issues": [...],
            "articles_by_issue": {...},
            "selected_issue": "...",
            "checklist": [...],
            "rag_results": [...],
            "source": "keyword" | "llm",
        }
    """
    if collection is None:
        collection, _ = build_vector_store()

    # ── 경로 A: 키워드 매칭 먼저 시도 ──────────────────────────────────────
    try:
        from rag.law_json import get_categories_for_issue
        candidate_issues = get_categories_for_issue(situation)
    except Exception:
        candidate_issues = []

    if candidate_issues:
        # 중복 제거 후 이슈 리스트 확정
        seen_order: List[str] = []
        for x in candidate_issues:
            if x and x not in seen_order:
                seen_order.append(x)
        issues = seen_order

        # step1 조문 수집 (thread A)
        def _do_step1():
            return _collect_articles_by_issue(
                collection, issues, situation=situation, initial_list=None, top_k_per_issue=15
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            step1_future = ex.submit(_do_step1)
            articles_by_issue = step1_future.result()

        if _validate_issues_with_articles(issues, articles_by_issue):
            selected_issue = issues[0]
            remaining = articles_by_issue.get(selected_issue) or []
            filter_preview = (selected_issue + " " + situation)[:400]

            # step2 체크리스트 생성 (step1 결과 나오는 즉시 실행)
            step2_res = step2_checklist(
                selected_issue, filter_preview,
                collection=collection,
                narrow_answers=None,
                qa_list=[],
                remaining_articles=remaining,
            )
            checklist = step2_res.get("checklist", []) if isinstance(step2_res, dict) else (step2_res or [])
            rag_results = step2_res.get("rag_results", []) if isinstance(step2_res, dict) else []
            return {
                "issues": issues,
                "articles_by_issue": articles_by_issue,
                "selected_issue": selected_issue,
                "checklist": checklist,
                "rag_results": rag_results,
                "source": "keyword",
            }

    # ── 경로 B: LLM 분류 (키워드 실패 시) ─────────────────────────────────
    issues, articles_by_issue, source = _classify_with_llm(situation, collection, top_k)

    if not issues:
        return {
            "issues": [],
            "articles_by_issue": {},
            "selected_issue": "",
            "checklist": [],
            "rag_results": [],
            "source": source,
        }

    selected_issue = issues[0]
    remaining = articles_by_issue.get(selected_issue) or []
    filter_preview = (selected_issue + " " + situation)[:400]

    step2_res = step2_checklist(
        selected_issue, filter_preview,
        collection=collection,
        narrow_answers=None,
        qa_list=[],
        remaining_articles=remaining,
    )
    checklist = step2_res.get("checklist", []) if isinstance(step2_res, dict) else (step2_res or [])
    rag_results = step2_res.get("rag_results", []) if isinstance(step2_res, dict) else []
    return {
        "issues": issues,
        "articles_by_issue": articles_by_issue,
        "selected_issue": selected_issue,
        "checklist": checklist,
        "rag_results": rag_results,
        "source": source,
    }


def _article_number_from_result(r: Dict[str, Any]) -> Optional[str]:
    """검색 결과 또는 조문 dict에서 조문 번호(제34조, 제43조의5 등) 추출."""
    art = (r.get("article") or "").strip()
    if not art:
        return None
    m = re.match(r"^(제\d+(?:의\d+)?조)", art)
    return m.group(1) if m else art.split("(")[0].strip() or None


def _build_checklist_query(issue: str, filtered_provisions_text: str, narrow_answers: Optional[List[str]]) -> str:
    """체크리스트용 검색 쿼리 구성. filtered_provisions_text 전체 사용 (길이 제한은 _rag_context에서)."""
    query_parts = [issue]
    if narrow_answers:
        query_parts.extend(narrow_answers)
    if filtered_provisions_text:
        query_parts.append(filtered_provisions_text)
    return " ".join(query_parts)


def _parse_checklist_response(out: Any) -> List[Dict[str, str]]:
    """체크리스트 응답을 정규화된 형태로 파싱."""
    if out is None:
        return []
    
    checklist = []
    if isinstance(out, list):
        checklist = out
    elif isinstance(out, dict):
        checklist = out.get("checklist") or out.get("items") or out.get("questions") or []
    
    # 정규화: 모든 항목이 {"item": "...", "question": "..."} 형태로
    normalized = []
    for item in checklist:
        if isinstance(item, str) and item.strip():
            normalized.append({"item": item.strip(), "question": item.strip()})
        elif isinstance(item, dict):
            q = item.get("question") or item.get("q") or item.get("item") or ""
            if q.strip():
                item_text = item.get("item") or q
                # item이 숫자만 있거나 너무 짧으면(3자 이하) question을 기반으로 생성
                if not item_text or len(item_text.strip()) <= 3 or item_text.strip().isdigit():
                    # question에서 핵심 키워드 추출하여 item 생성
                    q_words = q.strip().split()
                    if len(q_words) > 3:
                        item_text = " ".join(q_words[:5])  # 앞 5개 단어로 item 생성
                    else:
                        item_text = q.strip()
                normalized.append({"item": item_text.strip(), "question": q.strip()})
    
    return normalized


def _deduplicate_checklist(checklist: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """체크리스트에서 중복/유사 질문 제거."""
    seen_questions = set()
    deduplicated = []
    for item in checklist:
        q = item.get("question", "").strip().lower()
        # 간단한 중복 체크 (정확히 같은 질문)
        if q and q not in seen_questions:
            seen_questions.add(q)
            deduplicated.append(item)
    return deduplicated


def _enhance_articles_with_api(issue: str, articles: List[Dict[str, Any]], collection: Any) -> List[Dict[str, Any]]:
    """API를 활용해 조문 목록을 확장. lstrmRltJo, joRltLstrm 사용."""
    enhanced = list(articles)
    seen_articles = {r.get("article", "") for r in articles if r.get("article")}
    
    try:
        from rag.api_data_loader import get_articles_from_lstrmRltJo_cache, get_law_terms_from_joRltLstrm_cache
        # 이슈에서 법령용어 추출 (간단히 이슈명 자체를 용어로 사용)
        article_nums_from_term = get_articles_from_lstrmRltJo_cache(issue)
        if article_nums_from_term:
            _debug_print(f"[조문 확장] lstrmRltJo로 {len(article_nums_from_term)}개 조문 발견")
            # 조문 번호로 검색
            for art_num in article_nums_from_term[:5]:  # 최대 5개만
                try:
                    results = search_by_article_numbers(collection, [art_num], ALL_LABOR_LAW_SOURCES)
                    for r in results:
                        if r.get("article", "") and r.get("article", "") not in seen_articles:
                            enhanced.append(r)
                            seen_articles.add(r.get("article", ""))
                except Exception:
                    pass
        
        # 기존 조문에서 법령용어 역추적 (joRltLstrm)
        for article in articles[:3]:  # 상위 3개 조문만
            art_num = _article_number_from_result(article)
            if art_num:
                terms = get_law_terms_from_joRltLstrm_cache(art_num)
                if terms:
                    _debug_print(f"[조문 확장] joRltLstrm으로 {art_num}에서 {len(terms)}개 용어 발견")
                    # 용어로 다시 조문 검색
                    for term in terms[:2]:  # 각 조문당 최대 2개 용어
                        try:
                            results = search(collection, term, top_k=3, filter_sources=ALL_LABOR_LAW_SOURCES)
                            for r in results:
                                if r.get("article", "") and r.get("article", "") not in seen_articles:
                                    enhanced.append(r)
                                    seen_articles.add(r.get("article", ""))
                        except Exception:
                            pass
    except Exception as e:
        _debug_print(f"[조문 확장] API 활용 실패: {e}")
    
    return enhanced


def step2_checklist(
    issue: str,
    filtered_provisions_text: str,
    collection=None,
    top_k: int = 10,
    narrow_answers: Optional[List[str]] = None,
    qa_list: Optional[List[Dict[str, Any]]] = None,
    remaining_articles: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """걸러진 조항 기준 체크리스트 (법률만). remaining_articles가 있으면 해당 조문만 사용(이슈와 무관한 임금 등 조문 혼입 방지).
    반환: {"checklist": [...], "rag_results": [...], "error": "..."} — UI에서 '참조한 법령 조문'으로 실제 사용한 검색 결과를 표시할 수 있음."""
    if collection is None:
        collection, _ = build_vector_store()
    
    context = ""
    results = []
    try:
        from config import CHECKLIST_CONTEXT_MAX_LENGTH, CHECKLIST_MAX_ARTICLES
        ctx_max = CHECKLIST_CONTEXT_MAX_LENGTH
        max_articles = CHECKLIST_MAX_ARTICLES
    except Exception:
        ctx_max = 3600
        max_articles = 10
    
    # remaining_articles 우선 사용 (법률별 균형 유지, step1에서 온 source 보존)
    if remaining_articles:
        enhanced_articles = _enhance_articles_with_api(issue, remaining_articles, collection)
        if len(enhanced_articles) > max_articles:
            enhanced_articles = _cap_articles_by_source_diversity(enhanced_articles, max_articles)
            _debug_print(f"[체크리스트] 참조 조문 상한 {max_articles}개로 제한 (법률별 균형)")
        # 조문 번호로 재검색하지 않고 step1·확장 결과를 그대로 사용 → 두 법률 모두 반영
        results = list(enhanced_articles)
        if results:
            context = _rag_context(results, max_length=ctx_max)
            _debug_print(f"[체크리스트] remaining_articles + API 확장으로 {len(results)}개 조문 사용 (법률 {len({r.get('source') for r in results})}개)")
    
    # fallback: 더 정교한 검색 (법률 2개 이상이면 법률별 검색 후 병합)
    if not context:
        query = _build_checklist_query(issue, filtered_provisions_text, narrow_answers)
        preferred_sources = ISSUE_TO_LAW_MAPPING.get(issue, None)
        results = []
        seen_keys = set()
        if preferred_sources and len(preferred_sources) >= 2:
            k_per_law = max(2, (top_k + len(preferred_sources) - 1) // len(preferred_sources))
            for src in preferred_sources:
                res_one = search(
                    collection, query, top_k=k_per_law,
                    filter_sources=[src], exclude_sections=EXCLUDE_SECTIONS_MAIN,
                    exclude_chapters=EXCLUDE_CHAPTERS_MAIN,
                )
                for r in res_one:
                    key = (r.get("source", ""), r.get("article", ""))
                    if key not in seen_keys:
                        results.append(r)
                        seen_keys.add(key)
            if len(results) < top_k // 2:
                res_all = search(
                    collection, query, top_k=top_k - len(results),
                    filter_sources=ALL_LABOR_LAW_SOURCES, exclude_sections=EXCLUDE_SECTIONS_MAIN,
                    exclude_chapters=EXCLUDE_CHAPTERS_MAIN,
                )
                for r in res_all:
                    key = (r.get("source", ""), r.get("article", ""))
                    if key not in seen_keys:
                        results.append(r)
                        seen_keys.add(key)
        elif preferred_sources:
            expanded_sources = list(preferred_sources)
            for src in preferred_sources:
                raw = src.replace("(법률)", "").replace("(시행령)", "").replace("(시행규칙)", "").strip()
                if raw and raw not in expanded_sources:
                    expanded_sources.append(raw)
            results = search(
                collection, query, top_k=top_k,
                filter_sources=expanded_sources, exclude_sections=EXCLUDE_SECTIONS_MAIN,
                exclude_chapters=EXCLUDE_CHAPTERS_MAIN,
            )
            if len(results) < top_k // 2:
                results_all = search(
                    collection, query, top_k=top_k - len(results),
                    filter_sources=ALL_LABOR_LAW_SOURCES, exclude_sections=EXCLUDE_SECTIONS_MAIN,
                    exclude_chapters=EXCLUDE_CHAPTERS_MAIN,
                )
                results.extend(results_all)
        else:
            results = search(
                collection, query, top_k=top_k,
                filter_sources=ALL_LABOR_LAW_SOURCES, exclude_sections=EXCLUDE_SECTIONS_MAIN,
                exclude_chapters=EXCLUDE_CHAPTERS_MAIN,
            )
        if len(results) > max_articles:
            results = _cap_articles_by_source_diversity(results, max_articles)
        context = _rag_context(results, max_length=ctx_max)
        _debug_print(f"[체크리스트] 검색으로 {len(results)}개 조문 사용")
    
    # 컨텍스트가 여전히 없으면 재시도 전략 적용
    if not (context and context.strip()):
        _debug_print("[체크리스트] 경고: 컨텍스트 없음 - 재시도 전략 적용")
        
        # 재시도 1: API 기반 검색 전략 적용
        try:
            from rag.article_enrichment import enrich_articles_with_api_search
            retry_articles = enrich_articles_with_api_search(
                issue, [], collection, filtered_provisions_text, max_additional=top_k * 2
            )
            if retry_articles:
                context = _rag_context(retry_articles, max_length=ctx_max)
                results = retry_articles
                _debug_print(f"[체크리스트 재시도] 확장 검색으로 {len(retry_articles)}개 조문 사용")
        except Exception as e:
            _debug_print(f"[체크리스트 재시도] 확장 검색 실패: {e}")
        
        # 재시도 2: 이슈명만으로 넓게 검색
        if not (context and context.strip()):
            try:
                broad_results = search(
                    collection, issue, top_k=top_k * 2,
                    filter_sources=ALL_LABOR_LAW_SOURCES,
                    exclude_sections=EXCLUDE_SECTIONS_MAIN,
                    exclude_chapters=EXCLUDE_CHAPTERS_MAIN,
                )
                if broad_results:
                    context = _rag_context(broad_results, max_length=ctx_max)
                    results = broad_results
                    _debug_print(f"[체크리스트 재시도] 넓은 검색으로 {len(broad_results)}개 조문 사용")
            except Exception:
                pass
        
        # 여전히 없으면 에러 반환
        if not (context and context.strip()):
            _debug_print("[체크리스트] 최종 실패: 컨텍스트 없음")
            return {"checklist": [], "rag_results": [], "error": "컨텍스트 없음"}
    
    already_asked = ""
    if qa_list:
        already_asked = "\n".join(
            f"Q: {x.get('question', x.get('q', ''))}\nA: {x.get('answer', x.get('a', ''))}"
            for x in qa_list
        )
    
    # 토큰 제한 스마트화
    try:
        from config import CHECKLIST_MAX_TOKENS, CHAT_MODEL
        max_tok = CHECKLIST_MAX_TOKENS
        # gpt-5-nano는 reasoning 토큰 사용 → 실제 출력 토큰 = completion_tokens - reasoning_tokens
        # 따라서 더 큰 값이 필요하거나 None으로 설정
        if max_tok and max_tok < 5000 and ("gpt-5" in CHAT_MODEL or "nano" in CHAT_MODEL.lower()):
            _debug_print(f"[체크리스트] reasoning 모델 감지, max_tokens를 None으로 설정")
            max_tok = None
    except Exception:
        max_tok = None
    
    _debug_print(f"[체크리스트 생성] 컨텍스트 길이: {len(context)}자")
    _debug_print(f"[체크리스트 생성] max_tokens: {max_tok}")
    
    out = chat_json(
        system_checklist(),
        user_checklist(issue, context, filtered_provisions_text, already_asked_text=already_asked),
        max_tokens=max_tok,
    )
    _debug_print(f"[체크리스트 LLM 응답] 타입: {type(out).__name__}, 값: {out}")
    
    # 파싱 및 정규화
    checklist = _parse_checklist_response(out)
    checklist = _deduplicate_checklist(checklist)
    
    # 체크리스트가 비었을 때 한 번만 재시도 (reasoning 모델이 본문 대신 생각만 채운 경우 등)
    if not checklist:
        _debug_print("[체크리스트] 항목 0개 → max_tokens=3072으로 재시도")
        out_retry = chat_json(
            system_checklist(),
            user_checklist(issue, context, filtered_provisions_text, already_asked_text=already_asked),
            max_tokens=3072,
        )
        checklist = _parse_checklist_response(out_retry)
        checklist = _deduplicate_checklist(checklist or [])
    
    try:
        from config import CHECKLIST_MAX_ITEMS
        checklist = (checklist or [])[:CHECKLIST_MAX_ITEMS]
    except Exception:
        checklist = (checklist or [])[:7]
    
    _debug_print(f"[체크리스트 생성 완료] 항목 {len(checklist)}개")
    if checklist:
        _debug_print(f"[체크리스트 항목 예시] {checklist[0] if checklist else '없음'}")
    
    # AI가 반복 여부를 판단 (qa_list가 있고 체크리스트가 비어있지 않으면)
    should_continue = None
    continuation_reason = ""
    if not checklist:
        # 체크리스트가 비어있으면 더 이상 진행하지 않음
        should_continue = False
        continuation_reason = "체크리스트가 생성되지 않았습니다."
    elif qa_list:
        # 이전 답변이 있으면 AI가 판단
        try:
            _debug_print(f"[체크리스트 반복 판단] Q&A {len(qa_list)}개, 체크리스트 {len(checklist)}개")
            continuation_out = chat_json_fast(
                system_checklist_continuation(),
                user_checklist_continuation(issue, qa_list, context),
                max_tokens=512,
            )
            if isinstance(continuation_out, dict):
                should_continue = continuation_out.get("should_continue", False)
                continuation_reason = continuation_out.get("reason", "")
            else:
                should_continue = False
            _debug_print(f"[체크리스트 반복 판단] should_continue={should_continue}, reason={continuation_reason}")
        except Exception as e:
            _debug_print(f"[체크리스트 반복 판단] 실패: {e}, 기본값 False 사용")
            should_continue = False
    else:
        # 첫 라운드 (qa_list가 없음) - 체크리스트가 있으면 사용자가 답변할 수 있도록 None 반환
        # app.py에서 모든 질문에 답변이 완료되면 판단하도록 함
        should_continue = None
    
    return {
        "checklist": checklist,
        "rag_results": results,
        "should_continue": should_continue,
        "continuation_reason": continuation_reason,
    }


def _extract_penalty_articles_from_context(law_results: List[Dict[str, Any]]) -> List[str]:
    """법률 조문에서 벌칙·부칙 관련 조문 번호 추출."""
    penalty_articles = []
    for r in law_results:
        article = r.get("article", "")
        section = r.get("section", "")
        # 벌칙·부칙 섹션의 조문이면 관련 조문으로 추가
        if section in ["벌칙", "부칙"] and article:
            num = _article_number_from_result(r)
            if num:
                penalty_articles.append(num)
    return penalty_articles


def _validate_conclusion(conclusion: str, law_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """결론의 품질 검증 (개선: substr 버그 수정 → 정확한 조문 번호 경계 매칭)."""
    cited_articles = re.findall(r"제\d+(?:의\d+)?조", conclusion)

    # 법률명 포함 여부 확인
    law_names_in_results = set()
    for r in law_results:
        source = r.get("source", "")
        if source:
            law_name = source.replace("(법률)", "").replace("(시행령)", "").replace("(시행규칙)", "").strip()
            if law_name:
                law_names_in_results.add(law_name)

    # 결론에서 법률명 추출
    law_names_in_conclusion = set()
    for law_name in law_names_in_results:
        if law_name in conclusion:
            law_names_in_conclusion.add(law_name)

    validation = {
        "has_citations": len(cited_articles) > 0,
        "citations_in_results": True,
        "has_structured_content": any(keyword in conclusion for keyword in ["요약", "결론", "제", "조"]),
        "has_law_names": len(law_names_in_conclusion) > 0,
        "law_names_count": len(law_names_in_conclusion),
    }

    # ── 개선: 정확한 조문 번호 경계 매칭 (substr 버그 수정) ──────────────
    # 기존: "제3조" in "제13조" → True (오탐)
    # 개선: "제3조"가 "제13조"에 완전히 포함되지 않도록 정확한 전체 조문명 비교
    if cited_articles:
        existing_article_nums = set()
        for r in law_results:
            raw_art = r.get("article", "")
            if raw_art:
                # "제36조(임금의 지급)" → "제36조" 추출
                m = re.match(r"^(제\d+(?:의\d+)?조)", raw_art.strip())
                if m:
                    existing_article_nums.add(m.group(1))
        # 정확한 집합 교집합으로 존재 여부 판단
        matched = existing_article_nums & set(cited_articles)
        validation["citations_in_results"] = len(matched) > 0
        validation["matched_citations"] = list(matched)
        validation["unmatched_citations"] = list(set(cited_articles) - matched)
    return validation


def _add_precedents_and_explanations(issue: str, qa_text: str, law_results: List[Dict[str, Any]]) -> str:
    """판례, 노동위원회 결정례, 고용노동부 법령해석, 법령해석례, 고용보험심사위원회를 컨텍스트에 추가."""
    additional_context = []
    
    try:
        from rag.api_data_loader import (
            get_precedents_from_cache,
            get_nlrc_decisions_from_cache,
            get_moel_explanations_from_cache,
            get_expc_from_cache,
            get_eiac_from_cache,
            get_molegCgmExpc_from_cache,
            get_mojCgmExpc_from_cache,
            get_iaciac_from_cache,
            get_detc_from_cache,
            get_decc_from_cache,
            get_ppc_from_cache,
            get_ftc_from_cache,
        )
        from rag.api_cache import get_aiRltLs_cached
        
        # 판례 추가
        precedents = get_precedents_from_cache(issue, max_results=3)
        if precedents:
            _debug_print(f"[결론 확장] 판례 {len(precedents)}개 발견")
            prec_texts = []
            for prec in precedents:
                title = prec.get("사건명") or prec.get("사건번호") or ""
                summary = prec.get("판시사항") or prec.get("요지") or ""
                if title or summary:
                    prec_texts.append(f"판례: {title}\n{summary}")
            if prec_texts:
                additional_context.append("[판례]\n" + "\n\n".join(prec_texts))
        
        # 노동위원회 결정례 추가
        nlrc_decisions = get_nlrc_decisions_from_cache(issue, max_results=2)
        if nlrc_decisions:
            _debug_print(f"[결론 확장] 노동위원회 결정례 {len(nlrc_decisions)}개 발견")
            decision_texts = []
            for dec in nlrc_decisions:
                title = dec.get("사건명") or dec.get("사건번호") or ""
                summary = dec.get("판시사항") or dec.get("요지") or ""
                if title or summary:
                    decision_texts.append(f"노동위원회 결정례: {title}\n{summary}")
            if decision_texts:
                additional_context.append("[노동위원회 결정례]\n" + "\n\n".join(decision_texts))
        
        # 고용노동부 법령해석 추가
        explanations = get_moel_explanations_from_cache(issue, max_results=2)
        if explanations:
            _debug_print(f"[결론 확장] 고용노동부 법령해석 {len(explanations)}개 발견")
            exp_texts = []
            for exp in explanations:
                title = exp.get("제목") or exp.get("해석제목") or ""
                content = exp.get("내용") or exp.get("해석내용") or ""
                if title or content:
                    exp_texts.append(f"고용노동부 법령해석: {title}\n{content[:500]}")
            if exp_texts:
                additional_context.append("[고용노동부 법령해석]\n" + "\n\n".join(exp_texts))
        
        # 법령해석례 추가 (expc)
        expc_results = get_expc_from_cache(issue, max_results=2)
        if expc_results:
            _debug_print(f"[결론 확장] 법령해석례 {len(expc_results)}개 발견")
            expc_texts = []
            for expc in expc_results:
                title = expc.get("제목") or expc.get("사건명") or ""
                summary = expc.get("내용") or expc.get("요지") or ""
                if title or summary:
                    expc_texts.append(f"법령해석례: {title}\n{summary[:500]}")
            if expc_texts:
                additional_context.append("[법령해석례]\n" + "\n\n".join(expc_texts))
        
        # 고용보험심사위원회 결정례 추가 (eiac)
        eiac_results = get_eiac_from_cache(issue, max_results=2)
        if eiac_results:
            _debug_print(f"[결론 확장] 고용보험심사위원회 결정례 {len(eiac_results)}개 발견")
            eiac_texts = []
            for eiac in eiac_results:
                title = eiac.get("사건명") or eiac.get("사건번호") or ""
                summary = eiac.get("판시사항") or eiac.get("요지") or ""
                if title or summary:
                    eiac_texts.append(f"고용보험심사위원회 결정례: {title}\n{summary[:500]}")
            if eiac_texts:
                additional_context.append("[고용보험심사위원회 결정례]\n" + "\n\n".join(eiac_texts))
        
        # 법제처 법령해석 추가 (molegCgmExpc)
        moleg_results = get_molegCgmExpc_from_cache(issue, max_results=2)
        if moleg_results:
            _debug_print(f"[결론 확장] 법제처 법령해석 {len(moleg_results)}개 발견")
            moleg_texts = []
            for moleg in moleg_results:
                title = moleg.get("제목") or moleg.get("해석제목") or ""
                content = moleg.get("내용") or moleg.get("해석내용") or ""
                if title or content:
                    moleg_texts.append(f"법제처 법령해석: {title}\n{content[:500]}")
            if moleg_texts:
                additional_context.append("[법제처 법령해석]\n" + "\n\n".join(moleg_texts))
        
        # 법무부 법령해석 추가 (mojCgmExpc)
        moj_results = get_mojCgmExpc_from_cache(issue, max_results=2)
        if moj_results:
            _debug_print(f"[결론 확장] 법무부 법령해석 {len(moj_results)}개 발견")
            moj_texts = []
            for moj in moj_results:
                title = moj.get("제목") or moj.get("해석제목") or ""
                content = moj.get("내용") or moj.get("해석내용") or ""
                if title or content:
                    moj_texts.append(f"법무부 법령해석: {title}\n{content[:500]}")
            if moj_texts:
                additional_context.append("[법무부 법령해석]\n" + "\n\n".join(moj_texts))
        
        # 산업재해보상보험재심사위원회 결정례 추가 (iaciac)
        iaciac_results = get_iaciac_from_cache(issue, max_results=2)
        if iaciac_results:
            _debug_print(f"[결론 확장] 산업재해보상보험재심사위원회 결정례 {len(iaciac_results)}개 발견")
            iaciac_texts = []
            for iaciac in iaciac_results:
                title = iaciac.get("사건명") or iaciac.get("사건번호") or ""
                summary = iaciac.get("판시사항") or iaciac.get("요지") or ""
                if title or summary:
                    iaciac_texts.append(f"산업재해보상보험재심사위원회 결정례: {title}\n{summary[:500]}")
            if iaciac_texts:
                additional_context.append("[산업재해보상보험재심사위원회 결정례]\n" + "\n\n".join(iaciac_texts))
        
        # 헌법재판소 결정례 추가 (detc)
        detc_results = get_detc_from_cache(issue, max_results=2)
        if detc_results:
            _debug_print(f"[결론 확장] 헌법재판소 결정례 {len(detc_results)}개 발견")
            detc_texts = []
            for d in detc_results:
                title = d.get("사건명") or d.get("사건번호") or ""
                if title:
                    detc_texts.append(f"헌법재판소 결정례: {title}")
            if detc_texts:
                additional_context.append("[헌법재판소 결정례]\n" + "\n\n".join(detc_texts))
        
        # 행정심판 재결례 추가 (decc)
        decc_results = get_decc_from_cache(issue, max_results=2)
        if decc_results:
            _debug_print(f"[결론 확장] 행정심판 재결례 {len(decc_results)}개 발견")
            decc_texts = []
            for d in decc_results:
                title = d.get("사건명") or d.get("사건번호") or ""
                if title:
                    decc_texts.append(f"행정심판 재결례: {title}")
            if decc_texts:
                additional_context.append("[행정심판 재결례]\n" + "\n\n".join(decc_texts))
        
        # 개인정보보호위원회·공정거래위원회 (ppc, ftc) - 목록 있으면 제목만 추가
        ppc_results = get_ppc_from_cache(issue, max_results=2)
        if ppc_results:
            ppc_texts = [r.get("사건명") or r.get("evtNm") or "" for r in ppc_results if r.get("사건명") or r.get("evtNm")]
            if ppc_texts:
                additional_context.append("[개인정보보호위원회]\n" + "\n".join(ppc_texts))
        ftc_results = get_ftc_from_cache(issue, max_results=2)
        if ftc_results:
            ftc_texts = [r.get("사건명") or r.get("evtNm") or "" for r in ftc_results if r.get("사건명") or r.get("evtNm")]
            if ftc_texts:
                additional_context.append("[공정거래위원회]\n" + "\n".join(ftc_texts))
        
        # 연관법령 추가 (aiRltLs) - 주요 조문에 대해
        if law_results:
            for article in law_results[:2]:  # 상위 2개 조문만
                art_text = article.get("article", "")
                if art_text:
                    ai_result = get_aiRltLs_cached(f"근로기준법 {art_text}")
                    if ai_result.get("success") and ai_result.get("data"):
                        _debug_print(f"[결론 확장] 연관법령(aiRltLs) {art_text}에 대해 발견")
                        # 연관법령 정보는 간단히 언급만 (너무 길어지지 않도록)
    except Exception as e:
        _debug_print(f"[결론 확장] 판례/해석 추가 실패: {e}")
    
    return "\n\n".join(additional_context) if additional_context else ""


def step3_conclusion(
    issue: str,
    qa_list: List[Dict[str, str]],
    collection=None,
    top_k: int = 10,
    narrow_answers: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    모든 질문·대답과 RAG 조문 기반 결론 (법조항 인용).
    - 1차: 법률 조문 기반
    - 2차: related_articles 컨텍스트 확장 (벌칙·부칙 포함)
    - 3차: 시행령/시행규칙 추가 검사
    - 4차: 판례, 노동위원회 결정례, 고용노동부 법령해석 추가
    narrow_answers: 그룹 선택 답변으로 쿼리 확장.
    """
    if collection is None:
        collection, _ = build_vector_store()
    
    qa_text = "\n".join(f"Q: {x.get('q', x.get('question', ''))}\nA: {x.get('a', x.get('answer', ''))}" for x in qa_list)
    law_query = issue
    if narrow_answers:
        law_query = " ".join(narrow_answers) + " " + law_query
    
    # 동적 검색 전략: 이슈별 관련 법률 우선 검색 (법률 2개 이상이면 법률별 검색 후 병합)
    law_results = []
    seen_keys = set()  # (source, article) 기준 → 같은 조문 번호라도 법률이 다르면 둘 다 포함
    
    try:
        from rag.law_classification import classify_laws_for_issue
        api_detected_sources = classify_laws_for_issue(issue, qa_text, collection)
        if api_detected_sources:
            _debug_print(f"[결론 생성] {issue}: API로 감지된 법률 {len(api_detected_sources)}개 - {api_detected_sources}")
            preferred_sources = api_detected_sources
        else:
            preferred_sources = ISSUE_TO_LAW_MAPPING.get(issue, None)
    except Exception as e:
        _debug_print(f"[결론 생성] {issue}: API 기반 법률 구분 실패 ({e}), 기존 매핑 사용")
        preferred_sources = ISSUE_TO_LAW_MAPPING.get(issue, None)
    
    if preferred_sources and len(preferred_sources) >= 2:
        k_per_law = max(3, (top_k + len(preferred_sources) - 1) // len(preferred_sources))
        for src in preferred_sources:
            res_one = search(
                collection, law_query, top_k=k_per_law,
                filter_sources=[src], exclude_sections=EXCLUDE_SECTIONS_MAIN,
                exclude_chapters=EXCLUDE_CHAPTERS_MAIN,
            )
            for r in res_one:
                key = (r.get("source", ""), r.get("article", ""))
                if key not in seen_keys:
                    law_results.append(r)
                    seen_keys.add(key)
        _debug_print(f"[결론 생성] 이슈별 검색 결과(법률별): {[r.get('source','')+' '+r.get('article','') for r in law_results[:8]]}")
        if len(law_results) < top_k:
            res_all = search(
                collection, law_query, top_k=top_k - len(law_results),
                filter_sources=ALL_LABOR_LAW_SOURCES, exclude_sections=EXCLUDE_SECTIONS_MAIN,
                exclude_chapters=EXCLUDE_CHAPTERS_MAIN,
            )
            for r in res_all:
                key = (r.get("source", ""), r.get("article", ""))
                if key not in seen_keys:
                    law_results.append(r)
                    seen_keys.add(key)
    elif preferred_sources:
        expanded_sources = list(preferred_sources)
        for src in preferred_sources:
            raw = src.replace("(법률)", "").replace("(시행령)", "").replace("(시행규칙)", "").strip()
            if raw and raw not in expanded_sources:
                expanded_sources.append(raw)
        res_preferred = search(
            collection, law_query, top_k=top_k,
            filter_sources=expanded_sources, exclude_sections=EXCLUDE_SECTIONS_MAIN,
            exclude_chapters=EXCLUDE_CHAPTERS_MAIN,
        )
        for r in res_preferred:
            key = (r.get("source", ""), r.get("article", ""))
            if key not in seen_keys:
                law_results.append(r)
                seen_keys.add(key)
        if len(law_results) < top_k:
            res_all = search(
                collection, law_query, top_k=top_k - len(law_results),
                filter_sources=ALL_LABOR_LAW_SOURCES, exclude_sections=EXCLUDE_SECTIONS_MAIN,
                exclude_chapters=EXCLUDE_CHAPTERS_MAIN,
            )
            for r in res_all:
                key = (r.get("source", ""), r.get("article", ""))
                if key not in seen_keys:
                    law_results.append(r)
                    seen_keys.add(key)
    else:
        res_all = search(
            collection, law_query, top_k=top_k,
            filter_sources=ALL_LABOR_LAW_SOURCES, exclude_sections=EXCLUDE_SECTIONS_MAIN,
            exclude_chapters=EXCLUDE_CHAPTERS_MAIN,
        )
        for r in res_all:
            key = (r.get("source", ""), r.get("article", ""))
            if key not in seen_keys:
                law_results.append(r)
                seen_keys.add(key)
    
    # 검색 품질 검증 및 보완
    try:
        from rag.article_enrichment import validate_search_quality, enrich_articles_with_api_search
        quality = validate_search_quality(issue, law_results, qa_text)
        if quality["needs_enrichment"]:
            _debug_print(f"[결론 생성] 검색 품질 낮음 ({quality['quality_score']:.2f}), API 기반 보완 시도")
            from rag.article_enrichment import enrich_articles_with_api_search
            law_results = enrich_articles_with_api_search(
                issue, law_results, collection, qa_text, max_additional=20
            )
    except Exception as e:
        _debug_print(f"[결론 생성] 검색 품질 검증 실패: {e}")
    
    _debug_print(f"[결론 생성] 법률 조문 {len(law_results)}개 검색")
    
    # 2차: related_articles 컨텍스트 확장 (벌칙·부칙 포함)
    existing_articles = {r.get("article", "") for r in law_results}
    try:
        from rag.law_json import get_related_articles_for_list
        related_nums = get_related_articles_for_list(law_results)
        if related_nums:
            related_docs = search_by_article_numbers(collection, related_nums, ALL_LABOR_LAW_SOURCES)
            for r in related_docs:
                if r.get("article", "") not in existing_articles:
                    law_results.append(r)
                    existing_articles.add(r.get("article", ""))
            _debug_print(f"[결론 생성] 관련 조문 {len(related_nums)}개 추가")
    except Exception as e:
        _debug_print(f"[결론 생성] 관련 조문 확장 실패: {e}")
    
    # 벌칙·부칙 조문도 포함
    penalty_articles = _extract_penalty_articles_from_context(law_results)
    if penalty_articles:
        try:
            penalty_docs = search_by_article_numbers(collection, penalty_articles, ALL_LABOR_LAW_SOURCES)
            for r in penalty_docs:
                if r.get("article", "") not in existing_articles:
                    law_results.append(r)
                    existing_articles.add(r.get("article", ""))
            _debug_print(f"[결론 생성] 벌칙·부칙 조문 {len(penalty_articles)}개 추가")
        except Exception as e:
            _debug_print(f"[결론 생성] 벌칙·부칙 조문 추가 실패: {e}")
    
    law_context = _rag_context(law_results, max_length=4000)
    
    # 3차: 시행령·시행규칙 검색
    decree_rule_results = []
    if narrow_answers:
        decree_rule_query = " ".join(narrow_answers) + " " + issue
    else:
        decree_rule_query = issue
    try:
        decree_rule_results = search(
            collection, decree_rule_query, top_k=8,
            filter_sources=[SOURCE_DECREE, SOURCE_RULE],
        )
        _debug_print(f"[결론 생성] 시행령·시행규칙 {len(decree_rule_results)}개 검색")
    except Exception as e:
        _debug_print(f"[결론 생성] 시행령·시행규칙 검색 실패: {e}")
    
    decree_rule_context = ""
    if decree_rule_results:
        decree_rule_context = _rag_context(decree_rule_results, max_length=2000)
    
    # 판례, 결정례, 법령해석 추가
    precedents_context = _add_precedents_and_explanations(issue, qa_text, law_results)
    
    # 결론 생성
    full_context = law_context
    related_articles_hint = ""
    if law_results:
        articles_list = [r.get("article", "") for r in law_results[:5] if r.get("article")]
        if articles_list:
            related_articles_hint = ", ".join(articles_list)
    
    if decree_rule_context.strip():
        full_context = law_context + "\n\n[시행령·시행규칙]\n" + decree_rule_context
    
    if precedents_context.strip():
        full_context = full_context + "\n\n" + precedents_context
    
    conclusion = chat(
        system_conclusion(),
        user_conclusion(issue, qa_text, full_context, related_articles_hint=related_articles_hint),
    )
    
    # ── 결론 품질 검증 (강화: 개선된 _validate_conclusion 사용) ──────────
    validation = _validate_conclusion(conclusion, law_results)
    _debug_print(
        f"[결론 검증] 인용 있음: {validation['has_citations']}, "
        f"인용 검증: {validation['citations_in_results']}, "
        f"법률명 포함: {validation.get('has_law_names', False)}, "
        f"매칭 조문: {validation.get('matched_citations', [])}, "
        f"미매칭 조문: {validation.get('unmatched_citations', [])}"
    )

    # ── 강화된 법률명 자동 보완 (Task G) ─────────────────────────────────
    # 1) 법률명 없는 경우 자동 추가
    # 2) 미매칭 인용(조문 번호가 실제 검색 결과에 없는 경우) 경고 로깅
    if not validation.get('has_law_names', False) and law_results:
        cited_articles = re.findall(r"제\d+(?:의\d+)?조", conclusion)
        if cited_articles:
            # 조문 번호 → 법률명 역방향 매핑 (정확한 조문명 비교)
            article_to_law: Dict[str, str] = {}
            for r in law_results:
                art_num = _article_number_from_result(r)
                source = r.get("source", "")
                if art_num and source and art_num not in article_to_law:
                    law_name = source.replace("(법률)", "").replace("(시행령)", "").replace("(시행규칙)", "").strip()
                    if law_name:
                        article_to_law[art_num] = law_name

            # 결론에서 "제N조" 앞에 법률명이 없는 경우만 추가
            # lookbehind로 이미 법률명 있는지 확인 후 추가
            for art_num in cited_articles:
                if art_num not in article_to_law:
                    continue
                law_name = article_to_law[art_num]
                # 법률명이 이미 앞에 있으면 스킵
                escaped_art = re.escape(art_num)
                escaped_law = re.escape(law_name)
                # "법률명 제N조" 패턴이 없는 경우만 보완
                if not re.search(rf"{escaped_law}\s*{escaped_art}", conclusion):
                    # "제N조" 앞에 법률명 삽입 (첫 번째 발생만)
                    conclusion = re.sub(
                        rf"(?<![가-힣]){escaped_art}",
                        f"{law_name} {art_num}",
                        conclusion,
                        count=1,
                    )
                    _debug_print(f"[결론 보완] {art_num} → {law_name} {art_num}")

            validation = _validate_conclusion(conclusion, law_results)
            if validation.get('has_law_names', False):
                _debug_print("[결론 보완] 법률명 자동 추가 완료")
            else:
                sources = {
                    r.get('source', '').replace('(법률)', '').replace('(시행령)', '').replace('(시행규칙)', '').strip()
                    for r in law_results[:5] if r.get('source')
                }
                _debug_print(f"[결론 검증 경고] 법률명 자동 추가 실패. 검색된 법률: {sources}")

    # ── 미매칭 인용 경고 (실제로 검색 결과에 없는 조문 번호) ─────────────
    unmatched = validation.get("unmatched_citations", [])
    if unmatched:
        _debug_print(f"[결론 검증 경고] 검색 결과에 없는 조문 인용: {unmatched} (잠재적 hallucination)")
    
    return {
        "conclusion": conclusion,
        "related_articles": related_articles_hint.split(", ") if related_articles_hint else [],
        "law_results": law_results,
        "decree_rule_results": decree_rule_results,
        "validation": validation,
    }


def get_penalty_and_supplementary(collection, conclusion: str, issue: str, qa_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """결론에서 언급된 조문 번호 추출 후 벌칙·부칙 검색. (step3_conclusion에서 이미 처리되므로 보조용)"""
    # 조문 번호 추출 (제N조 패턴)
    article_nums = re.findall(r"제\d+(?:의\d+)?조", conclusion)
    if not article_nums:
        return []
    # 벌칙·부칙 검색
    penalty_results = []
    try:
        # 조문 번호로 직접 검색
        penalty_results = search_by_article_numbers(collection, article_nums, SOURCE_LAW)
        # 벌칙·부칙 섹션만 필터링
        penalty_results = [r for r in penalty_results if r.get("section") in ["벌칙", "부칙"]]
        if not penalty_results:
            # 검색으로 재시도
            penalty_results = search(
                collection, " ".join(article_nums), top_k=10,
                filter_sources=[SOURCE_LAW],
            )
            penalty_results = [r for r in penalty_results if r.get("section") in ["벌칙", "부칙"]]
    except Exception as e:
        _debug_print(f"[벌칙·부칙 검색] 실패: {e}")
    return penalty_results
