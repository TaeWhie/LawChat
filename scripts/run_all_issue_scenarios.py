# -*- coding: utf-8 -*-
"""
각 PRIMARY_ISSUE별로 시나리오 6개를 정의하고, 파이프라인(step1+step2)을 실행해
감지된 이슈와 체크리스트를 수집합니다. 결과는 JSON과 요약 텍스트로 저장됩니다.

실행: python scripts/run_all_issue_scenarios.py

기본 max_workers=4 (429 TPM 방지). CPU/네트워크에 따라 main(max_workers=...)로 조정 가능.
"""
import sys
import json
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import ALL_LABOR_LAW_SOURCES, RAG_MAIN_TOP_K, RAG_FILTER_TOP_K
from rag import (
    build_vector_store,
    step1_issue_classification,
    step2_checklist,
    filter_articles_by_issue_relevance,
)
from rag.store import search
from rag.labor_keywords import PRIMARY_ISSUES

# 이슈별 시나리오 6개 (해당 이슈가 잡히도록 구체적 상황)
SCENARIOS_BY_ISSUE = {
    "임금": [
        "월급을 두 달째 못 받았어요.",
        "포괄임금제라고 야근 수당을 안 준대요.",
        "퇴사했는데 마지막 달 급여를 안 줬어요.",
        "상여금을 약속했는데 안 줬어요.",
        "휴업수당을 한 푼도 못 받았어요.",
        "지연이자를 요구했는데 회사가 무시해요.",
    ],
    "퇴직금": [
        "1년 넘게 다녔는데 퇴직금을 못 받았어요.",
        "회사가 퇴직금 대신 퇴직연금을 안 가입했다고 해요.",
        "퇴사한 지 한 달 넘었는데 퇴직금이 안 들어왔어요.",
        "계약 해지당했는데 퇴직금 계산에서 일부 기간을 빼대요.",
        "퇴직연금 제도로 바꿨는데 기존 근속이 반영 안 됐어요.",
        "사장이 퇴직금을 주겠다고 했다가 말을 바꿨어요.",
    ],
    "해고/징계": [
        "사장님이 내일부터 나오지 말라고 했는데 해고 통지서도 없어요.",
        "정리해고 대상인데 예고 수당을 안 줬어요.",
        "징계위원회 없이 해고당했어요.",
        "권고사직 하라는 압박을 받고 있어요.",
        "해고 예고 기간 없이 당장 나가라고 해요.",
        "정당한 사유 없이 해고 통보를 받았어요.",
    ],
    "근로계약": [
        "근로계약서에 서명하지 말라고 해서 안 썼어요.",
        "기간제로 2년 썼는데 계속 재계약만 해요.",
        "취업규칙을 받아본 적이 없어요.",
        "계약서에 근로조건이 안 적혀 있어요.",
        "회사가 갑자기 계약 해지 통보했는데 사전 통지도 없어요.",
        "단기 알바인데 계약서 없이 일만 시켜요.",
    ],
    "휴일/휴가": [
        "연차휴가를 쓰려고 하니 회사가 거절해요.",
        "주휴일에도 일했는데 수당을 안 줬어요.",
        "5인 미만인데 연차가 없다고 해요.",
        "미사용 연차를 퇴직 시 소멸한다고 해요.",
        "대체공휴일 출근했는데 보상이 없어요.",
        "연차를 쓰면 불이익을 준다고 해요.",
    ],
    "근로시간": [
        "주당 60시간 넘게 일하는데 추가 수당을 못 받고 있어요.",
        "야근을 50시간 했는데 포괄임금제라 수당이 없다고 해요.",
        "휴게시간 없이 연속으로 일하게 해요.",
        "주 52시간 초과 근무하는데 연장 수당이 없어요.",
        "야간 근무 수당을 안 주고 있어요.",
        "휴일 근무했는데 대체휴일도 수당도 없어요.",
    ],
    "직장 내 괴롭힘": [
        "팀장님이 단톡에서 저한테 망신을 줘요.",
        "상사가 계속 욕하고 협박해요.",
        "회사에 괴롭힘 신고했는데 묵살당했어요.",
        "동료가 집단으로 무시하고 따돌려요.",
        "상사가 인격 모독 발언을 반복해요.",
        "괴롭힘 제보 후 배치를 불리하게 바꿨어요.",
    ],
    "근로자 보호": [
        "감봉을 당했는데 사유를 안 알려줘요.",
        "명부에 이름을 올리지 말라고 해요.",
        "재해보상금을 청구하려는데 회사가 거부해요.",
        "임신했다고 해서 해고하겠다고 해요.",
        "산전후 휴가 신청했는데 거절당했어요.",
        "육아기 근로시간 단축을 요청했는데 불이익을 줬어요.",
    ],
    "산재": [
        "일하다가 다쳐서 산재 신청하려는데 사장님이 반대해요.",
        "업무상 재해로 병원에 갔는데 회사가 산재 처리를 안 해줘요.",
        "산재 인정받았는데 요양 급여가 안 나와요.",
        "출퇴근 중 사고 났는데 업무상 재해가 아니라고 해요.",
        "산재 요양 끝났는데 장해급여 신청을 방해해요.",
        "산재 인정 여부를 노동청에 신고하려는데 회사가 협조 안 해요.",
    ],
    "산업안전": [
        "위험한데 작업하라고 해서 거부했더니 징계한다고 해요.",
        "안전장비 없이 고소 작업을 시켜요.",
        "작업중지권을 행사했는데 불이익을 줬어요.",
        "유해물질 다루는 작업인데 보호장비를 안 줘요.",
        "위험 작업 전 안전교육을 받은 적이 없어요.",
        "작업장 위험요소를 개선하라고 했는데 무시해요.",
    ],
    "노조": [
        "노조 가입했다고 승진에서 밀렸어요.",
        "우리 회사에 노조 만들려는데 회사가 방해해요.",
        "단체교섭 요구했는데 무시당했어요.",
        "노조 활동했다고 불리한 배치를 당했어요.",
        "단체협약 위반인데 회사가 이행 안 해요.",
        "파업 참가했다고 징계 위협해요.",
    ],
    "최저임금": [
        "수습 기간이라 최저임금보다 적게 준대요.",
        "아르바이트인데 시급이 최저임금보다 낮아요.",
        "수습 3개월 동안 월급을 깎는다고 해요.",
        "식대를 빼면 최저임금 미만이에요.",
        "주휴수당을 안 줘서 실질 시급이 최저임금 밑이에요.",
        "연차별로 최저임금을 다르게 적용한대요.",
    ],
    "남녀고용평등": [
        "여자라서 채용에서 불리하게 봤대요.",
        "결혼했다고 승진에서 제외됐어요.",
        "성희롱 신고했는데 오히려 불이익을 받았어요.",
        "임신 가능하다고 채용에서 탈락했어요.",
        "육아휴직 썼다고 평가에서 감점했어요.",
        "성희롱 피해자인데 회사가 방치해요.",
    ],
    "육아휴직": [
        "육아휴직 신청했는데 팀장이 복직 후 자리 없다고 협박해요.",
        "육아휴직 복직 후 원래 직무가 아닌 곳으로 배치됐어요.",
        "육아휴직 기간에 급여를 안 줬어요.",
        "육아휴직 반기 단위로만 쓰라고 해요.",
        "육아기 근로시간 단축을 거절당했어요.",
        "육아휴직 복직을 미루라고 압박해요.",
    ],
    "고용보험": [
        "실업급여를 신청했는데 거절당했어요.",
        "회사가 고용보험 가입을 안 해줬어요.",
        "육아휴직 급여를 받으려는데 자격이 안 된다고 해요.",
        "휴업급여를 신청했는데 회사가 서류를 안 내줘요.",
        "고용보험 이중 가입이라며 급여를 거절당했어요.",
        "실업 인정 기간을 짧게 잡아서 급여가 잘렸어요.",
    ],
    "도급·용역대금": [
        "프리랜서인데 돈을 못받았어요.",
        "용역 계약으로 일했는데 대금을 안 줬어요.",
        "도급으로 일했는데 수급인이 이행하지 않아요.",
        "외주 납품했는데 대금 결제를 6개월째 미뤄요.",
        "용역 완료했는데 잔금을 안 줘요.",
        "도급 계약 해지했는데 완료된 부분 대금도 안 줘요.",
    ],
}


def run_one(situation: str, collection):
    """한 상황에 대해 step1 → step2 실행, 감지 이슈와 체크리스트 반환."""
    try:
        issues, articles_by_issue, _, _ = step1_issue_classification(
            situation, collection=collection
        )
        if not issues:
            return {"issues": [], "checklist": [], "error": "이슈 없음"}
        issue = issues[0]
        remaining = list(articles_by_issue.get(issue, []))
        if not remaining:
            seen = set()
            for q in [issue, situation]:
                res = search(
                    collection, q, top_k=RAG_MAIN_TOP_K,
                    filter_sources=ALL_LABOR_LAW_SOURCES,
                    exclude_sections=["벌칙", "부칙"],
                    exclude_chapters=["제1장 총칙"],
                )
                for r in res:
                    art = r.get("article", "")
                    if art and art not in seen:
                        remaining.append(r)
                        seen.add(art)
            remaining = filter_articles_by_issue_relevance(
                issue, remaining, top_k=RAG_FILTER_TOP_K
            )
        filter_text = (situation + " " + issue)[:500]
        step2_res = step2_checklist(
            issue, filter_text, collection=collection,
            narrow_answers=None, qa_list=[], remaining_articles=remaining,
            situation=situation,
        )
        checklist = step2_res.get("checklist", []) or []
        return {
            "issues": issues,
            "primary_issue": issue,
            "checklist": [
                item.get("question") or item.get("item") or str(item)
                for item in checklist
            ],
        }
    except Exception as e:
        return {"issues": [], "checklist": [], "error": str(e)}


def main(max_workers: int = 4):
    """max_workers 기본 4 — 429(TPM) 방지를 위해 8에서 축소. 필요 시 인자로 조정."""
    print("벡터 스토어 로딩 중...")
    collection, _ = build_vector_store()
    print("OK\n")

    # (issue_name, idx, situation) 단위로 전체 작업 리스트 구성
    tasks = []
    for issue_name in PRIMARY_ISSUES:
        scenarios = SCENARIOS_BY_ISSUE.get(issue_name)
        if not scenarios:
            scenarios = [f"{issue_name} 관련 상담이에요."] * 6
        for idx, situation in enumerate(scenarios, 1):
            tasks.append((issue_name, idx, situation))

    print(f"총 {len(tasks)}개 시나리오 테스트를 병렬 실행합니다. (max_workers={max_workers})")

    # 스레드에서 run_one을 실행하고, 결과는 issue_name/idx 기준으로 모은 뒤
    # 메인 스레드에서 JSON/요약 텍스트를 생성한다.
    grouped_results = {}  # {issue_name: {idx: result_dict}}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_key = {}
        for issue_name, idx, situation in tasks:
            future = executor.submit(run_one, situation, collection)
            future_to_key[future] = (issue_name, idx, situation)

        for future in as_completed(future_to_key):
            issue_name, idx, situation = future_to_key[future]
            try:
                result = future.result()
            except Exception as e:  # 방어적인 예외 처리 (여기까지 오면 거의 없겠지만)
                result = {"issues": [], "checklist": [], "error": str(e)}
            result["situation"] = situation

            issue_bucket = grouped_results.setdefault(issue_name, {})
            issue_bucket[idx] = result

    # 모아둔 결과를 PRIMARY_ISSUES 순서와 시나리오 인덱스 순서에 맞게 정렬해
    # all_results / summary_lines를 생성한다.
    all_results = {}
    summary_lines = []

    for issue_name in PRIMARY_ISSUES:
        scenarios = SCENARIOS_BY_ISSUE.get(issue_name)
        if not scenarios:
            scenarios = [f"{issue_name} 관련 상담이에요."] * 6

        summary_lines.append("")
        summary_lines.append("=" * 70)
        summary_lines.append(f"## 이슈: {issue_name}")
        summary_lines.append("=" * 70)

        issue_bucket = grouped_results.get(issue_name, {})
        all_results[issue_name] = []

        for idx, situation in enumerate(scenarios, 1):
            result = issue_bucket.get(idx)
            if result is None:
                # 이론상 없을 수 없지만, 방어적으로 기본 값을 넣어둔다.
                result = {"issues": [], "checklist": [], "error": "결과 없음", "situation": situation}
            all_results[issue_name].append(result)

            summary_lines.append("")
            summary_lines.append(f"### 시나리오 {idx}: {situation}")
            summary_lines.append(f"  감지 이슈: {result.get('issues', [])}")
            if result.get("error"):
                summary_lines.append(f"  오류: {result['error']}")
            else:
                summary_lines.append("  체크리스트:")
                for i, q in enumerate(result.get("checklist", []), 1):
                    summary_lines.append(f"    {i}. {q}")

    out_dir = ROOT / "scripts"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"issue_scenarios_result_{ts}.json"
    txt_path = out_dir / f"issue_scenarios_result_{ts}.txt"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(summary_lines))

    print("\n저장 완료:")
    print(f"  JSON: {json_path}")
    print(f"  요약: {txt_path}")
    return all_results, summary_lines


if __name__ == "__main__":
    results, summary = main()
    print("\n" + "\n".join(summary))
