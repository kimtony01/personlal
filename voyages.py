"""등록 선박의 운항 감시: 현재 위치 → 남은 항로 → 앞으로 지날 해협의 신호등 → 대체 항로 → 경보 메일

위치가 오래됐으면 마지막 위치에서 속력만큼 항로를 따라 이동했다고 보고 현재 위치를 추정합니다.
"""
import logging
import math
from datetime import datetime, timedelta

import db
import mailer
from ports import PORT_DB
from sea_network import find_route, haversine_nm
from straits import LEVELS, STRAITS

log = logging.getLogger("voyages")
ARRIVAL_NM = 30
# 해협을 피해 갈 바닷길이 없을 때(예: 페르시아만 안 항구) 제시할 하역항 변경안 — 공개된 파이프라인 우회로
DEST_CHANGE = {
    "hormuz": [("푸자이라항", "UAE 하브샨–푸자이라 원유 파이프라인으로 호르무즈 밖에서 선적·하역"),
               ("얀부항", "사우디 동서(East-West) 원유 파이프라인으로 홍해 쪽에서 선적·하역")],
}


def bearing(lat1, lon1, lat2, lon2):
    p1, p2, dl = math.radians(lat1), math.radians(lat2), math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def _interp(a, b, f):
    """대권 대신 경위도 선형 보간 (짧은 구간용 근사). 날짜변경선을 넘는 구간 처리"""
    dlon = b[1] - a[1]
    if dlon > 180:
        dlon -= 360
    elif dlon < -180:
        dlon += 360
    lon = a[1] + dlon * f
    return (a[0] + (b[0] - a[0]) * f, (lon + 180) % 360 - 180)


def advance(points, dist_nm):
    """항로 points 를 따라 dist_nm 만큼 이동한 지점과 그 뒤의 남은 경로"""
    left = dist_nm
    for i in range(len(points) - 1):
        seg = haversine_nm(points[i], points[i + 1])
        if seg >= left and seg > 0:
            p = _interp(points[i], points[i + 1], left / seg)
            return p, [p] + [tuple(x[:2]) for x in points[i + 1:]]
        left -= seg
    return tuple(points[-1][:2]), [tuple(points[-1][:2])]


def ship_position(mmsi):
    """가장 최근 위치 (항적·선박 목록 중 최신)"""
    if not mmsi:
        return None
    cands = [t for t in db.get_tracks(mmsi, 1)]
    s = db.get_ship(mmsi)
    if s and s.get("lat") is not None:
        cands.append(s)
    if not cands:
        return None
    p = max(cands, key=lambda x: x["seen_at"])
    return {"lat": p["lat"], "lon": p["lon"], "sog": p.get("sog"), "cog": p.get("cog"), "seen_at": p["seen_at"]}


def strait_levels():
    out = {}
    for sid in STRAITS:
        st = db.latest_status(sid)
        out[sid] = {"level": st["level"] if st else None,
                    "reason": (st["data"]["eval"]["reasons"][0]["text"]
                               if st and st["data"]["eval"]["reasons"] else "특이 신호 없음")}
    return out


def _straits_info(ids, levels):
    return [{"id": s, "name": STRAITS[s]["name"], "level": levels.get(s, {}).get("level"),
             "reason": levels.get(s, {}).get("reason")} for s in ids]


def _alt_label(r):
    if "희망봉" in r["passages"]:
        return "희망봉 경유"
    names = [STRAITS[s]["name"] for s in r["straits"]]
    extra = [p for p in r["passages"] if p != "희망봉"]
    if names:
        return " · ".join(names) + " 경유"
    return (" · ".join(extra) + " 경유") if extra else "감시 해협 없이 운항"


def evaluate(v, levels=None, max_age_h=72, max_detour=2.0):
    levels = levels or strait_levels()
    now = datetime.now()
    dest = PORT_DB[v["dest"]]
    # 예시(데모) 선박은 위치를 직접 넣어 줌. 실제 선박은 AIS 기록에서
    pos = v.get("position") or ship_position(v.get("mmsi"))
    position, est = None, None
    if pos:
        age_h = (now - datetime.strptime(pos["seen_at"], "%Y-%m-%d %H:%M:%S")).total_seconds() / 3600
        position = dict(pos, age_h=round(age_h, 1), usable=age_h <= max_age_h)

    if position and position["usable"]:
        start = (position["lat"], position["lon"])
        base = find_route(start, v["dest"])
        speed = position["sog"] if position.get("sog") and position["sog"] > 3 else v["speed_kn"]
        if base and position["age_h"] >= 1:
            # 마지막 수신 이후 이동했을 거리만큼 항로를 따라 위치 추정
            est_pt, _ = advance(base["points"], speed * position["age_h"])
            est = {"lat": round(est_pt[0], 3), "lon": round(est_pt[1], 3), "hours": position["age_h"]}
            start = est_pt
            base = find_route(start, v["dest"])
        source = "estimated" if est else "ais"
    else:
        start, base, source = v["origin"], find_route(v["origin"], v["dest"]), "origin"

    if not base:
        return {"evaluated_at": db.now_str(), "error": "항로망에서 경로를 찾지 못했습니다", "position": position}
    cur = start if not isinstance(start, str) else (PORT_DB[start]["lat"], PORT_DB[start]["lon"])
    if haversine_nm(cur, (dest["lat"], dest["lon"])) <= ARRIVAL_NM:
        return {"evaluated_at": db.now_str(), "arrived": True, "position": position}

    pts = [list(p[:2]) for p in base["points"]]
    heading = (position.get("cog") if source == "ais" and position.get("cog") is not None
               else bearing(pts[0][0], pts[0][1], pts[1][0], pts[1][1]))
    days = base["distance_nm"] / (v["speed_kn"] * 24)
    straits = _straits_info(base["straits"], levels)
    risky = [s["id"] for s in straits if (s["level"] or 0) >= 1]

    alternatives = []
    if risky:
        banned = list(risky)
        for _ in range(2):
            r = find_route(start, v["dest"], banned_straits=banned)
            if not r or r["distance_nm"] > base["distance_nm"] * max_detour:
                break
            alt_straits = _straits_info(r["straits"], levels)
            alt_days = r["distance_nm"] / (v["speed_kn"] * 24)
            alternatives.append({
                "label": _alt_label(r), "points": [list(p[:2]) for p in r["points"]],
                "distance_nm": r["distance_nm"], "days": round(alt_days, 1),
                "delta_days": round(alt_days - days, 1), "straits": alt_straits,
                "max_level": max([s["level"] or 0 for s in alt_straits], default=0)})
            new = [s for s in r["straits"] if s not in banned]
            if not new:   # 더 피할 해협이 없으면 다음 대안은 같은 경로라 중단
                break
            banned += new
        # 바닷길로 피할 수 없으면 하역항 변경안
        if not alternatives:
            for sid in risky:
                for port, note in DEST_CHANGE.get(sid, []):
                    r = find_route(start, port, banned_straits=risky)
                    if not r:
                        continue
                    alt_straits = _straits_info(r["straits"], levels)
                    alt_days = r["distance_nm"] / (v["speed_kn"] * 24)
                    alternatives.append({
                        "label": f"하역항 변경: {port}", "note": note, "points": [list(p[:2]) for p in r["points"]],
                        "distance_nm": r["distance_nm"], "days": round(alt_days, 1),
                        "delta_days": round(alt_days - days, 1), "straits": alt_straits,
                        "max_level": max([s["level"] or 0 for s in alt_straits], default=0)})
        # 위험이 낮은 순 → 빠른 순
        alternatives.sort(key=lambda a: (a["max_level"], a["days"]))

    return {
        "evaluated_at": db.now_str(), "position": position, "estimated": est, "source": source,
        "heading": round(heading), "route_points": pts, "distance_nm": base["distance_nm"],
        "days": round(days, 1), "eta": (now + timedelta(days=days)).strftime("%Y-%m-%d"),
        "straits": straits, "level": max([s["level"] or 0 for s in straits], default=0),
        "alternatives": alternatives,
    }


# -------------------------------------------------------------
# 경보: 앞으로 지날 해협의 등급이 '올라갈 때만' 발송, 대기 시간 안에는 같은 등급 이하로 다시 보내지 않음
# -------------------------------------------------------------
def should_send(state, key, level, cooldown_h):
    """state: {key: {"level", "sent_level", "sent_at"}} 를 갱신하고 보낼지 여부 반환"""
    prev = state.get(key, {"level": 0, "sent_level": 0, "sent_at": None})
    send = False
    if level > prev["level"]:
        recent = prev["sent_at"] and datetime.now() - datetime.strptime(prev["sent_at"], "%Y-%m-%d %H:%M:%S") \
            < timedelta(hours=cooldown_h)
        send = not (recent and level <= prev["sent_level"])
    prev["level"] = level
    if send:
        prev["sent_level"], prev["sent_at"] = level, db.now_str()
    state[key] = prev
    return send


def voyage_message(v, ev, triggered):
    lines = [f"[항로 조기경보] {v['ship_name']} ({v['origin']} → {v['dest']})", ""]
    for s in ev["straits"]:
        if s["id"] in triggered:
            lines.append(f"■ {s['name']}: {LEVELS[s['level']]['label']} — {s['reason']}")
    lines += ["", f"남은 거리 약 {ev['distance_nm']:,}해리 · 약 {ev['days']}일 · 도착 예상 {ev['eta']}"]
    if ev["alternatives"]:
        lines += ["", "■ 대체 항로"]
        for a in ev["alternatives"]:
            st = ", ".join(f"{s['name']} {LEVELS[s['level']]['label']}" for s in a["straits"]) or "감시 해협 없음"
            lines.append(f"  - {a['label']}: 약 {a['distance_nm']:,}해리, {a['days']}일 ({a['delta_days']:+.1f}일) / {st}")
    lines += ["", "판단 근거와 지도는 대시보드에서 확인하세요: https://maritime-route-risk.streamlit.app/"]
    top = max(LEVELS[s["level"]]["label"] for s in ev["straits"] if s["id"] in triggered)
    return f"[항로 경보] {v['ship_name']} — 앞으로 지날 해협 {top}", "\n".join(lines)


def check_all(cooldown_h=6, max_age_h=72, max_detour=2.0):
    levels = strait_levels()
    for v in db.list_voyages():
        try:
            ev = evaluate(v, levels, max_age_h, max_detour)
        except Exception as e:
            log.exception("운항 %s 평가 실패", v["id"])
            ev = {"evaluated_at": db.now_str(), "error": str(e)}
        state = v.get("alert_state") or {}
        triggered = []
        for s in ev.get("straits", []):
            if should_send(state, s["id"], s["level"] or 0, cooldown_h):
                triggered.append(s["id"])
        if triggered:
            recipients = [r.strip() for r in v["recipients"].split(",") if r.strip()]
            target = f"voyage:{v['id']}"
            if not (mailer.configured() and recipients):
                db.log_alert(target, ev["level"], "not_configured", "메일 설정 또는 수신자 없음")
            else:
                subject, body = voyage_message(v, ev, triggered)
                try:
                    mailer.send(subject, body, recipients)
                    db.log_alert(target, ev["level"], "sent", ", ".join(recipients))
                except Exception as e:
                    db.log_alert(target, ev["level"], "failed", str(e))
        db.save_voyage_eval(v["id"], ev, state)
        log.info("운항 %s %s: %s", v["id"], v["ship_name"], ev.get("level", ev.get("error") or "도착"))
