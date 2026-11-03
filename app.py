"""Flask 웹 화면 - 저장된 결과를 보여 주고 사용자 입력(지정학 지수 수정, 비용 입력)만 처리

데이터 수집·위험 계산·알림은 scheduler.py 가 백그라운드에서 일정 간격으로 실행합니다.
실행: flask run  (또는 python app.py)
"""
import json
import logging
import os
from urllib.parse import urlencode

import plotly.graph_objects as go
from flask import Flask, Response, abort, jsonify, redirect, render_template, request
from markupsafe import Markup
from plotly.offline import get_plotlyjs

import db
import settings
from alternatives import OPTION_FIELDS, SCENARIO_FIELDS, comparison_payload, sanitize_inputs
import voyages
from collectors import known_ships, load_ship_history, load_ship_snapshot
from route_data import PORT_DB, ROUTE_DB, ROUTES_BY_ID, get_arctic_season_info
from scheduler import scheduler_status, start_scheduler
from settings import CONFIG

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

app = Flask(__name__)

DEFAULT_STRAIT = "hormuz"

# 상태 표시: 색만으로 구분하지 않도록 아이콘 + 글자를 함께 씀
STATUS = {
    0: {"label": "정상", "icon": "✓", "cls": "good"},
    1: {"label": "경고", "icon": "!", "cls": "warning"},
    2: {"label": "심각", "icon": "‼", "cls": "critical"},
    None: {"label": "수집 중", "icon": "…", "cls": "pending"},
}

# 밝은 테마 색. 항로 색은 고정 순서(현 항로 → 대안 1, 2, 3)로 쓰고, 지도 위에서 잘 보이도록 진한 색을 씀
# 파랑·주황·초록·보라: 일반 시력 기준 서로 뚜렷이 다른 4색 (dataviz 팔레트 검증 통과).
# 색약 기준 초록↔주황이 경계선이라 선 모양(ROUTE_DASHES)으로도 구분
ROUTE_COLORS = ["#1f6fd1", "#ef6c00", "#12a150", "#8e24aa"]
ROUTE_DASHES = ["solid", "dash", "dashdot", "longdash"]
INK = "#16181d"
CHART_TEXT = "#3d424b"
CHART_GRID = "#e4e6ea"
EDGE = "#ffffff"            # 표시 기호 테두리 (지도·차트에서 기호를 바탕과 분리)
GOOD, WARN, CRIT, NEUTRAL = "#0a8f0a", "#f2a900", "#d42f2f", "#6b7079"
GEO_BASE = dict(
    showland=True, landcolor="#ebe7df", showocean=True, oceancolor="#cfe4f7",
    showlakes=True, lakecolor="#cfe4f7",
    showcoastlines=True, coastlinecolor="#8f8a80", coastlinewidth=0.8,
    showcountries=True, countrycolor="#c4bfb4", countrywidth=0.6,
    showframe=False, bgcolor="rgba(0,0,0,0)",
)


@app.template_filter("money")
def money(v):
    """USD → $2.23M 처럼 읽기 쉬운 표기"""
    sign = "-" if v < 0 else ""
    v = abs(v)
    if v >= 1_000_000:
        return f"{sign}${v / 1_000_000:.2f}M"
    if v >= 1_000:
        return f"{sign}${v / 1_000:.0f}K"
    return f"{sign}${v:.0f}"


def fig_json(fig):
    # <script> 안에 넣으므로 "</script>" 같은 문자열이 태그를 닫지 않게 처리
    return Markup(fig.to_json().replace("</", "<\\/"))


def safe_json(obj):
    return Markup(json.dumps(obj, ensure_ascii=False).replace("</", "<\\/"))


# -------------------------------------------------------------
# 화면용 요약
# -------------------------------------------------------------
def strait_cards():
    """상단 해협 카드: 최신 등급·점수와 직전 계산 대비 변화"""
    cards = []
    for key, data in ROUTE_DB.items():
        hist = db.risk_history(data["id"], 2)
        latest = hist[-1] if hist else None
        delta = round(hist[-1]["score"] - hist[-2]["score"], 1) if len(hist) >= 2 else None
        cards.append({
            "id": data["id"], "name": key.split(" (")[0], "region": key.split(" (")[1].rstrip(")"),
            "score": latest["score"] if latest else None,
            "status": STATUS[latest["level"] if latest else None], "delta": delta,
        })
    return cards


def explain(sel):
    """판정을 한 문장으로: 등급, 다음 기준까지 남은 점수, 가장 큰 요인"""
    t = CONFIG["thresholds"]
    score, level = sel["score"], sel["level"]
    top = max(sel["contributions"], key=lambda c: c["points"])
    if level == 0:
        gap = f"경고 기준({t['warning']}점)까지 {t['warning'] - score:.1f}점 남았습니다."
    elif level == 1:
        gap = f"심각 기준({t['critical']}점)까지 {t['critical'] - score:.1f}점 남았습니다."
    else:
        gap = f"심각 기준({t['critical']}점)을 {score - t['critical']:.1f}점 넘었습니다."
    reason = f"가장 큰 요인은 <b>{top['label']}</b>({top['points']}점)입니다." if top["points"] > 0 else ""
    return Markup(f"{gap} {reason}")


# -------------------------------------------------------------
# 차트
# -------------------------------------------------------------
def build_trend_fig(history):
    t = CONFIG["thresholds"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=[h["computed_at"] for h in history], y=[h["score"] for h in history], mode="lines+markers",
        line=dict(color=ROUTE_COLORS[0], width=3), marker=dict(size=9, color=ROUTE_COLORS[0], line=dict(width=2, color=EDGE)),
        name="리스크 점수", hovertemplate="%{x}<br><b>%{y}점</b><extra></extra>",
    ))
    for y, label, color in ((t["warning"], "경고", WARN), (t["critical"], "심각", CRIT)):
        fig.add_hline(y=y, line=dict(color=color, dash="dash", width=2),
                      annotation_text=f"{label} {y}", annotation_position="top left",
                      annotation_font=dict(color=CHART_TEXT, size=11))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color=CHART_TEXT, size=12),
        height=230, margin=dict(l=40, r=10, t=10, b=30), showlegend=False, hovermode="x unified",
        xaxis=dict(showgrid=False, linecolor=CHART_GRID),
        yaxis=dict(showgrid=True, gridcolor=CHART_GRID, range=[0, 100], dtick=20, zeroline=False),
    )
    return fig


def land_trace(points, color, label):
    """육상 구간(파이프라인·철도): 굵은 점선 + 양 끝 사각 표시로 해상 구간과 구분"""
    return go.Scattergeo(
        lat=[p[0] for p in points], lon=[p[1] for p in points], mode="lines+markers",
        line=dict(width=5, color=color, dash="dot"),
        marker=dict(size=[10] + [0] * (len(points) - 2) + [10], symbol="square", color=color,
                    line=dict(width=1.5, color=EDGE)),
        name=f"  └ {label}", hoverinfo="name",
    )


def build_route_fig(curr_data, comparison, alert_triggered):
    """현 항로와 대안 경로를 한 지도에. 색은 비교표의 대안 순서와 고정 연결"""
    options = curr_data["scenario"]["options"]
    best_id = next((r["id"] for r in comparison["rows"] if not r["is_base"]), None)
    fig = go.Figure()
    for i, opt in enumerate(options):
        is_base = i == 0
        emphasized = is_base or opt["id"] == best_id
        fig.add_trace(go.Scattergeo(
            lat=[p[0] for p in opt["path"]], lon=[p[1] for p in opt["path"]], mode="lines",
            line=dict(width=7 if is_base else (4.5 if emphasized else 3.5), color=ROUTE_COLORS[i % len(ROUTE_COLORS)],
                      dash=ROUTE_DASHES[i % len(ROUTE_DASHES)]),
            opacity=1 if emphasized else 0.85,
            name=("현 항로: " if is_base else "") + opt["route_name"].replace("현 항로 유지: ", ""),
            hoverinfo="name",
        ))
        if opt.get("land_path"):
            fig.add_trace(land_trace(opt["land_path"], ROUTE_COLORS[i % len(ROUTE_COLORS)],
                                     opt.get("land_label", "육상 구간")))
    tz = curr_data["threat_zone"]
    fig.add_trace(go.Scattergeo(
        lat=[tz["lat"]], lon=[tz["lon"]], mode="markers",
        marker=dict(size=22, color=CRIT if alert_triggered else INK, symbol="x",
                    line=dict(width=2, color=EDGE)),
        name=f"감시 구역: {tz['name']}", hoverinfo="name",
    ))
    fig.update_layout(
        geo=dict(projection_type="natural earth", fitbounds="locations", **GEO_BASE),
        paper_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=0, b=0), height=400,
        legend=dict(orientation="h", yanchor="top", y=-0.02, x=0, font=dict(color=CHART_TEXT, size=12),
                    bgcolor="rgba(0,0,0,0)"),
    )
    return fig


def build_ship_fig(ships, history, mmsi):
    """선택한 실제 선박 위치와 수집된 항적 (최신 수집의 주변 선박은 흐리게)"""
    me = ships[mmsi]
    fig = go.Figure()
    near = [s for m, s in ships.items() if m != mmsi and s["current"]
            and abs(s["lat"] - me["lat"]) < 8 and abs(s["lon"] - me["lon"]) < 12]
    if near:
        fig.add_trace(go.Scattergeo(lat=[n["lat"] for n in near], lon=[n["lon"] for n in near], mode="markers",
                                    marker=dict(size=7, color=NEUTRAL, opacity=0.7, line=dict(width=1, color=EDGE)), text=[n["name"] for n in near],
                                    hoverinfo="text", name="주변 선박 (최신 수집)"))
    caption = None
    track = (history or {}).get(mmsi, {}).get("track", [])
    if len(track) >= 2:
        fig.add_trace(go.Scattergeo(lat=[p["lat"] for p in track], lon=[p["lon"] for p in track],
                                    mode="lines+markers", line=dict(width=4, color=ROUTE_COLORS[2]),
                                    marker=dict(size=9, color=ROUTE_COLORS[2], line=dict(width=1.5, color=EDGE)), name="수집된 항적",
                                    text=[p["time"] for p in track], hoverinfo="text"))
    else:
        caption = "항적은 이 선박이 AIS 수집에 2회 이상 잡히면 그려집니다."
    fig.add_trace(go.Scattergeo(lat=[me["lat"]], lon=[me["lon"]], mode="markers+text",
                                marker=dict(size=24, color=ROUTE_COLORS[0], symbol="star", line=dict(width=2, color=EDGE)),
                                text=[me["name"]], textposition="top center", textfont=dict(color=INK, size=13),
                                name=me["name"], hoverinfo="name"))
    fig.update_layout(
        geo=dict(projection_type="equirectangular", center=dict(lat=me["lat"], lon=me["lon"]),
                 projection_scale=6, **GEO_BASE),
        paper_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=0, b=0), height=320,
        legend=dict(orientation="h", yanchor="top", y=-0.02, x=0, font=dict(color=CHART_TEXT, size=12)),
    )
    return fig, caption


# -------------------------------------------------------------
# 라우트
# -------------------------------------------------------------
@app.route("/plotly.js")
def plotly_js():
    # 파이썬 plotly와 같은 버전의 plotly.js를 그대로 제공
    return Response(get_plotlyjs(), mimetype="application/javascript",
                    headers={"Cache-Control": "public, max-age=86400"})


@app.route("/healthz")
def healthz():
    # 잠들기 방지 핑용 (cron-job.org 등). DB 를 건드리지 않아 Neon 이 절전할 수 있음
    return "ok"


@app.route("/")
def index():
    args = request.args
    port_list = list(PORT_DB.keys())

    # ---- 해협 선택: 카드 클릭(?strait=) ----
    strait_id = args.get("strait", DEFAULT_STRAIT)
    if strait_id not in ROUTES_BY_ID:
        strait_id = DEFAULT_STRAIT
    route_key, curr_data = ROUTES_BY_ID[strait_id]

    # ---- 스케줄러가 저장한 최신 결과 ----
    sel = db.latest_risk(strait_id)
    news = db.latest_news(strait_id)
    ind = sel["indicators"] if sel else {}
    alert_triggered = bool(sel and sel["level"] >= 1)

    # ---- 대체 항로 비교 ----
    comparison = comparison_payload(strait_id)

    # ---- 차트 ----
    figures = {"fig-route": fig_json(build_route_fig(curr_data, comparison, alert_triggered))}
    history = db.risk_history(strait_id, CONFIG["trend"]["days"])
    trend_ready = len(history) >= CONFIG["trend"]["min_points"]
    if trend_ready:
        figures["fig-trend"] = fig_json(build_trend_fig(history))

    # ---- 선박 추적 (검색했을 때만) ----
    search_term = args.get("search_term", "").strip()
    real_ship_data = load_ship_snapshot()
    matches, ship = {}, None
    if search_term:
        history = load_ship_history()
        ships = known_ships(real_ship_data, history)
        q = search_term.upper()
        matches = {m: s["name"] for m, s in ships.items() if q in f"{s['name']} {m}".upper()}
        mmsi = args.get("mmsi") if args.get("mmsi") in matches else next(iter(matches), None)
        if mmsi:
            fig, caption = build_ship_fig(ships, history, mmsi)
            figures["fig-ship"] = fig_json(fig)
            ship = dict(ships[mmsi], mmsi=mmsi, caption=caption)

    t = CONFIG["thresholds"]
    return render_template(
        "index.html",
        cards=strait_cards(), strait_id=strait_id, route_key=route_key, strait_name=route_key.split(" (")[0],
        scenario=curr_data["scenario"], threat_zone=curr_data["threat_zone"],
        sel=sel, ind=ind, news=news, status=STATUS[sel["level"] if sel else None],
        explanation=explain(sel) if sel else None, thresholds=t,
        gauge={"warning": t["warning"], "critical": t["critical"], "score": sel["score"] if sel else 0},
        port_list=port_list, voyages=voyage_rows(), default_recipients=", ".join(settings.ALERT_RECIPIENTS),
        default_speed=CONFIG["voyage"]["default_speed_kn"],
        is_arctic=curr_data.get("is_arctic", False), arctic=get_arctic_season_info(),
        geo_override=db.get_geo_override(strait_id), return_qs=urlencode({"strait": strait_id}),
        comparison=comparison, comparison_json=safe_json(comparison),
        route_colors={o["id"]: ROUTE_COLORS[i % len(ROUTE_COLORS)] for i, o in enumerate(curr_data["scenario"]["options"])},
        scenario_fields=SCENARIO_FIELDS, option_fields=OPTION_FIELDS,
        trend_ready=trend_ready, trend_count=len(history), trend_min=CONFIG["trend"]["min_points"],
        figures_json=Markup("{" + ",".join(f'"{k}": {v}' for k, v in figures.items()) + "}"),
        search_term=search_term, matches=matches, ship=ship, ais_updated=(real_ship_data or {}).get("updated_at"),
        alert_recipients=settings.ALERT_RECIPIENTS, smtp_ok=settings.smtp_configured(),
        alerts=[a for a in db.recent_alerts(30) if a["strait_id"] == strait_id and a["status"] != "suppressed"][:3],
        jobs={j["id"]: j["next_run"] for j in (scheduler_status() or [])},
    )


# -------------------------------------------------------------
# 운항 감시
# -------------------------------------------------------------
def voyage_rows():
    rows = []
    for v in db.list_voyages():
        ev = v["last_eval"] or {}
        lv = ev.get("level") if ev else None
        if ev.get("arrived"):
            summary = "도착(또는 도착 직전)"
        elif ev.get("error"):
            summary = ev["error"]
        elif not ev:
            summary = "평가 중…"
        elif ev["issues"]:
            summary = ev["issues"][0]["title"] + (f" 외 {len(ev['issues']) - 1}건" if len(ev["issues"]) > 1 else "")
        else:
            summary = "남은 경로에 예측된 문제 없음"
        best = (ev.get("alternatives") or [None])[0]
        rows.append({"v": v, "ev": ev, "status": STATUS[lv if ev and not ev.get("error") else None],
                     "summary": summary, "best": best})
    return rows


def resolve_ship(text):
    """선박명 또는 MMSI 입력 → (선박명, MMSI 또는 None, 안내문)"""
    text = text.strip()
    ships = known_ships()
    if text.isdigit() and len(text) == 9:
        s = ships.get(text)
        return ((s["name"] if s else f"MMSI {text}"), text,
                "AIS 위치 기록이 있어 현재 위치 기준으로 감시합니다" if s else
                "아직 위치 기록 없음 — 다음 AIS 수집 때 MMSI 로 추적합니다")
    q = text.upper()
    exact = [m for m, s in ships.items() if s["name"].upper() == q]
    partial = [m for m, s in ships.items() if q and q in s["name"].upper()]
    if exact or len(partial) == 1:
        m = (exact or partial)[0]
        return ships[m]["name"], m, f"AIS 기록에서 선박을 찾아 MMSI {m} 로 연결했습니다"
    if partial:
        return text, None, f"이름이 비슷한 선박이 {len(partial)}척이라 연결하지 않았습니다 — MMSI 로 등록하면 정확합니다"
    return text, None, "AIS 기록에서 찾지 못해 출발항 기준으로 감시합니다 (MMSI 로 등록하면 위치 추적 가능)"


def build_voyage_fig(v, ev):
    """남은 경로, 위험 지점, 대체 노선, 현재 위치를 한 지도에"""
    fig = go.Figure()
    # 현재 경로를 먼저 그리고 대안을 위에 겹쳐 그림 (같은 구간을 지나는 대안도 보이도록)
    pts = ev.get("route_points") or []
    if pts:
        fig.add_trace(go.Scattergeo(lat=[p[0] for p in pts], lon=[p[1] for p in pts], mode="lines",
                                    line=dict(width=7, color=ROUTE_COLORS[0]), name="현재 계획 경로(남은 구간)",
                                    hoverinfo="name"))
    for i, a in enumerate([a for a in ev.get("alternatives", []) if a["points"]][:3]):
        fig.add_trace(go.Scattergeo(lat=[p[0] for p in a["points"]], lon=[p[1] for p in a["points"]], mode="lines",
                                    line=dict(width=4.5, color=ROUTE_COLORS[(i + 1) % len(ROUTE_COLORS)],
                                              dash=ROUTE_DASHES[(i + 1) % len(ROUTE_DASHES)]),
                                    name=f"대안 {i + 1}: {a['label']}", hoverinfo="name"))
        if a.get("land_points"):
            fig.add_trace(land_trace(a["land_points"], ROUTE_COLORS[(i + 1) % len(ROUTE_COLORS)],
                                     a.get("land_label", "육상 구간")))
    wx = [w for w in ev.get("weather", []) if w["level"] >= 1]
    for lv, color, label in ((1, WARN, "기상 경고 지점"), (2, CRIT, "기상 심각 지점")):
        sel = [w for w in wx if w["level"] == lv]
        if sel:
            fig.add_trace(go.Scattergeo(
                lat=[w["lat"] for w in sel], lon=[w["lon"] for w in sel], mode="markers",
                marker=dict(size=17, color=color, symbol="triangle-up", line=dict(width=2, color=INK)),
                text=[f"{w['near']} · 도착 예상 {w['eta']}<br>파고 {w['wave']} m · 풍속 {w['wind']} kn" for w in sel],
                hoverinfo="text", name=label))
    marker_color = {"good": INK, "warning": WARN, "critical": CRIT, "pending": NEUTRAL}
    for s in ev.get("straits", []):
        zone = ROUTES_BY_ID[s["id"]][1]["threat_zone"]
        st = STATUS[s["level"]]
        fig.add_trace(go.Scattergeo(
            lat=[zone["lat"]], lon=[zone["lon"]], mode="markers",
            marker=dict(size=22, symbol="x", color=marker_color[st["cls"]], line=dict(width=2, color=EDGE)),
            name=f"{s['name']}: {st['label']}", hoverinfo="name"))
    pos = ev.get("position")
    if pos and pos.get("usable"):
        fig.add_trace(go.Scattergeo(lat=[pos["lat"]], lon=[pos["lon"]], mode="markers",
                                    marker=dict(size=26, color=INK, symbol="star", line=dict(width=2, color=EDGE)),
                                    name=f"{v['ship_name']} ({pos['seen_at'][5:16]})", hoverinfo="name"))
    fig.update_layout(
        geo=dict(projection_type="natural earth", fitbounds="locations", **GEO_BASE),
        paper_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=0, b=0), height=430,
        legend=dict(orientation="h", yanchor="top", y=-0.02, x=0, font=dict(color=CHART_TEXT, size=12)),
    )
    return fig


def build_weather_fig(ev):
    """남은 경로를 따라 '도착 예상 시각'의 예보 파고 (풍속은 마우스를 올리면 표시)"""
    vc = CONFIG["voyage"]
    wx = ev.get("weather") or []
    color = {0: ROUTE_COLORS[0], 1: WARN, 2: CRIT}
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=[w["eta"] for w in wx], y=[w["wave"] for w in wx], mode="lines+markers",
        line=dict(color=ROUTE_COLORS[0], width=3),
        marker=dict(size=10, color=[color[w["level"]] for w in wx], line=dict(width=2, color=EDGE)),
        customdata=[[w["near"], w["wind"]] for w in wx],
        hovertemplate="%{x} · %{customdata[0]}<br>파고 <b>%{y} m</b> · 풍속 %{customdata[1]} kn<extra></extra>",
        name="예보 파고"))
    for y, label, c in ((vc["wave_warning_m"], "경고", WARN), (vc["wave_critical_m"], "심각", CRIT)):
        fig.add_hline(y=y, line=dict(color=c, dash="dash", width=2), annotation_text=f"{label} {y} m",
                      annotation_position="top left", annotation_font=dict(color=CHART_TEXT, size=11))
    top = max([w["wave"] or 0 for w in wx] + [vc["wave_critical_m"] + 0.5])
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color=CHART_TEXT, size=12),
        height=230, margin=dict(l=50, r=10, t=10, b=40), showlegend=False,
        xaxis=dict(showgrid=False, type="category", tickangle=0,
                   tickvals=[w["eta"] for w in wx][::max(1, -(-len(wx) // 4))]),
        yaxis=dict(showgrid=True, gridcolor=CHART_GRID, range=[0, top], title="파고 (m)", zeroline=False),
    )
    return fig


@app.post("/voyages")
def create_voyage():
    f = request.form
    if f.get("origin") not in PORT_DB or f.get("dest") not in PORT_DB or f.get("origin") == f.get("dest"):
        abort(400)
    name, mmsi, msg = resolve_ship(f.get("ship", "") or "이름 없는 선박")
    try:
        speed = float(f.get("speed_kn") or CONFIG["voyage"]["default_speed_kn"])
    except ValueError:
        speed = CONFIG["voyage"]["default_speed_kn"]
    try:
        cost = float(f["daily_cost_usd"]) if f.get("daily_cost_usd") else None
    except ValueError:
        cost = None
    recipients = ",".join(r.strip() for r in (f.get("recipients") or "").split(",") if "@" in r) or \
        ",".join(settings.ALERT_RECIPIENTS)
    vid = db.add_voyage(name, mmsi, f["origin"], f["dest"], max(1.0, min(30.0, speed)), cost, recipients)
    voyages.check_in_background(vid)
    return redirect(f"/voyage/{vid}?" + urlencode({"msg": msg}))


@app.post("/voyages/<int:voyage_id>/check")
def recheck_voyage(voyage_id):
    if not db.get_voyage(voyage_id):
        abort(404)
    voyages.check_voyage(voyage_id)
    return redirect(f"/voyage/{voyage_id}")


@app.post("/voyages/<int:voyage_id>/end")
def end_voyage(voyage_id):
    db.end_voyage(voyage_id)
    return redirect("/")


@app.route("/voyage/<int:voyage_id>")
def voyage_page(voyage_id):
    v = db.get_voyage(voyage_id)
    if not v:
        abort(404)
    ev = v["last_eval"] or {}
    figures = {}
    if ev and not ev.get("error") and not ev.get("arrived"):
        figures["fig-voyage"] = fig_json(build_voyage_fig(v, ev))
        if ev.get("weather"):
            figures["fig-wx"] = fig_json(build_weather_fig(ev))
    return render_template(
        "voyage.html", v=v, ev=ev, status=STATUS[ev.get("level") if ev and not ev.get("error") else None],
        level_status=STATUS, msg=request.args.get("msg"), alerts=db.voyage_alerts(voyage_id),
        vc=CONFIG["voyage"], smtp_ok=settings.smtp_configured(),
        figures_json=Markup("{" + ",".join(f'"{k}": {val}' for k, val in figures.items()) + "}"),
    )


@app.post("/geo/<strait_id>")
def update_geo(strait_id):
    """지정학 위협 지수 수정값 저장 / 추천값으로 되돌리기"""
    if strait_id not in ROUTES_BY_ID:
        abort(404)
    if request.form.get("action") == "reset":
        db.clear_geo_override(strait_id)
    else:
        try:
            level = int(request.form["geo_level"])
        except (KeyError, ValueError):
            abort(400)
        db.set_geo_override(strait_id, max(1, min(5, level)))
    qs = request.form.get("return_qs", "")
    return redirect("/" + (f"?{qs}" if qs else ""))


@app.post("/api/costs/<scenario_id>")
def update_costs(scenario_id):
    """비용 입력값 저장 후 대안별 총비용·순위를 다시 계산해서 돌려줌 (fetch 용)"""
    if scenario_id not in ROUTES_BY_ID:
        abort(404)
    body = request.get_json(silent=True) or {}
    db.save_cost_inputs(scenario_id, sanitize_inputs(scenario_id, body.get("inputs") or {}))
    return jsonify(comparison_payload(scenario_id))


# `flask run` 과 `python app.py` 어느 쪽으로 실행해도 스케줄러가 시작되도록 모듈 로드 시 시작
start_scheduler()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true"))
