# -*- coding: utf-8 -*-
"""
판례·헌재·해석례·위원회·부처해석 키워드별 목록+본문 저장. api_data/precedents/
노동법 핵심 키워드(TERM_SYNC_KEYWORDS)로 검색 후 상위 N건 본문 수집.
봇 차단 방지: rag.law_api_client 사용.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import PRECEDENTS_DATA_DIR
from rag.law_api_client import search_list, get_body
from rag.sync_common import (
    save_json,
    extract_list_from_response,
    extract_id_from_item,
)

from rag.labor_keywords import TERM_SYNC_KEYWORDS

# target별 표시명 (저장 디렉터리명 = target)
PRECEDENT_TARGETS = [
    "prec", "detc", "expc", "decc",
    "nlrc", "eiac", "iaciac", "ppc", "ftc",
    "moelCgmExpc", "molegCgmExpc", "mojCgmExpc",
]
DISPLAY_PER_KEYWORD = 5  # 키워드당 목록 건수
FETCH_BODY_PER_KEYWORD = 2  # 키워드당 본문 요청 건수


def safe_filename(s: str) -> str:
    return "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in s)


def sync_one_target(target: str) -> None:
    import time
    import random
    MAX_RETRIES = 3
    RETRY_DELAY_BASE = 10  # 재시도 전 기본 대기 시간 (초) - 봇 차단 방지
    RETRY_DELAY_RANDOM = 5  # 랜덤 추가 대기 시간
    
    out_base = PRECEDENTS_DATA_DIR / target
    list_dir = out_base / "by_keyword"
    list_dir.mkdir(parents=True, exist_ok=True)
    success_count = 0
    
    for kw in TERM_SYNC_KEYWORDS:
        fname = safe_filename(kw) + ".json"
        list_path = list_dir / fname
        
        # 목록 조회 재시도
        r = None
        for retry in range(MAX_RETRIES):
            try:
                r = search_list(target, query=kw, display=DISPLAY_PER_KEYWORD, page=1)
                if r.get("success"):
                    break
                error_msg = r.get("error", "Unknown")
                if retry < MAX_RETRIES - 1:
                    delay = RETRY_DELAY_BASE + random.uniform(0, RETRY_DELAY_RANDOM)
                    print(f"  [재시도 {retry+1}/{MAX_RETRIES}] {target} query={kw}: {error_msg} ({delay:.1f}초 대기)")
                    time.sleep(delay)
                else:
                    print(f"  [최종 실패] {target} query={kw}: {error_msg}")
            except Exception as e:
                if retry < MAX_RETRIES - 1:
                    delay = RETRY_DELAY_BASE + random.uniform(0, RETRY_DELAY_RANDOM)
                    print(f"  [재시도 {retry+1}/{MAX_RETRIES}] {target} query={kw}: {e} ({delay:.1f}초 대기)")
                    time.sleep(delay)
                else:
                    print(f"  [최종 실패] {target} query={kw}: {e}")
                    r = None
        
        if not r or not r.get("success"):
            print(f"  [건너뜀] {target} query={kw} - 재시도 실패")
            continue
        
        data = r.get("data", {})
        items = extract_list_from_response(data, target)
        # 목록 저장 (전체 응답)
        save_json(list_path, data)
        
        # 상위 N건 본문 저장
        body_dir = out_base / "body"
        body_dir.mkdir(parents=True, exist_ok=True)
        for item in items[:FETCH_BODY_PER_KEYWORD]:
            lid = extract_id_from_item(item, target)
            if not lid:
                continue
            body_path = body_dir / f"{lid}.json"
            if body_path.exists():
                continue
            
            # 본문 조회 재시도
            for retry in range(MAX_RETRIES):
                try:
                    br = get_body(target, lid)
                    if br.get("success"):
                        save_json(body_path, br.get("data", {}))
                        break
                    elif retry < MAX_RETRIES - 1:
                        delay = RETRY_DELAY_BASE + random.uniform(0, RETRY_DELAY_RANDOM)
                        print(f"    [재시도 {retry+1}/{MAX_RETRIES}] {target} ID={lid} ({delay:.1f}초 대기)")
                        time.sleep(delay)
                    else:
                        print(f"    [본문 저장 실패] {target} ID={lid}: {br.get('error', 'Unknown')}")
                except Exception as e:
                    if retry < MAX_RETRIES - 1:
                        delay = RETRY_DELAY_BASE + random.uniform(0, RETRY_DELAY_RANDOM)
                        print(f"    [재시도 {retry+1}/{MAX_RETRIES}] {target} ID={lid}: {e} ({delay:.1f}초 대기)")
                        time.sleep(delay)
                    else:
                        print(f"    [본문 저장 실패] {target} ID={lid}: {e}")
        
        success_count += 1
    
    print(f"  {target}: 키워드 {success_count}/{len(TERM_SYNC_KEYWORDS)}개 저장")


def main():
    print("sync_precedents: 판례·해석·위원회 키워드별 동기화")
    PRECEDENTS_DATA_DIR.mkdir(parents=True, exist_ok=True)
    for target in PRECEDENT_TARGETS:
        sync_one_target(target)
    print("완료: api_data/precedents/")


if __name__ == "__main__":
    main()
