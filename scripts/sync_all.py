# -*- coding: utf-8 -*-
"""
api_data 전체 동기화: laws -> terms -> related -> precedents.
(bylaws는 별표/서식 목록으로 현재 상담에서 미사용 → 제외. 필요 시 scripts/sync_bylaws.py 직접 실행)
실행 전 LAW_API_OC 환경변수 설정 필요. 봇 차단 방지를 위해 요청 간 딜레이 적용됨.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    for name in ("sync_laws", "sync_terms", "sync_related", "sync_precedents"):
        script = ROOT / "scripts" / f"{name}.py"
        print(f"\n=== {name} ===")
        subprocess.run([sys.executable, str(script)], cwd=str(ROOT), check=False)
    print("\n전체 동기화 완료.")


if __name__ == "__main__":
    main()
