# 노동법 RAG 챗봇 설정
import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
CHAT_MODEL = os.getenv("LAW_CHAT_MODEL", "gpt-5-nano")  # ChatGPT 5.0-nano
EMBEDDING_MODEL = os.getenv("LAW_EMBEDDING_MODEL", "text-embedding-3-small")

# 법령 데이터
LAWS_DIR = Path(__file__).resolve().parent / "laws"
VECTOR_DIR = Path(__file__).resolve().parent / "vector_store"

# RAG
RAG_TOP_K = 15
RAG_SCORE_THRESHOLD = 0.0  # 필요시 상향

# 규칙: RAG에 없는 내용은 "해당 내용은 제공된 법령 데이터에 없습니다." 로만 답변
