# -*- coding: utf-8 -*-
"""퇴직금 이슈에서 제2조, 제34조, 제36조가 관련도 필터 후 남는지 확인"""
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import SOURCE_LAW, RAG_MAIN_TOP_K, RAG_AUX_TOP_K, RAG_DEF_TOP_K, RAG_FILTER_TOP_K
from rag.store import build_vector_store, search
from rag.law_json import (
    get_related_terms_and_definition_terms,
    filter_and_rank_articles_by_issue,
    rerank_definition_results,
)

def article_numbers(articles):
    out = []
    for r in articles or []:
        m = re.match(r"(제\d+(?:의\d+)?조)", (r.get("article") or ""))
        if m:
            out.append(m.group(1))
    return out

issue = "퇴직금"
situation = "퇴직금을 받지 못했어요"
key_articles = {"제2조", "제34조", "제36조"}

print("퇴직금 이슈 → 제2조, 제34조, 제36조 포함 여부 확인")
print("=" * 50)

terms_tuple, def_tuple = get_related_terms_and_definition_terms(issue)
terms = set(terms_tuple)
def_terms = set(def_tuple)
print(f"관련어(추론): {sorted(terms)[:20]}...")
if def_terms:
    print(f"총칙 용어(정의 검색용): {sorted(def_terms)[:15]}...")

col, _ = build_vector_store()
seen = set()
arts = []
for q in [issue, situation, " ".join(terms)]:
    if not (q or str(q).strip()):
        continue
    res = search(col, q, top_k=RAG_MAIN_TOP_K, filter_sources=[SOURCE_LAW],
                 exclude_sections=["벌칙", "부칙"], exclude_chapters=["제1장 총칙"])
    for r in res:
        a = r.get("article", "")
        if a and a not in seen:
            arts.append(r)
            seen.add(a)
q_extra = f"{issue} {' '.join(terms)}".strip() or issue
res_extra = search(col, q_extra, top_k=RAG_AUX_TOP_K, filter_sources=[SOURCE_LAW], exclude_sections=["벌칙", "부칙"])
for r in res_extra:
    a = r.get("article", "")
    if a and a not in seen:
        arts.append(r)
        seen.add(a)
if def_terms:
    q_def = " ".join(def_terms)
    res_def = search(col, q_def, top_k=RAG_DEF_TOP_K, filter_sources=[SOURCE_LAW], exclude_sections=["벌칙", "부칙"])
    res_def = rerank_definition_results(res_def, def_terms, top_terms=["정의", "평균임금"])
    for r in res_def:
        a = r.get("article", "")
        if a and a not in seen:
            arts.append(r)
            seen.add(a)

before = article_numbers(arts)
print(f"검색만: {len(arts)}개 조문")
print(f"  조문 번호: {before}")

filtered = filter_and_rank_articles_by_issue(issue, arts, top_k=RAG_FILTER_TOP_K)
after = article_numbers(filtered)
print(f"관련도 필터 후: {len(filtered)}개 조문")
print(f"  조문 번호: {after}")

found = key_articles & set(after)
missing = key_articles - set(after)
print()
print("핵심 조문(제2조, 제34조, 제36조):")
for a in sorted(key_articles):
    status = "포함" if a in after else "누락"
    print(f"  {a}: {status}")
if len(found) == 3:
    print("\n결과: 3개 모두 포함됨.")
else:
    print(f"\n결과: {len(found)}/3 포함, 누락: {missing}")
sys.exit(0 if len(found) == 3 else 1)
