# -*- coding: utf-8 -*-
"""챗봇이 답변할 수 있는 기능(유형) 정의. 관련 질문 추천·필터에 사용."""

from typing import List, Dict, Any

# 답변 가능한 질문 유형. 기능 추가 시 여기에 항목만 추가하면 관련 질문에도 반영됨.
# id는 question_classifier.classify_question_type() 반환값과 일치시킴.
CHATBOT_CAPABILITIES: List[Dict[str, Any]] = [
    {
        "id": "knowledge",
        "name_ko": "정보·개념",
        "description_ko": "법률 용어, 정의, 개념, 적용 범위, 계산 방법/기준 등 지식 질문",
    },
    {
        "id": "calculation",
        "name_ko": "계산",
        "description_ko": "퇴직금·연장근로 수당 등 금액/기간 계산 (입사일·퇴사일·임금 등 구체 수치가 있으면 계산 가능)",
    },
    {
        "id": "situation",
        "name_ko": "상황 상담",
        "description_ko": "직장에서 겪은 구체적 상황을 말하면 체크리스트 후 법적 결론 안내",
    },
    {
        "id": "documents",
        "name_ko": "서류·서식",
        "description_ko": "해당 절차에 필요한 법령·행정규칙 별표·서식(제출 서류, 양식 등) 안내 (국가법령정보 API)",
    },
]

# 관련 질문으로 추천할 때 허용할 유형 (exception은 답변 제한 있으므로 제외)
ALLOWED_RELATED_QUESTION_TYPES = frozenset(c["id"] for c in CHATBOT_CAPABILITIES)


def get_related_question_capabilities() -> List[Dict[str, Any]]:
    """관련 질문 생성 시 '이 서비스가 답할 수 있는 유형' 목록. 기능 추가 시 CHATBOT_CAPABILITIES만 수정."""
    return list(CHATBOT_CAPABILITIES)


def format_capabilities_for_prompt(capabilities: List[Dict[str, Any]]) -> str:
    """프롬프트에 넣을 문자열: 유형별 이름·설명."""
    lines = []
    for c in capabilities:
        name = c.get("name_ko", c.get("id", ""))
        desc = c.get("description_ko", "")
        lines.append(f"- **{name}**: {desc}")
    return "\n".join(lines) if lines else ""
