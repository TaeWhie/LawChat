# -*- coding: utf-8 -*-
"""벡터 스토어 재구축 + 청크 개수 출력 (run.bat에서 호출)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

def main():
    from rag.load_laws import load_laws_auto
    from rag.store import build_vector_store

    chunks = load_laws_auto()
    n = len(chunks) if chunks else 0
    print(f"  청크 {n}개 로드 (api_data/laws 기준)")
    if n == 0:
        print("  경고: 청크가 없습니다. sync_laws 실행 후 api_data/laws/law/*.json 을 확인하세요.")
        return 1

    build_vector_store(force_rebuild=True)
    print("  벡터 스토어 재구축 완료.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
