# RAG 벡터 스토어 (ChromaDB) 및 검색
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional
from functools import lru_cache

import chromadb
from openai import OpenAI

from config import VECTOR_DIR, EMBEDDING_MODEL, RAG_TOP_K, OPENAI_API_KEY, OPENAI_BASE_URL, SOURCE_LAW
from rag.load_laws import load_laws_auto
from rag.context import openai_api_key_ctx

# OpenAI 임베딩 클라이언트 전역 재사용 (연결 재사용으로 속도 향상)
# 임베딩은 반드시 공식 OpenAI 엔드포인트를 사용해야 함
# (OPENAI_BASE_URL은 gpt-5-nano 같은 LLM 전용 프록시 URL이라 임베딩 API 미지원 → 404)
OPENAI_OFFICIAL_BASE_URL = "https://api.openai.com/v1"

# OpenAI 임베딩 클라이언트 캐시 (API 키별로 구분)
_embedding_clients: Dict[str, OpenAI] = {}

def _get_embedding_client(api_key: Optional[str] = None) -> OpenAI:
    """
    임베딩용 클라이언트 반환.
    1. 인자로 넘어온 키 (최우선)
    2. 컨텍스트에서 키 가져오기 (차선)
    3. 기본 키 사용 (최후)
    """
    actual_api_key = api_key or openai_api_key_ctx.get() or OPENAI_API_KEY
    
    if actual_api_key not in _embedding_clients:
        _embedding_clients[actual_api_key] = OpenAI(
            api_key=actual_api_key,
            base_url=OPENAI_OFFICIAL_BASE_URL,
        )
    return _embedding_clients[actual_api_key]

# 임베딩 캐싱 (텍스트 + 키 조합으로 캐싱)
@lru_cache(maxsize=1000)
def get_embedding(text: str, model: str = EMBEDDING_MODEL, api_key: Optional[str] = None) -> tuple:
    """텍스트 임베딩 (OpenAI)."""
    client = _get_embedding_client(api_key)
    r = client.embeddings.create(input=[text], model=model)
    return tuple(r.data[0].embedding)


def get_embeddings_batch(texts: List[str], model: str = EMBEDDING_MODEL, api_key: Optional[str] = None) -> List[List[float]]:
    """여러 텍스트를 배치 임베딩."""
    if not texts:
        return []
    client = _get_embedding_client(api_key)
    r = client.embeddings.create(input=texts, model=model)
    return [list(e.embedding) for e in r.data]


def build_vector_store(force_rebuild: bool = False):
    """
    법령 청크를 임베딩하여 ChromaDB에 저장.
    저장 위치: config.VECTOR_DIR (기본: 프로젝트/vector_store/)
    - 배포 시: GitHub Action 등에서 미리 구축해 둔 vector_store/ 가 있으면 로드만 하고 재구축하지 않음.
    - 개발/CI: existing == 0 이거나 force_rebuild 시에만 load_laws_auto() 후 임베딩 실행.
    반환: (collection, was_built) — was_built=True면 이번에 새로 구축함.
    """
    VECTOR_DIR.mkdir(parents=True, exist_ok=True)
    persistent_client = chromadb.PersistentClient(path=str(VECTOR_DIR))
    collection_name = "labor_law_articles"
    if force_rebuild:
        try:
            persistent_client.delete_collection(collection_name)
        except Exception:
            pass
    collection = persistent_client.get_or_create_collection(
        name=collection_name,
        metadata={"description": "근로기준법 등 노동법령 조문"},
    )
    # 이미 저장된 벡터 스토어가 있으면 로드만 하고 구축·임베딩은 건너뜀 (배포 시 CI에서 미리 만들어 둔 경우)
    existing = collection.count()
    if existing > 0 and not force_rebuild:
        return collection, False
    chunks = load_laws_auto()
    if not chunks:
        return collection, False
    # 이미 문서 수가 같으면 재임베딩 없이 기존 스토어 사용
    if existing >= len(chunks) and not force_rebuild:
        return collection, False
    if force_rebuild or existing == 0:
        ids = []
        documents = []
        metadatas = []
        for i, c in enumerate(chunks):
            ids.append(hashlib.sha256(f"{c['source']}_{c['article']}_{i}".encode()).hexdigest()[:24])
            # 임베딩용 텍스트 사용 (장 정보 포함) 또는 원본 텍스트
            doc_text = c.get("embedding_text", c["text"])
            documents.append(doc_text)
            meta = {"source": c["source"], "article": c["article"], "kind": c.get("kind", "")}
            if "section" in c:
                meta["section"] = c["section"]
            if "chapter" in c:
                meta["chapter"] = c["chapter"]
            if c.get("primary_category"):
                meta["primary_category"] = c["primary_category"]
            # 원본 텍스트를 메타데이터에 저장 (검색 결과 반환 시 사용)
            meta["original_text"] = c["text"]
            metadatas.append(meta)
        # 배치 임베딩 (한 번에 너무 많으면 나눔)
        # text-embedding-3-large는 최대 8192 토큰 (약 8000자) 제한
        # 각 문서를 최대 8000자로 제한하고, 배치 크기도 줄임
        import time
        MAX_TEXT_LENGTH = 8000  # 안전 마진 포함
        MAX_RETRIES = 3
        RETRY_DELAY = 2  # 재시도 전 대기 시간 (초)
        batch_size = 20  # 배치 크기 감소 (50 -> 20)
        client = _get_embedding_client()
        
        # 텍스트 길이 제한 (긴 문서는 분할)
        processed_docs = []
        processed_ids = []
        processed_meta = []
        
        for i, doc in enumerate(documents):
            if len(doc) > MAX_TEXT_LENGTH:
                # 긴 문서를 여러 청크로 분할
                chunks = []
                for start_idx in range(0, len(doc), MAX_TEXT_LENGTH):
                    chunk = doc[start_idx:start_idx + MAX_TEXT_LENGTH]
                    chunks.append(chunk)
                
                # 첫 번째 청크는 원본 ID 사용, 나머지는 서브 ID 추가
                for chunk_idx, chunk in enumerate(chunks):
                    processed_docs.append(chunk)
                    if chunk_idx == 0:
                        processed_ids.append(ids[i])
                        processed_meta.append(metadatas[i])
                    else:
                        # 서브 청크는 별도 ID 생성
                        sub_id = f"{ids[i]}_chunk{chunk_idx}"
                        processed_ids.append(sub_id)
                        sub_meta = metadatas[i].copy()
                        sub_meta["chunk_index"] = chunk_idx
                        processed_meta.append(sub_meta)
            else:
                processed_docs.append(doc)
                processed_ids.append(ids[i])
                processed_meta.append(metadatas[i])
        
        # 배치 임베딩 (재시도 포함)
        # API 제한: 한 요청당 최대 8192 토큰 → 약 25000자 이하로 배치 합계 제한
        MAX_CHARS_PER_BATCH = 25000
        for start in range(0, len(processed_docs), batch_size):
            batch_docs = processed_docs[start:start + batch_size]
            batch_ids = processed_ids[start:start + batch_size]
            batch_meta = processed_meta[start:start + batch_size]
            
            total_chars = sum(len(d) for d in batch_docs)
            # 배치 합계가 API 토큰 한도(8192)를 넘지 않도록 제한
            if total_chars > MAX_CHARS_PER_BATCH or total_chars > MAX_TEXT_LENGTH * batch_size:
                # 배치가 너무 크면 개별 처리
                for i, doc in enumerate(batch_docs):
                    for retry in range(MAX_RETRIES):
                        try:
                            emb = client.embeddings.create(input=[doc], model=EMBEDDING_MODEL)
                            collection.add(
                                ids=[batch_ids[i]],
                                documents=[batch_docs[i]],
                                metadatas=[batch_meta[i]],
                                embeddings=[emb.data[0].embedding]
                            )
                            break
                        except Exception as e:
                            if retry < MAX_RETRIES - 1:
                                print(f"  [재시도 {retry+1}/{MAX_RETRIES}] 문서 임베딩: {batch_ids[i]}")
                                time.sleep(RETRY_DELAY)
                            else:
                                print(f"  [임베딩 실패] 문서 {batch_ids[i]}: {e}")
                                # 실패해도 계속 진행하되 경고만 출력
            else:
                # 배치 처리 시도
                for retry in range(MAX_RETRIES):
                    try:
                        emb = client.embeddings.create(input=batch_docs, model=EMBEDDING_MODEL)
                        embeddings = [e.embedding for e in emb.data]
                        collection.add(ids=batch_ids, documents=batch_docs, metadatas=batch_meta, embeddings=embeddings)
                        break
                    except Exception as e:
                        if retry < MAX_RETRIES - 1:
                            print(f"  [재시도 {retry+1}/{MAX_RETRIES}] 배치 임베딩: {e}")
                            time.sleep(RETRY_DELAY)
                        else:
                            print(f"  [배치 임베딩 실패] 개별 처리로 전환: {e}")
                            # 배치 실패 시 개별 처리
                            for i, doc in enumerate(batch_docs):
                                for retry2 in range(MAX_RETRIES):
                                    try:
                                        emb = client.embeddings.create(input=[doc], model=EMBEDDING_MODEL)
                                        collection.add(
                                            ids=[batch_ids[i]],
                                            documents=[batch_docs[i]],
                                            metadatas=[batch_meta[i]],
                                            embeddings=[emb.data[0].embedding]
                                        )
                                        break
                                    except Exception as e2:
                                        if retry2 < MAX_RETRIES - 1:
                                            print(f"    [재시도 {retry2+1}/{MAX_RETRIES}] 문서 {batch_ids[i]}")
                                            time.sleep(RETRY_DELAY)
                                        else:
                                            print(f"    [임베딩 실패] 문서 {batch_ids[i]}: {e2}")
                            break
    return collection, True


def search(
    collection: Any,
    query: str,
    top_k: int = RAG_TOP_K,
    filter_sources: Optional[List[str]] = None,
    exclude_sections: Optional[List[str]] = None,
    filter_sections: Optional[List[str]] = None,
    exclude_chapters: Optional[List[str]] = None,
    min_score: float = 0.0,
    openai_api_key: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    유사도 기반 조문 검색.
    - openai_api_key가 제공되면 임베딩 시 해당 키 사용.
    """
    if not query or not query.strip():
        return []

    # 1. 쿼리 임베딩
    query_vector = list(get_embedding(query, api_key=openai_api_key))
    where = None
    if filter_sources or exclude_sections or filter_sections or exclude_chapters:
        clauses = []
        if filter_sources:
            clauses.append({"source": {"$in": filter_sources}})
        if exclude_sections:
            clauses.append({"section": {"$nin": exclude_sections}})
        if filter_sections:
            clauses.append({"section": {"$in": filter_sections}})
        if exclude_chapters:
            clauses.append({"chapter": {"$nin": exclude_chapters}})
        where = {"$and": clauses} if len(clauses) > 1 else clauses[0]
    results = collection.query(
        query_embeddings=[query_vector],
        n_results=top_k,
        where=where,
        include=["documents", "metadatas", "distances", "embeddings"],
    )
    out = []
    if results["documents"] and results["documents"][0]:
        embs = results.get("embeddings", [[]])[0] if results.get("embeddings") else []
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i] if results["metadatas"] else {}
            dist = results["distances"][0][i] if results.get("distances") else None
            emb = embs[i] if i < len(embs) else None
            original_text = meta.get("original_text", doc)
            item = {
                "text": original_text,
                "source": meta.get("source", ""),
                "article": meta.get("article", ""),
                "kind": meta.get("kind", ""),
                "section": meta.get("section", ""),
                "chapter": meta.get("chapter", ""),
                "distance": dist,
            }
            if meta.get("primary_category"):
                item["primary_category"] = meta["primary_category"]
            if emb is not None:
                item["embedding"] = emb
            out.append(item)
    return out


def _article_matches(a: str, art: str) -> bool:
    """'제36조(금품 청산)' matches '제36조', not '제361조'"""
    if not a or not art:
        return False
    return a == art or a.startswith(art + "(") or a.startswith(art + " ")


def search_by_article_numbers(
    collection: chromadb.Collection,
    article_numbers: List[str],
    sources: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """조문 번호(제17조 등) 리스트로 해당 조문 문서 검색. 시맨틱 검색으로 최적 매칭.
    sources가 None이면 SOURCE_LAW만, 리스트면 여러 법률에서 검색."""
    if not article_numbers:
        return []
    if sources is None:
        sources = [SOURCE_LAW]
    elif isinstance(sources, str):
        # 하위 호환성: 문자열이면 리스트로 변환
        sources = [sources]
    out = []
    seen = set()
    for art in article_numbers:
        res = search(collection, art, top_k=5, filter_sources=sources)
        for r in res:
            a = r.get("article", "")
            if _article_matches(a, art) and a not in seen:
                out.append(r)
                seen.add(a)
                break
    return out
