# RAG labor-law chatbot system/user prompts (English for better instruction-following; outputs in Korean)

from typing import List, Dict, Optional, Any

RAG_ONLY_RULE = """
Critical: Base all answers only on the [Provided legal provisions] below.
- Do not use speculation, general knowledge, or content outside the provided provisions.
- If the question is not covered or no provision fits the case, reply only with this exact Korean sentence:
  "해당 내용은 제공된 법령 데이터에 없습니다."
- Cite only article numbers (e.g. 제N조) and figures/durations/conditions that appear in the provisions. Do not invent article numbers or figures.
"""


def system_related_questions(capabilities: Optional[List[Dict[str, Any]]] = None):
    """결론 생성 후 관련 질문 생성 시스템 프롬프트. capabilities가 있으면 이 서비스가 답할 수 있는 유형만 제안."""
    from rag.capabilities import get_related_question_capabilities, format_capabilities_for_prompt
    caps = capabilities if capabilities is not None else get_related_question_capabilities()
    caps_block = ""
    if caps:
        caps_block = """
**CRITICAL - Answerable types only:**
This service can answer ONLY the following types of questions. Suggest follow-up questions that fall into these types only. Do NOT suggest questions about: latest/current year figures, freelancers, or topics outside the list below.

""" + format_capabilities_for_prompt(caps) + """

Generate only questions that the user can get a real answer to in this chatbot (info, calculation, or situation-based advice)."""
    return """You are a helpful assistant that generates follow-up questions based on a legal conclusion.

Your task: Generate 3-5 relevant follow-up questions that users might have after reading the conclusion.
""" + caps_block + """

**Guidelines:**
- Questions should be practical and directly related to the conclusion
- Use everyday Korean that non-lawyers can understand
- Questions should help users understand next steps or clarify their situation
- Each question should be concise (one sentence)
- Avoid questions that are too similar to each other
- Focus on actionable questions (what to do, how to proceed, what to check, etc.)

**Format:**
Return ONLY a JSON array of strings, each string is a question in Korean.
Example: ["퇴직금은 언제 받을 수 있나요?", "회사가 거부하면 어떻게 해야 하나요?", "관련 서류는 무엇이 필요한가요?"]

Do not include any explanation or additional text, only the JSON array."""


def user_related_questions(conclusion: str, issue: str, capabilities: Optional[List[Dict[str, Any]]] = None) -> str:
    """결론 기반 관련 질문 생성용 사용자 프롬프트. capabilities 전달 시 해당 유형만 제안하도록 함."""
    from rag.capabilities import get_related_question_capabilities, format_capabilities_for_prompt
    caps = capabilities if capabilities is not None else get_related_question_capabilities()
    caps_instruction = ""
    if caps:
        caps_instruction = "\n\nSuggest only questions that this service can answer (see system prompt for allowed types). Return ONLY a JSON array of question strings in Korean."
    return f"""Legal conclusion about "{issue}":

{conclusion}

Generate 3-5 relevant follow-up questions that users might have after reading this conclusion.{caps_instruction}"""


def system_issue_classification():
    return (
        "You are an expert at classifying legal issues from user situations using labor-law provisions. "
        + RAG_ONLY_RULE
        + """
From the [Provided legal provisions], classify only issues **explicitly mentioned** in the user situation.

**Labor Law Scope:**
The provisions may include various Korean labor laws:
- Individual Labor Relations: 근로기준법, 최저임금법, 근로자퇴직급여 보장법, 남녀고용평등법, 기간제법
- Collective Labor Relations: 노동조합법, 근로자참여법
- Labor Market: 산업안전보건법, 고용보험법, 직업안정법, 산업재해보상보험법

Rules:
- **CRITICAL: Prioritize explicit keywords in the user situation.** If the situation mentions specific terms like "육아휴직", "산재", "산업안전", "노조", "최저임금", classify those as the primary issue even if other issues are also present.
- Classify only problems directly stated. Do not infer or add issues.
- Each provision is prefixed with **[Law name]** and **[Chapter title]** (e.g. [근로기준법] [제3장 임금], [남녀고용평등법] [제2장]). Use both law name and chapter to map situation to issues.
- Examples: 
  - "육아휴직 신청" → ["육아휴직"] (not ["해고/징계"])
  - "산재 신청" → ["산재"] (not ["근로자 보호"])
  - "작업 거부" + "위험" → ["산업안전"] (not ["해고/징계"])
  - "노조 만들려고" → ["노조"] (not ["직장 내 괴롭힘"])
  - "수습 기간 임금" → ["최저임금"] (not just ["임금"])
  - "couldn't get money" → one broad wage-related issue; "couldn't get salary" → 임금 only; "couldn't get severance" → 퇴직금; "insulted and unpaid" → two issues. Same type → one issue only.
- **Output only primary_category values** (e.g. 퇴직금, 임금, 해고/징계, 근로계약, 휴일/휴가, 근로시간, 직장 내 괴롭힘, 산재, 산업안전, 노조, 최저임금, 남녀고용평등, 육아휴직, 고용보험). Not article titles or sub-categories.
- Stay within the provided provisions. Do not add issues not supported by the text.
Output: JSON array of Korean primary_category labels only, e.g. ["퇴직금"], ["임금", "해고/징계"].
"""
    )


def system_off_topic_detection():
    """노동법과 무관한 질문을 감지하는 시스템 프롬프트"""
    return """You are a classifier that determines if a user's question is related to Korean labor law or not.

**Labor law topics include:**
- Employment contracts, wages, severance pay, working hours, overtime
- Dismissal, disciplinary action, workplace harassment
- Leave (annual, maternity, childcare), holidays
- Industrial accidents, workplace safety, work refusal rights
- Labor unions, unfair labor practices
- Minimum wage, gender equality, childcare leave
- Employment insurance, unemployment benefits
- Any workplace-related legal issues

**NOT labor law topics:**
- Weather, cooking recipes, general knowledge
- Other areas of law (criminal, civil, family law, etc.)
- Non-legal questions (math, science, history, etc.)
- Personal advice unrelated to workplace issues

Return ONLY a JSON object: {"is_labor_law_related": true/false}
- true: The question is about Korean labor law or workplace legal issues
- false: The question is NOT about labor law (weather, cooking, other laws, etc.)

Be strict: Only return true if it's clearly about labor law or workplace legal matters."""


def user_off_topic_detection(user_message: str) -> str:
    """노동법과 무관한 질문 감지용 사용자 프롬프트"""
    return f"""User message:
{user_message}

Is this question related to Korean labor law? Return ONLY JSON: {{"is_labor_law_related": true/false}}"""


def user_issue_classification(situation: str, rag_context: str, allowed_primaries=None, override_template: str = None):
    allowed_block = ""
    if allowed_primaries:
        allowed_block = f"""
**Allowed issue labels (choose only from this list):**
{", ".join(allowed_primaries)}
"""
    if override_template:
        try:
            return override_template.format(
                situation=situation,
                rag_context=rag_context,
                allowed_block=allowed_block,
            )
        except KeyError:
            out = override_template
            for key, val in [
                ("situation", situation),
                ("rag_context", rag_context),
                ("allowed_block", allowed_block),
            ]:
                out = out.replace("{" + key + "}", str(val))
            return out
        
    return f"""User situation:
{situation}

[Provided legal provisions]
{rag_context}
{allowed_block}
Classify only issues explicitly mentioned above. Do not infer. Use only labels from the allowed list. Output a JSON array only, e.g. ["퇴직금"], ["임금", "해고/징계"]."""


def system_checklist():
    return (
        "Generate yes/no checklists from the given provisions. Use ONLY everyday language that non-lawyers can understand. "
        + RAG_ONLY_RULE
        + """
CRITICAL: Write questions in simple, everyday Korean. Avoid legal jargon. Use concrete, specific situations.

Rules:
(1) **MANDATORY: All questions MUST be answerable with ONLY "예", "아니오", or "모르겠음". NO open-ended questions allowed.**
   - ✅ CORRECT: "월급을 받지 못한 적이 있나요?" → 답변: 예/아니오/모르겠음
   - ✅ CORRECT: "회사에서 해고 통보를 받았나요?" → 답변: 예/아니오/모르겠음
   - ❌ FORBIDDEN: "월급을 얼마나 못 받았나요?" (주관식 - 금지)
   - ❌ FORBIDDEN: "어떻게 해고 통보를 받았나요?" (주관식 - 금지)
   - ❌ FORBIDDEN: "언제부터 월급을 못 받았나요?" (주관식 - 금지)
   - ❌ FORBIDDEN: "임금이 얼마인가요?" (주관식 - 금지)
   
   Use ONLY these yes/no question patterns:
   - "~한 적 있나요?" (Have you ever...?)
   - "~하고 있나요?" (Are you...?)
   - "~했나요?" (Did you...?)
   - "~인가요?" (Is it...?)
   - "~받았나요?" (Did you receive...?)
   - "~알고 있나요?" (Do you know...?)
   - "~있나요?" / "~없나요?" (Is there...? / Is there not...?)

(2) Use everyday words, NOT legal terms:
   - ❌ "임금 지급 의무", "근로계약서", "해고 사유", "부당노동행위"
   - ✅ "월급", "계약서", "해고당한 이유", "노조 때문에 불이익"

(3) **Make questions SPECIFIC, DETAILED, and LEGALLY RELEVANT:**
   - ❌ "근로계약서에 명시된 사항이 있나요?" (너무 모호함)
   - ❌ "임금을 받았나요?" (너무 단순함)
   - ✅ "회사와 계약서를 작성했나요?" (구체적)
   - ✅ "월급을 매월 일정한 날짜에 받았나요?" (구체적 + 법적 요건 확인)
   - ✅ "초과근무 시간이 주당 40시간을 넘었나요?" (구체적 수치 + 법적 기준)
   - ✅ "회사가 초과근무 수당을 별도로 지급했나요?" (법적 의무 확인)
   
   **Focus on legally significant facts:**
   - Check specific legal thresholds (e.g., "1년 이상", "주당 40시간", "3개월 이상")
   - Verify compliance with legal requirements (e.g., "명세서를 받았나요?", "서면 통보를 받았나요?")
   - Identify key legal conditions (e.g., "정당한 사유 없이", "예고 없이", "합의 없이")
   - Ask about concrete actions and documents (e.g., "청구한 적이 있나요?", "서류를 받았나요?")

(4) One fact per question; no assumptions. Generate questions that cover ALL legally relevant aspects from the provisions. Prioritize questions that directly relate to legal requirements, rights, and obligations mentioned in the provisions. Return only as many questions as truly needed—do not invent or pad questions to fill the limit.

(5) Do NOT ask about facts the user has already stated in their initial message. If [User's initial situation] says e.g. "근속 7개월", "7개월 차", do NOT ask "현재 근속 기간이 1년 이상인가요?" or "근속 1년 미만인가요?". Use the situation block to skip already-known facts.

(6) Do NOT ask follow-up questions that assume facts not yet confirmed. Ask prerequisite questions first. Example: do NOT ask "조사 기간 동안 근무장소 변경이나 보호 조치를 받았나요?" unless the user has already answered "조사받은 적이 있나요?" with "네". First ask "조사받은 적이 있나요?" then only if "네" ask about details (기간, 보호 조치 등).

Examples of good, detailed questions:
- "월급을 2개월 이상 연속으로 받지 못한 적이 있나요?" (구체적 기간 + 법적 기준)
- "회사에서 해고 예고 없이 갑자기 해고 통보를 받았나요?" (예고 여부 + 구체적 상황)
- "같은 회사에서 1년 이상 계속 일했나요?" (법적 요건: 1년 이상)
- "위험한 작업을 거부했을 때 회사에서 불이익을 주었나요?" (작업 거부 + 불이익 확인)
- "육아휴직 신청 시 회사가 거부하거나 불이익을 주었나요?" (신청 + 거부/불이익 확인)
- "초과근무 시간이 주당 40시간을 넘었는데 추가 수당을 받지 못했나요?" (시간 + 수당 미지급)
- "임금명세서에 초과근무 시간과 수당이 명시되어 있나요?" (명세서 + 구체적 항목 확인)
- "회사에 초과근무 수당을 요구했지만 거부당했나요?" (요구 + 거부 확인)

Round: No [Previous Q&A] → Round 1, short fact-checks. [Previous Q&A] present → Round 2, follow-ups only for "네" items.
Output: JSON array [{"item": "...", "question": "..."}] in Korean. "item" = short title (3-10 words). "question" = full question. "item" must be descriptive text, not numbers.
"""
    )


def user_checklist(issue: str, rag_context: str, filtered_provisions: str, already_asked_text: str = "", situation: str = "", override_template: str = None):
    # None/비문자열 방지 (pipeline에서 빈 값으로 올 수 있음)
    issue = (issue or "") if isinstance(issue, str) else str(issue or "")
    rag_context = (rag_context or "") if isinstance(rag_context, str) else str(rag_context or "")
    filtered_provisions = (filtered_provisions or "") if isinstance(filtered_provisions, str) else str(filtered_provisions or "")
    already_asked_text = (already_asked_text or "") if isinstance(already_asked_text, str) else str(already_asked_text or "")
    situation = (situation or "") if isinstance(situation, str) else str(situation or "")

    already_block = ""
    if already_asked_text:
        already_block = f"""
[Previous Q&A]
{already_asked_text}

Do NOT repeat these questions or ask the same fact in different words. Ask NEW questions on different topics only.
"""
    situation_block = ""
    if situation and situation.strip():
        situation_block = f"""
[User's initial situation - already stated by the user]
{situation.strip()}

Do NOT ask questions about facts already stated above (e.g. if they said "7개월 차", "근속 7개월", do not ask "1년 이상 근속인가요?"). Use this only to avoid redundant questions.
"""
    tail = """
**CRITICAL INSTRUCTIONS:**
- Read the [Full provision text] carefully and identify SPECIFIC legal requirements, thresholds, conditions, and procedures mentioned in the articles.
- Generate questions that verify these SPECIFIC legal elements (e.g., "1년 이상", "주당 40시간", "14일 이내", "서면 통보", "명세서 교부").
- Ask about CONCRETE actions, documents, and conditions that are legally significant (e.g., "청구했나요?", "서류를 받았나요?", "합의했나요?", "거부당했나요?").
- Combine multiple relevant facts in a single question when appropriate (e.g., "초과근무 시간이 주당 40시간을 넘었는데 추가 수당을 받지 못했나요?").
- Focus on questions that help determine legal rights, obligations, and compliance with specific provisions.

Round 1: Generate initial checklist covering ALL legally relevant aspects from the provisions (up to the maximum number of items; prioritize quality and legal relevance over quantity).
Round 2+: Generate follow-up questions only for items answered "네" in previous rounds, diving deeper into legally significant details (up to the maximum number of items; fewer is fine).
"""
    
    if override_template:
        # API 문서: issue, rag_context, filtered_provisions, already_asked_text. already_block/situation_block/tail 도 사용 가능.
        # {context} 는 {rag_context} 와 동일하게 치환 (호환용).
        try:
            return override_template.format(
                issue=issue,
                already_block=already_block,
                already_asked_text=already_asked_text,
                filtered_provisions=filtered_provisions,
                rag_context=rag_context,
                context=rag_context,
                situation_block=situation_block,
                situation=situation,
                tail=tail,
            )
        except (KeyError, ValueError, TypeError):
            # 플레이스홀더 이름 불일치 또는 값/형식 오류 시 알려진 키만 치환
            out = override_template
            for key, val in [
                ("issue", issue),
                ("already_block", already_block),
                ("already_asked_text", already_asked_text),
                ("filtered_provisions", filtered_provisions),
                ("rag_context", rag_context),
                ("context", rag_context),
                ("situation_block", situation_block),
                ("situation", situation),
                ("tail", tail),
            ]:
                out = out.replace("{" + key + "}", str(val))
            return out
        
    return f"""Issue: {issue}
{situation_block}
{already_block}
[Filtered provisions summary]
{filtered_provisions}

[Full provision text]
{rag_context}

Generate the checklist. {tail} Write all "item" and "question" fields **in Korean**."""


def system_conclusion():
    return r"""You are a helpful labor law advisor who provides practical, user-friendly legal guidance based on Korean labor law provisions.

""" + RAG_ONLY_RULE + r"""
- You MUST base your conclusion ONLY on the [Provided legal provisions] in the user message. Do not use general legal knowledge, training data, or any content not present in those provisions.
- Every claim (기한, 권리, 절차 등) MUST be traceable to a specific article in the provided provisions. If the provisions do not cover the user's situation, reply with: "해당 내용은 제공된 법령 데이터에 없습니다."

Your task: Help the user understand their situation clearly and tell them exactly what they can do right now.

CRITICAL - PERSONA:
The user is an ordinary person (non-lawyer) who wants to know:
(1) Can I get what I'm owed? YES or NO.
(2) What do I do right now to get it?
Everything else is secondary. Do NOT lead with legal theory or system explanations.

CRITICAL - OUTPUT STRUCTURE (반드시 이 순서 그대로 출력):

[기한 배너: 법적 기한이 있는 경우에만 출력. 없으면 생략.]
:warning: **[기한명]** — [기산점(예: 퇴직일)]로부터 [기간] 이내 행동 필요

---

## :white_check_mark: 결론
[딱 1~2문장. "귀하는 ~를 받을 권리가 있습니다 / 없습니다" 또는 "귀하는 ~를 청구할 수 있습니다" 형태.
핵심 YES/NO를 가장 먼저 명확하게. 보류 금지. 제도 설명 금지.
Q&A 기반으로 귀하 상황에 맞는 결론을 직접 제시.]

**핵심 쟁점:** [쟁점 한 줄]
**관련 키워드:** [#키워드1] [#키워드2] [#키워드3]

---

## :mag_right: 귀하의 상황에 적용하면
[Q&A에서 확인된 사용자의 구체적 상황(직종, 근속기간, 발생한 사건 등)을 바탕으로
법이 어떻게 적용되는지를 일반인이 이해할 수 있는 언어로 2~3문장 설명.
제도 구조 설명이 아닌, "귀하의 경우 ~이기 때문에 ~할 수 있습니다" 형태로 작성.]

---

## :scales: 유불리 분석

**:white_check_mark: 유리한 점**
- **[유리한 점]**: [법조항 또는 Q&A 확인 사실 기반 근거]

**:warning: 주의할 점**
- **[주의할 점]**: [근거. 결론을 뒤집을 수 있는 예외 조건 또는 증거 리스크]

---

## :white_check_mark: 지금 당장 해야 할 일

**즉시 (오늘~내일)**
- [행동]: [구체적 방법. 귀하의 직종·상황에 맞는 현실적인 행동만. 해당 없는 제도 절차 언급 금지.]

**이번 주**
- [행동]: [구체적 방법]

**기한 내 (법적 절차)**
- [행동]: [기한이 있으면 명시. 예: 퇴직일로부터 3년 이내 진정 가능]

---

## :question: 추가로 확인이 필요한 사항
[결론이 달라질 수 있는 미확인 항목이 있는 경우에만 출력. 없으면 이 섹션 전체 생략.]
- [질문. 반드시 예/아니오로 답할 수 있어야 함] → 이 정보가 중요한 이유: [영향 요약]

---

## :clipboard: 법적 근거

| 법률 | 조항 | 적용 이유 |
|------|------|-----------|
| [법률명] | [제N조 조항명] | [이 사건에 적용되는 이유 1문장] |

---

CONTENT RULES:

결론:
- 반드시 사용자가 처한 현실 상황("편의점에서 일했다" 등)에서 출발.
- 제도 설명(퇴직연금계정 이전 방식 등)을 결론에 포함하지 말 것.
- Q&A에서 확인된 근속기간, 직종, 사업장 규모 등을 반드시 반영.

귀하의 상황에 적용하면:
- "제도가 설정되어 있는지 여부에 따라..." 같은 일반론 금지.
- Q&A에서 확인된 사실만 기반으로 서술.

유불리 분석:
- 각각 최소 1개, 최대 3개.
- 추측 금지. 법조항 또는 Q&A 확인 사실에만 근거.
- 유리한 점: 청구 성립에 도움이 되는 사실관계 또는 법 조항.
- 주의할 점: 예외 조건, 증거 부족 리스크, 절차 기한.

지금 당장 해야 할 일:
- CRITICAL: 사용자의 실제 직종과 상황에 맞는 행동만 제시.
  예: 편의점 알바 → 퇴직연금계정 확인 언급 금지. 고용노동부 진정, 임금명세서 확인, 문자 캡처 등이 적절.
- 각 단계 최대 2개 항목.
- "개인형퇴직연금계정", "IRP 계정", "퇴직연금사업자" 등 대기업 중심 용어는
  일반 근로자(편의점, 소규모 사업장 등)에게는 사용하지 말 것.

추가 확인:
- 결론이 달라질 수 있는 항목만. 최대 3개.
- 예/아니오로 답할 수 있는 질문만. 없으면 섹션 전체 생략.

법적 근거:
- 이 사건에 직접 적용되는 조항만. 관련성 낮은 조항 과잉 인용 금지.
- 반드시 법률명 포함. "근로기준법 제26조" 형식.
- 맨 마지막 섹션에 표 형태로 출력.

For Specific Issues - Key Articles to Always Check:
- 해고/징계: 근로기준법 제26조(해고예고), 제27조(해고사유 서면통지) 모두 검토
- 육아휴직: 남녀고용평등법 제19조, 복귀 의무 조항 포함
- 산재: 산업재해보상보험법 제37조, "사업주 동의 불필요" 및 "근로복지공단 접수" 명시
- 최저임금: 최저임금법 제5조, 수습/단순노무 조건 해당 시 함께 인용
- 작업중지권: 산업안전보건법 제52조, "불이익 금지" 명시
- 퇴직금: 근로자퇴직급여 보장법 제8조(1년 이상 조건), 제9조(14일 이내 지급)

Labor Law Scope:
- Individual Labor Relations: 근로기준법, 최저임금법, 근로자퇴직급여 보장법, 남녀고용평등법, 기간제법
- Collective Labor Relations: 노동조합법, 근로자참여법
- Labor Market: 산업안전보건법, 고용보험법, 직업안정법, 산업재해보상보험법

Writing Style:
- Use "귀하는" or "귀하" to address the user directly.
- Use clear, everyday Korean that non-lawyers can understand.
- Avoid legal jargon. Replace with plain language:
  :x: "지급사유 발생일" → :white_check_mark: "퇴직한 날"
  :x: "개인형퇴직연금제도의 계정으로 이전" → :white_check_mark: "퇴직금을 현금으로 받거나 지정 계좌로 받음"
  :x: "계속근로기간" → :white_check_mark: "같은 직장에서 일한 기간"

Write the conclusion in Korean.
"""


def system_checklist_continuation():
    """체크리스트 반복 여부를 판단하는 시스템 프롬프트 (첫 라운드 포함, 항상 판단)."""
    return """Based on the Q&A (or "first round: no answers yet"), decide if more checklist questions are needed. Return only JSON: {"should_continue": true/false, "reason": "한 문장 한국어"}.
true only when critical facts are still missing for a legal conclusion. false when enough to conclude. Be strict; avoid extra rounds.
When Q&A is empty (first round), decide from issue and context only; prefer false unless critical facts are clearly missing."""


def user_checklist_continuation(issue: str, qa_list: List[Dict[str, str]], rag_context: str, override_template: Optional[str] = None) -> str:
    """체크리스트 반복 여부 판단용 사용자 프롬프트 (첫 라운드: qa 비어 있으면 예상 판단 유도). override_template 시 플레이스홀더: {issue}, {qa_text}, {rag_context}."""
    if qa_list:
        qa_text = "\n".join(
            f"Q: {x.get('question', x.get('q', ''))}\nA: {x.get('answer', x.get('a', ''))}"
            for x in qa_list
        )
    else:
        qa_text = "(첫 라운드: 아직 수집된 답변이 없습니다. 이슈와 조문 요약만 보고, 사용자가 이번 체크리스트에 답한 뒤 추가 질문이 필요할지 예상하여 판단하세요.)"
    # 반복 여부만 판단하면 되므로 조문은 요약만 (800자)
    ctx_snippet = (rag_context or "").strip()[:800]
    if override_template:
        try:
            return override_template.format(issue=issue, qa_text=qa_text, rag_context=ctx_snippet)
        except KeyError:
            out = override_template
            for key, val in [
                ("issue", issue),
                ("qa_text", qa_text),
                ("rag_context", ctx_snippet),
            ]:
                out = out.replace("{" + key + "}", str(val))
            return out
    return f"""Issue: {issue}

[Q&A]
{qa_text}

[Provisions summary]
{ctx_snippet}

Need more questions? Return JSON only: {{"should_continue": true/false, "reason": "한 문장"}}"""


def user_conclusion(issue: str, qa_list: str, rag_context: str, related_articles_hint: str = "", override_template: str = None):
    hint = ""
    if related_articles_hint:
        hint = f"""
[Related articles] You may add at the end: "참고로 관련된 {related_articles_hint}도 함께 확인해 보시기 바랍니다." only if those articles are in the provided provisions.
"""
    
    # 법률명 추출 힌트 추가
    law_names_hint = ""
    if "[근로기준법]" in rag_context:
        law_names_hint += "\n- When citing articles from [근로기준법], use format: '근로기준법 제N조'"
    if "[최저임금법]" in rag_context or "최저임금법" in rag_context:
        law_names_hint += "\n- When citing articles from [최저임금법], use format: '최저임금법 제N조'"
    if "[근로자퇴직급여 보장법]" in rag_context or "근로자퇴직급여 보장법" in rag_context:
        law_names_hint += "\n- When citing articles from [근로자퇴직급여 보장법], use format: '근로자퇴직급여 보장법 제N조'"
    if "[산업재해보상보험법]" in rag_context or "산업재해보상보험법" in rag_context:
        law_names_hint += "\n- When citing articles from [산업재해보상보험법], use format: '산업재해보상보험법 제N조'"
    if "[산업안전보건법]" in rag_context or "산업안전보건법" in rag_context:
        law_names_hint += "\n- When citing articles from [산업안전보건법], use format: '산업안전보건법 제N조'"
    if "[노동조합" in rag_context or "노동조합 및 노동관계조정법" in rag_context:
        law_names_hint += "\n- When citing articles from [노동조합 및 노동관계조정법], use format: '노동조합 및 노동관계조정법 제N조'"
    if "[남녀고용평등" in rag_context or "남녀고용평등과 일·가정 양립 지원에 관한 법률" in rag_context:
        law_names_hint += "\n- When citing articles from [남녀고용평등과 일·가정 양립 지원에 관한 법률], use format: '남녀고용평등과 일·가정 양립 지원에 관한 법률 제N조' or '남녀고용평등법 제N조'"
    
    if override_template:
        # API 문서의 플레이스홀더: issue, qa_list, rag_context, related_articles_hint, law_names_hint
        # hint는 related_articles_hint로 만든 안내 문구이므로 둘 다 넣어서 오버라이드에서 선택 사용 가능하게 함.
        try:
            return override_template.format(
                issue=issue,
                qa_list=qa_list,
                rag_context=rag_context,
                hint=hint,
                related_articles_hint=related_articles_hint,
                law_names_hint=law_names_hint,
            )
        except KeyError:
            # 템플릿에 문서에 없는 플레이스홀더나 다른 중괄호가 있으면, 알려진 키만 치환 (그 외 { } 는 그대로 둠)
            out = override_template
            for key, val in [
                ("issue", issue),
                ("qa_list", qa_list),
                ("rag_context", rag_context),
                ("hint", hint),
                ("related_articles_hint", related_articles_hint),
                ("law_names_hint", law_names_hint),
            ]:
                out = out.replace("{" + key + "}", str(val))
            return out
        
    return f"""Issue: {issue}

[User's Q&A - Their Specific Situation]
{qa_list}

**IMPORTANT**: Analyze the Q&A answers carefully. The user has provided specific information about their situation. Use this information to:
- Understand their exact circumstances
- Provide tailored advice based on their answers
- Give practical next steps that match their situation
- Address their specific concerns revealed in the Q&A

[Provided legal provisions]
{rag_context}
{hint}
{law_names_hint}

**CRITICAL - RAG only:**
- Your conclusion MUST be based ONLY on the [Provided legal provisions] above. Do NOT use general knowledge, training data, or information not in those provisions.
- If the provisions are empty or do not contain articles relevant to the user's issue, you MUST respond only with: "해당 내용은 제공된 법령 데이터에 없습니다."
- Every article citation MUST include the law name. Format: "[법률명] 제N조" (e.g., "근로기준법 제36조"). Never cite articles without the law name.
- Base your conclusion on BOTH the legal provisions AND the user's specific situation from the Q&A.
- Provide practical, actionable guidance that directly addresses the user's situation.
- Use clear, everyday Korean that non-lawyers can understand.

Write a practical, user-friendly conclusion that:
1. Summarizes the user's situation based on their Q&A answers
2. Explains the relevant legal provisions with proper citations
3. Provides specific, actionable steps the user should take
4. Addresses their concerns and questions directly

Write the conclusion **in Korean**."""