import os
import asyncio
import uuid
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field
import uvicorn

# LAW_DEBUG=1 일 때만 클라이언트에 예외 상세 노출
_LAW_DEBUG = os.getenv("LAW_DEBUG", "0") == "1"
# Rate limit: 분당 최대 요청 수 (0이면 비활성화)
_RATE_LIMIT_PER_MIN = int(os.getenv("RATE_LIMIT_PER_MINUTE", "0"))
_RATE_LIMIT_WINDOW = 60.0  # seconds
_rate_limit_store: Dict[str, List[float]] = {}

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
from rag.prompts import (
    system_related_questions,
    user_related_questions,
    system_issue_classification,
    user_issue_classification,
    system_checklist,
    user_checklist,
    system_checklist_continuation,
    user_checklist_continuation,
    system_conclusion,
    user_conclusion,
)
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
from config import ALL_LABOR_LAW_SOURCES, SOURCE_DECREE, SOURCE_RULE, OPENAI_API_KEY, LAW_API_OC
from rag.context import (
    openai_api_key_ctx,
    law_api_key_ctx,
    openai_base_url_ctx,
    chat_model_ctx,
    temperature_ctx,
    max_tokens_ctx,
    reasoning_effort_ctx,
    top_p_ctx,
)

app = FastAPI(
    title="LawChat Backend API",
    version=os.getenv("LAW_API_VERSION", "1.2.0"),
    description="노동법 RAG 오케스트레이션 백엔드. 이슈 분류·체크리스트·결론 파이프라인과 벡터 검색을 제공하며, LLM 호출은 요청 시 클라이언트가 보낸 API 키·모델·파라미터로 실행합니다(BYOK).",
)

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

# Global Vector Store Collection (lazy-loaded so Render port scan succeeds before long build)
collection = None
_collection_lock = None

def _get_collection_lock():
    global _collection_lock
    if _collection_lock is None:
        import threading
        _collection_lock = threading.Lock()
    return _collection_lock

def get_collection():
    """벡터 스토어 컬렉션 반환. 없으면 한 번만 구축 후 캐시 (첫 요청 시 지연 로딩)."""
    global collection
    if collection is not None:
        return collection
    with _get_collection_lock():
        if collection is not None:
            return collection
        col, _ = build_vector_store()
        collection = col
        try:
            import rag.graph as _g
            _g._collection_cache = col
        except Exception:
            pass
        return collection


@app.on_event("startup")
async def startup_event():
    """시작 시 무거운 벡터 스토어 구축은 하지 않음. 포트 바인딩을 위해 첫 요청 시 get_collection()에서 지연 로딩."""
    pass

# --- Data Models ---

class BaseRequest(BaseModel):
    openai_api_key: Optional[str] = Field(None, description="Custom OpenAI API Key")
    openai_base_url: Optional[str] = Field(None, description="Custom OpenAI API Base URL (e.g. Azure, proxy)")
    model: Optional[str] = Field(None, description="Chat model override (e.g. gpt-4o, gpt-4o-mini)")
    temperature: Optional[float] = Field(None, description="LLM temperature (0.0~2.0). 미지정 시 기본값 사용")
    max_tokens: Optional[int] = Field(None, description="LLM 최대 출력 토큰 수. 미지정 시 기본값 사용")
    reasoning_effort: Optional[str] = Field(None, description="추론 모델(o1/o3 등)용: low | medium | high. 미지정 시 기본값")
    top_p: Optional[float] = Field(None, description="LLM top_p (0.0~1.0). 미지정 시 기본값. 추론 모델에는 미적용")

class RouteRequest(BaseRequest):
    text: str

class ClassifyRequest(BaseRequest):
    situation: str
    top_k: int = 22
    prompt_overrides: Optional[Dict[str, str]] = Field(None, description="system_issue_classification, user_issue_classification 등")

class ChecklistRequest(BaseRequest):
    issue: str
    situation: str
    all_qa: List[Dict[str, str]] = []
    round: int = 1
    previous_rag_results: List[Dict[str, Any]] = []
    prompt_overrides: Optional[Dict[str, str]] = Field(None, description="system_checklist, user_checklist, system_checklist_continuation 등")

class ConclusionRequest(BaseRequest):
    issue: str
    all_qa: List[Dict[str, str]]
    stream: bool = False
    prompt_overrides: Optional[Dict[str, str]] = Field(None, description="system_conclusion, user_conclusion 등")
    checklist_rag_results: Optional[List[Dict[str, Any]]] = Field(None, description="체크리스트 단계에서 반환된 rag_results. 있으면 결론 AI가 해당 조문을 함께 참고합니다.")

class QARequest(BaseRequest):
    question: str
    context: Optional[str] = None


class BatchInvokeItem(BaseModel):
    message: str = Field(..., description="사용자 메시지")
    thread_id: Optional[str] = Field("default", description="대화 스레드 ID")
    temperature: Optional[float] = Field(None, description="해당 항목만 적용. 미지정 시 상위 요청 값 사용")
    max_tokens: Optional[int] = Field(None, description="해당 항목만 적용")
    reasoning_effort: Optional[str] = Field(None, description="해당 항목만 적용")
    top_p: Optional[float] = Field(None, description="해당 항목만 적용")


class BatchInvokeRequest(BaseRequest):
    """배치 invoke: 여러 메시지를 한 번에 처리."""
    requests: List[BatchInvokeItem] = Field(..., description="최대 10개 권장. 각 항목에 message, thread_id")


class InvokeRequest(BaseRequest):
    """챗봇과 동일한 1회 graph.invoke 요청 (app_chatbot과 동일 성능)."""
    message: str = Field(..., description="사용자 입력 메시지")
    thread_id: Optional[str] = Field("default", description="대화 스레드 ID (체크포인터 구분용)")
    prompt_overrides: Optional[Dict[str, str]] = Field(None, description="단계별 프롬프트 덮어쓰기")
    response_format: Optional[str] = Field(None, description="출력 형식: markdown | plain. 기본 markdown")
    max_length: Optional[int] = Field(None, description="응답 메시지 최대 문자 수. 초과 시 잘림")
    language: Optional[str] = Field(None, description="응답 언어: ko | en. 기본 ko")
    tone: Optional[str] = Field(None, description="톤: formal | casual. 기본 formal")
    top_k: Optional[int] = Field(None, description="이슈 분류·검색 시 가져올 조문 수 (기본 22)")
    filter_sources: Optional[List[str]] = Field(None, description="검색 대상 법령 목록. 비우면 전체 노동법")
    stream: Optional[bool] = Field(False, description="true 시 응답을 SSE로 스트리밍(마지막 AI 메시지). false면 일반 JSON")

# --- Helper Functions ---


def _error_detail(default: str, e: Exception, raw_request: Optional[Request] = None) -> str:
    """LAW_DEBUG=1 또는 요청 헤더 X-Law-Debug: 1 이면 예외 메시지를 포함해 반환 (재배포 없이 디버깅용)."""
    if _LAW_DEBUG:
        return f"{default} {str(e)}"
    if raw_request and raw_request.headers.get("X-Law-Debug") == "1":
        return f"{default} {str(e)}"
    return default


def _effective_openai_key(keys: Optional[BaseRequest]) -> Optional[str]:
    """요청·컨텍스트·환경변수 순으로 유효한 OpenAI API 키 반환 (asyncio.to_thread 내부에서 키 부재 방지)."""
    if keys and getattr(keys, "openai_api_key", None) and str(keys.openai_api_key).strip():
        return str(keys.openai_api_key).strip()
    return openai_api_key_ctx.get() or OPENAI_API_KEY


def _require_openai_key(request: BaseRequest) -> None:
    """LLM 사용 API: 클라이언트가 openai_api_key를 보내야 함. 없으면 400."""
    key = getattr(request, "openai_api_key", None) and str(request.openai_api_key or "").strip()
    if not key:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "MISSING_API_KEY",
                "message": "이 API는 LLM을 사용합니다. 요청 바디에 openai_api_key(필수)를 넣어 주세요. model(선택)으로 모델을 지정할 수 있습니다.",
            },
        )

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


def _serialize_invoke_result(r: dict, max_length: Optional[int] = None, response_format: Optional[str] = None) -> dict:
    """graph.invoke() 결과를 app_chatbot과 동일한 JSON 구조로 변환. max_length/response_format 적용."""
    import re
    msgs = r.get("messages") or []
    msg_list = []
    for m in msgs:
        c = getattr(m, "content", None) or str(m)
        if response_format == "plain" and c:
            c = re.sub(r"\*+([^*]+)\*+", r"\1", c)
            c = re.sub(r"#{1,6}\s*", "", c)
            c = re.sub(r"\n+", "\n", c).strip()
        if max_length and len(c) > max_length:
            c = c[:max_length] + "..."
        kind = "AIMessage" if isinstance(m, AIMessage) else "HumanMessage"
        msg_list.append({"t": kind, "c": c})
    out = {
        "status": "ok",
        "messages": msg_list,
        "phase": r.get("phase"),
        "checklist": r.get("checklist"),
        "selected_issue": r.get("selected_issue"),
        "situation": r.get("situation"),
        "articles_by_issue": r.get("articles_by_issue"),
        "checklist_rag_results": r.get("checklist_rag_results"),
    }
    if r.get("usage"):
        out["usage"] = r["usage"]
    return out

def set_api_keys(keys: BaseRequest):
    """Sets ContextVar for API keys / base URL / model / model params. 법령 API 키는 요청에서 받지 않고 서버 Secret(LAW_API_OC)만 사용."""
    if keys.openai_api_key and keys.openai_api_key.strip():
        openai_api_key_ctx.set(keys.openai_api_key.strip())
    if keys.openai_base_url is not None and keys.openai_base_url.strip():
        openai_base_url_ctx.set(keys.openai_base_url.strip())
    law_api_key_ctx.set(LAW_API_OC or "")
    if keys.model is not None and keys.model.strip():
        chat_model_ctx.set(keys.model.strip())
    if getattr(keys, "temperature", None) is not None:
        temperature_ctx.set(keys.temperature)
    if getattr(keys, "max_tokens", None) is not None:
        max_tokens_ctx.set(keys.max_tokens)
    if getattr(keys, "reasoning_effort", None) is not None and str(keys.reasoning_effort).strip():
        reasoning_effort_ctx.set(keys.reasoning_effort.strip())
    if getattr(keys, "top_p", None) is not None:
        top_p_ctx.set(keys.top_p)


def _invoke_graph_with_request_keys(
    effective_key: str,
    message: str,
    thread_id: str,
    effective_base_url: Optional[str] = None,
    effective_model: Optional[str] = None,
    prompt_overrides: Optional[Dict[str, str]] = None,
    response_format: Optional[str] = None,
    max_length: Optional[int] = None,
    language: Optional[str] = None,
    tone: Optional[str] = None,
    top_k: Optional[int] = None,
    filter_sources: Optional[List[str]] = None,
    effective_temperature: Optional[float] = None,
    effective_max_tokens: Optional[int] = None,
    effective_reasoning_effort: Optional[str] = None,
    effective_top_p: Optional[float] = None,
):
    """
    워커 스레드 내부에서 요청 바디의 키·모델 파라미터를 ContextVar에 설정한 뒤 graph.invoke 실행.
    서버는 OpenAI API 키를 제공하지 않음. 클라이언트가 요청 바디에 openai_api_key를 반드시 넣어야 함.
    """
    openai_api_key_ctx.set((effective_key or "").strip() or "")
    if effective_base_url:
        openai_base_url_ctx.set(effective_base_url)
    if effective_model:
        chat_model_ctx.set(effective_model)
    law_api_key_ctx.set(LAW_API_OC or "")
    if effective_temperature is not None:
        temperature_ctx.set(effective_temperature)
    if effective_max_tokens is not None:
        max_tokens_ctx.set(effective_max_tokens)
    if effective_reasoning_effort:
        reasoning_effort_ctx.set(effective_reasoning_effort)
    if effective_top_p is not None:
        top_p_ctx.set(effective_top_p)
    graph = get_graph()
    initial_state = {
        "messages": [HumanMessage(content=message or " ")],
        "prompt_overrides": prompt_overrides or {},
        "response_format": response_format,
        "max_length": max_length,
        "language": language,
        "tone": tone,
        "top_k": top_k,
        "filter_sources": filter_sources,
    }
    return graph.invoke(
        initial_state,
        config={"configurable": {"thread_id": thread_id}},
    )

# --- Endpoints ---

@app.middleware("http")
async def context_middleware(request: Request, call_next):
    """trace_id(X-Request-Id) 부여, 선택 시 rate limit 적용."""
    import time
    request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
    if _RATE_LIMIT_PER_MIN > 0:
        client = request.client.host if request.client else "unknown"
        now = time.time()
        if client not in _rate_limit_store:
            _rate_limit_store[client] = []
        times = _rate_limit_store[client]
        times[:] = [t for t in times if now - t < _RATE_LIMIT_WINDOW]
        if len(times) >= _RATE_LIMIT_PER_MIN:
            return JSONResponse(
                status_code=429,
                content={"code": "RATE_LIMITED", "detail": "요청 한도 초과. 잠시 후 다시 시도해 주세요."},
            )
        times.append(now)
    response = await call_next(request)
    response.headers["X-Request-Id"] = request_id
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


@app.api_route("/api/v1/health", methods=["GET", "HEAD"])
async def health_check(request: Request):
    """Health check: 버전, 벡터스토어·의존성 상태. GET/HEAD 모두 200 (Render 등 HEAD 헬스체크 대응)."""
    version = os.getenv("LAW_API_VERSION", "1.2.0")
    vector_store_ready = collection is not None
    try:
        from pathlib import Path
        from config import VECTOR_DIR
        vector_dir_exists = Path(VECTOR_DIR).exists() if VECTOR_DIR else False
    except Exception:
        vector_dir_exists = False
    body = {
        "status": "ok",
        "version": version,
        "context_supported": True,
        "vector_store_ready": vector_store_ready,
        "vector_dir_exists": vector_dir_exists,
    }
    from fastapi.responses import JSONResponse, Response
    if request.method == "HEAD":
        return Response(status_code=200)
    return JSONResponse(content=body, status_code=200)


@app.get("/api/v1/prompts")
async def get_default_prompts():
    """
    프롬프트 커스터마이징용: prompt_overrides에 사용하는 모든 기본(기본값) 프롬프트를 반환합니다.
    user_* 프롬프트는 플레이스홀더 예시(<situation>, <issue> 등)로 호출한 템플릿 형태로 반환됩니다.
    """
    # user 프롬프트용 플레이스홀더 (템플릿 구조 확인용)
    ph_situation = "<situation>"
    ph_rag = "<rag_context>"
    ph_issue = "<issue>"
    ph_filtered = "<filtered_provisions>"
    ph_asked = "<already_asked_text>"
    ph_qa_list = "<qa_list>"
    ph_question = "<question>"
    qa_sample = [{"question": "<Q1>", "answer": "<A1>"}]

    prompts = {
        "system_issue_classification": system_issue_classification(),
        "user_issue_classification": user_issue_classification(ph_situation, ph_rag),
        "system_checklist": system_checklist(),
        "user_checklist": user_checklist(ph_issue, ph_rag, ph_filtered, ph_asked),
        "system_checklist_continuation": system_checklist_continuation(),
        "user_checklist_continuation": user_checklist_continuation(ph_issue, qa_sample, ph_rag),
        "system_conclusion": system_conclusion(),
        "user_conclusion": user_conclusion(ph_issue, ph_qa_list, ph_rag),
        "system_knowledge_qa": system_knowledge_qa(),
        "user_knowledge_qa": user_knowledge_qa(ph_question, ph_rag),
        "system_calculation_qa": system_calculation_qa(),
        "user_calculation_qa": user_calculation_qa(ph_question, ph_rag),
        "system_exception_qa": system_exception_qa(),
        "user_exception_qa": user_exception_qa(ph_question, ph_rag),
    }
    placeholders = {
        "user_issue_classification": ["situation", "rag_context", "allowed_block(optional)"],
        "user_checklist": ["issue", "rag_context", "filtered_provisions", "already_asked_text"],
        "user_checklist_continuation": ["issue", "qa_text (Q&A 목록)", "rag_context"],
        "user_conclusion": ["issue", "qa_list", "rag_context", "related_articles_hint", "law_names_hint"],
        "user_knowledge_qa": ["question", "rag_context"],
        "user_calculation_qa": ["question", "rag_context"],
        "user_exception_qa": ["question", "rag_context"],
    }
    return {
        "prompts": prompts,
        "placeholders": placeholders,
        "usage": "prompt_overrides에 넣을 때 위 키와 동일한 이름으로 덮어쓰면 됩니다. user_* 템플릿은 플레이스홀더를 {변수명} 형태로 사용하세요.",
    }


@app.post("/api/v1/chat/route")
async def route_question(request: RouteRequest):
    """Routes the user question to the appropriate type."""
    _require_openai_key(request)
    set_api_keys(request)
    q_type = await asyncio.to_thread(classify_type, request.text)
    return {"question_type": q_type}


@app.post("/api/v1/chat/invoke")
async def chat_invoke(request: InvokeRequest, raw_request: Request):
    """app_chatbot과 동일: 1회 graph.invoke로 전체 RAG 플로우 실행 (라우팅·이슈분류·체크리스트·결론·지식/계산/서류 분기 포함)."""
    _require_openai_key(request)
    try:
        effective_key = _effective_openai_key(request)
        thread_id = (request.thread_id or "default").strip() or "default"
        message = request.message.strip() or " "
        effective_base = (request.openai_base_url or openai_base_url_ctx.get() or "").strip() or None
        effective_model = (getattr(request, "model", None) or chat_model_ctx.get() or "").strip() or None
        overrides = getattr(request, "prompt_overrides", None) or None
        result = await asyncio.to_thread(
            _invoke_graph_with_request_keys,
            effective_key,
            message,
            thread_id,
            effective_base,
            effective_model,
            overrides,
            getattr(request, "response_format", None),
            getattr(request, "max_length", None),
            getattr(request, "language", None),
            getattr(request, "tone", None),
            getattr(request, "top_k", None),
            getattr(request, "filter_sources", None),
            getattr(request, "temperature", None),
            getattr(request, "max_tokens", None),
            getattr(request, "reasoning_effort", None),
            getattr(request, "top_p", None),
        )
        payload = _serialize_invoke_result(
            result,
            max_length=result.get("max_length") or getattr(request, "max_length", None),
            response_format=result.get("response_format") or getattr(request, "response_format", None),
        )
        if getattr(request, "stream", None):
            # SSE: 청크 단위로 마지막 AI 메시지 전송 후, done 이벤트에 메타데이터 포함
            def _invoke_stream():
                import json as _json
                msgs = payload.get("messages") or []
                last_content = ""
                for m in reversed(msgs):
                    if isinstance(m, dict) and m.get("t") == "AIMessage" and m.get("c"):
                        last_content = m.get("c", "")
                        break
                chunk_size = 80
                for i in range(0, len(last_content), chunk_size):
                    yield f"data: {_json.dumps({'type': 'chunk', 'content': last_content[i:i+chunk_size]}, ensure_ascii=False)}\n\n"
                meta = {k: payload.get(k) for k in ("status", "phase", "checklist", "selected_issue", "situation", "usage") if payload.get(k) is not None}
                meta["messages"] = payload.get("messages")
                yield f"data: {_json.dumps({'type': 'done', **meta}, ensure_ascii=False, default=str)}\n\n"
            return StreamingResponse(
                _invoke_stream(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        return JSONResponse(status_code=200, content=_standardize(payload))
    except Exception as e:
        print(f"ERROR in chat_invoke: {str(e)}")
        detail = _error_detail("상담 처리 중 오류가 발생했습니다.", e, raw_request)
        raise HTTPException(
            status_code=500,
            detail={"code": "INTERNAL_ERROR", "message": detail} if isinstance(detail, str) else detail,
        )


@app.post("/api/v1/chat/invoke/batch")
async def chat_invoke_batch(request: BatchInvokeRequest, raw_request: Request):
    """여러 메시지를 순차 처리. openai_api_key·model은 상위에서 공통 적용."""
    _require_openai_key(request)
    effective_key = _effective_openai_key(request)
    effective_base = (request.openai_base_url or openai_base_url_ctx.get() or "").strip() or None
    effective_model = (getattr(request, "model", None) or chat_model_ctx.get() or "").strip() or None
    overrides = getattr(request, "prompt_overrides", None) or None
    results = []
    for item in request.requests[:20]:  # 최대 20개
        try:
            thread_id = (item.thread_id or "default").strip() or "default"
            msg = item.message.strip() or " "
            eff_temp = getattr(item, "temperature", None) if getattr(item, "temperature", None) is not None else getattr(request, "temperature", None)
            eff_max = getattr(item, "max_tokens", None) if getattr(item, "max_tokens", None) is not None else getattr(request, "max_tokens", None)
            eff_reason = getattr(item, "reasoning_effort", None) or getattr(request, "reasoning_effort", None)
            eff_top_p = getattr(item, "top_p", None) if getattr(item, "top_p", None) is not None else getattr(request, "top_p", None)
            result = await asyncio.to_thread(
                _invoke_graph_with_request_keys,
                effective_key, msg, thread_id,
                effective_base, effective_model,
                overrides, None, None, None, None, None, None,
                eff_temp, eff_max, eff_reason, eff_top_p,
            )
            payload = _serialize_invoke_result(result)
            results.append({"status": "ok", "result": payload})
        except Exception as e:
            results.append({"status": "error", "message": str(e)})
    return JSONResponse(status_code=200, content=_standardize({"results": results, "count": len(results)}))


@app.post("/api/v1/chat/classify")
async def classify_issue(request: ClassifyRequest, raw_request: Request):
    """Classifies the user situation into legal issues."""
    _require_openai_key(request)
    try:
        set_api_keys(request)
        effective_key = _effective_openai_key(request)
        if _LAW_DEBUG:
            print(f"DEBUG: Classifying situation: {request.situation[:50]}...")
        overrides = getattr(request, "prompt_overrides", None) or {}
        issues, articles_by_issue, _, _ = await asyncio.to_thread(
            step1_issue_classification,
            request.situation,
            collection=get_collection(),
            top_k=request.top_k,
            prompt_overrides=overrides,
            openai_api_key=effective_key,
            law_api_key=None,
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
        detail = _error_detail("이슈 분류 중 오류가 발생했습니다.", e, raw_request)
        raise HTTPException(status_code=500, detail=detail)

@app.post("/api/v1/chat/checklist")
async def generate_checklist(request: ChecklistRequest, raw_request: Request):
    """Generates a checklist for a specific issue and situation."""
    _require_openai_key(request)
    try:
        set_api_keys(request)
        
        narrow_answers = [x.get("answer", "").strip() for x in request.all_qa if x.get("answer") and x.get("answer").strip() not in ("네", "아니요", "모르겠음", "(미입력)")]
        
        # Merge previous results if any
        remaining = request.previous_rag_results
        
        effective_key = _effective_openai_key(request)
        query = (request.issue + " " + " ".join(narrow_answers))[:500] if narrow_answers else request.issue
        new_results = await asyncio.to_thread(
            search, get_collection(), query, top_k=12,
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
                
        filter_text = (request.issue + " " + request.situation.strip() + " " + "\n".join(f"Q: {x['question']} A: {x['answer']}" for x in request.all_qa))[:500]
        
        overrides = getattr(request, "prompt_overrides", None) or {}
        step2_res = await asyncio.to_thread(
            step2_checklist, request.issue, filter_text, collection=get_collection(),
            narrow_answers=narrow_answers or None,
            qa_list=request.all_qa,
            remaining_articles=merged,
            situation=request.situation.strip() or None,
            prompt_overrides=overrides,
            openai_api_key=effective_key,
        )
        
        return JSONResponse(status_code=200, content=_standardize(step2_res))
    except Exception as e:
        print(f"ERROR in generate_checklist: {str(e)}")
        detail = _error_detail("체크리스트 생성 중 오류가 발생했습니다.", e, raw_request)
        raise HTTPException(status_code=500, detail=detail)

@app.post("/api/v1/chat/conclusion")
async def generate_conclusion(request: ConclusionRequest, raw_request: Request):
    """Generates a final conclusion based on QA history."""
    _require_openai_key(request)
    try:
        set_api_keys(request)
        
        narrow_answers = [x.get("answer", "").strip() for x in request.all_qa if x.get("answer") and x.get("answer").strip() not in ("네", "아니요", "모르겠음", "(미입력)")]
        
        if request.stream:
            # 제너레이터는 응답 전송 스레드에서 실행되므로 컨텍스트 미복사 → 유효 키를 미리 캡처
            effective_key = request.openai_api_key or openai_api_key_ctx.get()

            def stream_generator():
                try:
                    for chunk in step3_conclusion_stream(
                        request.issue, request.all_qa, collection=get_collection(), narrow_answers=narrow_answers or None,
                        checklist_rag_results=getattr(request, "checklist_rag_results", None) or None,
                        openai_api_key=effective_key
                    ):
                        yield chunk
                except Exception as e:
                    yield f"Error: {str(e)}"
            return StreamingResponse(stream_generator(), media_type="text/event-stream")
        else:
            effective_key = _effective_openai_key(request)
            overrides = getattr(request, "prompt_overrides", None) or {}
            res = await asyncio.to_thread(
                step3_conclusion, request.issue, request.all_qa, collection=get_collection(), narrow_answers=narrow_answers or None,
                checklist_rag_results=getattr(request, "checklist_rag_results", None) or None,
                prompt_overrides=overrides,
                openai_api_key=effective_key
            )
            # Add penalty/supplementary info
            conclusion_text = res.get("conclusion", "")
            penalty = await asyncio.to_thread(
                get_penalty_and_supplementary, get_collection(), conclusion_text, request.issue, request.all_qa
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
            # 토큰 사용량: 결론 생성 LLM 호출 기준 (debug_info.llm_conclusion.usage)
            llm_meta = res.get("debug_info") or {}
            if isinstance(llm_meta.get("llm_conclusion"), dict) and llm_meta["llm_conclusion"].get("usage"):
                res["usage"] = llm_meta["llm_conclusion"]["usage"]
            return JSONResponse(status_code=200, content=_standardize(res))
    except Exception as e:
        print(f"ERROR in generate_conclusion: {str(e)}")
        detail = _error_detail("결론 도출 중 오류가 발생했습니다.", e, raw_request)
        raise HTTPException(status_code=500, detail=detail)

@app.post("/api/v1/chat/qa/knowledge")
async def knowledge_qa(request: QARequest, raw_request: Request):
    """Handles knowledge-based questions."""
    _require_openai_key(request)
    try:
        set_api_keys(request)
        effective_key = _effective_openai_key(request)
        search_results = await asyncio.to_thread(
            search, get_collection(), request.question, top_k=5,
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
        detail = _error_detail("지식 답변 생성 중 오류가 발생했습니다.", e, raw_request)
        raise HTTPException(status_code=500, detail=detail)

@app.post("/api/v1/chat/qa/calculation")
async def calculation_qa(request: QARequest, raw_request: Request):
    """Handles calculation questions."""
    _require_openai_key(request)
    try:
        set_api_keys(request)
        effective_key = _effective_openai_key(request)
        from rag.pipeline import _rag_context

        def _run_calculation():
            search_results = search(
                get_collection(), request.question, top_k=5,
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
        detail = _error_detail("금액 계산 중 오류가 발생했습니다.", e, raw_request)
        raise HTTPException(status_code=500, detail=detail)

@app.post("/api/v1/chat/qa/documents")
async def documents_qa(request: QARequest, raw_request: Request):
    """서류·서식 질문. 국가법령정보 licbyl/admbyl API 사용. 서버 Secret(LAW_API_OC) 필요."""
    try:
        set_api_keys(request)
        # graph와 동일한 쿼리 전처리: 서류 관련 표현 제거 후 첫 단어(2자 이상) 사용
        query = (request.question or "").strip()
        for w in ("필요한 서류", "필요 서류", "제출서류", "서식", "서류", "양식", "별표", "뭐가", "무엇", "어떤", "무슨", "가 필요", "가 있나", "가 있나요", "?"):
            query = query.replace(w, " ").strip()
        query = query or (request.question or "").strip() or "근로"
        first_word = (query.split() or [query])[0].strip()
        if len(first_word) >= 2:
            query = first_word
        law_key = (law_api_key_ctx.get() or LAW_API_OC or "").strip() or None

        def _run_documents():
            docs = search_documents_for_topic(query, display=15, oc=law_key)
            answer = format_documents_answer(docs, query)
            return answer, docs

        answer, docs = await asyncio.to_thread(_run_documents)
        return JSONResponse(status_code=200, content=_standardize({"answer": answer, "documents": docs}))
    except ValueError as e:
        if "LAW_API_OC" in str(e) or "설정되지 않았습니다" in str(e):
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "DOCUMENTS_REQUIRES_LAW_API_KEY",
                    "message": "서류·서식 검색은 국가법령정보 API(OC) 키가 필요합니다. 서버에 LAW_API_OC Secret을 설정해 주세요.",
                },
            )
        raise HTTPException(status_code=500, detail=_error_detail("서류·서식 조회 중 오류가 발생했습니다.", e, raw_request))
    except Exception as e:
        print(f"ERROR in documents_qa: {str(e)}")
        detail = _error_detail("서류·서식 조회 중 오류가 발생했습니다.", e, raw_request)
        raise HTTPException(status_code=500, detail=detail)

# --- Law Browsing Endpoints ---

@app.get("/api/v1/laws/chapters")
async def list_chapters(raw_request: Request, law_id: Optional[str] = None, source: Optional[str] = None):
    """Lists chapters for a law."""
    try:
        data = get_chapters(law_id, source)
        return JSONResponse(status_code=200, content=_standardize(data))
    except Exception as e:
        print(f"ERROR in list_chapters: {str(e)}")
        detail = _error_detail("장 목록을 불러오는 중 오류가 발생했습니다.", e, raw_request)
        raise HTTPException(status_code=500, detail=detail)

@app.get("/api/v1/laws/articles/{chapter_number}")
async def list_articles(chapter_number: str, raw_request: Request, law_id: Optional[str] = None, source: Optional[str] = None):
    """Lists articles in a chapter."""
    try:
        data = get_articles_by_chapter(chapter_number, law_id, source)
        return JSONResponse(status_code=200, content=_standardize(data))
    except Exception as e:
        print(f"ERROR in list_articles: {str(e)}")
        detail = _error_detail("조문 목록을 불러오는 중 오류가 발생했습니다.", e, raw_request)
        raise HTTPException(status_code=500, detail=detail)

@app.get("/api/v1/laws/list")
async def list_laws(raw_request: Request):
    """Lists available laws."""
    try:
        data = get_laws()
        return JSONResponse(status_code=200, content=_standardize(data))
    except Exception as e:
        print(f"ERROR in list_laws: {str(e)}")
        detail = _error_detail("법령 목록을 불러오는 중 오류가 발생했습니다.", e, raw_request)
        raise HTTPException(status_code=500, detail=detail)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
