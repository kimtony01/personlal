"""스케줄러 작업을 1회 실행 (GitHub Actions 가 1시간마다 호출)

순서: AIS 수집 → 뉴스가 오래됐으면 뉴스 수집 → 위험 계산 + 운항 평가 + 경보 메일
실행: python run_jobs.py
"""
import logging

import settings
from scheduler import ais_job, bootstrap_job
from settings import CONFIG

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("run_jobs")

if __name__ == "__main__":
    if CONFIG["schedule"]["ais_enabled"] and settings.AISSTREAM_API_KEY:
        try:
            ais_job()
        except Exception:
            # AIS 가 실패해도 위험 계산·경보는 진행
            log.exception("AIS 수집 실패")
    bootstrap_job()
