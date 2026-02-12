# RAG 벡터 스토어 (ChromaDB) 및 검색
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional

import chromadb
from openai import OpenAI

from config import LAWS_DIR, VECTOR_DIR, EMBEDDING_MODEL, RAG_TOP_K, OPENAI_API_KEY
from rag.load_laws import load_laws_from_dir


def get_embedding(client: OpenAI, text: str, model: str = EMBEDDING_MODEL) -> List[float]:
    """텍스트 임베딩 (OpenAI)."""
    r = client.embeddings.create(input=[text], model=model)
    return r.data[0].embedding


def build_vector_store(force_rebuild: bool = False) -> chromadb.Collection:
    """법령 청크를 임베딩하여 ChromaDB에 저장. 이미 있으면 재사용."""
    VECTOR_DIR.mkdir(parents=True, exist_ok=True)
    client = OpenAI(api_key=OPENAI_API_KEY)
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
    chunks = load_laws_from_dir(LAWS_DIR)
    if not chunks:
        return collection
    # 이미 문서 수가 같으면 스킵 (간단 체크)
    existing = collection.count()
    if existing >= len(chunks) and not force_rebuild:
        return collection
    if force_rebuild or existing == 0:
        ids = []
        documents = []
        metadatas = []
        for i, c in enumerate(chunks):
            ids.append(hashlib.sha256(f"{c['source']}_{c['article']}_{i}".encode()).hexdigest()[:24])
            documents.append(c["text"])
            metadatas.append({"source": c["source"], "article": c["article"], "kind": c["kind"]})
        # 배치 임베딩 (한 번에 너무 많으면 나눔)
        batch_size = 50
        for start in range(0, len(documents), batch_size):
            batch_docs = documents[start:start + batch_size]
            batch_ids = ids[start:start + batch_size]
            batch_meta = metadatas[start:start + batch_size]
            emb = client.embeddings.create(input=batch_docs, model=EMBEDDING_MODEL)
            embeddings = [e.embedding for e in emb.data]
            collection.add(ids=batch_ids, documents=batch_docs, metadatas=batch_meta, embeddings=embeddings)
    return collection


def search(
    collection: chromadb.Collection,
    query: str,
    top_k: int = RAG_TOP_K,
    filter_sources: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """쿼리와 유사한 조문 검색. 임베딩은 OpenAI로 생성."""
    client = OpenAI(api_key=OPENAI_API_KEY)
    query_embedding = get_embedding(client, query)
    where = None
    if filter_sources:
        where = {"source": {"$in": filter_sources}}
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where=where,
        include=["documents", "metadatas", "distances"],
    )
    out = []
    if results["documents"] and results["documents"][0]:
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i] if results["metadatas"] else {}
            dist = results["distances"][0][i] if results.get("distances") else None
            out.append({
                "text": doc,
                "source": meta.get("source", ""),
                "article": meta.get("article", ""),
                "kind": meta.get("kind", ""),
                "distance": dist,
            })
    return out
