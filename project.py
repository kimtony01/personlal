"""해상 항로 조기경보 — Streamlit 화면

수집·판단·메일은 GitHub Actions 가 30분마다 monitor.py 로 실행하고 결과를 DB(Neon)에 저장합니다.
이 화면은 저장된 결과를 읽어 보여 주고, 선박 등록과 신호등 기준 조절만 처리합니다.
"""
import os
import tomllib
from datetime import date, timedelta
from pathlib import Path

import requests
import streamlit as st

st.set_page_config(page_title="해상 항로 조기경보", page_icon="🌊", layout="wide", initial_sidebar_state="expanded")

# Streamlit Cloud 의 Secrets 를 환경변수로 (db.py 등이 os.getenv 로 읽음)
try:
    for _k, _v in st.secrets.items():
        if isinstance(_v, str):
            os.environ.setdefault(_k, _v)
except Exception:
    pass
from dotenv import load_dotenv  # noqa: E402

load_dotenv()

import plotly.graph_objects as go  # noqa: E402

try:
    from googletrans import Translator  # 뉴스 제목 한글 번역 (없으면 원문 표시)
except ImportError:
    Translator = None

import db  # noqa: E402
import rules  # noqa: E402
import voyages  # noqa: E402
from ports import PORT_DB  # noqa: E402
from sea_network import find_route  # noqa: E402
from straits import LEVELS, STRAITS  # noqa: E402

with open(Path(__file__).resolve().parent / "config.toml", "rb") as f:
    CONFIG = tomllib.load(f)

# 해협별 대표 항로 (등록 선박이 없을 때 대체 항로 비교 예시)
SAMPLE_ROUTES = {"hormuz": ("담맘항", "울산항"), "suez": ("부산항", "로테르담항"),
                 "malacca": ("부산항", "뭄바이항"), "panama": ("부산항", "뉴욕항")}
BLUE, ALT_COLORS = "#2563eb", ["#ea580c", "#16a34a", "#9333ea"]

# -------------------------------------------------------------
# 스타일
# -------------------------------------------------------------
st.markdown("""
<style>
    .stApp { background-color: #f8fafc; }
    .block-container { padding-top: 2rem; max-width: 1400px; }
    h1, h2, h3 { color: #0f172a !important; font-weight: 700 !important; letter-spacing: -0.3px; }
    .stCaption, p, label { color: #64748b; }
    section[data-testid="stSidebar"] { background-color: #ffffff; border-right: 1px solid #e2e8f0; }
    div[data-testid="stVerticalBlockBorderWrapper"] { background: #ffffff; border-radius: 14px; }
    a { color: #2563eb !important; text-decoration: none !important; font-weight: 600; }

    .app-header { display: flex; align-items: center; justify-content: space-between; background: #fff;
        border: 1px solid #e2e8f0; border-radius: 16px; padding: 16px 24px; margin-bottom: 18px;
        box-shadow: 0 1px 3px rgba(15,23,42,0.06); }
    .brand { display: flex; align-items: center; gap: 12px; }
    .brand-icon { width: 38px; height: 38px; border-radius: 10px; background: linear-gradient(135deg, #2563eb, #38bdf8);
        display: flex; align-items: center; justify-content: center; font-size: 1.2rem; }
    .brand-title { color: #0f172a; font-weight: 800; font-size: 1.2rem; }
    .brand-sub { color: #94a3b8; font-size: 0.8rem; }
    .pill { display: inline-block; padding: 3px 12px; border-radius: 999px; font-weight: 700; font-size: 0.8rem; }

    .sig-card { background: #fff; border: 1px solid #e2e8f0; border-radius: 14px; padding: 14px 16px;
        min-height: 128px; box-shadow: 0 1px 3px rgba(15,23,42,0.05); }
    .sig-card.sel { border: 2px solid #2563eb; }
    .sig-name { color: #0f172a; font-weight: 800; font-size: 1.02rem; }
    .sig-region { color: #94a3b8; font-size: 0.75rem; margin-bottom: 8px; }
    .sig-why { color: #475569; font-size: 0.8rem; margin-top: 8px; line-height: 1.4; }

    .banner { border-radius: 14px; padding: 16px 20px; margin: 6px 0 18px; border: 1px solid transparent; }
    .banner b { color: #0f172a; }
    .banner ul { margin: 6px 0 0 0; padding-left: 18px; }
    .banner li { color: #334155; font-size: 0.9rem; }

    .card { background: #fff; border: 1px solid #e2e8f0; border-radius: 14px; padding: 16px 18px;
        box-shadow: 0 1px 3px rgba(15,23,42,0.05); margin-bottom: 12px; }
    .card h4 { margin: 0 0 8px; color: #0f172a; font-size: 0.98rem; }
    .card .big { color: #0f172a; font-weight: 800; font-size: 1.3rem; }
    .card .muted { color: #64748b; font-size: 0.82rem; line-height: 1.5; }
    .row { display: flex; justify-content: space-between; gap: 10px; padding: 5px 0; border-bottom: 1px solid #f1f5f9;
        font-size: 0.86rem; color: #334155; }
    .row:last-child { border-bottom: none; }
    .news-card { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 12px 16px; margin-bottom: 10px; }
</style>
""", unsafe_allow_html=True)


def pill(level, text=None):
    lv = LEVELS[level]
    return (f"<span class='pill' style='background:{lv['bg']};color:{lv['color']}'>"
            f"{lv['icon']} {text or lv['label']}</span>")


# -------------------------------------------------------------
# 데이터 읽기
# -------------------------------------------------------------
@st.cache_data(ttl=120, show_spinner=False)
def load_statuses():
    return {sid: db.latest_status(sid) for sid in STRAITS}


@st.cache_data(ttl=120, show_spinner=False)
def load_history(sid):
    return db.status_history(sid, 30)


@st.cache_data(ttl=3600, show_spinner=False)
def load_traffic(portname):
    data, _ = db.load_blob(f"portwatch:{portname}")
    return data or []


@st.cache_data(ttl=600, show_spinner=False)
def fetch_news(query, display=6):
    api_key = os.getenv("NEWSAPI_KEY")
    if not api_key:
        return None
    try:
        res = requests.get("https://newsapi.org/v2/everything", timeout=8, params={
            "q": query, "language": "en", "sortBy": "publishedAt", "pageSize": display, "apiKey": api_key})
        res.raise_for_status()
        translator, results = Translator() if Translator else None, []
        for a in res.json().get("articles", []):
            title, desc = a.get("title") or "", a.get("description") or ""
            if translator:
                try:
                    title = translator.translate(title[:500], src="en", dest="ko").text if title else title
                    desc = translator.translate(desc[:500], src="en", dest="ko").text if desc else desc
                except Exception:
                    pass  # 번역 실패 시 원문 표시
            results.append({"title": title, "link": a.get("url", "#"), "desc": desc,
                            "source": (a.get("source") or {}).get("name", "출처 미상"),
                            "date": (a.get("publishedAt") or "")[:10]})
        return results
    except Exception as e:
        return {"error": str(e)}


ISSUE_KEYWORDS_KO = {
    "공격/충돌": ["공격", "충돌", "드론", "폭격", "미사일", "타격"],
    "봉쇄/장악": ["봉쇄", "장악", "통제", "폐쇄", "차단", "나포"],
    "제재": ["제재", "금수"],
    "기상 악화": ["폭풍", "태풍", "허리케인", "해일"],
    "지연/정체": ["지연", "정체", "대기", "혼잡"],
}


def summarize_news(items):
    combined = " ".join((n.get("title") or "") + " " + (n.get("desc") or "") for n in items)
    found = sorted(((k, sum(combined.count(w) for w in ws)) for k, ws in ISSUE_KEYWORDS_KO.items()),
                   key=lambda x: -x[1])
    issues = [k for k, n in found if n > 0][:3]
    return {"count": len(items), "sources": len({n["source"] for n in items}),
            "issues": ", ".join(issues) if issues else "뚜렷한 위협 이슈 없음 (일상적 운항 관련 보도 위주)"}


# -------------------------------------------------------------
# 사이드바: 내 선박 · 신호등 기준
# -------------------------------------------------------------
st.sidebar.markdown("### 🚢 내 선박")
active = db.list_voyages()
voyage_opts = {None: "선택 안 함"} | {v["id"]: f"{v['ship_name']} · {v['origin']}→{v['dest']}" for v in active}
# 처음 열었을 때는 가장 최근 등록 선박을 선택
default_vid = st.session_state.get("voyage_id", "unset")
sel_vid = st.sidebar.selectbox("추적 중인 선박", list(voyage_opts), format_func=voyage_opts.get,
                               index=list(voyage_opts).index(default_vid) if default_vid in voyage_opts else
                               (1 if len(voyage_opts) > 1 else 0))
st.session_state["voyage_id"] = sel_vid
voyage = next((v for v in active if v["id"] == sel_vid), None)
if voyage:
    st.sidebar.caption(f"MMSI {voyage['mmsi'] or '없음 (출발항 기준 계산)'} · 속력 {voyage['speed_kn']}노트 · "
                       f"알림 {voyage['recipients'] or '없음'}")
    if st.sidebar.button("운항 종료", width="stretch"):
        db.end_voyage(voyage["id"])
        st.session_state["voyage_id"] = None
        st.rerun()

with st.sidebar.expander("➕ 선박 등록", expanded=not active):
    q = st.text_input("선박명 또는 MMSI(9자리)", placeholder="예: HMM ALGECIRAS 또는 440123000")
    mmsi, ship_name = None, q.strip()
    if q.strip():
        if q.strip().isdigit() and len(q.strip()) == 9:
            mmsi = q.strip()
            found = db.get_ship(mmsi)
            ship_name = (found or {}).get("name") or f"MMSI {mmsi}"
            st.caption(f"✓ AIS 기록: {found['name']} (마지막 수신 {found['seen_at'][5:16]})" if found
                       else "아직 AIS 기록 없음 — 다음 수집부터 이 번호로 추적합니다")
        else:
            cands = db.search_ships(q)
            labels = {None: "목록에 없음 — 이름만 등록 (출발항 기준 계산)"}
            labels |= {c["mmsi"]: f"{c['name']} · MMSI {c['mmsi']} · {(c['seen_at'] or '')[5:16]}" for c in cands}
            pick = st.selectbox(f"AIS에서 찾은 선박 {len(cands)}척", list(labels), format_func=labels.get,
                                index=1 if len(cands) == 1 else 0)
            if pick:
                mmsi, ship_name = pick, next(c["name"] for c in cands if c["mmsi"] == pick)
    port_list = list(PORT_DB)
    origin = st.selectbox("출발항", port_list, index=port_list.index("부산항"))
    dest = st.selectbox("도착항", port_list, index=port_list.index("로테르담항"))
    speed = st.number_input("평균 속력 (노트)", 5.0, 30.0, float(CONFIG["voyage"]["default_speed_kn"]), 0.5)
    email = st.text_input("경보 받을 메일 (쉼표로 여러 명)", value=os.getenv("ALERT_RECIPIENTS", ""))
    if st.button("등록하고 추적 시작", width="stretch", disabled=not ship_name):
        if origin == dest:
            st.error("출발항과 도착항이 같습니다.")
        else:
            vid = db.add_voyage(ship_name, mmsi, origin, dest, speed,
                                ",".join(e.strip() for e in email.split(",") if "@" in e))
            st.session_state["voyage_id"] = vid
            st.rerun()

st.sidebar.markdown("### ⚙️ 신호등 기준")
th = dict(CONFIG["rules"])
enabled = {}
with st.sidebar.expander("기준 조절", expanded=False):
    st.caption("바꾼 기준은 이 화면에만 적용됩니다. 메일은 기본 기준(config.toml)으로 판단합니다.")
    for key, label in rules.LAYERS.items():
        enabled[key] = st.toggle(label, value=True, key=f"on_{key}")
    th["news_ratio"] = st.slider("뉴스: 최근 7일 평균이 평소의 몇 배면 주의", 1.2, 3.0, float(th["news_ratio"]), 0.1,
                                 key="th_news_ratio")
    th["traffic_warn_pct"] = st.slider("통항: 몇 % 줄면 주의", 5, 50, th["traffic_warn_pct"], key="th_warn")
    th["traffic_crit_pct"] = st.slider("통항: 몇 % 줄면 심각", 10, 80, th["traffic_crit_pct"], key="th_crit")
    if th["traffic_crit_pct"] <= th["traffic_warn_pct"]:
        st.caption("⚠ '심각' 기준이 '주의' 기준보다 커야 합니다.")
    if st.button("기본값으로", width="stretch"):
        for k in [k for k in st.session_state if k.startswith(("on_", "th_"))]:
            del st.session_state[k]
        st.rerun()

# -------------------------------------------------------------
# 판단 (저장된 원래 값 + 현재 기준)
# -------------------------------------------------------------
statuses = load_statuses()
evals = {sid: (rules.evaluate(s["data"]["raw"], th, enabled) if s else {"level": None, "reasons": [], "layers": {}})
         for sid, s in statuses.items()}
levels = {sid: {"level": e["level"], "reason": rules.headline(e)} for sid, e in evals.items()}
last_run = max((s["computed_at"] for s in statuses.values() if s), default=None)

ev = None
if voyage:
    try:
        ev = voyages.evaluate(voyage, levels, CONFIG["ais"]["position_max_age_hours"],
                              CONFIG["voyage"]["max_detour_ratio"])
    except Exception as e:
        ev = {"error": str(e)}

if "strait" not in st.session_state:
    ahead = [s for s in (ev or {}).get("straits", []) if (s["level"] or 0) >= 1]
    worst = max(STRAITS, key=lambda s: evals[s]["level"] or 0)
    st.session_state["strait"] = ahead[0]["id"] if ahead else worst
overall = max([e["level"] for e in evals.values() if e["level"] is not None], default=None)

# -------------------------------------------------------------
# 헤더
# -------------------------------------------------------------
st.markdown(f"""
<div class="app-header">
  <div class="brand"><div class="brand-icon">🌊</div>
    <div><div class="brand-title">해상 항로 조기경보</div>
    <div class="brand-sub">공식 경보 · 뉴스 사건 · 실제 통항량 · 재해로 판단 · 30분마다 자동 갱신
    {f'· 마지막 확인 {last_run[5:16]}' if last_run else ''}</div></div></div>
  <div>{pill(overall, '전체 ' + LEVELS[overall]['label']) if overall is not None else pill(None)}</div>
</div>""", unsafe_allow_html=True)

if not db.USE_PG:
    st.warning("DB(DATABASE_URL)가 설정되지 않아 임시 저장소를 쓰고 있습니다. 앱이 재시작되면 등록한 선박이 사라집니다.")

# -------------------------------------------------------------
# ① 위험 신호등
# -------------------------------------------------------------
cols = st.columns(len(STRAITS))
for col, (sid, s) in zip(cols, STRAITS.items()):
    e = evals[sid]
    why = rules.headline(e)
    col.markdown(f"""
<div class="sig-card {'sel' if sid == st.session_state['strait'] else ''}">
  <div class="sig-name">{s['name']}</div><div class="sig-region">{s['region']}</div>
  {pill(e['level'])}
  <div class="sig-why">{why if len(why) < 70 else why[:68] + '…'}</div>
</div>""", unsafe_allow_html=True)
    if col.button("자세히", key=f"pick_{sid}", width="stretch"):
        st.session_state["strait"] = sid
        st.rerun()

sid = st.session_state["strait"]
cur, e = STRAITS[sid], evals[sid]
lv = LEVELS[e["level"]]
reason_items = "".join(f"<li>{r['text']}" + (f" · <a href='{r['url']}' target='_blank'>출처</a>" if r.get("url") else "")
                       + "</li>" for r in e["reasons"])
st.markdown(f"""
<div class="banner" style="background:{lv['bg']}; border-color:{lv['color']}33;">
  <b style="font-size:1.05rem;">{lv['icon']} {cur['name']} — {lv['label']}</b>
  {'<ul>' + reason_items + '</ul>' if reason_items else
   f"<div style='color:#334155;font-size:0.9rem;margin-top:4px;'>{rules.headline(e)}</div>"}
</div>""", unsafe_allow_html=True)


# -------------------------------------------------------------
# ② 지도 + 추적 선박 + 대체 항로
# -------------------------------------------------------------
def arrows(fig, pts, color, n=4):
    """경로 위 진행 방향 화살표"""
    if len(pts) < 2:
        return
    idx = sorted({int(i * (len(pts) - 2) / max(n - 1, 1)) for i in range(n)})
    lat, lon, ang = [], [], []
    for i in idx:
        (a1, o1), (a2, o2) = pts[i], pts[i + 1]
        lat.append((a1 + a2) / 2)
        lon.append((o1 + o2) / 2)
        ang.append(voyages.bearing(a1, o1, a2, o2))
    fig.add_trace(go.Scattergeo(lat=lat, lon=lon, mode="markers", hoverinfo="skip", showlegend=False,
                                marker=dict(symbol="triangle-up", size=11, color=color, angle=ang, angleref="up",
                                            line=dict(width=1, color="white"))))


def strait_markers(fig, ids, highlight=None):
    for s_id in ids:
        s, l = STRAITS[s_id], LEVELS[evals[s_id]["level"]]
        fig.add_trace(go.Scattergeo(
            lat=[s["lat"]], lon=[s["lon"]], mode="markers+text", text=[s["name"]], textposition="top center",
            textfont=dict(color="#0f172a", size=12), hovertext=f"{s['name']}: {l['label']}", hoverinfo="text",
            marker=dict(size=22 if s_id == highlight else 16, color=l["color"], symbol="circle",
                        line=dict(width=2, color="white")), name=f"{s['name']} {l['label']}", showlegend=False))


def base_layout(fig, height=470, fit=True):
    fig.update_layout(
        geo=dict(projection_type="natural earth", showland=True, landcolor="#e2e8f0", showocean=True,
                 oceancolor="#f1f7fd", showcountries=True, countrycolor="#cbd5e1", coastlinecolor="#94a3b8",
                 showframe=False, bgcolor="rgba(0,0,0,0)", **({"fitbounds": "locations"} if fit else {})),
        paper_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=0, b=0), height=height,
        legend=dict(orientation="h", yanchor="top", y=-0.02, x=0, font=dict(color="#475569", size=12)))
    return fig


def route_label(sids):
    return " → ".join(STRAITS[s]["name"] for s in sids) or "감시 해협 없음"


map_col, info_col = st.columns([2.3, 1])
ok_ev = ev and not ev.get("error") and not ev.get("arrived")
with map_col:
    fig = go.Figure()
    if ok_ev:
        risky_ahead = any((s["level"] or 0) >= 1 for s in ev["straits"])
        track = db.get_tracks(voyage["mmsi"], 200) if voyage.get("mmsi") else []
        if len(track) >= 2:
            fig.add_trace(go.Scattergeo(lat=[t["lat"] for t in track], lon=[t["lon"] for t in track], mode="lines",
                                        line=dict(width=3, color="#94a3b8"), name="지나온 길(AIS)", hoverinfo="name"))
        if risky_ahead:
            for i, a in enumerate(ev["alternatives"][:2]):
                fig.add_trace(go.Scattergeo(lat=[p[0] for p in a["points"]], lon=[p[1] for p in a["points"]],
                                            mode="lines", line=dict(width=3, color=ALT_COLORS[i], dash="dash"),
                                            name=f"대체 {i + 1}: {a['label']} ({a['delta_days']:+.1f}일)",
                                            hoverinfo="name"))
        pts = ev["route_points"]
        fig.add_trace(go.Scattergeo(lat=[p[0] for p in pts], lon=[p[1] for p in pts], mode="lines",
                                    line=dict(width=5, color=BLUE), name="남은 항로", hoverinfo="name"))
        arrows(fig, pts, BLUE)
        strait_markers(fig, [s["id"] for s in ev["straits"]], sid)
        pos = ev.get("position")
        if ev.get("estimated") and pos:
            fig.add_trace(go.Scattergeo(lat=[pos["lat"]], lon=[pos["lon"]], mode="markers", hoverinfo="name",
                                        marker=dict(size=11, color="white", line=dict(width=2, color="#0f172a")),
                                        name=f"마지막 수신 위치 ({pos['seen_at'][5:16]})"))
        here = pts[0]
        fig.add_trace(go.Scattergeo(lat=[here[0]], lon=[here[1]], mode="markers+text", text=[voyage["ship_name"]],
                                    textposition="bottom center", textfont=dict(color="#0f172a", size=13),
                                    marker=dict(size=24, color="#0f172a", symbol="star", line=dict(width=2, color="white")),
                                    name="현재 위치" + (" (추정)" if ev.get("estimated") else ""), hoverinfo="name"))
        fig.add_trace(go.Scattergeo(lat=[here[0]], lon=[here[1]], mode="markers", hoverinfo="skip", showlegend=False,
                                    marker=dict(symbol="triangle-up", size=16, color="#f59e0b", angle=ev["heading"],
                                                angleref="up", line=dict(width=1, color="#0f172a"))))
        base_layout(fig)
    else:
        sample = SAMPLE_ROUTES.get(sid)
        if sample:
            r = find_route(*sample)
            fig.add_trace(go.Scattergeo(lat=[p[0] for p in r["points"]], lon=[p[1] for p in r["points"]],
                                        mode="lines", line=dict(width=4, color=BLUE),
                                        name=f"대표 항로: {sample[0]} → {sample[1]}", hoverinfo="name"))
            arrows(fig, [p[:2] for p in r["points"]], BLUE)
        strait_markers(fig, list(STRAITS), sid)
        base_layout(fig, fit=False)
    st.plotly_chart(fig, width="stretch", config={"displaylogo": False})

with info_col:
    if voyage and ev and ev.get("error"):
        st.error(f"계산 실패: {ev['error']}")
    elif voyage and ev and ev.get("arrived"):
        st.success(f"✓ {voyage['ship_name']}이(가) 도착항 근처에 있습니다. 사이드바에서 '운항 종료'를 누르세요.")
    elif ok_ev:
        pos = ev.get("position")
        if ev["source"] == "ais":
            where = f"AIS 수신 {pos['age_h']:g}시간 전"
        elif ev["source"] == "estimated":
            where = f"마지막 수신 {pos['age_h']:g}시간 전 → 속력으로 추정"
        else:
            where = ("AIS 위치가 오래돼 출발항 기준" if pos else "AIS 기록 없음 — 출발항 기준")
        straits_html = "".join(f"<div class='row'><span>{s['name']}</span>{pill(s['level'])}</div>"
                               for s in ev["straits"]) or "<div class='muted'>앞으로 지날 감시 해협 없음</div>"
        st.markdown(f"""
<div class="card"><h4>🚢 {voyage['ship_name']}</h4>
  <div class="muted">{voyage['origin']} → {voyage['dest']}</div>
  <div class="row"><span>남은 거리</span><b>약 {ev['distance_nm']:,}해리</b></div>
  <div class="row"><span>도착 예상</span><b>{ev['eta']} (약 {ev['days']}일)</b></div>
  <div class="row"><span>위치 기준</span><b>{where}</b></div>
  <div class="row"><span>진행 방향</span><b>{ev['heading']}°</b></div>
</div>
<div class="card"><h4>앞으로 지날 해협</h4>{straits_html}</div>""", unsafe_allow_html=True)
        risky = [s for s in ev["straits"] if (s["level"] or 0) >= 1]
        if risky and ev["alternatives"]:
            best = ev["alternatives"][0]
            st.markdown(f"""
<div class="card" style="border-color:#fdba74;"><h4>🧭 대체 항로 추천</h4>
  <div class="big">{best['label']}</div>
  <div class="muted">약 {best['distance_nm']:,}해리 · {best['days']}일 (<b>{best['delta_days']:+.1f}일</b>)<br>
  지나는 해협: {", ".join(f"{s['name']} {LEVELS[s['level']]['label']}" for s in best['straits']) or '감시 해협 없음'}<br>
  이유: {risky[0]['name']} {LEVELS[risky[0]['level']]['label']} — {risky[0]['reason']}</div>
</div>""", unsafe_allow_html=True)
        elif risky:
            st.warning("위험 해협을 피하는 대체 항로를 항로망에서 찾지 못했습니다.")
        else:
            st.markdown("<div class='card'><h4>✓ 현재 항로 유지</h4><div class='muted'>앞으로 지날 해협이 모두 "
                        "정상입니다.</div></div>", unsafe_allow_html=True)
    else:
        st.markdown("""
<div class="card"><h4>🚢 선박을 등록해 보세요</h4>
  <div class="muted">사이드바에서 선박명 또는 MMSI와 출발·도착항을 넣으면<br>
  · 현재 위치와 진행 방향, 남은 항로<br>· 앞으로 지날 해협의 신호등<br>· 위험할 때 대체 항로와 경보 메일<br>
  을 자동으로 보여 드립니다.</div></div>""", unsafe_allow_html=True)
        sample = SAMPLE_ROUTES.get(sid)
        if sample and (e["level"] or 0) >= 1:
            alt = find_route(*sample, banned_straits=[sid])
            base_r = find_route(*sample)
            if alt:
                st.markdown(f"""
<div class="card" style="border-color:#fdba74;"><h4>🧭 대표 항로 기준 대체 항로</h4>
  <div class="muted">{sample[0]} → {sample[1]} ({route_label(base_r['straits'])})</div>
  <div class="big">{voyages._alt_label(alt)}</div>
  <div class="muted">{alt['distance_nm']:,}해리 (현재 항로 {base_r['distance_nm']:,}해리,
  {alt['distance_nm'] - base_r['distance_nm']:+,}해리)</div></div>""", unsafe_allow_html=True)

# -------------------------------------------------------------
# ③ 관련 뉴스 (원래 기능 유지)
# -------------------------------------------------------------
st.markdown(f"### 📰 관련 뉴스 · {cur['name']}")
news = fetch_news(cur["news_keyword"])
if news is None:
    st.caption("NewsAPI 키가 설정되지 않았습니다.")
elif isinstance(news, dict):
    st.caption(f"뉴스를 가져오지 못했습니다: {news['error']}")
elif not news:
    st.caption("관련 뉴스가 없습니다.")
else:
    b = summarize_news(news)
    st.markdown(f"""<div class="card"><div class="muted">최근 기사 <b>{b['count']}건</b> (출처 {b['sources']}곳) 종합:
        주로 <b style='color:#d97706'>{b['issues']}</b> 관련 보도</div></div>""", unsafe_allow_html=True)
    ncols = st.columns(2)
    for i, n in enumerate(news):
        ncols[i % 2].markdown(f"""
<div class="news-card"><a href="{n['link']}" target="_blank" style="color:#0f172a;font-size:0.95rem;">{n['title']}</a>
<div style="color:#64748b;font-size:0.8rem;margin-top:4px;">📰 {n['source']} · {n['date']} · {(n['desc'] or '')[:90]}…</div>
</div>""", unsafe_allow_html=True)

# -------------------------------------------------------------
# ④ 판단 근거 · 기록 · 대체 항로 비교
# -------------------------------------------------------------
st.markdown(f"### 🔎 왜 이 색인가 · {cur['name']}")
L = e.get("layers", {})
c1, c2, c3, c4 = st.columns(4)


def card(col, title, body):
    col.markdown(f"<div class='card' style='min-height:190px'><h4>{title}</h4>{body}</div>", unsafe_allow_html=True)


off = L.get("official")
if off is None:
    card(c1, "① 공식 판단", "<div class='muted'>꺼짐</div>")
else:
    def official_row(it):
        stale = " · <b>갱신 필요</b>" if it["stale"] else ""
        link = f" · <a href='{it['url']}' target='_blank'>출처</a>" if it.get("url") else ""
        note = " · 판단에는 쓰지 않음(지정 유지)" if it.get("context") else ""
        return (f"<div class='row'><span>{it['name']}</span><span>{it['value']}{stale}</span></div>"
                f"<div class='muted'>{it['date'] or ''}{link}{note}</div>")
    rows = "".join(official_row(it) for it in off["items"]) or "<div class='muted'>현재 등록된 공식 경보 없음</div>"
    card(c1, "① 공식 판단", rows + "<div class='muted' style='margin-top:6px'>미국 MSCI · JMIC/UKMTO · Lloyd's JWC "
                                   "(official_status.toml 에서 직접 관리)</div>")

nw = L.get("news")
if nw is None:
    card(c2, "② 뉴스 사건", "<div class='muted'>꺼짐</div>")
elif not nw["available"]:
    card(c2, "② 뉴스 사건", f"<div class='muted'>{nw['note']}</div>")
else:
    card(c2, "② 뉴스 사건", f"""<div class='big'>평소의 {nw['ratio'] if nw['ratio'] is not None else '-'}배
      <span class='muted'>(주의 기준 {th['news_ratio']:g}배)</span></div>
      <div class='row'><span>최근 {nw['avg_days']}일 하루 평균</span><b>{nw['avg']:g}건</b></div>
      <div class='row'><span>평소 (그 전 {nw['baseline_days']}일 중앙값)</span><b>{nw['median']:g}건</b></div>
      <div class='row'><span>최근 24시간</span><b>{nw['events']:g}건</b></div>
      <div class='muted'>GDELT: 해협 {cur['radius_km']}km 안, 위치가 확인된 위협·공격·봉쇄 사건.
      2023 홍해 사태 소급 검증에서 나포 26일 전 첫 경고</div>""")

tr = L.get("traffic")
if tr is None:
    card(c3, "③ 실제 통항량", "<div class='muted'>꺼짐</div>")
elif not tr.get("available") and "recent_avg" not in tr:
    card(c3, "③ 실제 통항량", f"<div class='muted'>{tr.get('note', '데이터 없음')}</div>")
else:
    card(c3, "③ 실제 통항량", f"""<div class='big'>{tr['change_pct']:+.0f}% <span class='muted'>작년 같은 시기 대비</span></div>
      <div class='row'><span>최근 7일 하루 평균</span><b>{tr['recent_avg']:g}척</b></div>
      <div class='row'><span>작년 같은 7일</span><b>{tr['base_avg']:g}척</b></div>
      <div class='muted'>{tr.get('note', '')} {tr['latest_date']}까지 (주 1회 갱신) ·
      <a href='https://portwatch.imf.org' target='_blank'>IMF PortWatch</a></div>""")

ds = L.get("disaster")
if ds is None:
    card(c4, "④ 운항 불가 재해", "<div class='muted'>꺼짐</div>")
elif not ds["available"]:
    card(c4, "④ 운항 불가 재해", "<div class='muted'>재해 경보를 가져오지 못했습니다</div>")
else:
    body = "".join(f"<div class='row'><span>{h['name']}</span>{pill(2 if h['alert'] == 'Red' else 1, h['alert'])}</div>"
                   f"<div class='muted'>해협에서 {h['km']}km</div>" for h in ds["hits"])
    card(c4, "④ 운항 불가 재해", (body or "<div class='muted'>해협 근처 태풍·쓰나미 경보 없음</div>") +
         "<div class='muted' style='margin-top:6px'>GDACS (EU·UN 재난경보) Orange·Red만 반영. "
         "일반 파도·바람은 보지 않음</div>")

g1, g2 = st.columns(2)
with g1:
    st.markdown("##### 뉴스 사건 수 (하루 단위, 최근 30일)")
    raw = (statuses[sid] or {}).get("data", {}).get("raw", {})
    w = list(reversed((raw.get("news_windows") or [])[:30]))
    if any(x is not None for x in w):
        f2 = go.Figure(go.Bar(x=[f"-{len(w) - 1 - i}일" for i in range(len(w))], y=w, marker_color="#93c5fd",
                              name="갈등 사건 수"))
        if nw and nw.get("available"):
            f2.add_hline(y=nw["median"], line=dict(color="#94a3b8", dash="dot"),
                         annotation_text=f"평소 {nw['median']:g}건", annotation_position="bottom left")
            f2.add_hline(y=nw["threshold"], line=dict(color="#f59e0b", dash="dash"),
                         annotation_text=f"주의 기준(7일 평균) {nw['threshold']:g}건", annotation_position="top left")
        f2.update_layout(height=230, margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor="rgba(0,0,0,0)",
                         plot_bgcolor="rgba(0,0,0,0)", yaxis=dict(gridcolor="#e2e8f0"), showlegend=False)
        st.plotly_chart(f2, width="stretch", config={"displaylogo": False})
    else:
        st.caption("수집된 기록이 아직 없습니다.")
with g2:
    st.markdown("##### 하루 통항 척수 (최근 120일 · 작년 같은 시기)")
    series = load_traffic(cur["portwatch"])
    if series:
        by = dict(series)
        recent = series[-120:]
        last_year = [by.get((date.fromisoformat(d) - timedelta(days=364)).isoformat()) for d, _ in recent]
        f3 = go.Figure()
        f3.add_trace(go.Scatter(x=[d for d, _ in recent], y=last_year, mode="lines", name="작년 같은 시기",
                                line=dict(color="#cbd5e1", width=2)))
        f3.add_trace(go.Scatter(x=[d for d, _ in recent], y=[n for _, n in recent], mode="lines", name="올해",
                                line=dict(color=BLUE, width=2.5)))
        f3.update_layout(height=230, margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor="rgba(0,0,0,0)",
                         plot_bgcolor="rgba(0,0,0,0)", yaxis=dict(gridcolor="#e2e8f0"),
                         legend=dict(orientation="h", y=1.1, x=0))
        st.plotly_chart(f3, width="stretch", config={"displaylogo": False})
    else:
        st.caption("통항 데이터가 아직 없습니다.")

hist = load_history(sid)
if hist:
    st.markdown("##### 신호등 기록 (최근 30일, 기본 기준)")
    f4 = go.Figure(go.Scatter(x=[h["computed_at"] for h in hist], y=[h["level"] for h in hist], mode="lines",
                              line=dict(shape="hv", color="#0f172a", width=2)))
    f4.update_layout(height=170, margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor="rgba(0,0,0,0)",
                     plot_bgcolor="rgba(0,0,0,0)",
                     yaxis=dict(tickvals=[0, 1, 2], ticktext=["정상", "주의", "심각"], range=[-0.3, 2.3],
                                gridcolor="#e2e8f0"))
    st.plotly_chart(f4, width="stretch", config={"displaylogo": False})

if ok_ev and ev["alternatives"]:
    st.markdown("##### 대체 항로 비교")
    rows = [{"항로": "현재 항로", "거리(해리)": f"{ev['distance_nm']:,}", "남은 일수": ev["days"], "차이": "기준",
             "지나는 해협": ", ".join(f"{LEVELS[s['level']]['icon']} {s['name']}" for s in ev["straits"]) or "없음"}]
    rows += [{"항로": a["label"], "거리(해리)": f"{a['distance_nm']:,}", "남은 일수": a["days"],
              "차이": f"{a['delta_days']:+.1f}일",
              "지나는 해협": ", ".join(f"{LEVELS[s['level']]['icon']} {s['name']}" for s in a["straits"]) or "없음"}
             for a in ev["alternatives"]]
    st.dataframe(rows, hide_index=True, width="stretch")
    st.caption("거리는 주요 항로를 단순화한 항로망 기준 근사값, 일수 = 거리 ÷ (평균 속력 × 24). 운하 통항료·보험료는 포함하지 않습니다.")

st.caption("이 도구는 위험을 맞힌다는 보장이 아니라, 평소와 다른 움직임을 먼저 알려 주는 조기 경보입니다. "
           "사전 정보가 없는 단발성 사건은 미리 잡을 수 없습니다.")
