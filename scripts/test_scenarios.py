# -*- coding: utf-8 -*-
"""
노동법 챗봇 시나리오 테스트 스크립트
10개 시나리오를 자동으로 테스트하고 결과를 분석합니다.

[왜 여기서는 되는데 Streamlit에서는 안 되나요?]
- 여기: 같은 프로세스에서 step1 → step2 → step3 를 직접 호출하고, 반환값을 바로 받습니다.
- Streamlit: 브라우저 제출 → 서버가 백그라운드 스레드로 graph.invoke() 실행 → 결과를
  메모리(_pending_result) 또는 파일(.streamlit_pending/)에 넣고, 다음 rerun에서 꺼내 씁니다.
  그 '다음 rerun'이 다른 워커 프로세스로 가면 메모리는 비어 있어서 결과를 못 찾습니다.
  그래서 app_chatbot.py 에서는 파일 폴백을 두어, 스레드가 끝나면 파일에도 쓰고,
  폴링 시 메모리에 없으면 파일에서 읽도록 했습니다. Streamlit 재시작 후 적용됩니다.
"""
import sys
from pathlib import Path
import json
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_core.messages import HumanMessage, AIMessage

from rag import (
    build_vector_store,
    step1_issue_classification,
    step2_checklist,
    step3_conclusion,
)
from rag.store import search_by_article_numbers

# 테스트 시나리오 정의
SCENARIOS = [
    {
        "id": 1,
        "name": "부당해고 및 해고 예고",
        "situation": "방금 사장님이 내일부터 나오지 말래요. 이유도 제대로 안 알려줬고 서류 한 장 안 줬는데, 이거 그냥 받아들여야 하나요?",
        "expected_articles": ["제23조", "제26조", "제27조"],
        "expected_laws": ["근로기준법"],
        "expected_issues": ["해고/징계"],
    },
    {
        "id": 2,
        "name": "직장 내 괴롭힘",
        "situation": "팀장님이 단톡방에서 저한테 '머리가 나쁘냐'며 대놓고 망신을 줘요. 회사에 말해도 모른 척하는데 어떻게 해야 하죠?",
        "expected_articles": ["제76조의2", "제76조의3"],
        "expected_laws": ["근로기준법"],
        "expected_issues": ["괴롭힘"],
    },
    {
        "id": 3,
        "name": "임금 체불 및 퇴직금 지급 기한",
        "situation": "퇴사한 지 20일이 넘었는데 사장님이 돈을 안 줘요. 새 알바 올 때까지 기다리라는데 법적으로 문제없나요?",
        "expected_articles": ["제36조"],
        "expected_laws": ["근로기준법", "근로자퇴직급여 보장법"],
        "expected_issues": ["퇴직금", "임금"],
    },
    {
        "id": 4,
        "name": "포괄임금제와 연장근로 수당",
        "situation": "저희 회사는 포괄임금제라 야근 수당을 못 준대요. 근데 매달 야근을 50시간 넘게 하거든요. 정말 한 푼도 못 받나요?",
        "expected_articles": ["제56조"],
        "expected_laws": ["근로기준법"],
        "expected_issues": ["근로시간", "임금"],
    },
    {
        "id": 5,
        "name": "5인 미만 사업장 적용 범위",
        "situation": "5인 미만 사업장은 원래 연차 휴가가 없나요? 빨간 날 일해도 시급은 똑같이 받는데 이게 맞나요?",
        "expected_articles": ["제11조"],
        "expected_laws": ["근로기준법"],
        "expected_issues": ["휴일/휴가"],
    },
    {
        "id": 6,
        "name": "최저임금 및 수습기간",
        "situation": "이번에 수습으로 들어왔는데 사장님이 수습 기간에는 월급을 조금 깎아도 법적으로 문제가 없다고 하네요. 정말인가요?",
        "expected_articles": ["제5조"],
        "expected_laws": ["최저임금법"],
        "expected_issues": ["최저임금"],
    },
    {
        "id": 7,
        "name": "육아휴직 및 불이익 금지",
        "situation": "육아휴직 신청하려고 하는데 팀장님이 복직 후에 제 자리가 없을 수도 있다고 협박해요. 이거 불법 아닌가요?",
        "expected_articles": ["제19조"],
        "expected_laws": ["남녀고용평등과 일·가정 양립 지원에 관한 법률"],
        "expected_issues": ["육아휴직"],
    },
    {
        "id": 8,
        "name": "산재 신청 및 사업주 동의",
        "situation": "일하다가 다쳐서 산재 신청 하려는데 사장님이 절대 안 된다고 화를 내요. 사장님 동의 없으면 신청 못 하나요?",
        "expected_articles": ["제37조"],
        "expected_laws": ["산업재해보상보험법"],
        "expected_issues": ["산재"],
    },
    {
        "id": 9,
        "name": "산업안전 및 작업중지권",
        "situation": "바람이 너무 심하게 불어서 작업하기 위험한데 반장님이 계속 올라가라고 해요. 제가 작업을 거부하면 징계받나요?",
        "expected_articles": ["제52조"],
        "expected_laws": ["산업안전보건법"],
        "expected_issues": ["산업안전"],
    },
    {
        "id": 10,
        "name": "노동조합 가입 및 불이익",
        "situation": "우리 회사 사람들과 노조를 만들려고 하는데 회사가 알면 승진도 안 시켜주고 괴롭힐 것 같아요. 보호받을 수 있나요?",
        "expected_articles": ["제81조"],
        "expected_laws": ["노동조합 및 노동관계조정법"],
        "expected_issues": ["노조"],
    },
]


def test_scenario(scenario: dict, collection) -> dict:
    """단일 시나리오 테스트"""
    print(f"\n{'='*80}")
    print(f"[시나리오 {scenario['id']}] {scenario['name']}")
    print(f"상황: {scenario['situation']}")
    print(f"{'='*80}")
    
    result = {
        "scenario_id": scenario["id"],
        "scenario_name": scenario["name"],
        "situation": scenario["situation"],
        "step1": {},
        "step2": {},
        "step3": {},
        "issues": [],
        "checklist": [],
        "conclusion": "",
        "found_articles": [],
        "found_laws": [],
        "missing_articles": [],
        "missing_laws": [],
        "score": 0,
    }
    
    try:
        # Step 1: 이슈 분류
        print("\n[Step 1] 이슈 분류 중...")
        issues, articles_by_issue, source = step1_issue_classification(
            scenario["situation"], collection=collection
        )
        result["step1"] = {
            "issues": issues,
            "source": source,
            "articles_by_issue": {k: len(v) for k, v in articles_by_issue.items()},
        }
        result["issues"] = issues
        
        if not issues:
            print("  [실패] 이슈 분류 실패")
            return result
        
        print(f"  [성공] 이슈 분류 성공: {issues}")
        
        # 이슈 검증
        expected_issues = scenario.get("expected_issues", [])
        found_issues = [i for i in expected_issues if any(e in i or i in e for e in issues)]
        if found_issues:
            print(f"  [성공] 예상 이슈 발견: {found_issues}")
        else:
            print(f"  [경고] 예상 이슈 미발견. 예상: {expected_issues}, 실제: {issues}")
        
        # Step 2: 체크리스트 생성
        issue = issues[0]
        print(f"\n[Step 2] 체크리스트 생성 중... (이슈: {issue})")
        
        # 이슈별 조문 사용
        remaining = list(articles_by_issue.get(issue, []))
        if not remaining:
            print("  ⚠️ 이슈별 조문 없음, 검색으로 보완")
            remaining = []
        
        filter_preview = scenario["situation"][:400]
        step2_res = step2_checklist(
            issue, filter_preview, collection=collection,
            narrow_answers=None,
            qa_list=[],
            remaining_articles=remaining,
        )
        checklist = step2_res.get("checklist", []) or []
        result["step2"] = {
            "checklist_count": len(checklist),
            "checklist": checklist,
        }
        result["checklist"] = checklist
        
        if checklist:
            print(f"  [성공] 체크리스트 생성 성공: {len(checklist)}개")
            for i, item in enumerate(checklist[:3], 1):
                q = item.get("question", item.get("item", ""))
                print(f"    {i}. {q[:60]}...")
        else:
            print("  [실패] 체크리스트 생성 실패")
        
        # Step 3: 결론 생성 (체크리스트 답변 시뮬레이션)
        print(f"\n[Step 3] 결론 생성 중...")
        
        # 체크리스트에 대한 답변 시뮬레이션 (모두 "네"로 가정)
        qa_list = []
        for item in checklist:
            q = item.get("question", item.get("item", ""))
            qa_list.append({"question": q, "answer": "네"})
        
        if not qa_list:
            # 체크리스트가 없으면 상황만으로 결론 생성
            qa_list = [{"question": scenario["situation"], "answer": "해당 상황입니다"}]
        
        step3_res = step3_conclusion(
            issue, qa_list, collection=collection, narrow_answers=None
        )
        conclusion = step3_res.get("conclusion", "")
        law_results = step3_res.get("law_results", [])
        
        result["step3"] = {
            "conclusion_length": len(conclusion),
            "law_results_count": len(law_results),
        }
        result["conclusion"] = conclusion
        
        # 조문 및 법률 검증
        found_articles = []
        found_laws = []
        
        # 결론에서 조문 번호 추출
        import re
        article_pattern = r"제\d+(?:의\d+)?조"
        mentioned_articles = re.findall(article_pattern, conclusion)
        result["found_articles"] = mentioned_articles
        
        # 법률명 추출 (더 정확하게)
        conclusion_lower = conclusion.lower()
        for law_name in scenario.get("expected_laws", []):
            # 법률명의 다양한 형태로 검색
            law_variants = [
                law_name,
                law_name.replace(" 및 ", " ").replace("에 관한 법률", "").replace("법률", ""),
                law_name.split("(")[0] if "(" in law_name else law_name,
            ]
            for variant in law_variants:
                if variant and len(variant) > 2:
                    # 결론에서 법률명 찾기 (부분 매칭도 허용)
                    if variant in conclusion or variant in conclusion_lower:
                        if law_name not in found_laws:
                            found_laws.append(law_name)
                        break
        
        # 추가: RAG 컨텍스트에서 법률명 추출 (결론에 없어도 검색 결과에 있으면 인정)
        if not found_laws and law_results:
            for r in law_results[:5]:
                source = r.get("source", "")
                if source:
                    law_name_from_source = source.replace("(법률)", "").replace("(시행령)", "").replace("(시행규칙)", "").strip()
                    for expected_law in scenario.get("expected_laws", []):
                        if expected_law in law_name_from_source or law_name_from_source in expected_law:
                            if expected_law not in found_laws:
                                found_laws.append(expected_law)
        
        result["found_laws"] = found_laws
        
        # 누락된 조문/법률 확인
        expected_articles = scenario.get("expected_articles", [])
        missing_articles = []
        for exp_art in expected_articles:
            if not any(exp_art in art or art in exp_art for art in mentioned_articles):
                missing_articles.append(exp_art)
        result["missing_articles"] = missing_articles
        
        expected_laws = scenario.get("expected_laws", [])
        missing_laws = [law for law in expected_laws if law not in found_laws]
        result["missing_laws"] = missing_laws
        
        # 점수 계산
        score = 0
        if issues:
            score += 20
        if checklist:
            score += 20
        if conclusion:
            score += 20
        if found_articles:
            score += min(20, len(found_articles) * 5)
        if found_laws:
            score += min(20, len(found_laws) * 10)
        
        result["score"] = score
        
        print(f"  [성공] 결론 생성 성공 ({len(conclusion)}자)")
        print(f"  [점수] {score}/100")
        
        # 검증 결과 출력
        if found_articles:
            print(f"  [발견] 조문: {found_articles}")
        if missing_articles:
            print(f"  [누락] 조문: {missing_articles}")
        if found_laws:
            print(f"  [발견] 법률: {found_laws}")
        if missing_laws:
            print(f"  [누락] 법률: {missing_laws}")
        
    except Exception as e:
        print(f"  [오류] {e}")
        import traceback
        traceback.print_exc()
        result["error"] = str(e)
    
    return result


def test_scenario_via_graph(scenario: dict, graph) -> dict:
    """Streamlit과 동일한 graph.invoke() 경로로 시나리오 검증. 통과 조건: 체크리스트 또는 결론이 나와야 함."""
    sid = scenario["id"]
    name = scenario["name"]
    situation = scenario["situation"]
    result = {
        "scenario_id": sid,
        "scenario_name": name,
        "situation": situation,
        "passed": False,
        "phase": None,
        "ai_content_len": 0,
        "checklist_len": 0,
        "error": None,
    }
    try:
        r = graph.invoke(
            {"messages": [HumanMessage(content=situation)]},
            config={"configurable": {"thread_id": f"scenario_{sid}"}},
        )
        phase = r.get("phase") or "input"
        result["phase"] = phase
        msgs = r.get("messages") or []
        ai_content = ""
        for m in reversed(msgs):
            if isinstance(m, AIMessage) and getattr(m, "content", None):
                ai_content = (m.content or "").strip()
                break
        result["ai_content_len"] = len(ai_content)
        checklist = r.get("checklist") or []
        result["checklist_len"] = len(checklist)
        # 통과: phase가 checklist(체크리스트 있음) 또는 conclusion이고, AI 응답이 충분히 있음
        if phase == "checklist" and checklist and len(ai_content) >= 30:
            result["passed"] = True
        elif phase == "conclusion" and len(ai_content) >= 50:
            result["passed"] = True
        elif phase == "input" and len(ai_content) >= 80 and "이슈를 찾지 못했습니다" not in ai_content and "상담" not in ai_content[:100]:
            # 지식/계산 질문으로 바로 답한 경우도 통과로 인정 (유의미한 답변)
            result["passed"] = True
    except Exception as e:
        result["error"] = str(e)
    return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description="노동법 챗봇 시나리오 테스트")
    parser.add_argument("--graph", action="store_true", help="Streamlit과 동일한 graph.invoke() 경로로 검증")
    args = parser.parse_args()

    print("="*80)
    print("노동법 챗봇 시나리오 테스트")
    print(f"총 {len(SCENARIOS)}개 시나리오")
    if args.graph:
        print("[모드] graph 경로 (Streamlit 동일)")
    print("="*80)

    if args.graph:
        from rag.graph import get_graph
        print("\n그래프 로드 중...")
        graph = get_graph()
        print("[OK] 그래프 준비 완료\n")
        results = []
        for scenario in SCENARIOS:
            print(f"[시나리오 {scenario['id']}] {scenario['name']} ... ", end="", flush=True)
            result = test_scenario_via_graph(scenario, graph)
            results.append(result)
            status = "PASS" if result["passed"] else "FAIL"
            print(f"{status} (phase={result['phase']}, ai_len={result['ai_content_len']}, checklist={result['checklist_len']})")
            if result.get("error"):
                print(f"    error: {result['error']}")
        # 요약
        passed = sum(1 for r in results if r["passed"])
        print("\n" + "="*80)
        print(f"graph 경로 결과: {passed}/{len(SCENARIOS)} 통과")
        print("="*80)
        for r in results:
            if not r["passed"]:
                print(f"  [FAIL] {r['scenario_id']}: {r['scenario_name']} phase={r['phase']} ai_len={r['ai_content_len']}")
        sys.exit(0 if passed == len(SCENARIOS) else 1)

    # 벡터 스토어 준비 (기존 파이프라인 테스트)
    print("\n벡터 스토어 준비 중...")
    collection, _ = build_vector_store()
    print("[OK] 벡터 스토어 준비 완료\n")

    # 각 시나리오 테스트
    results = []
    for scenario in SCENARIOS:
        result = test_scenario(scenario, collection)
        results.append(result)
    
    # 결과 요약
    print("\n" + "="*80)
    print("테스트 결과 요약")
    print("="*80)
    
    total_score = 0
    for result in results:
        score = result.get("score", 0)
        total_score += score
        if score >= 60:
            status = "[PASS]"
        elif score >= 40:
            status = "[WARN]"
        else:
            status = "[FAIL]"
        print(f"{status} 시나리오 {result['scenario_id']}: {result['scenario_name']} - {score}/100점")
        if result.get("missing_articles"):
            print(f"    누락 조문: {result['missing_articles']}")
        if result.get("missing_laws"):
            print(f"    누락 법률: {result['missing_laws']}")
    
    avg_score = total_score / len(results) if results else 0
    print(f"\n평균 점수: {avg_score:.1f}/100")
    
    # 결과를 JSON 파일로 저장
    output_file = f"scenario_test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({
            "test_date": datetime.now().isoformat(),
            "total_scenarios": len(SCENARIOS),
            "average_score": avg_score,
            "results": results,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n상세 결과가 {output_file}에 저장되었습니다.")
    
    # 개선 사항 제안
    print("\n" + "="*80)
    print("개선 사항 분석")
    print("="*80)
    
    missing_laws_count = {}
    missing_articles_count = {}
    
    for result in results:
        for law in result.get("missing_laws", []):
            missing_laws_count[law] = missing_laws_count.get(law, 0) + 1
        for art in result.get("missing_articles", []):
            missing_articles_count[art] = missing_articles_count.get(art, 0) + 1
    
    if missing_laws_count:
        print("\n[누락] 자주 누락되는 법률:")
        for law, count in sorted(missing_laws_count.items(), key=lambda x: x[1], reverse=True):
            print(f"  - {law}: {count}회")
    
    if missing_articles_count:
        print("\n[누락] 자주 누락되는 조문:")
        for art, count in sorted(missing_articles_count.items(), key=lambda x: x[1], reverse=True):
            print(f"  - {art}: {count}회")


if __name__ == "__main__":
    main()
