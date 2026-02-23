import os
import re
import json
import asyncio
import contextvars
from typing import List, Dict, Any, Optional, Generator
from fastapi import FastAPI, Header, HTTPException, Body, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
import uvicorn

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
from config import ALL_LABOR_LAW_SOURCES, SOURCE_DECREE, SOURCE_RULE
from rag.context import openai_api_key_ctx, law_api_key_ctx, openai_base_url_ctx

app = FastAPI(title="LawChat Backend API", version="1.0.0")

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

# --- Data Models ---

class BaseRequest(BaseModel):
    openai_api_key: Optional[str] = Field(None, description="Custom OpenAI API Key")
    law_api_key: Optional[str] = Field(None, description="Custom Law (LIDB) API Key")

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

# --- Helper Functions ---

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
    except:
        return str(obj)

def set_api_keys(keys: BaseRequest):
    """Sets ContextVar for API keys if provided in the request (thread-safe for FastAPI)."""
    if keys.openai_api_key:
        print(f"DEBUG: Setting OpenAI API Key in context: {keys.openai_api_key[:10]}...")
        openai_api_key_ctx.set(keys.openai_api_key)
    if keys.law_api_key:
        print(f"DEBUG: Setting Law API Key in context: {keys.law_api_key[:5]}...")
        law_api_key_ctx.set(keys.law_api_key)

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

@app.get("/api/v1/health")
async def health_check():
    """Health check endpoint to verify deployment version."""
    return {"status": "ok", "version": "1.0.5-explicit-keys", "context_supported": True}

@app.post("/api/v1/chat/route")
async def route_question(request: RouteRequest):
    """Routes the user question to the appropriate type."""
    q_type = classify_type(request.text)
    return {"question_type": q_type}

@app.post("/api/v1/chat/classify")
async def classify_issue(request: ClassifyRequest):
    """Classifies the user situation into legal issues."""
    try:
        set_api_keys(request)
        print(f"DEBUG: Classifying situation: {request.situation[:50]}...")
        
        # Explicitly pass keys and run in thread
        issues, articles_by_issue, _, _ = await asyncio.to_thread(
            step1_issue_classification, 
            request.situation, 
            collection=collection, 
            top_k=request.top_k,
            openai_api_key=request.openai_api_key,
            law_api_key=request.law_api_key
        )
        print(f"DEBUG: Issues found: {issues}")
        
        # Return a minimal, 100% JSON-safe structure
        safe_articles = {}
        for issue, articles in articles_by_issue.items():
            safe_articles[str(issue)] = []
            for a in articles:
                # ONLY include known safe strings
                safe_articles[str(issue)].append({
                    "article": str(a.get("article", "")),
                    "title": str(a.get("title", ""))
                })
                
        content = {
            "status": "success",
            "issues": issues,
            "articles_by_issue": safe_articles
        }
        print("DEBUG: Content built, standardizing...")
        standardized = _standardize(content)
        print("DEBUG: Standardized successfully. Returning JSONResponse.")
        return JSONResponse(status_code=200, content=standardized)
    except Exception as e:
        ctx_val = openai_api_key_ctx.get()
        print(f"ERROR in classify_issue: {str(e)}")
        detail = f"이슈 분류 중 오류가 발생했습니다: {str(e)} | Context OpenAI Key: {bool(ctx_val)}"
        if ctx_val:
            detail += f" ({ctx_val[:5]}...)"
        raise HTTPException(status_code=500, detail=detail)

@app.post("/api/v1/chat/checklist")
async def generate_checklist(request: ChecklistRequest):
    """Generates a checklist for a specific issue and situation."""
    try:
        set_api_keys(request)
        
        narrow_answers = [x.get("answer", "").strip() for x in request.all_qa if x.get("answer") and x.get("answer").strip() not in ("네", "아니요", "모르겠음", "(미입력)")]
        
        # Merge previous results if any
        remaining = request.previous_rag_results
        
        query = (request.issue + " " + " ".join(narrow_answers))[:500] if narrow_answers else request.issue
        new_results = await asyncio.to_thread(
            search, collection, query, top_k=12,
            filter_sources=ALL_LABOR_LAW_SOURCES,
            exclude_sections=["벌칙", "부칙"],
            exclude_chapters=["제1장 총칙"],
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
        )
        
        return JSONResponse(status_code=200, content=_standardize(step2_res))
    except Exception as e:
        print(f"ERROR in generate_checklist: {str(e)}")
        raise HTTPException(status_code=500, detail=f"체크리스트 생성 중 오류가 발생했습니다: {str(e)}")

@app.post("/api/v1/chat/conclusion")
async def generate_conclusion(request: ConclusionRequest):
    """Generates a final conclusion based on QA history."""
    try:
        set_api_keys(request)
        
        narrow_answers = [x.get("answer", "").strip() for x in request.all_qa if x.get("answer") and x.get("answer").strip() not in ("네", "아니요", "모르겠음", "(미입력)")]
        
        if request.stream:
            def stream_generator():
                try:
                    for chunk in step3_conclusion_stream(
                        request.issue, request.all_qa, collection=collection, narrow_answers=narrow_answers or None
                    ):
                        yield chunk
                except Exception as e:
                    yield f"Error: {str(e)}"
            return StreamingResponse(stream_generator(), media_type="text/event-stream")
        else:
            res = await asyncio.to_thread(
                step3_conclusion, request.issue, request.all_qa, collection=collection, narrow_answers=narrow_answers or None
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
                    max_tokens=300
                )
                if isinstance(questions_result, list):
                    res["related_questions"] = questions_result[:5]
            except:
                res["related_questions"] = []
                
            return JSONResponse(status_code=200, content=_standardize(res))
    except Exception as e:
        print(f"ERROR in generate_conclusion: {str(e)}")
        raise HTTPException(status_code=500, detail=f"결론 도출 중 오류가 발생했습니다: {str(e)}")

@app.post("/api/v1/chat/qa/knowledge")
async def knowledge_qa(request: QARequest):
    """Handles knowledge-based questions."""
    try:
        set_api_keys(request)
        search_results = await asyncio.to_thread(
            search, collection, request.question, top_k=5,
            filter_sources=ALL_LABOR_LAW_SOURCES,
            exclude_sections=["벌칙", "부칙"],
        )
        from rag.pipeline import _rag_context
        context = _rag_context(search_results, max_length=2000)
        res = await asyncio.to_thread(
            chat_with_metadata,
            system_knowledge_qa(),
            user_knowledge_qa(request.question, context),
            max_tokens=1000
        )
        return JSONResponse(status_code=200, content=_standardize({
            "answer": res.get("content"),
            "metadata": res
        }))
    except Exception as e:
        print(f"ERROR in knowledge_qa: {str(e)}")
        raise HTTPException(status_code=500, detail=f"지식 답변 생성 중 오류가 발생했습니다: {str(e)}")

@app.post("/api/v1/chat/qa/calculation")
async def calculation_qa(request: QARequest):
    """Handles calculation questions."""
    try:
        set_api_keys(request)
        search_results = search(
            collection, request.question, top_k=5,
            filter_sources=ALL_LABOR_LAW_SOURCES,
        )
        from rag.pipeline import _rag_context
        context = _rag_context(search_results, max_length=2000)
        res = chat_with_metadata(
            system_calculation_qa(),
            user_calculation_qa(request.question, context),
            max_tokens=1500
        )
        return JSONResponse(status_code=200, content=_standardize({
            "answer": res.get("content"),
            "metadata": res
        }))
    except Exception as e:
        print(f"ERROR in calculation_qa: {str(e)}")
        raise HTTPException(status_code=500, detail=f"금액 계산 중 오류가 발생했습니다: {str(e)}")

@app.post("/api/v1/chat/qa/documents")
async def documents_qa(request: QARequest):
    """Handles document/form related questions."""
    set_api_keys(request)
    query = request.question
    for w in ("필요한 서류", "서식", "제출서류", "양식"):
        query = query.replace(w, "").strip()
    docs = search_documents_for_topic(query or request.question)
    answer = format_documents_answer(docs, query or request.question)
    return JSONResponse(status_code=200, content=_standardize({"answer": answer, "documents": docs}))

# --- Law Browsing Endpoints ---

@app.get("/api/v1/laws/chapters")
async def list_chapters(law_id: Optional[str] = None, source: Optional[str] = None):
    """Lists chapters for a law."""
    return JSONResponse(status_code=200, content=_standardize(get_chapters(law_id, source)))

@app.get("/api/v1/laws/articles/{chapter_number}")
async def list_articles(chapter_number: str, law_id: Optional[str] = None, source: Optional[str] = None):
    """Lists articles in a chapter."""
    return JSONResponse(status_code=200, content=_standardize(get_articles_by_chapter(chapter_number, law_id, source)))

@app.get("/api/v1/laws/list")
async def list_laws():
    """Lists available laws."""
    return JSONResponse(status_code=200, content=_standardize(get_laws()))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
