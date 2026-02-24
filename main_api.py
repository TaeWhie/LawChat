import os
import asyncio
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field
import uvicorn

# LAW_DEBUG=1 일 때만 클라이언트에 예외 상세 노출
_LAW_DEBUG = os.getenv("LAW_DEBUG", "0") == "1"

# LawChat RAG components
from rag.store import build_vector_store, search
from rag.pipeline import (
    step1_issue_classification, 
    step2_checklist, 
    step3_conclusion, 
    step3_conclusion_stream,
    get_penalty_and_supplementary
)
from rag.question_classifier import classify_question_type
from rag.llm import chat, chat_stream, chat_json_fast, chat_with_metadata
from rag.api_documents import search_documents_for_topic, format_documents_answer
from rag.prompts import system_related_questions, user_related_questions
from rag.capabilities import get_related_question_capabilities, ALLOWED_RELATED_QUESTION_TYPES
from rag.question_classifier import (
    calculate_severance_pay, 
    calculate_overtime_pay,
    classify_question_type as classify_type,
    system_knowledge_qa, 
    user_knowledge_qa, 
    system_calculation_qa, 
    user_calculation_qa, 
    system_exception_qa, 
    user_exception_qa
)
from rag.law_json import get_laws, get_chapters, get_articles_by_chapter
from rag.graph import get_graph
from langchain_core.messages import HumanMessage, AIMessage
from config import ALL_LABOR_LAW_SOURCES, SOURCE_DECREE, SOURCE_RULE, OPENAI_API_KEY
from rag.context import openai_api_key_ctx, law_api_key_ctx, openai_base_url_ctx, chat_model_ctx

app = FastAPI(title="LawChat Backend API", version=os.getenv("LAW_API_VERSION", "1.2.0"))

# CORS Configuration
# CORS settings
# 로컬 개발 및 배포 테스트를 위해 기본값은 ["*"]이나, 
# 상업용 운영 시에는 .env의 ALLOWED_ORIGINS에 실제 프론트엔드 도메인을 명시해야 합니다.
allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "*")
origins = [origin.strip() for origin in allowed_origins_env.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Vector Store Collection
collection = None

@app.on_event("startup")
async def startup_event():
    global collection
    col, _ = build_vector_store()
    collection = col
    # 그래프가 동일 벡터 스토어를 쓰도록 캐시 공유 (중복 로드 방지)
    try:
        import rag.graph as _g
        _g._collection_cache = col
    except Exception:
        pass

# --- Data Models ---

class BaseRequest(BaseModel):
    openai_api_key: Optional[str] = Field(None, description="Custom OpenAI API Key")
    openai_base_url: Optional[str] = Field(None, description="Custom OpenAI API Base URL (e.g. Azure, proxy)")
    law_api_key: Optional[str] = Field(None, description="Custom Law (LIDB) API Key")
    model: Optional[str] = Field(None, description="Chat model override (e.g. gpt-4o, gpt-4o-mini)")

class RouteRequest(BaseRequest):
    text: str

class ClassifyRequest(BaseRequest):
    situation: str
    top_k: int = 22

class ChecklistRequest(BaseRequest):
    issue: str
    situation: str
    all_qa: List[Dict[str, str]] = []
    round: int = 1
    previous_rag_results: List[Dict[str, Any]] = []

class ConclusionRequest(BaseRequest):
    issue: str
    all_qa: List[Dict[str, str]]
    stream: bool = False

class QARequest(BaseRequest):
    question: str
    context: Optional[str] = None


class InvokeRequest(BaseRequest):
    """챗봇과 동일한 1회 graph.invoke 요청 (app_chatbot과 동일 성능)."""
    message: str = Field(..., description="사용자 입력 메시지")
    thread_id: Optional[str] = Field("default", description="대화 스레드 ID (체크포인터 구분용)")

# --- Helper Functions ---


def _effective_openai_key(keys: Optional[BaseRequest]) -> Optional[str]:
    """요청·컨텍스트·환경변수 순으로 유효한 OpenAI API 키 반환 (asyncio.to_thread 내부에서 키 부재 방지)."""
    if keys and getattr(keys, "openai_api_key", None) and str(keys.openai_api_key).strip():
        return str(keys.openai_api_key).strip()
    return openai_api_key_ctx.get() or OPENAI_API_KEY

def _standardize(obj):
    """Recursively converts objects into JSON-serializable types with maximal defensiveness."""
    try:
        if isinstance(obj, dict):
            return {str(k): _standardize(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [_standardize(v) for v in obj]
        elif isinstance(obj, (str, int, float, bool)) or obj is None:
            return obj
        else:
            return str(obj)
    except Exception:
        return str(obj)


def _serialize_invoke_result(r: dict) -> dict:
    """graph.invoke() 결과를 app_chatbot과 동일한 JSON 구조로 변환."""
    msgs = r.get("messages") or []
    msg_list = []
    for m in msgs:
        c = getattr(m, "content", None) or str(m)
        kind = "AIMessage" if isinstance(m, AIMessage) else "HumanMessage"
        msg_list.append({"t": kind, "c": c})
    return {
        "status": "ok",
        "messages": msg_list,
        "phase": r.get("phase"),
        "checklist": r.get("checklist"),
        "selected_issue": r.get("selected_issue"),
        "situation": r.get("situation"),
        "articles_by_issue": r.get("articles_by_issue"),
        "checklist_rag_results": r.get("checklist_rag_results"),
    }

def set_api_keys(keys: BaseRequest):
    """Sets ContextVar for API keys / base URL / model if provided (thread-safe; asyncio.to_thread 시 컨텍스트 복사됨)."""
    if keys.openai_api_key and keys.openai_api_key.strip():
        openai_api_key_ctx.set(keys.openai_api_key.strip())
    if keys.openai_base_url is not None and keys.openai_base_url.strip():
        openai_base_url_ctx.set(keys.openai_base_url.strip())
    if keys.law_api_key and keys.law_api_key.strip():
        law_api_key_ctx.set(keys.law_api_key.strip())
    if keys.model is not None and keys.model.strip():
        chat_model_ctx.set(keys.model.strip())

# --- Endpoints ---

@app.middleware("http")
async def context_middleware(request, call_next):
    """Middleware to reset context vars after each request to prevent contamination."""
    # ContextVar are automatically scoped to the task, so we don't strictly need to clear them,
    # but it's good practice for predictability.
    # openai_api_key_ctx.set(None)
    # law_api_key_ctx.set(None)
    response = await call_next(request)
    return response

@app.get("/")
async def root():
    """루트 접속 시 API 안내. 브라우저에서 base URL만 열었을 때 Not Found 대신 표시."""
    return {
        "service": "LawChat Backend API",
        "docs": "/docs",
        "health": "/api/v1/health",
        "message": "API 사용법은 GET /docs 에서 확인하세요.",
    }


@app.get("/api/v1/health")
async def health_check():
    """Health check endpoint to verify deployment version."""
    version = os.getenv("LAW_API_VERSION", "1.2.0")
    return {"status": "ok", "version": version, "context_supported": True}

@app.post("/api/v1/chat/route")
async def route_question(request: RouteRequest):
    """Routes the user question to the appropriate type."""
    q_type = await asyncio.to_thread(classify_type, request.text)
    return {"question_type": q_type}


@app.post("/api/v1/chat/invoke")
async def chat_invoke(request: InvokeRequest):
    """app_chatbot과 동일: 1회 graph.invoke로 전체 RAG 플로우 실행 (라우팅·이슈분류·체크리스트·결론·지식/계산/서류 분기 포함)."""
    try:
        set_api_keys(request)
        thread_id = (request.thread_id or "default").strip() or "default"
        config = {"configurable": {"thread_id": thread_id}}
        graph = get_graph()
        result = await asyncio.to_thread(
            graph.invoke,
            {"messages": [HumanMessage(content=request.message.strip() or " ")]},
            config=config,
        )
        payload = _serialize_invoke_result(result)
        return JSONResponse(status_code=200, content=_standardize(payload))
    except Exception as e:
        print(f"ERROR in chat_invoke: {str(e)}")
        detail = "상담 처리 중 오류가 발생했습니다."
        if _LAW_DEBUG:
            detail += f" {str(e)}"
        raise HTTPException(status_code=500, detail=detail)

@app.post("/api/v1/chat/classify")
async def classify_issue(request: ClassifyRequest):
    """Classifies the user situation into legal issues."""
    try:
        set_api_keys(request)
        effective_key = _effective_openai_key(request)
        if _LAW_DEBUG:
            print(f"DEBUG: Classifying situation: {request.situation[:50]}...")
        issues, articles_by_issue, _, _ = await asyncio.to_thread(
            step1_issue_classification,
            request.situation,
            collection=collection,
            top_k=request.top_k,
            openai_api_key=effective_key,
            law_api_key=request.law_api_key
        )
        if _LAW_DEBUG:
            print(f"DEBUG: Issues found: {issues}")
        safe_articles = {}
        for issue, articles in articles_by_issue.items():
            safe_articles[str(issue)] = []
            for a in articles:
                safe_articles[str(issue)].append({
                    "article": str(a.get("article", "")),
                    "title": str(a.get("title", ""))
                })
        content = {
            "status": "success",
            "issues": issues,
            "articles_by_issue": safe_articles
        }
        return JSONResponse(status_code=200, content=_standardize(content))
    except Exception as e:
        print(f"ERROR in classify_issue: {str(e)}")
        detail = "이슈 분류 중 오류가 발생했습니다."
        if _LAW_DEBUG:
            detail += f" {str(e)}"
        raise HTTPException(status_code=500, detail=detail)

@app.post("/api/v1/chat/checklist")
async def generate_checklist(request: ChecklistRequest):
    """Generates a checklist for a specific issue and situation."""
    try:
        set_api_keys(request)
        
        narrow_answers = [x.get("answer", "").strip() for x in request.all_qa if x.get("answer") and x.get("answer").strip() not in ("네", "아니요", "모르겠음", "(미입력)")]
        
        # Merge previous results if any
        remaining = request.previous_rag_results
        
        effective_key = _effective_openai_key(request)
        query = (request.issue + " " + " ".join(narrow_answers))[:500] if narrow_answers else request.issue
        new_results = await asyncio.to_thread(
            search, collection, query, top_k=12,
            filter_sources=ALL_LABOR_LAW_SOURCES,
            exclude_sections=["벌칙", "부칙"],
            exclude_chapters=["제1장 총칙"],
            openai_api_key=effective_key,
        )
        
        seen_art = {r.get("article", "") for r in remaining}
        merged = list(remaining)
        for r in new_results:
            if r.get("article", "") and r.get("article", "") not in seen_art:
                merged.append(r)
                seen_art.add(r.get("article", ""))
                
        filter_text = (request.issue + " " + "\n".join(f"Q: {x['question']} A: {x['answer']}" for x in request.all_qa))[:400]
        
        step2_res = await asyncio.to_thread(
            step2_checklist, request.issue, filter_text, collection=collection,
            narrow_answers=narrow_answers or None,
            qa_list=request.all_qa,
            remaining_articles=merged,
            openai_api_key=effective_key,
        )
        
        return JSONResponse(status_code=200, content=_standardize(step2_res))
    except Exception as e:
        print(f"ERROR in generate_checklist: {str(e)}")
        detail = "체크리스트 생성 중 오류가 발생했습니다."
        if _LAW_DEBUG:
            detail += f" {str(e)}"
        raise HTTPException(status_code=500, detail=detail)

@app.post("/api/v1/chat/conclusion")
async def generate_conclusion(request: ConclusionRequest):
    """Generates a final conclusion based on QA history."""
    try:
        set_api_keys(request)
        
        narrow_answers = [x.get("answer", "").strip() for x in request.all_qa if x.get("answer") and x.get("answer").strip() not in ("네", "아니요", "모르겠음", "(미입력)")]
        
        if request.stream:
            # 제너레이터는 응답 전송 스레드에서 실행되므로 컨텍스트 미복사 → 유효 키를 미리 캡처
            effective_key = request.openai_api_key or openai_api_key_ctx.get()

            def stream_generator():
                try:
                    for chunk in step3_conclusion_stream(
                        request.issue, request.all_qa, collection=collection, narrow_answers=narrow_answers or None,
                        openai_api_key=effective_key
                    ):
                        yield chunk
                except Exception as e:
                    yield f"Error: {str(e)}"
            return StreamingResponse(stream_generator(), media_type="text/event-stream")
        else:
            effective_key = _effective_openai_key(request)
            res = await asyncio.to_thread(
                step3_conclusion, request.issue, request.all_qa, collection=collection, narrow_answers=narrow_answers or None,
                openai_api_key=effective_key
            )
            # Add penalty/supplementary info
            conclusion_text = res.get("conclusion", "")
            penalty = await asyncio.to_thread(
                get_penalty_and_supplementary, collection, conclusion_text, request.issue, request.all_qa
            )
            res["penalty_supplementary"] = penalty
            
            # Generate related questions
            try:
                caps = get_related_question_capabilities()
                questions_result = await asyncio.to_thread(
                    chat_json_fast,
                    system_related_questions(caps),
                    user_related_questions(conclusion_text, request.issue, caps),
                    max_tokens=300,
                    openai_api_key=effective_key
                )
                if isinstance(questions_result, list):
                    res["related_questions"] = questions_result[:5]
            except:
                res["related_questions"] = []
                
            return JSONResponse(status_code=200, content=_standardize(res))
    except Exception as e:
        print(f"ERROR in generate_conclusion: {str(e)}")
        detail = "결론 도출 중 오류가 발생했습니다."
        if _LAW_DEBUG:
            detail += f" {str(e)}"
        raise HTTPException(status_code=500, detail=detail)

@app.post("/api/v1/chat/qa/knowledge")
async def knowledge_qa(request: QARequest):
    """Handles knowledge-based questions."""
    try:
        set_api_keys(request)
        effective_key = _effective_openai_key(request)
        search_results = await asyncio.to_thread(
            search, collection, request.question, top_k=5,
            filter_sources=ALL_LABOR_LAW_SOURCES,
            exclude_sections=["벌칙", "부칙"],
            openai_api_key=effective_key
        )
        from rag.pipeline import _rag_context
        context = _rag_context(search_results, max_length=2000)
        res = await asyncio.to_thread(
            chat_with_metadata,
            system_knowledge_qa(),
            user_knowledge_qa(request.question, context),
            max_tokens=1000,
            openai_api_key=effective_key
        )
        return JSONResponse(status_code=200, content=_standardize({
            "answer": res.get("content"),
            "metadata": res
        }))
    except Exception as e:
        print(f"ERROR in knowledge_qa: {str(e)}")
        detail = "지식 답변 생성 중 오류가 발생했습니다."
        if _LAW_DEBUG:
            detail += f" {str(e)}"
        raise HTTPException(status_code=500, detail=detail)

@app.post("/api/v1/chat/qa/calculation")
async def calculation_qa(request: QARequest):
    """Handles calculation questions."""
    try:
        set_api_keys(request)
        effective_key = _effective_openai_key(request)
        from rag.pipeline import _rag_context

        def _run_calculation():
            search_results = search(
                collection, request.question, top_k=5,
                filter_sources=ALL_LABOR_LAW_SOURCES,
                openai_api_key=effective_key
            )
            context = _rag_context(search_results, max_length=2000)
            return chat_with_metadata(
                system_calculation_qa(),
                user_calculation_qa(request.question, context),
                max_tokens=1500,
                openai_api_key=effective_key
            )
        res = await asyncio.to_thread(_run_calculation)
        return JSONResponse(status_code=200, content=_standardize({
            "answer": res.get("content"),
            "metadata": res
        }))
    except Exception as e:
        print(f"ERROR in calculation_qa: {str(e)}")
        detail = "금액 계산 중 오류가 발생했습니다."
        if _LAW_DEBUG:
            detail += f" {str(e)}"
        raise HTTPException(status_code=500, detail=detail)

@app.post("/api/v1/chat/qa/documents")
async def documents_qa(request: QARequest):
    """Handles document/form related questions."""
    try:
        set_api_keys(request)
        query = request.question
        for w in ("필요한 서류", "서식", "제출서류", "양식"):
            query = query.replace(w, "").strip()
        query = query or request.question

        def _run_documents():
            docs = search_documents_for_topic(query)
            answer = format_documents_answer(docs, query)
            return answer, docs

        answer, docs = await asyncio.to_thread(_run_documents)
        return JSONResponse(status_code=200, content=_standardize({"answer": answer, "documents": docs}))
    except Exception as e:
        print(f"ERROR in documents_qa: {str(e)}")
        detail = "서류·서식 조회 중 오류가 발생했습니다."
        if _LAW_DEBUG:
            detail += f" {str(e)}"
        raise HTTPException(status_code=500, detail=detail)

# --- Law Browsing Endpoints ---

@app.get("/api/v1/laws/chapters")
async def list_chapters(law_id: Optional[str] = None, source: Optional[str] = None):
    """Lists chapters for a law."""
    try:
        data = get_chapters(law_id, source)
        return JSONResponse(status_code=200, content=_standardize(data))
    except Exception as e:
        print(f"ERROR in list_chapters: {str(e)}")
        detail = "장 목록을 불러오는 중 오류가 발생했습니다."
        if _LAW_DEBUG:
            detail += f" {str(e)}"
        raise HTTPException(status_code=500, detail=detail)

@app.get("/api/v1/laws/articles/{chapter_number}")
async def list_articles(chapter_number: str, law_id: Optional[str] = None, source: Optional[str] = None):
    """Lists articles in a chapter."""
    try:
        data = get_articles_by_chapter(chapter_number, law_id, source)
        return JSONResponse(status_code=200, content=_standardize(data))
    except Exception as e:
        print(f"ERROR in list_articles: {str(e)}")
        detail = "조문 목록을 불러오는 중 오류가 발생했습니다."
        if _LAW_DEBUG:
            detail += f" {str(e)}"
        raise HTTPException(status_code=500, detail=detail)

@app.get("/api/v1/laws/list")
async def list_laws():
    """Lists available laws."""
    try:
        data = get_laws()
        return JSONResponse(status_code=200, content=_standardize(data))
    except Exception as e:
        print(f"ERROR in list_laws: {str(e)}")
        detail = "법령 목록을 불러오는 중 오류가 발생했습니다."
        if _LAW_DEBUG:
            detail += f" {str(e)}"
        raise HTTPException(status_code=500, detail=detail)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
