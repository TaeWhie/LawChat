from contextvars import ContextVar
from typing import Optional

# Context variables for dynamic API keys / model (request-local)
openai_api_key_ctx: ContextVar[Optional[str]] = ContextVar("openai_api_key", default=None)
law_api_key_ctx: ContextVar[Optional[str]] = ContextVar("law_api_key", default=None)
openai_base_url_ctx: ContextVar[Optional[str]] = ContextVar("openai_base_url", default=None)
chat_model_ctx: ContextVar[Optional[str]] = ContextVar("chat_model", default=None)
# 모델 파라미터 (API 요청에서 지정 시 적용)
temperature_ctx: ContextVar[Optional[float]] = ContextVar("temperature", default=None)
max_tokens_ctx: ContextVar[Optional[int]] = ContextVar("max_tokens", default=None)
reasoning_effort_ctx: ContextVar[Optional[str]] = ContextVar("reasoning_effort", default=None)
top_p_ctx: ContextVar[Optional[float]] = ContextVar("top_p", default=None)
