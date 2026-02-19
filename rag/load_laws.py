# 법령 청크 로드 (API 전용)
# api_data/laws/law/*.json 에서 rag.api_data_loader.load_chunks_from_api_laws() 로 조(條) 단위 청크 로드.
from pathlib import Path
from typing import List, Dict, Any

from config import LAWS_DATA_DIR


def load_laws_auto() -> List[Dict[str, Any]]:
    """api_data/laws/law에 동기화된 JSON에서만 청크 로드. 없으면 빈 리스트."""
    import sys
    from rag.api_data_loader import load_chunks_from_api_laws

    law_dir = LAWS_DATA_DIR / "law"
    if not law_dir.exists():
        print("[load_laws_auto] api_data/laws/law 디렉터리가 없습니다. sync_laws를 실행하세요.", file=sys.stderr)
        return []
    body_files = [p for p in law_dir.glob("*.json") if p.name != "list.json"]
    if not body_files:
        print("[load_laws_auto] api_data/laws/law에 본문 JSON이 없습니다. sync_laws를 실행하세요.", file=sys.stderr)
        return []
    chunks = load_chunks_from_api_laws()
    if not chunks:
        print("[load_laws_auto] API 본문에서 청크를 추출할 수 없습니다. 본문 JSON 구조를 확인하세요.", file=sys.stderr)
        return []
    return chunks
