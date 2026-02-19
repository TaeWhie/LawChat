# -*- coding: utf-8 -*-
"""
국가법령정보 공동활용 API 전체 테스트
OC 키: 환경변수 LAW_API_OC 또는 아래 OC_KEY
API_checked_items.md의 모든 항목 테스트

헤더는 rag.law_api_client를 사용해 봇 차단을 방지합니다.
"""
import json
import time
from typing import Dict, Any, List

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.law_api_client import search_list, LAW_API_OC

OC_KEY = "xognl427"  # 테스트용 폴백 (config/환경변수 없을 때)

# 테스트할 API 목록 (API_checked_items.md 기준)
TEST_APIS = [
    # 법령
    {"name": "현행법령 목록", "target": "law", "query": "근로기준법", "type": "JSON"},
    {"name": "행정규칙 목록", "target": "admrul", "query": "근로기준법", "type": "JSON"},
    {"name": "법령 별표·서식 목록", "target": "licbyl", "query": "근로기준법", "type": "JSON"},
    {"name": "행정규칙 별표·서식 목록", "target": "admbyl", "query": "근로기준법", "type": "JSON"},
    
    # 판례·해석·심판
    {"name": "판례 목록", "target": "prec", "query": "퇴직금", "type": "JSON"},
    {"name": "헌재결정례 목록", "target": "detc", "query": "근로", "type": "JSON"},
    {"name": "법령해석례 목록", "target": "expc", "query": "근로기준법", "type": "JSON"},
    {"name": "행정심판례 목록", "target": "decc", "query": "근로", "type": "JSON"},
    
    # 위원회
    {"name": "개인정보보호위원회 목록", "target": "ppc", "query": "개인정보", "type": "JSON"},
    {"name": "고용보험심사위원회 목록", "target": "eiac", "query": "고용보험", "type": "JSON"},
    {"name": "공정거래위원회 목록", "target": "ftc", "query": "공정거래", "type": "JSON"},
    {"name": "노동위원회 목록", "target": "nlrc", "query": "해고", "type": "JSON"},
    {"name": "산업재해보상보험재심사위원회 목록", "target": "iaciac", "query": "산재", "type": "JSON"},
    
    # 법령해석 (부처별)
    {"name": "고용노동부 법령해석 목록", "target": "moelCgmExpc", "query": "근로기준법", "type": "JSON"},
    {"name": "법제처 법령해석 목록", "target": "molegCgmExpc", "query": "근로기준법", "type": "JSON"},
    {"name": "법무부 법령해석 목록", "target": "mojCgmExpc", "query": "근로", "type": "JSON"},
    
    # 지능형 법령정보지식베이스
    {"name": "법령용어 조회", "target": "lstrmAI", "query": "임금", "type": "JSON"},
    {"name": "일상용어 조회", "target": "dlytrm", "query": "월급", "type": "JSON"},
    {"name": "관련법령 조회", "target": "lsRlt", "query": "근로기준법", "type": "JSON"},
    {"name": "지능형 검색 API", "target": "aiSearch", "query": "퇴직금", "type": "JSON"},
    {"name": "연관법령 API", "target": "aiRltLs", "query": "근로기준법", "type": "JSON"},
    {"name": "법령용어-일상용어 연계", "target": "lstrmRlt", "query": "임금", "type": "JSON", "use_service": True},
    {"name": "일상용어-법령용어 연계", "target": "dlytrmRlt", "query": "월급", "type": "JSON", "use_service": True},
    {"name": "법령용어-조문 연계", "target": "lstrmRltJo", "query": "청원", "type": "JSON", "use_service": True},  # "임금"은 타임아웃 발생
    {"name": "조문-법령용어 연계", "target": "joRltLstrm", "query": "000200", "type": "JSON", "use_service": True, "use_jo": True},  # 조번호 필요
]

# 본문 조회용 (목록 조회 후 ID 필요)
SERVICE_APIS = [
    {"name": "현행법령 본문", "target": "law"},
    {"name": "판례 본문", "target": "prec"},
    {"name": "법령해석례 본문", "target": "expc"},
    {"name": "헌재결정례 본문", "target": "detc"},
    {"name": "행정심판례 본문", "target": "decc"},
    {"name": "고용노동부 법령해석 본문", "target": "moelCgmExpc"},
    {"name": "법제처 법령해석 본문", "target": "molegCgmExpc"},
    {"name": "법무부 법령해석 본문", "target": "mojCgmExpc"},
    {"name": "개인정보보호위원회 본문", "target": "ppc"},
    {"name": "고용보험심사위원회 본문", "target": "eiac"},
    {"name": "공정거래위원회 본문", "target": "ftc"},
    {"name": "노동위원회 본문", "target": "nlrc"},
    {"name": "산업재해보상보험재심사위원회 본문", "target": "iaciac"},
]


def test_api_search(api_info: Dict[str, Any]) -> Dict[str, Any]:
    """목록 조회 API 테스트 (rag.law_api_client 사용, 브라우저 헤더 자동 적용)"""
    name = api_info["name"]
    target = api_info["target"]
    query = api_info.get("query", "")
    use_jo = api_info.get("use_jo", False)
    oc = LAW_API_OC or OC_KEY

    print(f"\n{'='*70}")
    print(f"테스트: {name}")
    query_display = f"JO={query}" if use_jo else f"query={query}" if query else "query 없음"
    print(f"target: {target}, {query_display}")
    print(f"{'='*70}")

    try:
        result = search_list(
            target,
            query=query if not use_jo else None,
            jo=query if use_jo else None,
            display=3,
            page=1,
            oc=oc,
            timeout=15,
        )
    except ValueError as e:
        print(f"[에러] {e}")
        return {"success": False, "error": str(e), "status_code": None}

    # 아래에서 result 활용 (response 대신 result)
    if not result.get("success"):
        content_type = result.get("content_type", "")
        print(f"응답 Content-Type: {content_type}")
        print(f"응답 상태 코드: {result.get('status_code', 'N/A')}")
        print(f"[실패] {result.get('error', 'Unknown')}")
        if result.get("response_preview"):
            print(f"응답 미리보기: {result['response_preview'][:500]}")
        return result

    content_type = result.get("content_type", "")
    print(f"응답 Content-Type: {content_type}")
    print(f"응답 상태 코드: {result.get('status_code', 'N/A')}")
    data = result.get("data")

    print("[성공] JSON 파싱 성공")
    print(f"응답 키: {list(data.keys()) if isinstance(data, dict) else '리스트'}")

    total_cnt = None
    if isinstance(data, dict):
        for key in data.keys():
            if isinstance(data.get(key), dict):
                total_cnt = data[key].get("totalCnt")
                if total_cnt is not None:
                    print(f"검색 결과 개수: {total_cnt}")
                for k in ["law", "prec", "expc", "detc", "decc", "admrul", "licbyl", "admbyl",
                         "ppc", "eiac", "ftc", "nlrc", "iaciac",
                         "moelCgmExpc", "molegCgmExpc", "mojCgmExpc",
                         "lstrmAI", "dlytrm", "lsRlt", "lstrmRlt", "dlytrmRlt",
                         "lstrmRltJo", "joRltLstrm", "aiSearch", "aiRltLs"]:
                    if k in data[key]:
                        results = data[key][k]
                        if isinstance(results, list) and len(results) > 0:
                            print(f"\n첫 번째 결과 샘플 (키: {k}):")
                            print(json.dumps(results[0], ensure_ascii=False, indent=2)[:800])
                        break
                break

    return {
        "success": True,
        "data": data,
        "status_code": result.get("status_code"),
        "content_type": content_type,
        "total_cnt": total_cnt,
    }


def main():
    print("="*70)
    print("국가법령정보 공동활용 API 전체 테스트")
    print(f"OC 키: {LAW_API_OC or OC_KEY}")
    print(f"총 {len(TEST_APIS)}개 API 테스트")
    print("="*70)
    
    results = {}
    
    # 모든 API 테스트
    for i, api_info in enumerate(TEST_APIS, 1):
        print(f"\n[{i}/{len(TEST_APIS)}] 진행 중...")
        result = test_api_search(api_info)
        results[api_info["name"]] = result
        
        # 서버 부하 방지를 위한 딜레이
        if i < len(TEST_APIS):
            time.sleep(1)
    
    # 요약
    print(f"\n{'='*70}")
    print("테스트 결과 요약")
    print(f"{'='*70}")
    
    success_count = sum(1 for r in results.values() if r.get("success"))
    total_count = len(results)
    
    print(f"총 테스트: {total_count}개")
    print(f"성공: {success_count}개")
    print(f"실패: {total_count - success_count}개")
    print(f"성공률: {success_count/total_count*100:.1f}%")
    
    print(f"\n상세 결과:")
    print(f"{'API 이름':<40} {'상태':<10} {'상태코드':<10} {'비고'}")
    print("-" * 70)
    
    for name, result in results.items():
        status = "[성공]" if result.get("success") else "[실패]"
        status_code = result.get("status_code", "N/A")
        note = ""
        
        if result.get("success"):
            total_cnt = result.get("total_cnt")
            if total_cnt is not None:
                note = f"결과: {total_cnt}건"
        else:
            error = result.get("error", "Unknown")
            note = error[:30] if len(error) > 30 else error
        
        print(f"{name:<40} {status:<10} {str(status_code):<10} {note}")
    
    # 실패한 API 상세 정보
    failed_apis = {name: r for name, r in results.items() if not r.get("success")}
    if failed_apis:
        print(f"\n{'='*70}")
        print("실패한 API 상세 정보")
        print(f"{'='*70}")
        for name, result in failed_apis.items():
            print(f"\n{name}:")
            print(f"  에러: {result.get('error', 'Unknown')}")
            print(f"  상태 코드: {result.get('status_code', 'N/A')}")
            print(f"  Content-Type: {result.get('content_type', 'N/A')}")
            if result.get("response_preview"):
                print(f"  응답 미리보기: {result['response_preview']}")
    
    # 결과를 JSON 파일로 저장
    output_file = "api_test_all_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n상세 결과가 {output_file}에 저장되었습니다.")


if __name__ == "__main__":
    main()
