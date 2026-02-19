# -*- coding: utf-8 -*-
"""
노동 관련 법령·행정규칙 목록 조회 후 본문 저장.
api_data/laws/law/, api_data/laws/admrul/
봇 차단 방지: rag.law_api_client 사용 (브라우저 헤더 + 딜레이).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import LAWS_DATA_DIR
from rag.law_api_client import search_list, get_body
from rag.sync_common import save_json, extract_list_from_response, extract_id_from_item, extract_mst_from_law_item

# 노동 관련 법률 목록 (개별적/집단적/노동시장 법률 모두 포함)
LABOR_LAW_QUERIES = [
    # 개별적 근로관계법
    "근로기준법",
    "최저임금법",
    "근로자퇴직급여 보장법",
    "남녀고용평등과 일·가정 양립 지원에 관한 법률",
    "기간제 및 단시간근로자 보호 등에 관한 법률",
    # 집단적 노사관계법
    "노동조합 및 노동관계조정법",
    "근로자참여 및 협력증진에 관한 법률",
    # 노동시장 및 협력적 법률
    "산업안전보건법",
    "고용보험법",
    "직업안정법",
    "산업재해보상보험법",
]

MAX_LIST = 100
MAX_BODY_PER_TARGET = 25


def sync_target(target: str, query: str, out_dir: Path, max_bodies: int) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    list_path = out_dir / "list.json"
    r = search_list(target, query=query, display=MAX_LIST, page=1)
    if not r.get("success"):
        print(f"  [실패] {target} query={query}: {r.get('error', 'Unknown')}")
        return 0
    data = r.get("data", {})
    save_json(list_path, data)
    items = extract_list_from_response(data, target)
    print(f"  {target}: 목록 {len(items)}건 저장, 본문 최대 {max_bodies}건 수집")
    count = 0
    for item in items[:max_bodies]:
        # target=law: 반드시 법령일련번호(MST)가 있어야 함. 없으면 id(1,2,3…)는 응답 순번이라 재외국민등록법 등 엉뚱한 본문이 나옴.
        mst = extract_mst_from_law_item(item) if target == "law" else None
        if target == "law" and not mst:
            continue
        lid = extract_id_from_item(item, target)
        if not lid:
            continue
        save_id = mst if (target == "law" and mst) else lid
        body_path = out_dir / f"{save_id}.json"
        if body_path.exists():
            count += 1
            continue
        if target == "law" and mst:
            br = get_body(target, lid, mst=mst)
        else:
            br = get_body(target, lid)
        if br.get("success"):
            save_json(body_path, br.get("data", {}))
            count += 1
    return count


def main():
    print("sync_laws: 노동 관련 법령·행정규칙 동기화")
    print(f"동기화할 법률: {len(LABOR_LAW_QUERIES)}개")
    law_dir = LAWS_DATA_DIR / "law"
    adm_dir = LAWS_DATA_DIR / "admrul"
    
    total_law = 0
    total_admrul = 0
    
    # 각 법률에 대해 동기화
    for i, query in enumerate(LABOR_LAW_QUERIES, 1):
        print(f"\n[{i}/{len(LABOR_LAW_QUERIES)}] {query} 동기화 중...")
        count_law = sync_target("law", query, law_dir, MAX_BODY_PER_TARGET)
        count_admrul = sync_target("admrul", query, adm_dir, MAX_BODY_PER_TARGET)
        total_law += count_law
        total_admrul += count_admrul
    
    print(f"\n완료: 법률 본문 {total_law}건, 행정규칙 본문 {total_admrul}건 저장 (기존 파일 제외)")


if __name__ == "__main__":
    main()
