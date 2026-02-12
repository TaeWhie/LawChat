# 법령 문서 로드 및 조(條) 단위 청킹
import re
from pathlib import Path
from typing import List, Dict, Any

def _split_into_articles(content: str, source_label: str) -> List[Dict[str, Any]]:
    """마크다운 내용을 #### 로 시작하는 조 단위로 분리."""
    chunks: List[Dict[str, Any]] = []
    # 블록 단위로 자르기: #### 부터 다음 #### 직전까지
    blocks = re.split(r'(?=^####\s+)', content, flags=re.MULTILINE)
    for block in blocks:
        block = block.strip()
        if not block or not block.startswith('####'):
            continue
        first_line = block.split('\n')[0]
        match = re.match(r'^####\s+(\[.+?\])\s+(제\d+(?:의\d+)?조[^\n]*)', first_line)
        if match:
            kind = match.group(1)  # [법률], [시행령], [시행규칙]
            title = match.group(2).strip()
            text = block
            chunks.append({
                "text": text,
                "source": source_label,
                "article": title,
                "kind": kind,
            })
    return chunks


def load_laws_from_dir(laws_dir: Path) -> List[Dict[str, Any]]:
    """laws 디렉터리 내 모든 .md 파일을 조 단위로 로드."""
    all_chunks: List[Dict[str, Any]] = []
    for path in sorted(laws_dir.glob("*.md")):
        content = path.read_text(encoding="utf-8")
        label = path.stem  # 예: 근로기준법(법률)
        chunks = _split_into_articles(content, label)
        all_chunks.extend(chunks)
    return all_chunks
