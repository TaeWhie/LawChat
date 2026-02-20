# -*- coding: utf-8 -*-
"""법령·행정규칙 별표·서식(서류) 조회. 국가법령정보 licbyl/admbyl API 사용."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    from rag.law_api_client import search_list
except ImportError:
    search_list = None  # type: ignore


def _extract_items(data: Any, target: str) -> List[Dict[str, Any]]:
    """API 응답에서 목록 추출. 응답 구조에 따라 다양한 키 시도."""
    if not data or not isinstance(data, dict):
        return []
    # 국가법령정보 API: licBylSearch / admBylSearch (camelCase) 루트, 목록은 licbyl/admbyl 키
    root_key = "licBylSearch" if target == "licbyl" else "admBylSearch" if target == "admbyl" else None
    if root_key and root_key in data:
        root = data[root_key]
        if isinstance(root, dict):
            # 실제 API: licbyl / admbyl (소문자) 에 리스트
            it = root.get("licbyl") or root.get("admbyl") or root.get("admrulbyl") or root.get("item") or root.get("items")
            if isinstance(it, list):
                return it
            if isinstance(it, dict):
                return [it]
            for k in ("list", "result", "rows"):
                v = root.get(k)
                if isinstance(v, list):
                    return v
    # 기존 fallback
    for key in (target, "licbyl", "admbyl", "admrulbyl", "result", "items", "list"):
        val = data.get(key)
        if isinstance(val, list):
            return val
        if isinstance(val, dict) and "item" in val:
            it = val["item"]
            return [it] if isinstance(it, dict) else it if isinstance(it, list) else []
    if "별표명" in data or "서식명" in data or "관련행정규칙명" in data or "관련법령명" in data:
        return [data]
    return []


def _item_to_doc(item: Any, source_label: str) -> Optional[Dict[str, str]]:
    """API 항목 하나를 서류 정보 dict로 변환."""
    if not isinstance(item, dict):
        return None
    # 한글 키 + 국가법령정보 API camelCase (bylNm, lawNm 등)
    name = (
        item.get("별표명")
        or item.get("서식명")
        or item.get("별표서식명")
        or item.get("명칭")
        or item.get("title")
        or item.get("bylNm")
        or item.get("bylName")
        or ""
    )
    law_name = (
        item.get("관련법령명")
        or item.get("관련행정규칙명")
        or item.get("관련법령")
        or item.get("lawName")
        or item.get("lawNm")
        or item.get("licNm")
        or item.get("admrulNm")
        or ""
    )
    link = (
        item.get("별표서식파일링크")
        or item.get("별표서식PDF파일링크")
        or item.get("링크")
        or item.get("url")
        or item.get("bylPdfFileLink")
        or ""
    )
    if not name and not law_name:
        return None
    return {
        "name": (name or law_name or "서식").strip(),
        "law_name": str(law_name).strip(),
        "source": source_label,
        "link": str(link).strip(),
    }


# 키워드 -> 법령명 매핑 (API는 법령명 검색 시 유리)
_QUERY_TO_LAW: Dict[str, str] = {
    "퇴직금": "근로기준법",
    "퇴사": "근로기준법",
    "연차": "근로기준법",
    "임금": "근로기준법",
    "최저임금": "최저임금법",
    "육아휴직": "남녀고용평등과 일·가정 양립 지원에 관한 법률",
    "산재": "산업재해보상보험법",
    "산업안전": "산업안전보건법",
    "노조": "노동조합 및 노동관계조정법",
}


def search_documents_for_topic(
    query: str,
    *,
    display: int = 15,
    timeout: Optional[int] = None,
) -> List[Dict[str, str]]:
    """
    주제(퇴직금, 육아휴직 등)에 맞는 법령·행정규칙 별표·서식 목록 조회.
    licbyl(법령 별표·서식) + admbyl(행정규칙 별표·서식) API 사용.
    """
    if not search_list:
        return []
    results: List[Dict[str, str]] = []
    seen: set = set()
    q = (query or "").strip()
    # 키워드에 해당하는 법령명으로 보조 검색 (퇴직금 -> 근로기준법 등). 결과 없을 때만 사용
    fallback_query = _QUERY_TO_LAW.get(q) or (q and len(q) >= 2 and _QUERY_TO_LAW.get(q[:4]))

    for use_query in ([q] + ([fallback_query] if fallback_query and fallback_query != q else [])):
        if not use_query:
            continue
        # search=2: 해당법령검색 (법령명), search=1: 별표서식명 검색. 둘 다 시도해 결과 병합
        for target, label in (("licbyl", "법령 별표·서식"), ("admbyl", "행정규칙 별표·서식")):
            for search_scope in (2, 1):  # 2=법령명, 1=서식명
                try:
                    resp = search_list(
                        target,
                        query=use_query or "*",
                        display=display,
                        output_type="JSON",
                        timeout=timeout,
                        extra_params={"search": search_scope},
                    )
                    if not resp.get("success") or not resp.get("data"):
                        continue
                    data = resp.get("data") or {}
                    items = _extract_items(data, target)
                    for item in items:
                        doc = _item_to_doc(item, label)
                        if not doc:
                            continue
                        key = (doc["name"], doc["law_name"])
                        if key not in seen:
                            seen.add(key)
                            results.append(doc)
                except Exception:
                    continue
        if results:
            break  # 이미 결과 있으면 fallback 불필요

    return results[:20]  # 최대 20개


def format_documents_answer(docs: List[Dict[str, str]], topic: str) -> str:
    """서류 목록을 사용자용 답변 텍스트로 포맷."""
    if not docs:
        return (
            f"'{topic}' 관련하여 제공된 API에서 별표·서식을 찾지 못했습니다. "
            "국가법령정보센터(www.law.go.kr)에서 해당 키워드로 검색해 보시거나, "
            "구체적인 상황을 말씀해 주시면 필요한 서류를 안내해 드리겠습니다."
        )
    lines = [f"**'{topic}' 관련 법령·행정규칙 별표·서식**\n"]
    for i, d in enumerate(docs, 1):
        name = d.get("name") or "서식"
        law = d.get("law_name", "")
        src = d.get("source", "")
        line = f"{i}. {name}"
        if law:
            line += f" ({law})"
        if src:
            line += f" - {src}"
        lines.append(line)
    lines.append("\n※ 상세 서식 파일은 국가법령정보센터(www.law.go.kr)에서 해당 법령·행정규칙을 검색해 확인하실 수 있습니다.")
    return "\n".join(lines)
