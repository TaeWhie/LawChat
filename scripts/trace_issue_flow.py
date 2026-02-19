# -*- coding: utf-8 -*-
"""
이슈 추출·조항 필터링 전 과정을 세부 값과 함께 출력.
- 상황 → 쿼리 확장 → 검색 결과(조항 번호) → LLM 이슈 분류 → 정규화 → 이슈별 조항 → 선택 이슈 조항

사용: python scripts/trace_issue_flow.py [상황문구]
      python scripts/trace_issue_flow.py "퇴직금을 받지 못했어요" --out report.txt
"""
import os
import re
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import SOURCE_LAW
from rag.store import build_vector_store, search
from rag.law_json import (
    get_categories_for_issue,
    get_primary_categories_list,
    normalize_issue_to_primary,
)
from rag.pipeline import step1_issue_classification


def article_number_list(articles):
    """검색 결과 리스트에서 조항 번호(제N조)만 추출."""
    out = []
    for r in articles or []:
        m = re.match(r"(제\d+(?:의\d+)?조)", (r.get("article") or ""))
        if m:
            out.append(m.group(1))
    return out


def run_trace(situation: str, out_file=None):
    def w(s=""):
        line = s if isinstance(s, str) else json.dumps(s, ensure_ascii=False, indent=2)
        print(line)
        if out_file:
            out_file.write(line + "\n")

    w("=" * 70)
    w("이슈·조항 과정 트레이스")
    w("=" * 70)
    w(f"입력 상황: {situation}")
    w()

    collection, _ = build_vector_store()

    # --- 1) 쿼리 확장 (이슈-카테고리 연동) ---
    try:
        cats = get_categories_for_issue(situation)
        query = situation + " " + " ".join(cats) if cats else situation
    except Exception:
        query = situation
        cats = []
    w("[1] 쿼리 확장")
    w(f"  카테고리 추가: {cats}")
    w(f"  최종 쿼리: {query}")
    w()

    # --- 2) 초기 조항 검색 ---
    results = search(
        collection, query, top_k=22,
        filter_sources=[SOURCE_LAW],
        exclude_sections=["벌칙", "부칙"],
        exclude_chapters=["제1장 총칙"],
    )
    initial_arts = article_number_list(results)
    w("[2] 초기 조항 검색 (법률 본칙, 총칙 제외)")
    w(f"  조항 수: {len(results)}")
    w(f"  조항 번호: {initial_arts}")
    if results:
        w("  상위 5건 (거리):")
        for r in results[:5]:
            w(f"    - {r.get('article', '')[:50]} (거리: {r.get('distance', 0):.4f})")
    w()

    # --- 3) 이슈 분류 (step1 내부에서 이슈별 추가 검색까지 수행) ---
    w("[3] 이슈 분류 (LLM + 정규화)")
    try:
        allowed = get_primary_categories_list()
        w(f"  허용 primary_category 목록({len(allowed)}개): {allowed}")
    except Exception:
        pass
    w("  ※ pipeline 상세(LLM 원시응답, raw→norm 매핑, 조항번호)는 stderr에 출력됩니다.")
    w()
    issues, step1_articles, _ = step1_issue_classification(situation, collection=collection)
    w("  → step1 반환값(issues): " + str(issues))
    w()

    if not issues:
        w("이슈 없음. 종료.")
        return

    # --- 4) 이슈별 조항 (step1 반환값 사용, 없으면 검색) ---
    w("[4] 이슈별 조항")
    articles_by_issue = dict(step1_articles) if step1_articles else {}
    for iss in issues[:3]:
        if iss in articles_by_issue and articles_by_issue[iss]:
            continue
        seen = set()
        arts = []
        for q in [iss, situation]:
            res = search(
                collection, q, top_k=18,
                filter_sources=[SOURCE_LAW],
                exclude_sections=["벌칙", "부칙"],
                exclude_chapters=["제1장 총칙"],
            )
            for r in res:
                a = r.get("article", "")
                if a and a not in seen:
                    arts.append(r)
                    seen.add(a)
        articles_by_issue[iss] = arts
        nums = article_number_list(arts)
        w(f"  이슈 '{iss}': 조항 {len(arts)}개")
        w(f"    조항 번호: {nums}")
    w()

    # --- 5) 선택 이슈 조항 (STEP2 타겟 질문 제거됨) ---
    selected = issues[0]
    pre_selected = articles_by_issue.get(selected) or []
    w("[5] 선택 이슈 조항")
    w(f"  선택 이슈: {selected}")
    w(f"  조항 총계: {len(pre_selected)}개")
    w("=" * 70)


if __name__ == "__main__":
    args = list(sys.argv[1:])
    out_path = None
    if "--out" in args:
        i = args.index("--out")
        if i + 1 < len(args):
            out_path = args.pop(i + 1)
        args.pop(i)
    situation = " ".join(args).strip() if args else "퇴직금을 받지 못했어요"

    f = None
    if out_path:
        f = open(out_path, "w", encoding="utf-8")
    try:
        run_trace(situation, out_file=f)
    finally:
        if f:
            f.close()
            print(f"\n보고서 저장: {out_path}", file=sys.stderr)
