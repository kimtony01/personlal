"""GDELT 과거 기록 채우기 (처음 1회): 뉴스 사건의 '평소 수준'을 바로 비교할 수 있도록 지난 N일치 15분 파일을 처리

실행: python backfill_gdelt.py 30
이미 처리한 구간 이전만 채우므로 여러 번 실행해도 중복으로 세지 않습니다.
"""
import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from dotenv import load_dotenv

load_dotenv()

import db  # noqa: E402
import signals  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("backfill")


def main(days):
    latest = signals.requests.get(signals.GDELT_LAST, headers=signals.HEADERS, timeout=30).text.split()[2]
    latest_dt = datetime.strptime(latest.rsplit("/", 1)[1].split(".")[0], "%Y%m%d%H%M%S")
    have = db.gdelt_hours(signals.FILES_KEY, "0000")
    # 이미 처리한 가장 이른 시간 이전까지만 (없으면 최신 파일까지)
    end = datetime.strptime(have[0]["hour"], "%Y-%m-%d %H") - timedelta(minutes=15) if have else latest_dt
    start = (latest_dt - timedelta(days=days)).replace(minute=0)
    stamps = []
    t = start
    while t <= end:
        stamps.append(signals._ts(t))
        t += timedelta(minutes=15)
    log.info("%d개 파일 처리 (%s ~ %s)", len(stamps), stamps[0] if stamps else "-", stamps[-1] if stamps else "-")

    def work(ts):
        try:
            return ts, signals.gdelt_file_counts(ts)
        except Exception as e:
            log.warning("%s 실패: %s", ts, e)
            return ts, None

    done = 0
    with ThreadPoolExecutor(max_workers=6) as pool:
        for ts, counts in pool.map(work, stamps):
            if counts is not None:
                signals._save_file_counts(ts, counts)
                done += 1
            if done and done % 200 == 0:
                log.info("%d / %d", done, len(stamps))
    if not have:
        db.save_blob("gdelt_last", signals._ts(end))
    log.info("완료: %d개 파일", done)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 30)
