# -*- coding: utf-8 -*-
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from langchain_core.messages import HumanMessage, AIMessage
from rag.graph import get_graph

g = get_graph()
# 시나리오 6: 최저임금 및 수습기간
situation = "이번에 수습으로 들어왔는데 사장님이 수습 기간에는 월급을 조금 깎아도 법적으로 문제가 없다고 하네요. 정말인가요?"
r = g.invoke(
    {"messages": [HumanMessage(content=situation)]},
    config={"configurable": {"thread_id": "scenario_6"}},
)
print("phase:", r.get("phase"))
print("checklist len:", len(r.get("checklist") or []))
msgs = r.get("messages") or []
lines = ["phase: " + str(r.get("phase"))]
for i, m in enumerate(msgs):
    name = type(m).__name__
    c = getattr(m, "content", None) or ""
    lines.append(f"  [{i}] {name} len={len(c)}")
    if c:
        lines.append(c[:600])
ai_content = "\n".join(lines)
out_path = Path(__file__).resolve().parent / "try_query_out.txt"
out_path.write_text(ai_content, encoding="utf-8")
last_ai = ""
for m in reversed(msgs):
    if isinstance(m, AIMessage) and getattr(m, "content", None):
        last_ai = (m.content or "")[:500]
        break
print("last AI len:", len(last_ai))
print("last AI:", repr(last_ai[:200]))
print("Written to", out_path)
