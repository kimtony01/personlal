"""신호 수집: 뉴스 사건(GDELT), 통항량(IMF PortWatch), 재해(GDACS), 공식 판단(직접 관리하는 표)

각 함수는 판단에 쓸 '원래 값'만 돌려줍니다. 정상·주의·심각 판단은 rules.py 가 합니다.
"""
import csv
import io
import logging
import math
import tomllib
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

import db
from straits import STRAITS

log = logging.getLogger("signals")
BASE_DIR = Path(__file__).resolve().parent
HEADERS = {"User-Agent": "route-risk-monitor/1.0 (personal research project)"}

GDELT_LAST = "http://data.gdeltproject.org/gdeltv2/lastupdate.txt"
GDELT_FILE = "http://data.gdeltproject.org/gdeltv2/{ts}.export.CSV.zip"
PORTWATCH_URL = ("https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/"
                 "Daily_Chokepoints_Data/FeatureServer/0/query")
GDACS_URL = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"
FILES_KEY = "__files__"   # gdelt_hourly 에서 '그 시간에 처리한 파일 수'를 담는 행 (빠진 시간 보정용)


def km_between(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))


# -------------------------------------------------------------
# 뉴스 사건 (GDELT 2.0 Events, 15분 단위 공개 파일)
# 기사에서 자동 추출한 사건 중 '갈등'(QuadClass 3 = 말로 하는 갈등: 위협·경고·비난,
# 4 = 물리적 갈등: 공격·나포·봉쇄)이 해협 반경 안에서 일어난 것만 셈
# -------------------------------------------------------------
def gdelt_file_counts(ts):
    """15분 파일 하나 → {strait_id: [events, material, goldstein]}. 파일이 없으면 None"""
    res = requests.get(GDELT_FILE.format(ts=ts), headers=HEADERS, timeout=60)
    if res.status_code == 404:
        return None
    res.raise_for_status()
    zf = zipfile.ZipFile(io.BytesIO(res.content))
    counts = {sid: [0, 0, 0.0] for sid in STRAITS}
    with zf.open(zf.namelist()[0]) as f:
        for row in csv.reader(io.TextIOWrapper(f, encoding="utf-8", errors="replace"), delimiter="\t"):
            if len(row) < 58 or row[29] not in ("3", "4") or not row[56] or not row[57]:
                continue
            try:
                lat, lon, gs = float(row[56]), float(row[57]), float(row[30] or 0)
            except ValueError:
                continue
            for sid, s in STRAITS.items():
                if abs(lat - s["lat"]) < 15 and km_between(lat, lon, s["lat"], s["lon"]) <= s["radius_km"]:
                    c = counts[sid]
                    c[0] += 1
                    c[1] += row[29] == "4"
                    c[2] += gs
    return counts


def _ts(dt):
    return dt.strftime("%Y%m%d%H%M%S")


def _save_file_counts(ts, counts):
    hour = f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]} {ts[8:10]}"
    rows = [(sid, hour, c[0], c[1], round(c[2], 2)) for sid, c in counts.items()]
    rows.append((FILES_KEY, hour, 1, 0, 0.0))
    db.add_gdelt_counts(rows)


def update_gdelt(max_files=16):
    """마지막으로 처리한 파일 다음부터 최신 파일까지 처리 (한 번에 최대 4시간 분량)"""
    latest = requests.get(GDELT_LAST, headers=HEADERS, timeout=30).text.split()[2]
    latest_ts = latest.rsplit("/", 1)[1].split(".")[0]
    state, _ = db.load_blob("gdelt_last")
    latest_dt = datetime.strptime(latest_ts, "%Y%m%d%H%M%S")
    start = datetime.strptime(state, "%Y%m%d%H%M%S") + timedelta(minutes=15) if state else latest_dt
    start = max(start, latest_dt - timedelta(minutes=15 * (max_files - 1)))
    done = 0
    t = start
    while t <= latest_dt:
        counts = gdelt_file_counts(_ts(t))
        if counts is not None:
            _save_file_counts(_ts(t), counts)
            done += 1
        db.save_blob("gdelt_last", _ts(t))
        t += timedelta(minutes=15)
    log.info("GDELT 파일 %d개 처리 (최신 %s)", done, latest_ts)
    return done


def news_windows(strait_id, now_utc=None, days=90):
    """(24시간 단위 사건 수 목록 — 가장 최근이 앞, 최근 24시간 중 물리적 충돌 사건 수)

    처리한 파일이 하루의 절반 미만인 구간은 None. 빠진 파일이 있으면 '하루 96개 파일' 기준으로 비례 보정
    """
    now_utc = now_utc or datetime.now(timezone.utc).replace(tzinfo=None)
    end = now_utc.replace(minute=0, second=0, microsecond=0)
    since = (end - timedelta(days=days + 1)).strftime("%Y-%m-%d %H")
    ev = {r["hour"]: r for r in db.gdelt_hours(strait_id, since)}
    files = {r["hour"]: r["events"] for r in db.gdelt_hours(FILES_KEY, since)}
    windows, material = [], None
    for d in range(days):
        hours = [(end - timedelta(hours=h + 24 * d)).strftime("%Y-%m-%d %H") for h in range(24)]
        n_files = sum(files.get(h, 0) for h in hours)
        if n_files < 48:
            windows.append(None)
            continue
        n = sum(ev[h]["events"] for h in hours if h in ev)
        windows.append(round(n * 96 / n_files, 1))
        if d == 0:
            material = round(sum(ev[h]["material"] for h in hours if h in ev) * 96 / n_files, 1)
    return windows, material


# -------------------------------------------------------------
# 통항량 (IMF PortWatch: 위성 AIS 기반 해협별 하루 통항 척수, 주 1회 갱신)
# -------------------------------------------------------------
def portwatch_series(portname, days=400):
    """[(date, n_total)] — 12시간 동안은 DB 캐시 사용"""
    key = f"portwatch:{portname}"
    cached, updated = db.load_blob(key)
    if cached and updated and datetime.now() - datetime.strptime(updated, "%Y-%m-%d %H:%M:%S") < timedelta(hours=12):
        return [tuple(x) for x in cached]
    since = (date.today() - timedelta(days=days)).isoformat()
    res = requests.get(PORTWATCH_URL, headers=HEADERS, timeout=90, params={
        "where": f"portname='{portname}' AND date >= DATE '{since}'", "outFields": "date,n_total",
        "orderByFields": "date", "returnGeometry": "false", "resultRecordCount": 1000, "f": "json"})
    body = res.json()
    if "error" in body:
        raise RuntimeError(body["error"].get("message"))
    series = [(f["attributes"]["date"], f["attributes"]["n_total"]) for f in body["features"]]
    db.save_blob(key, series)
    return series


def traffic_signal(series):
    """최근 7일 평균 vs 작년 같은 7일(364일 전, 요일 맞춤) 평균"""
    by_date = dict(series)
    if not series:
        return None
    last = date.fromisoformat(series[-1][0])
    recent = [by_date.get((last - timedelta(days=i)).isoformat()) for i in range(7)]
    base = [by_date.get((last - timedelta(days=364 + i)).isoformat()) for i in range(7)]
    recent, base = [x for x in recent if x is not None], [x for x in base if x is not None]
    if len(recent) < 5 or len(base) < 5 or sum(base) == 0:
        return None
    r, b = sum(recent) / len(recent), sum(base) / len(base)
    return {"recent_avg": round(r, 1), "base_avg": round(b, 1), "change_pct": round((r / b - 1) * 100, 1),
            "latest_date": last.isoformat()}


# -------------------------------------------------------------
# 운항 불가급 재해 (GDACS: EU JRC·UN 공동 재난 경보 — 열대저기압, 지진·쓰나미)
# -------------------------------------------------------------
def gdacs_events():
    res = requests.get(GDACS_URL, headers=HEADERS, timeout=60,
                       params={"eventlist": "TC;EQ", "alertlevel": "Orange;Red"})
    res.raise_for_status()
    out = []
    for f in res.json().get("features", []):
        p, g = f["properties"], f.get("geometry") or {}
        if g.get("type") != "Point":
            continue
        out.append({"type": p["eventtype"], "name": p.get("name") or p.get("eventname"), "alert": p["alertlevel"],
                    "current": bool(p.get("iscurrent")), "from": p.get("fromdate"), "to": p.get("todate"),
                    "lon": g["coordinates"][0], "lat": g["coordinates"][1],
                    "url": (p.get("url") or {}).get("report") if isinstance(p.get("url"), dict) else p.get("url")})
    return out


def disaster_hits(strait_id, events, tc_km, eq_km, now_utc=None):
    s = STRAITS[strait_id]
    now_utc = now_utc or datetime.now(timezone.utc).replace(tzinfo=None)
    hits = []
    for e in events:
        km = km_between(s["lat"], s["lon"], e["lat"], e["lon"])
        if e["type"] == "TC" and e["current"] and km <= tc_km:
            hits.append(dict(e, km=round(km)))
        elif e["type"] == "EQ" and km <= eq_km and e["from"]:
            if now_utc - datetime.fromisoformat(e["from"][:19]) <= timedelta(hours=48):
                hits.append(dict(e, km=round(km)))
    return hits


# -------------------------------------------------------------
# 공식 판단 (official_status.toml)
# -------------------------------------------------------------
def load_official():
    with open(BASE_DIR / "official_status.toml", "rb") as f:
        return tomllib.load(f)
