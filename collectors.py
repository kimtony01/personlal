"""데이터 수집: 뉴스(NewsAPI), 해양 기상(Open-Meteo), AIS 선박 통계(ship_data.json)

모든 함수는 외부 데이터를 가져와 '원 지표값'만 돌려줍니다. 점수 계산은 risk.py 에서 합니다.
"""
import json
from datetime import datetime, timedelta, timezone

import requests

from risk import analyze_articles
import db
from settings import CONFIG, NEWSAPI_KEY, SHIP_DATA_PATH, SHIP_HISTORY_PATH
from translate import translate_many_ko

NEWSAPI_URL = "https://newsapi.org/v2/everything"
MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT = 15


# -------------------------------------------------------------
# 뉴스 (해협 1곳당 NewsAPI 3회 호출)
# -------------------------------------------------------------
def _newsapi(query, frm, to=None, page_size=1):
    params = {"q": query, "language": "en", "from": frm.strftime("%Y-%m-%d"), "sortBy": "publishedAt",
              "pageSize": page_size, "apiKey": NEWSAPI_KEY}
    if to:
        params["to"] = to.strftime("%Y-%m-%d")
    res = requests.get(NEWSAPI_URL, params=params, timeout=TIMEOUT)
    body = res.json()
    if body.get("status") != "ok":
        raise RuntimeError(body.get("message") or f"HTTP {res.status_code}")
    return body.get("totalResults", 0), body.get("articles", [])


def collect_news(query):
    """최근 7일 / 직전 7일 / 최근 30일 기사 수 + 최근 7일 기사 표본(최대 100건)의 키워드 분석"""
    if not NEWSAPI_KEY:
        return {"error": "NEWSAPI_KEY 미설정"}
    today = datetime.now()
    try:
        count_7d, articles = _newsapi(query, today - timedelta(days=7), page_size=100)
        count_prev7d, _ = _newsapi(query, today - timedelta(days=14), today - timedelta(days=7))
        count_30d, _ = _newsapi(query, today - timedelta(days=30))
    except Exception as e:
        return {"error": f"뉴스 수집 실패: {e}"}

    analysis = analyze_articles(articles, CONFIG["news"])
    top = analysis["top_articles"]
    translated = translate_many_ko([a["title_en"] for a in top] + [a["desc_en"] for a in top])
    for a, title_ko, desc_ko in zip(top, translated[:len(top)], translated[len(top):]):
        a["title_ko"], a["desc_ko"] = title_ko, desc_ko

    return {
        "count_7d": count_7d, "count_prev7d": count_prev7d, "count_30d": count_30d,
        "sample_size": analysis["sample_size"], "strong_count": analysis["strong_count"],
        "keyword_multiplier": analysis["keyword_multiplier"], "strong_share": analysis["strong_share"],
        "issue_hits": analysis["issue_hits"], "top_articles": top, "error": None,
    }


# -------------------------------------------------------------
# 해양 기상: 해협 주변 좌표들의 향후 N시간 최대 파고(m) / 최대 풍속(kn)
# -------------------------------------------------------------
def _hourly_max(url, lat, lon, variable, extra=None):
    params = {"latitude": lat, "longitude": lon, "hourly": variable, "forecast_days": 3, "timezone": "UTC"}
    params.update(extra or {})
    res = requests.get(url, params=params, timeout=TIMEOUT)
    res.raise_for_status()
    hourly = res.json().get("hourly", {})
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    until = now + timedelta(hours=CONFIG["weather"]["forecast_hours"])
    values = [v for t, v in zip(hourly.get("time", []), hourly.get(variable, []))
              if v is not None and now - timedelta(hours=1) <= datetime.fromisoformat(t) <= until]
    return max(values) if values else None


def collect_weather(points):
    wave_max = wind_max = None
    errors = []
    for lat, lon in points:
        try:
            w = _hourly_max(MARINE_URL, lat, lon, "wave_height")
            if w is not None:
                wave_max = w if wave_max is None else max(wave_max, w)
        except Exception as e:
            errors.append(f"파고({lat},{lon}): {e}")
        try:
            s = _hourly_max(FORECAST_URL, lat, lon, "wind_speed_10m", {"wind_speed_unit": "kn"})
            if s is not None:
                wind_max = s if wind_max is None else max(wind_max, s)
        except Exception as e:
            errors.append(f"풍속({lat},{lon}): {e}")
    return {"wave_max_m": wave_max, "wind_max_kn": wind_max,
            "error": "; ".join(errors) if errors and wave_max is None and wind_max is None else None}


# -------------------------------------------------------------
# AIS: ship_data.json(collector.py 결과)에서 해협 구역 안 선박 수 / 평균 속도
# -------------------------------------------------------------
def load_ship_snapshot():
    if db.USE_PG:
        return db.load_blob("ship_data")
    if not SHIP_DATA_PATH.exists():
        return None
    try:
        with open(SHIP_DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def ais_stats(snapshot, box):
    (lat_lo, lat_hi), (lon_lo, lon_hi) = box["lat"], box["lon"]
    speeds, count = [], 0
    for info in snapshot.get("ships", {}).values():
        lat, lon = info.get("lat"), info.get("lon")
        if lat is None or lon is None:
            continue
        if lat_lo <= lat <= lat_hi and lon_lo <= lon <= lon_hi:
            count += 1
            # AIS 규격상 SOG 102.3 은 '값 없음'
            if info.get("speed") is not None and info["speed"] < 102.3:
                speeds.append(info["speed"])
    return count, (sum(speeds) / len(speeds) if speeds else None)


def load_ship_history():
    if db.USE_PG:
        return db.load_blob("ship_history") or {}
    if not SHIP_HISTORY_PATH.exists():
        return {}
    try:
        with open(SHIP_HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def known_ships(snapshot=None, history=None):
    """최신 스냅샷 + 항적 기록의 마지막 수신 위치. 이번 수집에 안 잡힌 배도 찾을 수 있게 함"""
    snapshot = snapshot if snapshot is not None else load_ship_snapshot()
    history = history if history is not None else load_ship_history()
    ships = {}
    for m, h in (history or {}).items():
        if h.get("track"):
            last = h["track"][-1]
            ships[m] = {"name": (h.get("name") or "").strip() or f"MMSI:{m}", "lat": last["lat"], "lon": last["lon"],
                        "speed": last.get("speed"), "destination": None, "seen_at": last["time"], "current": False}
    for m, i in ((snapshot or {}).get("ships") or {}).items():
        if i.get("lat") is not None:
            prev = ships.get(m)
            # 추적 수집(항적에만 기록)이 스냅샷보다 최신이면 항적 쪽 위치를 유지
            if prev and prev["seen_at"] > snapshot["updated_at"]:
                prev["current"] = True
                continue
            ships[m] = {"name": (i.get("name") or "").strip() or (prev or {}).get("name") or f"MMSI:{m}",
                        "lat": i["lat"], "lon": i["lon"], "speed": i.get("speed"),
                        "destination": i.get("destination"), "seen_at": snapshot["updated_at"], "current": True}
    return ships


def hourly_series(url, points, variable, extra=None):
    """여러 좌표의 시간별 예보를 한 번에 조회 (50곳씩 나눠 요청). [(times, values)] 좌표 순서대로"""
    out = []
    for i in range(0, len(points), 50):
        chunk = points[i:i + 50]
        params = {"latitude": ",".join(str(p[0]) for p in chunk), "longitude": ",".join(str(p[1]) for p in chunk),
                  "hourly": variable, "forecast_days": 8, "timezone": "UTC"}
        params.update(extra or {})
        res = requests.get(url, params=params, timeout=TIMEOUT)
        res.raise_for_status()
        body = res.json()
        body = body if isinstance(body, list) else [body]
        out += [(b["hourly"]["time"], b["hourly"][variable]) for b in body]
    return out
