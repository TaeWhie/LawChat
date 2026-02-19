# -*- coding: utf-8 -*-
"""
용어·연계 API 덤프. api_data/terms/
노동법 핵심 키워드 기준 검색 후 저장. 봇 차단 방지: rag.law_api_client 사용.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import TERMS_DATA_DIR
from rag.law_api_client import search_list
from rag.sync_common import save_json
from rag.labor_keywords import TERM_SYNC_KEYWORDS

# 용어/연계 API target → 검색에 쓸 키워드 (query 또는 일부는 JO)
TERM_TARGETS = [
    ("lstrmAI", "query"),   # 법령용어
    ("dlytrm", "query"),   # 일상용어
    ("lstrmRlt", "query"),  # 법령용어-일상용어 연계 (lawService.do)
    ("dlytrmRlt", "query"), # 일상용어-법령용어 연계 (lawService.do)
    ("lstrmRltJo", "query"), # 법령용어-조문 연계 (이슈→조문 번호 확장용, lawService.do)
]
KEYWORDS = TERM_SYNC_KEYWORDS


def sync_one(target: str, param_type: str, value: str, out_path: Path) -> bool:
    if param_type == "query":
        r = search_list(target, query=value, display=20, page=1)
    else:
        r = search_list(target, jo=value, display=20, page=1)
    if not r.get("success"):
        return False
    save_json(out_path, r.get("data", {}))
    return True


def main():
    print("sync_terms: 용어·연계 데이터 동기화 (노동 키워드 기준)")
    TERMS_DATA_DIR.mkdir(parents=True, exist_ok=True)
    for target, param_type in TERM_TARGETS:
        # 키워드별로 저장 (파일명에 키워드 사용 시 특수문자 제거)
        for kw in KEYWORDS:
            safe = kw.replace(" ", "_")
            out_path = TERMS_DATA_DIR / f"{target}_{safe}.json"
            if sync_one(target, param_type, kw, out_path):
                print(f"  {target} query={kw} -> {out_path.name}")
            else:
                print(f"  [실패] {target} query={kw}")
    # 통합 파일 1개씩 (대표 키워드로)
    for target, param_type in TERM_TARGETS:
        out_path = TERMS_DATA_DIR / f"{target}.json"
        if sync_one(target, param_type, "근로기준법", out_path):
            print(f"  {target} (대표) -> {target}.json")
    print("완료: api_data/terms/")


if __name__ == "__main__":
    main()
