"""운항 감시: 등록한 선박의 남은 경로 전체에서 문제를 예측하고, 대체 노선을 계산하고, 경고 메일을 보냄

한 번의 평가(evaluate)에서 하는 일
1. 현재 위치 결정: 등록 MMSI 의 최근 AIS 위치(설정 시간 이내) → 없으면 출발항
2. 남은 경로 계산: sea_network 의 해상 항로망에서 현재 위치 → 도착항 최단 경로
3. 문제 예측
   - 해협: 경로에 있는 감시 해협의 최신 위험 등급 (scheduler 가 계산한 값)
   - 기상: 남은 경로를 일정 간격으로 나눠, 배가 그 지점에 '도착할 예상 시각'의 파고·풍속 예보
4. 문제가 있으면 대체 노선: 문제 해협·구간을 뺀 경로, 선적/하역지 변경, 진입 시각 조정
5. 이슈 등급이 올라가면 운항별 수신자에게 경고 메일
"""
import logging
import threading
from datetime import datetime, timedelta, timezone

import db
import settings
from alerts import send_email
from collectors import FORECAST_URL, MARINE_URL, hourly_series, known_ships
from risk import LEVEL_LABEL
from route_data import PIPE_EAST_WEST, PIPE_HABSHAN_FUJAIRAH, PIPE_LABEL, PORT_DB, RAIL_LABEL, ROUTES_BY_ID
from sea_network import find_route, haversine_nm, port_node, sample_route
from settings import CONFIG

log = logging.getLogger("voyages")
VC = CONFIG["voyage"]
GULF_NODES = {"PGN", "PGC", "HRM"}

# 대체 노선 설명에 붙이는 공개 자료 (route_data.py 와 같은 출처)
LOADING_SWITCH = {
    "얀부항": "사우디 동서 파이프라인(아브카이크→얀부) 연계. EIA(2025-06-16): 500만 b/d, 2019년 일시 700만 b/d",
    "푸자이라항": "UAE 하브샨–푸자이라 파이프라인 연계. EIA(2025-06-16): 180만 b/d. UAE 원유 대체 구매에 해당",
}
RAIL_NOTE = "USDA AMS: 미 서안→동안 철도 약 6일"
PIPELINES = {"얀부항": PIPE_EAST_WEST, "푸자이라항": PIPE_HABSHAN_FUJAIRAH}


def strait_name(sid):
    return ROUTES_BY_ID[sid][0].split(" (")[0]


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _local(dt_utc):
    """UTC → 이 컴퓨터의 현지 시각 문자열"""
    return (dt_utc.replace(tzinfo=timezone.utc).astimezone()).strftime("%m-%d %H:%M")


def _weather_level(wave, wind):
    lv = 0
    if (wave or 0) >= VC["wave_warning_m"] or (wind or 0) >= VC["wind_warning_kn"]:
        lv = 1
    if (wave or 0) >= VC["wave_critical_m"] or (wind or 0) >= VC["wind_critical_kn"]:
        lv = 2
    return lv


# -------------------------------------------------------------
# 현재 위치
# -------------------------------------------------------------
def ship_position(mmsi):
    if not mmsi:
        return None
    ship = known_ships().get(mmsi)
    if not ship:
        return None
    age = datetime.now() - datetime.strptime(ship["seen_at"], "%Y-%m-%d %H:%M:%S")
    ship = dict(ship, age_hours=round(age.total_seconds() / 3600, 1))
    ship["usable"] = age <= timedelta(hours=VC["position_max_age_hours"])
    return ship


# -------------------------------------------------------------
# 경로상 기상
# -------------------------------------------------------------
def route_weather(route, speed_kn, depart_utc, extra_delay_h=0):
    """남은 경로 표본 지점별로 '도착 예상 시각'의 파고·풍속. (지점 목록, 시계열, 오류)"""
    now = _utcnow()
    horizon = now + timedelta(hours=VC["forecast_hours"])
    samples = []
    for s in sample_route(route["points"], VC["sample_step_nm"]):
        eta = depart_utc + timedelta(hours=s["dist_nm"] / speed_kn + extra_delay_h)
        if eta <= horizon:
            samples.append(dict(s, eta=eta))
    if not samples:
        return [], {}, None
    pts = [(s["lat"], s["lon"]) for s in samples]
    try:
        waves = hourly_series(MARINE_URL, pts, "wave_height")
        winds = hourly_series(FORECAST_URL, pts, "wind_speed_10m", {"wind_speed_unit": "kn"})
    except Exception as e:
        return [], {}, f"기상 예보 조회 실패: {e}"
    series = {"wave": waves, "wind": winds}
    for i, s in enumerate(samples):
        s["wave"], s["wind"] = _value_at(waves[i], s["eta"]), _value_at(winds[i], s["eta"])
        s["level"] = _weather_level(s["wave"], s["wind"])
    return samples, series, None


def _value_at(series, when):
    times, values = series
    if not times:
        return None
    t0 = datetime.fromisoformat(times[0])
    idx = round((when - t0).total_seconds() / 3600)
    if idx < 0 or idx >= len(values):
        return None
    # 앞뒤 1시간 중 값이 있는 것
    for j in (idx, idx - 1, idx + 1):
        if 0 <= j < len(values) and values[j] is not None:
            return round(values[j], 1)
    return None


def weather_segments(samples):
    """위험 지점이 연속된 구간으로 묶기"""
    segs, cur = [], None
    for s in samples:
        if s["level"] >= 1:
            if cur is None:
                cur = {"from": s["near"], "to": s["near"], "eta_from": s["eta"], "eta_to": s["eta"],
                       "max_wave": s["wave"], "max_wind": s["wind"], "level": s["level"], "points": []}
            cur["to"], cur["eta_to"] = s["near"], s["eta"]
            cur["max_wave"] = max(filter(None, [cur["max_wave"], s["wave"]]), default=None)
            cur["max_wind"] = max(filter(None, [cur["max_wind"], s["wind"]]), default=None)
            cur["level"] = max(cur["level"], s["level"])
            cur["points"].append((s["lat"], s["lon"]))
        elif cur:
            segs.append(cur)
            cur = None
    if cur:
        segs.append(cur)
    return segs


def delay_effect(samples, series):
    """진입(출발) 시각을 늦추면 경로상 기상 위험이 사라지는지. 처음으로 위험이 0이 되는 지연 시간"""
    if not samples:
        return None
    for d in VC["delay_options_hours"]:
        worst, max_wave, max_wind, evaluated = 0, 0, 0, 0
        for i, s in enumerate(samples):
            wave = _value_at(series["wave"][i], s["eta"] + timedelta(hours=d))
            wind = _value_at(series["wind"][i], s["eta"] + timedelta(hours=d))
            if wave is None and wind is None:
                continue  # 예보 범위를 벗어남
            evaluated += 1
            worst = max(worst, _weather_level(wave, wind))
            max_wave, max_wind = max(max_wave, wave or 0), max(max_wind, wind or 0)
        if evaluated and worst == 0:
            return {"hours": d, "max_wave": max_wave, "max_wind": max_wind}
    return None


# -------------------------------------------------------------
# 해협
# -------------------------------------------------------------
def strait_status(straits):
    out = []
    for sid in straits:
        r = db.latest_risk(sid)
        top = sorted(r["contributions"], key=lambda c: -c["points"])[:2] if r else []
        out.append({"id": sid, "name": strait_name(sid), "level": r["level"] if r else None,
                    "score": r["score"] if r else None,
                    "reasons": [f"{c['label']} {c['points']}점({c['detail']})" for c in top if c["points"] > 0]})
    return out


# -------------------------------------------------------------
# 대체 노선
# -------------------------------------------------------------
def _describe(label, kind, r, speed_kn, base, daily_cost, note=None, land_days=0, start_utc=None, land=None):
    days = r["distance_nm"] / (speed_kn * 24) + land_days
    samples, _, werr = route_weather(r, speed_kn, start_utc or _utcnow())
    straits = strait_status(r["straits"])
    risk_levels = [s["level"] or 0 for s in straits] + [s["level"] for s in samples]
    via = [strait_name(s) for s in r["straits"]] + r["passages"]
    if kind == "route" and via:
        label = f"{label}: {' · '.join(via)} 경유"
    alt = {
        "label": label, "kind": kind, "note": note,
        "distance_nm": r["distance_nm"], "days": round(days, 1),
        "delta_nm": r["distance_nm"] - base["distance_nm"], "delta_days": round(days - base["days"], 1),
        "straits": straits, "passages": r["passages"],
        "max_wave": max([s["wave"] for s in samples if s["wave"] is not None], default=None),
        "max_wind": max([s["wind"] for s in samples if s["wind"] is not None], default=None),
        "risk_level": max(risk_levels, default=0), "weather_error": werr,
        "points": [(p[0], p[1]) for p in r["points"]],
    }
    if land:
        alt["land_points"], alt["land_label"] = land
    if daily_cost:
        alt["delta_cost_usd"] = round(alt["delta_days"] * daily_cost)
    return alt


def compute_alternatives(v, start, route, base, risky_straits, weather_samples, weather_series, depart_utc):
    speed, dest, cost = v["speed_kn"], v["dest"], v["daily_cost_usd"]
    candidates = []  # (label, kind, route, note, land_days, (육상 좌표, 이름) 또는 None)

    if risky_straits:
        names = ", ".join(strait_name(s) for s in risky_straits)
        r1 = find_route(start, dest, banned_straits=risky_straits)
        if r1:
            candidates.append((f"{names} 회피 경로", "route", r1, None, 0, None))
            # 두 번째 대안: 첫 대안이 지나는 다른 해협(또는 우회 수로)까지 빼고 다시 찾기
            if r1["straits"]:
                r2 = find_route(start, dest, banned_straits=list(risky_straits) + r1["straits"])
            elif r1["passages"]:
                r2 = find_route(start, dest, banned_straits=risky_straits, banned_passages=r1["passages"][:1])
            else:
                r2 = None
            if r2:
                candidates.append((f"{names} 회피 (다른 우회로)", "route", r2, None, 0, None))
        # 바닷길로는 못 피하는 경우: 페르시아만 안 출발/도착 + 호르무즈
        if "hormuz" in risky_straits:
            start_in_gulf = (port_node(v["origin"]) in GULF_NODES) if isinstance(start, str) else \
                (start[0] > 24 and 47 < start[1] < 56.4)
            others = [s for s in risky_straits if s != "hormuz"]
            if start_in_gulf:
                for port, note in LOADING_SWITCH.items():
                    r = find_route(port, dest, banned_straits=others)
                    if r:
                        candidates.append((f"선적지 변경: {port}", "loading", r, note, 0,
                                           (PIPELINES[port], PIPE_LABEL)))
            if port_node(dest) in GULF_NODES:
                for port, note in LOADING_SWITCH.items():
                    r = find_route(start, port, banned_straits=others)
                    if r:
                        candidates.append((f"하역지 변경: {port} (이후 육상 운송)", "unloading", r, note, 0,
                                           (list(reversed(PIPELINES[port])), PIPE_LABEL)))
        # 파나마 위험 + 미 동안 도착: 서안 하역 후 철도
        if "panama" in risky_straits and PORT_DB[dest]["region"] == "미주동안":
            r = find_route(start, "롱비치항", banned_straits=risky_straits)
            if r:
                d = PORT_DB[dest]
                rail = [(33.75, -118.2), (35.1, -106.6), (41.85, -87.65), (d["lat"], d["lon"])]
                candidates.append(("미 서안(롱비치) 하역 + 철도", "rail", r, RAIL_NOTE, 6, (rail, RAIL_LABEL)))

    # 기상 위험 구간을 지나지 않는 경로
    bad_edges = set()
    for s in weather_samples:
        k = s["seg"]
        if s["level"] >= 1 and 1 <= k <= len(route["nodes"]) - 1:
            bad_edges.add((route["nodes"][k - 1], route["nodes"][k]))
    if bad_edges:
        r3 = find_route(start, dest, banned_straits=risky_straits, banned_edges=bad_edges)
        if r3:
            candidates.append(("기상 위험 구간 우회", "route", r3, None, 0, None))

    alts, seen = [], {tuple(route["nodes"])}
    for label, kind, r, note, land_days, land in candidates:
        key = tuple(r["nodes"]) + (kind,)
        if tuple(r["nodes"]) in seen and kind == "route":
            continue
        if key in seen or r["distance_nm"] > base["distance_nm"] * VC["max_detour_ratio"] + 500:
            continue
        seen.add(key)
        seen.add(tuple(r["nodes"]))
        alts.append(_describe(label, kind, r, speed, base, cost, note, land_days, depart_utc, land))

    # 기상만 문제라면 진입 시각 조정
    delay = delay_effect(weather_samples, weather_series) if any(s["level"] for s in weather_samples) else None
    if delay:
        alts.append({
            "label": f"출발·진입 {delay['hours']}시간 늦추기", "kind": "delay", "note": None,
            "distance_nm": base["distance_nm"], "days": round(base["days"] + delay["hours"] / 24, 1),
            "delta_nm": 0, "delta_days": round(delay["hours"] / 24, 1), "straits": strait_status(route["straits"]),
            "passages": [], "max_wave": delay["max_wave"], "max_wind": delay["max_wind"],
            "risk_level": max([s["level"] or 0 for s in strait_status(route["straits"])], default=0),
            "points": [], **({"delta_cost_usd": round(delay["hours"] / 24 * cost)} if cost else {}),
        })
    alts.sort(key=lambda a: (a["risk_level"], a["days"]))
    return alts


# -------------------------------------------------------------
# 평가
# -------------------------------------------------------------
def evaluate(v):
    depart = _utcnow()
    pos = ship_position(v["mmsi"])
    use_pos = pos and pos["usable"]
    start = (pos["lat"], pos["lon"]) if use_pos else v["origin"]
    d = PORT_DB[v["dest"]]

    ev = {"evaluated_at": db.now_str(), "position": pos,
          "start_label": f"현재 위치 ({pos['seen_at'][5:16]} 수신)" if use_pos else f"출발항 {v['origin']} (위치 미확인)"}
    if use_pos and haversine_nm((pos["lat"], pos["lon"]), (d["lat"], d["lon"])) < 30:
        ev.update(arrived=True, level=0, issues=[], alternatives=[], straits=[], weather=[])
        return ev

    route = find_route(start, v["dest"])
    if not route:
        ev.update(error="경로를 찾지 못했습니다.", level=None, issues=[], alternatives=[])
        return ev
    days = route["distance_nm"] / (v["speed_kn"] * 24)
    base = {"distance_nm": route["distance_nm"], "days": round(days, 1)}
    eta = depart + timedelta(days=days)

    samples, series, werr = route_weather(route, v["speed_kn"], depart)
    straits = strait_status(route["straits"])
    segs = weather_segments(samples)

    issues = []
    for s in straits:
        if (s["level"] or 0) >= 1:
            issues.append({"key": f"strait:{s['id']}", "kind": "strait", "level": s["level"],
                           "title": f"{s['name']} {LEVEL_LABEL[s['level']]} (점수 {s['score']})",
                           "detail": " · ".join(s["reasons"])})
    for seg in segs:
        where = seg["from"] if seg["from"] == seg["to"] else f"{seg['from']} ~ {seg['to']}"
        when = _local(seg["eta_from"]) if seg["eta_from"] == seg["eta_to"] else \
            f"{_local(seg['eta_from'])} ~ {_local(seg['eta_to'])}"
        issues.append({"key": "weather", "kind": "weather", "level": seg["level"],
                       "title": f"기상 {LEVEL_LABEL[seg['level']]}: {where} 부근",
                       "detail": f"도착 예상 {when} · 예보 최대 파고 {seg['max_wave']} m, 풍속 {seg['max_wind']} kn",
                       "points": seg["points"]})
    level = max([i["level"] for i in issues], default=0)
    risky = [s["id"] for s in straits if (s["level"] or 0) >= 1]
    alternatives = compute_alternatives(v, start, route, base, risky, samples, series, depart) if level >= 1 else []

    ev.update(
        level=level, issues=issues, alternatives=alternatives, straits=straits,
        distance_nm=route["distance_nm"], days=base["days"], eta=_local(eta),
        route_points=[(p[0], p[1]) for p in route["points"]],
        weather=[{"lat": s["lat"], "lon": s["lon"], "eta": _local(s["eta"]), "wave": s["wave"], "wind": s["wind"],
                  "level": s["level"], "near": s["near"]} for s in samples],
        weather_checked_nm=samples[-1]["dist_nm"] if samples else 0, weather_error=werr,
    )
    return ev


# -------------------------------------------------------------
# 알림
# -------------------------------------------------------------
def update_alert_state(v, ev):
    """이슈별로 등급이 올라간 것만 골라냄. (새 상태, 알림 대상 이슈 key 목록)"""
    state = dict(v.get("alert_state") or {})
    now = datetime.now()
    cooldown = timedelta(hours=CONFIG["alerts"]["cooldown_hours"])
    current = {}
    for i in ev.get("issues", []):
        current[i["key"]] = max(current.get(i["key"], 0), i["level"])

    triggered = []
    for key, level in current.items():
        st = state.get(key, {})
        if level > st.get("level", 0):
            last = st.get("alerted_at")
            recent = last and now - datetime.strptime(last, "%Y-%m-%d %H:%M:%S") < cooldown
            if not (recent and level <= st.get("alerted_level", 0)):
                triggered.append(key)
    for key in set(state) | set(current):
        state.setdefault(key, {})["level"] = current.get(key, 0)
    return state, triggered


def build_message(v, ev, triggered):
    route_txt = f"{v['origin']} → {v['dest']}"
    issues = ev["issues"]
    head = [i for i in issues if i["key"] in triggered] or issues
    subject = f"[운항 경고] {v['ship_name']} ({route_txt}) — {LEVEL_LABEL[ev['level']]}: " + \
        ", ".join(i["title"].split(" (")[0] for i in head[:2])
    lines = [
        f"선박: {v['ship_name']}" + (f" (MMSI {v['mmsi']})" if v["mmsi"] else ""),
        f"항로: {route_txt}",
        f"기준 위치: {ev['start_label']}",
        f"남은 거리 약 {ev['distance_nm']:,}해리 · 약 {ev['days']}일 · 도착 예상 {ev['eta']} "
        f"(속력 {v['speed_kn']}노트 가정, 거리는 항로망 근사값)",
        "", "■ 예측된 문제",
    ]
    for i in issues:
        mark = "★ 새로 발생/상승 " if i["key"] in triggered else ""
        lines.append(f"  - {mark}[{LEVEL_LABEL[i['level']]}] {i['title']}")
        lines.append(f"      {i['detail']}")
    lines += ["", "■ 대체 노선 (위험이 낮고 짧은 순)"]
    if ev["alternatives"]:
        for n, a in enumerate(ev["alternatives"], 1):
            straits = ", ".join(f"{s['name']}({LEVEL_LABEL.get(s['level'], '수집 중')})" for s in a["straits"]) or "감시 해협 없음"
            cost = f", 비용 차이 약 {a['delta_cost_usd']:+,} USD" if "delta_cost_usd" in a else ""
            weather = f", 예보 최대 파고 {a['max_wave']} m" if a.get("max_wave") is not None else ""
            lines.append(f"  {n}. {a['label']}: 약 {a['distance_nm']:,}해리 / {a['days']}일 "
                         f"(현재 계획 대비 {a['delta_days']:+}일{cost}) — 경유 해협: {straits}{weather}")
            if a.get("note"):
                lines.append(f"      참고: {a['note']}")
    else:
        lines.append("  - 항로망에서 찾은 대체 노선이 없습니다.")
    lines += ["", "※ 위험 점수 가중치·경계값과 속력은 가정값이 포함된 추정입니다. 실제 운항 판단은 선사·선장 판단을 따르세요.",
              f"※ 대시보드: http://127.0.0.1:5000/voyage/{v['id']}"]
    return subject, "\n".join(lines)


def notify(v, ev, triggered):
    level = ev["level"]
    titles = "; ".join(i["title"] for i in ev["issues"] if i["key"] in triggered)
    recipients = [r.strip() for r in v["recipients"].split(",") if r.strip()]
    if not ((settings.SMTP_HOST or settings.BREVO_API_KEY) and settings.SMTP_FROM and recipients):
        db.log_voyage_alert(v["id"], level, titles, "not_configured", "SMTP 설정 또는 수신자 없음")
        return False
    subject, body = build_message(v, ev, triggered)
    try:
        send_email(subject, body, recipients)
        db.log_voyage_alert(v["id"], level, titles, "sent", ", ".join(recipients))
        return True
    except Exception as e:
        db.log_voyage_alert(v["id"], level, titles, "failed", str(e))
        return False


def check_voyage(voyage_id):
    v = db.get_voyage(voyage_id)
    if not v or not v["active"]:
        return None
    ev = evaluate(v)
    state, triggered = update_alert_state(v, ev)
    if triggered and notify(v, ev, triggered):
        now = db.now_str()
        for key in triggered:
            state[key].update(alerted_level=state[key]["level"], alerted_at=now)
    db.save_voyage_eval(voyage_id, ev, state)
    log.info("운항 %s 평가: 등급 %s, 이슈 %d, 알림 %s", voyage_id, ev.get("level"), len(ev.get("issues", [])),
             triggered or "-")
    return ev


def check_all():
    for v in db.list_voyages():
        try:
            check_voyage(v["id"])
        except Exception:
            log.exception("운항 %s 평가 실패", v["id"])


def check_in_background(voyage_id):
    threading.Thread(target=check_voyage, args=(voyage_id,), daemon=True).start()


def tracked_mmsis():
    return sorted({v["mmsi"] for v in db.list_voyages() if v["mmsi"]})
