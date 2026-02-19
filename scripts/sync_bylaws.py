# -*- coding: utf-8 -*-
"""
별표/서식 목록 저장. api_data/bylaws/
licbyl(법령 별표/서식), admbyl(행정규칙 별표/서식). 봇 차단 방지: rag.law_api_client 사용.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import BYLAWS_DATA_DIR
from rag.law_api_client import search_list
from rag.sync_common import save_json

QUERY = "근로기준법"
MAX_LIST = 50


def main():
    print("sync_bylaws: 별표/서식 목록 동기화")
    BYLAWS_DATA_DIR.mkdir(parents=True, exist_ok=True)
    for target in ("licbyl", "admbyl"):
        r = search_list(target, query=QUERY, display=MAX_LIST, page=1)
        path = BYLAWS_DATA_DIR / f"{target}_list.json"
        if r.get("success"):
            save_json(path, r.get("data", {}))
            print(f"  {target} -> {path.name}")
        else:
            print(f"  [실패] {target}: {r.get('error', 'Unknown')}")
    print("완료: api_data/bylaws/")


if __name__ == "__main__":
    main()
