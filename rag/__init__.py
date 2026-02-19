from rag.store import build_vector_store, search
from rag.pipeline import (
    step1_issue_classification,
    step2_checklist,
    step3_conclusion,
    get_penalty_and_supplementary,
    filter_articles_by_issue_relevance,
)
from rag.precedent_query import (
    build_precedent_queries,
    build_precedent_search_keywords,
    build_precedent_ref_articles,
)

# api_cache는 필요할 때만 import (순환 import 방지)
try:
    from rag.api_cache import get_aiSearch_cached, get_aiRltLs_cached
except ImportError:
    # api_cache가 없을 경우를 대비한 fallback
    def get_aiSearch_cached(*args, **kwargs):
        raise NotImplementedError("api_cache module not available")
    def get_aiRltLs_cached(*args, **kwargs):
        raise NotImplementedError("api_cache module not available")

__all__ = [
    "build_vector_store",
    "search",
    "step1_issue_classification",
    "step2_checklist",
    "step3_conclusion",
    "get_penalty_and_supplementary",
    "filter_articles_by_issue_relevance",
    "build_precedent_queries",
    "build_precedent_search_keywords",
    "build_precedent_ref_articles",
    "get_aiSearch_cached",
    "get_aiRltLs_cached",
]
