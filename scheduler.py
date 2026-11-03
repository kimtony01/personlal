"""APScheduler 작업: 뉴스 수집 / 기상 수집 + 위험 계산 + 알림 / AIS 수집

웹 페이지를 여는 것과 무관하게 일정 간격으로 실행되고, 결과는 SQLite 에 저장됩니다.
Flask 라우트는 저장된 결과만 읽어서 보여 줍니다.
"""
import asyncio
import logging
import os
import sys
import threading
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

import db
import settings
from alerts import notify_if_escalated
from collectors import ais_stats, collect_news, collect_weather, load_ship_snapshot
from risk import ais_drop_ratio, compute_score, news_indicators, recommend_geo_level
from route_data import ROUTE_DB, get_arctic_season_info
from settings import CONFIG

log = logging.getLogger("scheduler")
_scheduler = None
_start_lock = threading.Lock()


# -------------------------------------------------------------
# 작업
# -------------------------------------------------------------
def news_job():
    for key, route in ROUTE_DB.items():
        data = collect_news(route["news_keyword"])
        db.save_news_snapshot(route["id"], data)
        log.info("뉴스 수집 %s: %s", route["id"], data.get("error") or f"7일 {data['count_7d']}건")


def resolve_geo_level(route, news):
    """(지수, 출처 설명, 추천값)"""
    if route.get("is_arctic"):
        level, msg = get_arctic_season_info()
        return level, f"계절 자동: {msg}", level
    recommended = recommend_geo_level(news["strong_share"], CONFIG["news"]) if news else None
    override = db.get_geo_override(route["id"])
    if override:
        return override["level"], f"사용자 수정값 ({override['updated_at'][:10]} 수정)", recommended
    if recommended:
        return recommended, "키워드 집계 추천값", recommended
    return None, "뉴스 데이터 없음", None


def _fresh_ais_snapshot():
    snap = load_ship_snapshot()
    if not snap or not snap.get("updated_at"):
        return None
    try:
        age = datetime.now() - datetime.strptime(snap["updated_at"], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return snap if age <= timedelta(hours=CONFIG["ais"]["max_snapshot_age_hours"]) else None


def risk_job():
    ais_snap = _fresh_ais_snapshot()
    for key, route in ROUTE_DB.items():
        sid = route["id"]
        errors = {}

        news = db.latest_news(sid)
        if not news:
            failed = db.latest_news(sid, successful_only=False)
            errors["news"] = (failed or {}).get("error") or "뉴스 수집 기록 없음"
        news_ratio, news_growth = news_indicators(news)

        weather = collect_weather(route["weather_points"])
        if weather["error"]:
            errors["weather"] = weather["error"]

        geo_level, geo_source, geo_recommended = resolve_geo_level(route, news)

        ais_count = ais_speed = ais_ratio = None
        if ais_snap:
            ais_count, ais_speed = ais_stats(ais_snap, route["ais_box"])
            db.save_ais_snapshot(sid, ais_snap["updated_at"], ais_count, ais_speed)
            baseline = db.ais_baseline(sid, ais_snap["updated_at"])
            ais_ratio = ais_drop_ratio(ais_count, ais_speed, baseline, CONFIG["ais"])
        else:
            errors["ais"] = "최근 AIS 스냅샷 없음 (collector.py 수집 필요)"

        indicators = {
            "news_ratio": news_ratio, "news_growth_pct": news_growth,
            "news_count_7d": news and news["count_7d"], "news_count_30d": news and news["count_30d"],
            "keyword_multiplier": news and news["keyword_multiplier"],
            "strong_share": news and news["strong_share"], "news_collected_at": news and news["collected_at"],
            "wave_max_m": weather["wave_max_m"], "wind_max_kn": weather["wind_max_kn"],
            "geo_level": geo_level, "geo_source": geo_source, "geo_recommended": geo_recommended,
            "ais_count": ais_count, "ais_avg_speed": ais_speed, "ais_ratio": ais_ratio,
        }
        score, level, contributions = compute_score(indicators, CONFIG)

        prev = db.latest_risk(sid)
        db.save_risk_snapshot(sid, level, score, indicators, contributions, errors)
        log.info("위험 계산 %s: %.1f점 (등급 %d)", sid, score, level)

        notify_if_escalated(key, route, prev["level"] if prev else None, level, score, contributions, news)

    # 해협 점수가 갱신된 직후, 등록된 운항들의 남은 경로 전체를 다시 평가 (경고 메일 포함)
    import voyages
    voyages.check_all()


def ais_job():
    import collector
    import voyages
    asyncio.run(collector.collect_and_save(CONFIG["schedule"]["ais_collect_seconds"]))
    # 등록된 운항 선박은 MMSI 로 따로 구독해 위치를 더 확실히 잡음
    mmsis = voyages.tracked_mmsis()
    if mmsis:
        got = asyncio.run(collector.collect_tracked(mmsis, CONFIG["voyage"]["tracked_collect_seconds"]))
        log.info("등록 선박 추적: %d척 중 %d척 위치 수신", len(mmsis), len(got))


def bootstrap_job():
    """시작 직후 1회: 뉴스가 오래됐으면 먼저 수집한 뒤 위험 계산"""
    interval = timedelta(minutes=CONFIG["schedule"]["news_interval_minutes"])
    stale = True
    for route in ROUTE_DB.values():
        latest = db.latest_news(route["id"], successful_only=False)
        if latest and datetime.now() - datetime.strptime(latest["collected_at"], "%Y-%m-%d %H:%M:%S") < interval:
            stale = False
            break
    if stale:
        news_job()
    risk_job()


# -------------------------------------------------------------
# 시작
# -------------------------------------------------------------
def _reloader_parent():
    """Flask 디버그 리로더의 '감시용 부모 프로세스'이면 True (여기서는 스케줄러를 띄우지 않음)"""
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        return False
    debug = os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true") or "--debug" in sys.argv
    return debug and "--no-reload" not in sys.argv


def start_scheduler():
    global _scheduler
    if not settings.SCHEDULER_ENABLED or _reloader_parent():
        return None
    with _start_lock:
        if _scheduler:
            return _scheduler
        s = CONFIG["schedule"]
        now = datetime.now()
        sched = BackgroundScheduler(daemon=True, job_defaults={"coalesce": True, "max_instances": 1,
                                                               "misfire_grace_time": 600})
        sched.add_job(bootstrap_job, id="bootstrap", next_run_time=now)
        sched.add_job(risk_job, "interval", id="risk", minutes=s["risk_interval_minutes"],
                      next_run_time=now + timedelta(minutes=s["risk_interval_minutes"]))
        sched.add_job(news_job, "interval", id="news", minutes=s["news_interval_minutes"],
                      next_run_time=now + timedelta(minutes=s["news_interval_minutes"]))
        if s["ais_enabled"] and settings.AISSTREAM_API_KEY:
            # 위험 계산보다 먼저 최신 스냅샷이 생기도록 바로 1회 수집
            sched.add_job(ais_job, "interval", id="ais", minutes=s["ais_interval_minutes"], next_run_time=now)
        sched.start()
        _scheduler = sched
        log.info("스케줄러 시작: %s", [j.id for j in sched.get_jobs()])
        return sched


def scheduler_status():
    if not _scheduler:
        return None
    return [{"id": j.id, "next_run": j.next_run_time.strftime("%Y-%m-%d %H:%M") if j.next_run_time else "-"}
            for j in _scheduler.get_jobs()]


if __name__ == "__main__":
    # 웹 서버 없이 작업만 한 번 돌려 보기: python scheduler.py
    logging.basicConfig(level=logging.INFO)
    bootstrap_job()
