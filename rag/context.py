from contextvars import ContextVar
from typing import Optional

# Context variables for dynamic API keys / model (request-local)
openai_api_key_ctx: ContextVar[Optional[str]] = ContextVar("openai_api_key", default=None)
law_api_key_ctx: ContextVar[Optional[str]] = ContextVar("law_api_key", default=None)
openai_base_url_ctx: ContextVar[Optional[str]] = ContextVar("openai_base_url", default=None)
chat_model_ctx: ContextVar[Optional[str]] = ContextVar("chat_model", default=None)
