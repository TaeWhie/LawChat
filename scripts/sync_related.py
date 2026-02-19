# -*- coding: utf-8 -*-
"""
관련법령(lsRlt)·일상용어-법령용어 연계(dlytrmRlt)·조문-법령용어 연계(joRltLstrm) 조회 후 저장. api_data/related/
봇 차단 방지: rag.law_api_client 사용.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import RELATED_DATA_DIR, LAWS_DATA_DIR
from rag.law_api_client import search_list
from rag.sync_common import save_json, load_json, extract_list_from_response
from rag.labor_keywords import TERM_SYNC_KEYWORDS

DEFAULT_QUERY = "근로기준법"
MAX_LIST = 30
# 일상용어 → 법령용어 연계(dlytrmRlt): TERM_SYNC_KEYWORDS와 동일 키워드 + 일상 표현 보강
DLYTRM_QUERIES = list(TERM_SYNC_KEYWORDS) + [
    "월급", "급여", "체불", "야근", "괴롭힘", "통보", "예고",
]
# joRltLstrm(조문→법령용어): API는 JO 파라미터(6자리 조문키). 근로기준법 등 자주 쓰는 조문 번호
JO_ARTICLE_NUMBERS = [
    2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20,
    34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50,
    51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72,
]


def get_law_names_from_sync() -> list:
    """api_data/laws/law/list.json에서 법령명 추출 (중복 제거)."""
    list_path = LAWS_DATA_DIR / "law" / "list.json"
    data = load_json(list_path)
    if not data:
        return []
    items = extract_list_from_response(data, "law")
    names = []
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("법령명한글") or item.get("법령명") or item.get("lawNm")
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


def safe_query_filename(q: str) -> str:
    return "".join(c if c.isalnum() or c in ("_", "-", " ") else "_" for c in q).strip().replace(" ", "_")


def main():
    print("sync_related: 관련법령(lsRlt) + 일상용어-법령용어(dlytrmRlt) 동기화")
    RELATED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    # lsRlt: 관련법령
    queries = get_law_names_from_sync()
    if not queries:
        queries = [DEFAULT_QUERY]
    for q in queries[:10]:
        safe = safe_query_filename(q)
        path = RELATED_DATA_DIR / f"lsRlt_{safe}.json"
        r = search_list("lsRlt", query=q, display=MAX_LIST, page=1)
        if r.get("success"):
            save_json(path, r.get("data", {}))
            print(f"  lsRlt query={q} -> {path.name}")
        else:
            print(f"  [실패] lsRlt query={q}")
    # dlytrmRlt: 일상용어-법령용어 연계 (이슈 정규화·쿼리 확장용)
    seen = set()
    for q in DLYTRM_QUERIES:
        if not (q and q.strip()) or q in seen:
            continue
        seen.add(q)
        safe = safe_query_filename(q)
        path = RELATED_DATA_DIR / f"dlytrmRlt_{safe}.json"
        r = search_list("dlytrmRlt", query=q, display=50, page=1)
        if r.get("success"):
            save_json(path, r.get("data", {}))
            print(f"  dlytrmRlt query={q} -> {path.name}")
        else:
            print(f"  [실패] dlytrmRlt query={q}")
    # joRltLstrm: 조문 번호 → 법령용어 연계 (조문 확장·역추적용)
    for num in JO_ARTICLE_NUMBERS:
        jo_param = f"{num:06d}"
        path = RELATED_DATA_DIR / f"joRltLstrm_{num}.json"
        r = search_list("joRltLstrm", jo=jo_param, display=50, page=1)
        if r.get("success") and r.get("data"):
            save_json(path, r.get("data", {}))
            print(f"  joRltLstrm jo={jo_param} -> {path.name}")
        else:
            print(f"  [실패] joRltLstrm jo={jo_param}")
    print("완료: api_data/related/")


if __name__ == "__main__":
    main()
