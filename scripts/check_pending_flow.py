#!/usr/bin/env python3
"""파일 폴백 직접 검증: 저장 경로·직렬화·읽기 확인."""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_core.messages import AIMessage, HumanMessage

# app_chatbot와 동일한 경로·함수 사용
_PENDING_DIR = Path(tempfile.gettempdir()) / "lawchat_pending"


def _json_safe(obj):
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(x) for x in obj]
    return str(obj)


def _serialize_ok_result(r):
    msgs = r.get("messages") or []
    msg_list = []
    for m in msgs:
        c = getattr(m, "content", None) or str(m)
        kind = "AIMessage" if isinstance(m, AIMessage) else "HumanMessage"
        msg_list.append({"t": kind, "c": c})
    raw = {
        "status": "ok",
        "messages": msg_list,
        "phase": r.get("phase"),
        "checklist": r.get("checklist"),
        "selected_issue": r.get("selected_issue"),
        "situation": r.get("situation"),
        "articles_by_issue": r.get("articles_by_issue"),
        "checklist_rag_results": r.get("checklist_rag_results"),
    }
    return _json_safe(raw)


def _deserialize_result(data: dict):
    status = data.get("status", "ok")
    if status == "error":
        return ("error", data.get("error", ""))
    msg_list = data.get("messages") or []
    new_msgs = []
    for x in msg_list:
        if x.get("t") == "AIMessage":
            new_msgs.append(AIMessage(content=x.get("c") or ""))
        else:
            new_msgs.append(HumanMessage(content=x.get("c") or ""))
    result = {
        "messages": new_msgs,
        "phase": data.get("phase"),
        "checklist": data.get("checklist"),
        "selected_issue": data.get("selected_issue"),
        "situation": data.get("situation"),
        "articles_by_issue": data.get("articles_by_issue"),
        "checklist_rag_results": data.get("checklist_rag_results"),
    }
    return ("ok", result)


def main():
    print("1. PENDING_DIR:", _PENDING_DIR)
    print("2. exists:", _PENDING_DIR.exists())

    req_id = "test_req_123"
    p = _PENDING_DIR / f"{req_id}.json"

    # 가짜 결과로 저장
    r = {
        "messages": [AIMessage(content="테스트 응답")],
        "phase": "checklist",
        "checklist": [{"question": "q1"}],
        "selected_issue": "임금",
        "situation": "상황",
        "articles_by_issue": {},
        "checklist_rag_results": [],
    }
    _PENDING_DIR.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(_serialize_ok_result(r), ensure_ascii=False), encoding="utf-8")
    print("3. wrote:", p, "exists:", p.exists())

    # 읽기
    data = json.loads(p.read_text(encoding="utf-8"))
    status, loaded = _deserialize_result(data)
    p.unlink(missing_ok=True)
    print("4. read ok, status:", status, "phase:", loaded.get("phase"), "msg:", (loaded.get("messages") or [])[0].content if loaded.get("messages") else "")
    print("OK")


if __name__ == "__main__":
    main()
