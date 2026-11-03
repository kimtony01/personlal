"""해상 항로 조기경보 — Streamlit 화면

수집·판단·메일은 GitHub Actions 가 30분마다 monitor.py 로 실행하고 결과를 DB(Neon)에 저장합니다.
이 화면은 저장된 결과를 읽어 보여 주고, 선박 등록과 신호등 기준 조절만 처리합니다.
"""
import math
import os
import tomllib
from datetime import date, datetime, timedelta
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
    .stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin: 12px 0; }
    .stats div { background: #f8fafc; border-radius: 10px; padding: 8px 10px; }
    .stats span { display: block; color: #64748b; font-size: 0.72rem; }
    .stats b { color: #0f172a; font-size: 0.95rem; }
    .card .pill { margin: 2px 4px 2px 0; }
    .card.rec { border-color: #fdba74; background: #fffbf5; }
    .card.ok { border-color: #bbf7d0; background: #f7fef9; }
    .tile { background: #fff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 12px 14px; min-height: 104px; }
    .tile .big { color: #0f172a; font-weight: 800; font-size: 1.35rem; margin: 2px 0; }
    .tile .muted { color: #64748b; font-size: 0.78rem; }
    .news-item { padding: 8px 0; border-bottom: 1px solid #f1f5f9; }
    .news-item:last-child { border-bottom: none; }
    .news-item a { color: #0f172a !important; font-size: 0.93rem; }
    .news-item .muted { color: #64748b; font-size: 0.78rem; margin-top: 2px; }
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
def fetch_news(query, display=8):
    api_key = os.getenv("NEWSAPI_KEY")
    if not api_key:
        return None
    try:
        res = requests.get("https://newsapi.org/v2/everything", timeout=8, params={
            "q": query, "searchIn": "title,description", "language": "en", "sortBy": "publishedAt",
            "pageSize": display, "apiKey": api_key})
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
if st.session_state.get("voyage_id", "unset") != sel_vid:
    st.session_state["strait_clicked"] = False   # 다른 배를 고르면 그 배의 항로 기준으로 다시
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
  <div class="sig-why">{why if len(why) < 46 else why[:44] + '…'}</div>
</div>""", unsafe_allow_html=True)
    if col.button("자세히", key=f"pick_{sid}", width="stretch"):
        st.session_state["strait"] = sid
        st.session_state["strait_clicked"] = True
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
        mid = voyages._interp((a1, o1), (a2, o2), 0.5)
        lat.append(mid[0])
        lon.append(mid[1])
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


def unwrap_lons(lons):
    """날짜변경선을 넘을 때 경도가 -180/180 에서 끊기지 않게 이어 붙임 (예: 170, -175 → 170, 185)"""
    out = [lons[0]]
    for x in lons[1:]:
        d = (x - out[-1] + 180) % 360 - 180
        out.append(out[-1] + d)
    return out


def view_bounds(lines, pad=0.12, aspect=2.0):
    """보여 줄 범위: (중심 경도, 경도 범위, 위도 범위). lines = 선마다 [(lat, lon), ...]

    날짜변경선을 넘는 항로도 한 덩어리로 이어 계산. 지구 반 바퀴를 넘으면 세계 지도(범위 None)
    """
    ref = lines[0][0][1]
    lats, lons = [], []
    for line in lines:
        ul = unwrap_lons([p[1] for p in line])
        shift = round((ref - ul[0]) / 360) * 360   # 각 선의 시작을 기준 경도 근처로
        lons += [x + shift for x in ul]
        lats += [p[0] for p in line]
    lon0, lon1 = min(lons), max(lons)
    if lon1 - lon0 > 200:
        main = unwrap_lons([p[1] for p in lines[0]])
        return (min(main) + max(main)) / 2, None, None
    lat0, lat1 = min(lats), max(lats)
    dlon = max(lon1 - lon0, 12) * (1 + 2 * pad)
    dlat = max(lat1 - lat0, 8) * (1 + 2 * pad)
    dlat = max(dlat, dlon / aspect)          # 화면 비율에 맞춰 위도 범위를 넓힘 (가로로 납작해지지 않게)
    dlon = max(dlon, dlat * aspect * 0.8)
    clat, clon = (lat0 + lat1) / 2, (lon0 + lon1) / 2
    lat_rng = [max(clat - dlat / 2, -75), min(clat + dlat / 2, 85)]
    return clon, [clon - dlon / 2, clon + dlon / 2], lat_rng


def ship_shape(lat, lon, heading, pts):
    """진행 방향으로 회전한 작은 배 모양(뾰족한 뱃머리) 꼭짓점. 크기는 지도에 보이는 항로 범위에 맞춤"""
    _, lon_rng, lat_rng = view_bounds([pts])
    span = 140 if lon_rng is None else max(lat_rng[1] - lat_rng[0],
                                            (lon_rng[1] - lon_rng[0]) * math.cos(math.radians(lat)), 3)
    size = span * 0.013
    h = math.radians(heading)
    fwd, right = (math.sin(h), math.cos(h)), (math.cos(h), -math.sin(h))   # (동, 북) 단위 벡터
    hull = [(2.2, 0), (0.9, 0.42), (-1.1, 0.42), (-1.3, 0), (-1.1, -0.42), (0.9, -0.42), (2.2, 0)]   # (앞, 옆) 뾰족한 뱃머리
    out_lat, out_lon = [], []
    for x, y in hull:
        east, north = x * fwd[0] + y * right[0], x * fwd[1] + y * right[1]
        out_lat.append(lat + north * size)
        out_lon.append(lon + east * size / max(math.cos(math.radians(lat)), 0.2))
    return out_lat, out_lon


def base_layout(fig, height=470, lines=None):
    """lines 를 주면 그 범위로 확대 (fitbounds 는 날짜변경선을 넘는 항로에서 지도를 반으로 갈라서 직접 계산)"""
    view = {}
    if lines:
        center, lon_rng, lat_rng = view_bounds(lines)
        view = {"projection_rotation": {"lon": center}}
        if lon_rng:
            view |= {"lonaxis": {"range": lon_rng}, "lataxis": {"range": lat_rng}}
    fig.update_layout(
        geo=dict(projection_type="natural earth", resolution=50, showland=True, landcolor="#e5e7eb",
                 showocean=True, oceancolor="#eef6fd", showlakes=True, lakecolor="#eef6fd",
                 showcountries=True, countrycolor="#cbd5e1", countrywidth=0.6,
                 showcoastlines=True, coastlinecolor="#64748b", coastlinewidth=0.7,
                 showframe=False, bgcolor="rgba(0,0,0,0)", **view),
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
        live = ev["source"] != "origin"
        label = {"ais": "현재 위치(AIS)", "estimated": "현재 위치(추정)", "origin": "출발항 기준(위치 미수신)"}[ev["source"]]
        hull_lat, hull_lon = ship_shape(here[0], here[1], ev["heading"], pts)
        # 실제 위치 = 진한 배, 위치를 아직 못 받음(출발항 기준) = 흰 배에 진한 테두리
        fig.add_trace(go.Scattergeo(lat=hull_lat, lon=hull_lon, mode="lines", fill="toself",
                                    fillcolor="#0f172a" if live else "#ffffff",
                                    line=dict(width=1.5 if live else 2.5, color="#ffffff" if live else "#0f172a"),
                                    name=label, hoverinfo="name"))
        label_lat = max(hull_lat) + (max(hull_lat) - min(hull_lat)) * 0.6   # 배와 겹치지 않게 위로 띄움
        fig.add_trace(go.Scattergeo(lat=[label_lat], lon=[here[1]], mode="text", text=[voyage["ship_name"]],
                                    textposition="top center", textfont=dict(color="#0f172a", size=12),
                                    hoverinfo="skip", showlegend=False))
        lines = [[tuple(p[:2]) for p in pts]]
        if len(track) >= 2:
            lines.append([(t["lat"], t["lon"]) for t in track])
        for a in (ev["alternatives"][:2] if risky_ahead else []):
            lines.append([tuple(p[:2]) for p in a["points"]])
        base_layout(fig, lines=lines)
    else:
        sample = SAMPLE_ROUTES.get(sid)
        if sample:
            r = find_route(*sample)
            fig.add_trace(go.Scattergeo(lat=[p[0] for p in r["points"]], lon=[p[1] for p in r["points"]],
                                        mode="lines", line=dict(width=4, color=BLUE),
                                        name=f"대표 항로: {sample[0]} → {sample[1]}", hoverinfo="name"))
            arrows(fig, [p[:2] for p in r["points"]], BLUE)
        strait_markers(fig, list(STRAITS), sid)
        base_layout(fig)
    st.plotly_chart(fig, width="stretch", config={"displaylogo": False})

with info_col:
    if voyage and ev and ev.get("error"):
        st.error(f"계산 실패: {ev['error']}")
    elif voyage and ev and ev.get("arrived"):
        st.success(f"✓ {voyage['ship_name']}이(가) 도착항 근처에 있습니다. 사이드바에서 '운항 종료'를 누르세요.")
    elif ok_ev:
        pos = ev.get("position")
        where = {"ais": "실시간", "estimated": "추정 위치", "origin": "출발항 기준"}[ev["source"]]
        ahead = " ".join(f"{pill(s['level'], s['name'])}" for s in ev["straits"]) or \
            "<span class='muted'>감시 해협 없음</span>"
        st.markdown(f"""
<div class="card"><h4>🚢 {voyage['ship_name']}</h4>
  <div class="muted">{voyage['origin']} → {voyage['dest']}</div>
  <div class="stats">
    <div><span>남은 거리</span><b>{ev['distance_nm']:,}해리</b></div>
    <div><span>도착 예상</span><b>{ev['eta'][5:]}</b></div>
    <div><span>위치</span><b>{where}</b></div>
  </div>
  <div class="muted" style="margin-bottom:4px">앞으로 지날 해협</div>{ahead}
</div>""", unsafe_allow_html=True)
        risky = [s for s in ev["straits"] if (s["level"] or 0) >= 1]
        if risky and ev["alternatives"]:
            best = ev["alternatives"][0]
            st.markdown(f"""<div class="card rec"><span class="muted">🧭 대체 항로 추천</span>
  <div class="big">{best['label']}</div><div class="muted">{best['delta_days']:+.1f}일 · {risky[0]['name']}
  {LEVELS[risky[0]['level']]['label']} 회피</div></div>""", unsafe_allow_html=True)
        elif risky:
            st.warning("위험 해협을 피하는 대체 항로를 찾지 못했습니다.")
        else:
            st.markdown("<div class='card ok'><b>✓ 현재 항로 유지</b> <span class='muted'>· 앞으로 지날 해협 모두 정상"
                        "</span></div>", unsafe_allow_html=True)
        with st.expander("자세히 보기"):
            if ev["source"] == "ais":
                loc = f"AIS 수신 {pos['age_h']:g}시간 전 ({pos['seen_at'][5:16]})"
            elif ev["source"] == "estimated":
                loc = f"마지막 수신 {pos['age_h']:g}시간 전 위치에서 속력으로 추정"
            else:
                loc = ("AIS 위치가 오래돼 출발항 기준으로 계산" if pos else
                       "아직 무료 AIS에 신호가 잡히지 않아 출발항 기준으로 계산 (잡히면 자동으로 실제 위치로 바뀜)")
            st.markdown(f"""<div class="row"><span>위치</span><b>{loc}</b></div>
<div class="row"><span>남은 거리 · 일수</span><b>약 {ev['distance_nm']:,}해리 · {ev['days']}일 ({ev['eta']} 도착)</b></div>
<div class="row"><span>진행 방향</span><b>{ev['heading']}°</b></div>
<div class="row"><span>평균 속력</span><b>{voyage['speed_kn']}노트</b></div>
<div class="row"><span>MMSI</span><b>{voyage['mmsi'] or '없음'}</b></div>
<div class="row"><span>경보 메일</span><b>{voyage['recipients'] or '없음'}</b></div>""", unsafe_allow_html=True)
            for s in risky:
                st.caption(f"{LEVELS[s['level']]['icon']} {s['name']}: {s['reason']}")
            if ev["alternatives"]:
                rows = [{"항로": "현재 항로", "일수": ev["days"], "차이": "기준",
                         "해협": " ".join(f"{LEVELS[s['level']]['icon']}{s['name']}" for s in ev["straits"]) or "없음"}]
                rows += [{"항로": a["label"], "일수": a["days"], "차이": f"{a['delta_days']:+.1f}일",
                          "해협": " ".join(f"{LEVELS[s['level']]['icon']}{s['name']}" for s in a["straits"]) or "없음"}
                         for a in ev["alternatives"]]
                st.dataframe(rows, hide_index=True, width="stretch")
                st.caption("거리·일수는 항로망 기준 근사값 (운하 통항료·보험료 미포함)")
    else:
        st.markdown("""<div class="card"><h4>🚢 내 선박 추적</h4>
  <div class="muted">사이드바 <b>➕ 선박 등록</b>에서 MMSI와 출발·도착항을 넣으면 위치·남은 항로·대체 항로가
  여기에 나옵니다.</div></div>""", unsafe_allow_html=True)
        sample = SAMPLE_ROUTES.get(sid)
        if sample and (e["level"] or 0) >= 1:
            alt, base_r = find_route(*sample, banned_straits=[sid]), find_route(*sample)
            if alt:
                st.markdown(f"""<div class="card rec"><span class="muted">🧭 예: {sample[0]} → {sample[1]}</span>
  <div class="big">{voyages._alt_label(alt)}</div>
  <div class="muted">{alt['distance_nm'] - base_r['distance_nm']:+,}해리 · {cur['name']} 회피</div></div>""",
                            unsafe_allow_html=True)

# -------------------------------------------------------------
# ③ 관련 뉴스 — 선박을 추적 중이면 그 배가 앞으로 지날 해협의 뉴스만, 아니면 위에서 고른 해협
# -------------------------------------------------------------
def news_item(n, desc=False):
    d = f"<div class='muted'>{n['desc']}</div>" if desc and n.get("desc") else ""
    return (f"<div class='news-item'><a href='{n['link']}' target='_blank'>{n['title']}</a>"
            f"<div class='muted'>{n['source']} · {n['date']}</div>{d}</div>")


def show_news(s_id, title):
    st.markdown(f"#### 📰 {title}")
    news = fetch_news(STRAITS[s_id]["news_keyword"])
    if news is None:
        st.caption("NewsAPI 키가 설정되지 않았습니다.")
    elif isinstance(news, dict):
        st.caption(f"뉴스를 가져오지 못했습니다: {news['error']}")
    elif not news:
        st.caption("최근 관련 뉴스가 없습니다.")
    else:
        b = summarize_news(news)
        st.caption(f"최근 {b['count']}건 · 주로 {b['issues']} 관련 보도")
        st.markdown("<div class='card'>" + "".join(news_item(n) for n in news[:3]) + "</div>",
                    unsafe_allow_html=True)
        if len(news) > 3:
            with st.expander(f"뉴스 더 보기 ({len(news) - 3}건)"):
                st.markdown("".join(news_item(n, desc=True) for n in news[3:]), unsafe_allow_html=True)


if ok_ev:
    if ev["straits"]:
        for s in ev["straits"]:
            show_news(s["id"], f"{voyage['ship_name']} 항로 뉴스 · {s['name']} {LEVELS[s['level']]['icon']}")
    else:
        st.caption(f"📰 {voyage['ship_name']}의 남은 항로에는 감시 해협이 없어 관련 뉴스를 표시하지 않습니다.")
elif not voyage:
    show_news(sid, f"관련 뉴스 · {cur['name']}")

# -------------------------------------------------------------
# ④ 판단 근거 (요약 → 자세히 보기) — 선박을 추적 중이면 그 배가 앞으로 지날 해협만
# -------------------------------------------------------------
def evidence(sid):
    cur, e = STRAITS[sid], evals[sid]
    L = e.get("layers", {})
    contrib = {}
    for r in e["reasons"]:
        contrib[r["layer"]] = max(contrib.get(r["layer"], 0), r["level"])


    def tile(col, key, title, value, sub):
        lv = contrib.get(key, 0) if key in L else None
        color = LEVELS[lv]["color"] if lv else "#e2e8f0"
        col.markdown(f"""<div class="tile" style="border-left:4px solid {color}">
      <div class="muted">{title}</div><div class="big">{value}</div><div class="muted">{sub}</div></div>""",
                     unsafe_allow_html=True)


    off, nw, tr, ds = L.get("official"), L.get("news"), L.get("traffic"), L.get("disaster")
    c1, c2, c3, c4 = st.columns(4)
    if off is None:
        tile(c1, "official", "① 공식 경보", "꺼짐", "")
    else:
        active_items = [it for it in off["items"] if it["level"] and not it["stale"]]
        stale = sum(1 for it in off["items"] if it["stale"])
        tile(c1, "official", "① 공식 경보", active_items[0]["value"] if active_items else "없음",
             f"갱신 필요 {stale}건" if stale else ("전쟁위험 지정 해역" if off["items"] else "등록된 발표 없음"))
    if nw is None:
        tile(c2, "news", "② 뉴스 사건", "꺼짐", "")
    elif not nw["available"]:
        tile(c2, "news", "② 뉴스 사건", "-", nw["note"])
    else:
        tile(c2, "news", "② 뉴스 사건", f"{nw['ratio']}배" if nw["ratio"] else f"{nw['avg']:g}건",
             f"평소 대비 · 주의 기준 {th['news_ratio']:g}배")
    if tr is None:
        tile(c3, "traffic", "③ 실제 통항량", "꺼짐", "")
    elif "recent_avg" not in tr:
        tile(c3, "traffic", "③ 실제 통항량", "-", tr.get("note", "데이터 없음"))
    else:
        tile(c3, "traffic", "③ 실제 통항량", f"{tr['change_pct']:+.0f}%",
             "작년 같은 시기 대비" if tr.get("available") else "통항이 적어 판단 제외")
    if ds is None:
        tile(c4, "disaster", "④ 운항 불가 재해", "꺼짐", "")
    else:
        tile(c4, "disaster", "④ 운항 불가 재해", f"{len(ds['hits'])}건" if ds["hits"] else "없음",
             "태풍·쓰나미 경보 (GDACS)" if ds["available"] else "경보를 가져오지 못함")

    with st.expander("자세히 보기 — 근거 상세 · 그래프 · 기록"):
        d1, d2 = st.columns(2)
        with d1:
            st.markdown("**① 공식 경보** · 직접 관리하는 표 (official_status.toml)")
            for it in (off or {}).get("items", []):
                tag = " · 갱신 필요(판단 제외)" if it["stale"] else (" · 지정 유지(판단 제외)" if it.get("context") else "")
                link = f" · [출처]({it['url']})" if it.get("url") else ""
                st.markdown(f"- {it['name']}: **{it['value']}** ({it['date'] or '-'}){tag}{link}")
            if not (off or {}).get("items"):
                st.caption("등록된 발표 없음")
            st.markdown("**④ 운항 불가 재해** · GDACS Orange·Red만, 일반 파도·바람은 보지 않음")
            for h in (ds or {}).get("hits", []):
                st.markdown(f"- {h['name']} **{h['alert']}** · 해협에서 {h['km']}km")
            if not (ds or {}).get("hits"):
                st.caption("해협 근처 경보 없음")
        with d2:
            if nw and nw.get("available"):
                st.markdown(f"**② 뉴스 사건** · 최근 {nw['avg_days']}일 하루 평균 **{nw['avg']:g}건**, "
                            f"평소(그 전 {nw['baseline_days']}일 중앙값) **{nw['median']:g}건**")
            st.caption(f"GDELT: 해협 {cur['radius_km']}km 안, 위치가 확인된 위협·공격·봉쇄 사건. "
                       "2023 홍해 사태 소급 검증에서 Galaxy Leader 나포 26일 전 첫 경고")
            if tr and "recent_avg" in tr:
                st.markdown(f"**③ 실제 통항량** · 최근 7일 하루 **{tr['recent_avg']:g}척**, "
                            f"작년 같은 7일 **{tr['base_avg']:g}척** ({tr['latest_date']}까지)")
            st.caption("IMF PortWatch 위성 AIS, 주 1회 갱신 — 사건 뒤에 켜지는 '확인' 지표")

        chart = dict(height=210, margin=dict(l=10, r=10, t=30, b=10), paper_bgcolor="rgba(0,0,0,0)",
                     plot_bgcolor="rgba(0,0,0,0)", yaxis=dict(gridcolor="#e2e8f0"), font=dict(size=11))
        g1, g2 = st.columns(2)
        with g1:
            raw = (statuses[sid] or {}).get("data", {}).get("raw", {})
            w = list(reversed((raw.get("news_windows") or [])[:30]))
            if any(x is not None for x in w):
                end = datetime.strptime(statuses[sid]["computed_at"][:10], "%Y-%m-%d").date()
                xs = [(end - timedelta(days=len(w) - 1 - i)).strftime("%m/%d") for i in range(len(w))]
                f2 = go.Figure(go.Bar(x=xs, y=w, marker_color="#93c5fd"))
                if nw and nw.get("available"):
                    f2.add_hline(y=nw["median"], line=dict(color="#94a3b8", dash="dot"),
                                 annotation_text="평소", annotation_position="bottom left")
                    f2.add_hline(y=nw["threshold"], line=dict(color="#f59e0b", dash="dash"),
                                 annotation_text="주의 기준", annotation_position="top left")
                f2.update_layout(title=dict(text="뉴스 사건 수 (하루)", font=dict(size=13)), showlegend=False,
                                 xaxis=dict(nticks=8, tickangle=0), **chart)
                st.plotly_chart(f2, width="stretch", config={"displaylogo": False})
        with g2:
            series = load_traffic(cur["portwatch"])
            if series:
                by, recent = dict(series), series[-120:]
                last_year = [by.get((date.fromisoformat(d) - timedelta(days=364)).isoformat()) for d, _ in recent]
                f3 = go.Figure()
                f3.add_trace(go.Scatter(x=[d for d, _ in recent], y=last_year, mode="lines", name="작년",
                                        line=dict(color="#cbd5e1", width=2)))
                f3.add_trace(go.Scatter(x=[d for d, _ in recent], y=[n for _, n in recent], mode="lines", name="올해",
                                        line=dict(color=BLUE, width=2.5)))
                f3.update_layout(title=dict(text="하루 통항 척수", font=dict(size=13)),
                                 legend=dict(orientation="h", y=1.15, x=0.6), **chart)
                st.plotly_chart(f3, width="stretch", config={"displaylogo": False})

        hist = load_history(sid)
        if hist:
            f4 = go.Figure(go.Scatter(x=[h["computed_at"] for h in hist], y=[h["level"] for h in hist], mode="lines",
                                      line=dict(shape="hv", color="#0f172a", width=2)))
            f4.update_layout(title=dict(text="신호등 기록 (최근 30일)", font=dict(size=13)), height=170,
                             margin=dict(l=10, r=10, t=30, b=10), paper_bgcolor="rgba(0,0,0,0)",
                             plot_bgcolor="rgba(0,0,0,0)", font=dict(size=11),
                             yaxis=dict(tickvals=[0, 1, 2], ticktext=["정상", "주의", "심각"], range=[-0.3, 2.3],
                                        gridcolor="#e2e8f0"))
            st.plotly_chart(f4, width="stretch", config={"displaylogo": False})


if ok_ev:
    show_ids = [s["id"] for s in ev["straits"]]
    # 위 신호등 카드에서 '자세히'를 직접 누른 해협은 항로에 없어도 보여 줌
    if st.session_state.get("strait_clicked") and sid not in show_ids:
        show_ids = [sid] + show_ids
elif voyage:
    show_ids = []
else:
    show_ids = [sid]

if not show_ids:
    if ok_ev:
        st.caption(f"🔎 {voyage['ship_name']}의 남은 항로에는 감시 해협이 없습니다. "
                   "다른 해협의 근거는 위 신호등 카드의 '자세히'를 누르면 볼 수 있습니다.")
elif len(show_ids) == 1:
    st.markdown(f"#### 🔎 판단 근거 · {STRAITS[show_ids[0]]['name']}")
    evidence(show_ids[0])
else:
    st.markdown(f"#### 🔎 판단 근거 · {voyage['ship_name']} 항로")
    for tab, s_id in zip(st.tabs([f"{LEVELS[evals[x]['level']]['icon']} {STRAITS[x]['name']}" for x in show_ids]),
                         show_ids):
        with tab:
            evidence(s_id)

st.caption("조기 경보 도구입니다. 평소와 다른 움직임을 먼저 알려 주지만, 사전 정보가 없는 단발성 사건은 미리 잡을 수 없습니다.")
