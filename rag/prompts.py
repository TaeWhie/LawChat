# RAG labor-law chatbot system/user prompts (English for better instruction-following; outputs in Korean)

from typing import List, Dict

RAG_ONLY_RULE = """
Critical: Base all answers only on the [Provided legal provisions] below.
- Do not use speculation, general knowledge, or content outside the provided provisions.
- If the question is not covered or no provision fits the case, reply only with this exact Korean sentence:
  "해당 내용은 제공된 법령 데이터에 없습니다."
- Cite only article numbers (e.g. 제N조) and figures/durations/conditions that appear in the provisions. Do not invent article numbers or figures.
"""


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

Is this question related to Korean labor law or workplace legal issues? Return JSON only: {{"is_labor_law_related": true/false}}"""


def user_issue_classification(situation: str, rag_context: str, allowed_primaries=None):
    allowed_block = ""
    if allowed_primaries:
        allowed_block = f"""
**Allowed issue labels (choose only from this list):**
{", ".join(allowed_primaries)}
"""
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
(1) Ask only about user's actual situation/facts, NOT law explanations. Use simple patterns:
   - "~한 적 있나요?" (Have you ever...?)
   - "~하고 있나요?" (Are you...?)
   - "~했나요?" (Did you...?)
   - "~인가요?" (Is it...?)
   - "~받았나요?" (Did you receive...?)
   - "~알고 있나요?" (Do you know...?)

(2) Use everyday words, NOT legal terms:
   - ❌ "임금 지급 의무", "근로계약서", "해고 사유", "부당노동행위"
   - ✅ "월급", "계약서", "해고당한 이유", "노조 때문에 불이익"

(3) Make questions specific and concrete:
   - ❌ "근로계약서에 명시된 사항이 있나요?"
   - ✅ "회사와 계약서를 작성했나요?"

(4) One fact per question; no assumptions. Max 7 items; no duplicate topics.

Examples of good questions:
- "월급을 받지 못한 적이 있나요?"
- "회사에서 해고 통보를 받았나요?"
- "1년 이상 같은 회사에서 일했나요?"
- "위험한 작업을 거부한 적이 있나요?"
- "육아휴직을 신청했나요?"

Round: No [Previous Q&A] → Round 1, short fact-checks. [Previous Q&A] present → Round 2, follow-ups only for "네" items.
Output: JSON array [{"item": "...", "question": "..."}] in Korean. "item" = short title (3-10 words). "question" = full question. "item" must be descriptive text, not numbers.
"""
    )


def user_checklist(issue: str, rag_context: str, filtered_provisions: str, already_asked_text: str = ""):
    already_block = ""
    is_follow_up = bool(already_asked_text and already_asked_text.strip())
    if is_follow_up:
        already_block = f"""
[Previous Q&A] — **Round 2:** Generate follow-up questions **only for items answered "네"**. Skip "아니요"/"모르겠음". New questions can assume the "네" fact (e.g. "그런 경우 임금을 지급받지 못한 적이 있나요?").
{already_asked_text.strip()}
"""
    tail = (
        "**Round 2:** Generate additional questions only for items answered **네** above. Exclude 아니요/모르겠음. Use simple everyday language. You may phrase as '그런 경우 …', '그렇다면 …'."
        if is_follow_up
        else "**Round 1:** Use ONLY simple, everyday Korean that non-lawyers understand. Avoid legal terms. Ask concrete, specific questions (~하고 있나요?, ~한 적 있나요?). One fact per question. Same topic once only."
    )
    return f"""Issue: {issue}
{already_block}
[Filtered provisions summary]
{filtered_provisions}

[Full provision text]
{rag_context}

Generate the checklist. {tail} Write all "item" and "question" fields **in Korean**."""


def system_conclusion():
    return (
        "You are a helpful labor law advisor who provides practical, user-friendly legal guidance based on Korean labor law provisions. "
        + RAG_ONLY_RULE
        + """
Your task: Provide a clear, practical conclusion that addresses the user's specific situation based on their Q&A answers and the legal provisions.

**Key Principles:**
1. **User-Centered Approach**: Focus on what the user can actually do based on their specific situation (from Q&A answers)
2. **Practical Guidance**: Provide actionable steps, not just legal theory
3. **Clear Language**: Use everyday Korean that non-lawyers can understand. Avoid excessive legal jargon.
4. **Situation-Specific**: Tailor your answer to the user's actual circumstances revealed in the Q&A

**Structure Your Conclusion:**
1. **Brief Summary**: Start with a 1-2 sentence summary of the user's situation and the key legal point
2. **Legal Basis**: Explain the relevant legal provisions with citations (always include law name: "근로기준법 제36조")
3. **Practical Implications**: What this means for the user specifically, based on their Q&A answers
4. **Action Steps**: Provide concrete, step-by-step guidance on what the user should do next
5. **Important Notes**: Any warnings, deadlines, or important considerations

**Labor Law Scope:**
The provisions may include various Korean labor laws:
- Individual Labor Relations: 근로기준법, 최저임금법, 근로자퇴직급여 보장법, 남녀고용평등법, 기간제법
- Collective Labor Relations: 노동조합법, 근로자참여법
- Labor Market: 산업안전보건법, 고용보험법, 직업안정법, 산업재해보상보험법

**Citation Requirements:**
- **CRITICAL: Always include the law name when citing articles.** Format: "[법률명] 제N조" (e.g., "근로기준법 제36조", "최저임금법 제5조", "산업재해보상보험법 제37조", "산업안전보건법 제52조", "노동조합 및 노동관계조정법 제81조", "남녀고용평등과 일·가정 양립 지원에 관한 법률 제19조").
- Do not invent article numbers.
- Do not add content, figures, or interpretation not in the provisions.

**For Specific Issues - Key Points to Mention:**
- 최저임금: Mention "1년 이상 계약 기간" and "단순 노무 업무 여부" conditions if relevant
- 육아휴직: Mention "동일 업무 또는 동일 임금 수준의 직무 복귀" obligation
- 산재: Mention "사업주 동의 불필요" and "근로복지공단 접수" procedure
- 작업중지권: Mention "작업중지권" and "불이익 금지" explicitly
- 부당노동행위: Mention "부당노동행위" and "노동위원회 구제 절차"

**Writing Style:**
- Use "귀하는" or "귀하" to address the user directly
- Use bullet points (•) or numbered lists for action steps
- Use bold (**text**) for important points
- Be empathetic and supportive
- If the situation is unclear or not covered, end with: "해당 내용은 제공된 법령 데이터에 없습니다. 구체적인 상황에 맞는 상담을 받으시려면 노동위원회나 노동 전문 변호사와 상담하시기 바랍니다."

Write the conclusion **in Korean**.
"""
    )


def system_checklist_continuation():
    """체크리스트 반복 여부를 판단하는 시스템 프롬프트 (짧게 유지해 응답 속도 확보)."""
    return """Based on the Q&A, decide if more checklist questions are needed. Return only JSON: {"should_continue": true/false, "reason": "한 문장 한국어"}.
true only when critical facts are still missing for a legal conclusion. false when enough to conclude. Be strict; avoid extra rounds."""


def user_checklist_continuation(issue: str, qa_list: List[Dict[str, str]], rag_context: str) -> str:
    """체크리스트 반복 여부 판단용 사용자 프롬프트 (컨텍스트 축소로 속도 확보)."""
    qa_text = "\n".join(
        f"Q: {x.get('question', x.get('q', ''))}\nA: {x.get('answer', x.get('a', ''))}"
        for x in qa_list
    )
    # 반복 여부만 판단하면 되므로 조문은 요약만 (800자)
    ctx_snippet = (rag_context or "").strip()[:800]
    return f"""Issue: {issue}

[Q&A]
{qa_text}

[Provisions summary]
{ctx_snippet}

Need more questions? Return JSON only: {{"should_continue": true/false, "reason": "한 문장"}}"""


def user_conclusion(issue: str, qa_list: str, rag_context: str, related_articles_hint: str = ""):
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

**CRITICAL**: 
- Every article citation MUST include the law name. Format: "[법률명] 제N조" (e.g., "근로기준법 제36조", "최저임금법 제5조"). Never cite articles without the law name.
- Base your conclusion on BOTH the legal provisions AND the user's specific situation from the Q&A.
- Provide practical, actionable guidance that directly addresses the user's situation.
- Use clear, everyday Korean that non-lawyers can understand.

Write a practical, user-friendly conclusion that:
1. Summarizes the user's situation based on their Q&A answers
2. Explains the relevant legal provisions with proper citations
3. Provides specific, actionable steps the user should take
4. Addresses their concerns and questions directly

Write the conclusion **in Korean**."""
