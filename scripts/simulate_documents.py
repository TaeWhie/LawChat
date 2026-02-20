# -*- coding: utf-8 -*-
"""서류·서식(licbyl/admbyl) API 및 그래프 시뮬레이션."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

def main():
    out_path = Path(__file__).resolve().parent / "simulate_documents_out.txt"
    out_lines = []

    # 1) API 직접 호출
    print("=" * 60)
    print("[1] API 직접 호출 (search_documents_for_topic)")
    print("=" * 60)
    try:
        from rag.api_documents import search_documents_for_topic, format_documents_answer
        queries = ["퇴직금", "근로기준법", "육아휴직"]
        for q in queries:
            print(f"\n  query: {q}")
            docs = search_documents_for_topic(q, display=5)
            print(f"  -> {len(docs)}건")
            for i, d in enumerate(docs[:3], 1):
                print(f"     {i}. {d.get('name', '')} ({d.get('law_name', '')}) - {d.get('source', '')}")
            if docs:
                answer = format_documents_answer(docs[:5], q)
                out_lines.append(f"\n--- query: {q} ---\n{answer}\n")
    except Exception as e:
        print(f"  오류: {e}")
        out_lines.append(f"API 직접 호출 오류: {e}\n")
        import traceback
        traceback.print_exc()

    # 2) 질문 유형 분류
    print("\n" + "=" * 60)
    print("[2] 질문 유형 분류 (documents 감지)")
    print("=" * 60)
    try:
        from rag.question_classifier import classify_question_type
        test_questions = [
            "퇴직금 받을 때 필요한 서류가 뭔가요?",
            "육아휴직 신청 서식 알려줘",
            "월급 계산법",  # knowledge
            "퇴직금 얼마 받아요?",  # calculation
        ]
        for q in test_questions:
            t = classify_question_type(q)
            print(f"  '{q[:40]}...' -> {t}")
            out_lines.append(f"  '{q}' -> {t}\n")
    except Exception as e:
        print(f"  오류: {e}")
        out_lines.append(f"분류 오류: {e}\n")

    # 3) 그래프 end-to-end (서류 질문)
    print("\n" + "=" * 60)
    print("[3] 그래프 시뮬레이션 (서류 질문)")
    print("=" * 60)
    try:
        from langchain_core.messages import HumanMessage, AIMessage
        from rag.graph import get_graph
        graph = get_graph()
        query = "퇴직금 관련 필요한 서류가 뭔가요?"
        print(f"  query: {query}")
        r = graph.invoke(
            {"messages": [HumanMessage(content=query)]},
            config={"configurable": {"thread_id": "sim_documents_1"}},
        )
        msgs = r.get("messages") or []
        last_ai = ""
        for m in reversed(msgs):
            if isinstance(m, AIMessage) and getattr(m, "content", None):
                last_ai = m.content or ""
                break
        print(f"  phase: {r.get('phase')}")
        print(f"  답변 길이: {len(last_ai)}자")
        if last_ai:
            has_list = "1." in last_ai or "별표" in last_ai or "서식" in last_ai
            print("  목록/서식 포함:", has_list)
            print("  --- 답변 일부 ---")
            try:
                print((last_ai[:600] + ("..." if len(last_ai) > 600 else "")).replace("\u2014", "-"))
            except UnicodeEncodeError:
                print(last_ai[:200], "...")
            out_lines.append(f"\n--- 그래프 답변 ---\n{last_ai}\n")
        else:
            print("  (답변 없음)")
            out_lines.append("그래프 답변 없음\n")
    except Exception as e:
        print(f"  오류: {e}")
        out_lines.append(f"그래프 오류: {e}\n")
        import traceback
        traceback.print_exc()

    out_path.write_text("\n".join(out_lines), encoding="utf-8")
    print(f"\n결과 저장: {out_path}")

if __name__ == "__main__":
    main()
