# -*- coding: utf-8 -*-
"""계산법/계산 시뮬레이션: 퇴직금·연장근로 RAG+계산 동작 확인."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_core.messages import HumanMessage, AIMessage
from rag.graph import get_graph

def run_query(graph, query: str, label: str) -> dict:
    r = graph.invoke(
        {"messages": [HumanMessage(content=query)]},
        config={"configurable": {"thread_id": f"sim_{label}"}},
    )
    msgs = r.get("messages") or []
    last_ai = ""
    for m in reversed(msgs):
        if isinstance(m, AIMessage) and getattr(m, "content", None):
            last_ai = m.content or ""
            break
    return {
        "phase": r.get("phase"),
        "ai_len": len(last_ai),
        "has_검색된_조문": "검색된 조문" in last_ai or "**검색된 조문**" in last_ai,
        "has_계산_결과": "계산 결과" in last_ai or "**계산 결과**" in last_ai,
        "has_예상_퇴직금": "예상 퇴직금" in last_ai or "퇴직금" in last_ai,
        "has_총_수당": "총 수당" in last_ai,
        "snippet": last_ai[:800] if last_ai else "",
        "full": last_ai,
    }

def main():
    print("Building graph and vector store...")
    graph = get_graph()
    print("OK\n")

    out_path = Path(__file__).resolve().parent / "simulate_calculation_out.txt"
    out_lines = []

    cases = [
        ("1_퇴직금_계산법", "퇴직금 계산법"),
        ("2_퇴직금_실제계산", "2020년 1월 1일 입사 2024년 12월 31일 퇴사 월급 300만원 퇴직금 얼마?"),
        ("3_연장근로_계산법", "연장근로 수당 계산법"),
        ("4_연장근로_실제계산", "8시간 근무하고 2시간 연장했는데 시급 1만원이에요. 수당 얼마 받아야 해요?"),
    ]

    for label, query in cases:
        print("=" * 60)
        print(f"[{label}] {query}")
        print("-" * 60)
        try:
            out = run_query(graph, query, label)
            print("phase:", out["phase"], "| ai_len:", out["ai_len"])
            print("검색된 조문 포함:", out["has_검색된_조문"], "| 계산 결과 포함:", out["has_계산_결과"])
            print("예상 퇴직금/총 수당:", out["has_예상_퇴직금"], out["has_총_수당"])
            print()
            out_lines.append(f"\n{'='*60}\n[{label}]\n{query}\n\nphase={out['phase']} | ai_len={out['ai_len']} | 검색된조문={out['has_검색된_조문']} | 계산결과={out['has_계산_결과']}\n\n{out['full']}")
            snippet_safe = out["snippet"].replace("\u2003", " ").replace("\n", " ")
            for c in ["\U0001f4c5", "\U0001f4b0", "\U0001f4ca", "\U000023f0", "\U0001f319", "\U0001f4cb", "\U0001f4dd"]:
                snippet_safe = snippet_safe.replace(c, "")
            if len(snippet_safe) > 400:
                snippet_safe = snippet_safe[:400] + "..."
            print(snippet_safe)
            if len(out["full"]) > 800:
                print("\n... (이하 생략, 총", len(out["full"]), "자)")
            print()
        except Exception as e:
            print("ERROR:", e)
            out_lines.append(f"\n[{label}] ERROR: {e}")
            import traceback
            traceback.print_exc()
        print()

    if out_lines:
        out_path.write_text("\n".join(out_lines).lstrip(), encoding="utf-8")
        print("Full output written to", out_path)

if __name__ == "__main__":
    main()
