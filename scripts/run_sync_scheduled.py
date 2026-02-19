# -*- coding: utf-8 -*-
"""
동기화 스케줄 실행용 엔트리포인트.
Windows 작업 스케줄러 또는 cron에서 이 스크립트를 주기 실행하면 sync_all이 실행되고
결과가 api_data/sync.log에 추가됩니다.

예 (Windows 작업 스케줄러):
  프로그램: python
  인수: scripts/run_sync_scheduled.py
  시작 위치: 프로젝트 루트
  트리거: 매일 새벽 2시 등

예 (PowerShell 한 번 등록):
  schtasks /create /tn "LawChat Sync" /tr "python d:\PhythonProject\LawChat\scripts\run_sync_scheduled.py" /sc daily /st 02:00 /ru SYSTEM
"""
import os
import sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
LOG_FILE = ROOT / "api_data" / "sync.log"


def main():
    sys.path.insert(0, str(ROOT))
    os.chdir(ROOT)
    start = datetime.now().isoformat()
    try:
        import subprocess
        r = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "sync_all.py")],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=3600,
        )
        success = r.returncode == 0
        tail = (r.stderr or r.stdout or "")[-500:]
    except Exception as e:
        success = False
        tail = str(e)
    line = f"{start} | {'OK' if success else 'FAIL'} | {tail}\n"
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
