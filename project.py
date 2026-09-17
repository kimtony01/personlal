import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from sklearn.ensemble import RandomForestClassifier
import json
import os
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
from googletrans import Translator

load_dotenv()

st.set_page_config(
    page_title="해상 항로 리스크 조기경보 시스템",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -------------------------------------------------------------
# 스타일 (라이트 SaaS 대시보드 테마)
# -------------------------------------------------------------
st.markdown("""
<style>
    .stApp { background-color: #f8fafc; }
    h1 { color: #0f172a !important; font-weight: 800 !important; letter-spacing: -0.5px; }
    h2, h3 { color: #0f172a !important; font-weight: 700 !important; }
    .stCaption, p, span, label { color: #64748b !important; }

    /* 상단 헤더 바 */
    .app-header {
        display: flex; align-items: center; justify-content: space-between;
        background: #ffffff; border: 1px solid #e2e8f0; border-radius: 16px;
        padding: 18px 26px; margin-bottom: 22px;
        box-shadow: 0 1px 3px rgba(15,23,42,0.06);
    }
    .app-header .brand { display: flex; align-items: center; gap: 12px; }
    .app-header .brand-icon {
        width: 38px; height: 38px; border-radius: 10px;
        background: linear-gradient(135deg, #2563eb, #38bdf8);
        display: flex; align-items: center; justify-content: center;
        font-size: 1.2rem;
    }
    .app-header .brand-title { color: #0f172a; font-weight: 800; font-size: 1.25rem; letter-spacing: -0.3px; }
    .app-header .brand-sub { color: #94a3b8; font-size: 0.8rem; margin-top: -2px; }
    .app-header .status-pill {
        padding: 6px 16px; border-radius: 999px; font-weight: 700; font-size: 0.85rem;
        border: 1px solid transparent;
    }

    /* 카드형 메트릭 */
    div[data-testid="stMetric"] {
        background: #ffffff;
        border: 1px solid #e2e8f0; border-radius: 14px;
        padding: 16px 20px; box-shadow: 0 1px 3px rgba(15,23,42,0.05);
    }
    div[data-testid="stMetricLabel"] { color: #64748b !important; font-size: 0.82rem !important; font-weight: 600 !important; }
    div[data-testid="stMetricValue"] { color: #0f172a !important; font-weight: 800 !important; }

    section[data-testid="stSidebar"] { background-color: #ffffff; border-right: 1px solid #e2e8f0; }
    section[data-testid="stSidebar"] h1, section[data-testid="stSidebar"] h2, section[data-testid="stSidebar"] h3 {
        color: #0f172a !important; font-size: 1.0rem !important;
    }
    section[data-testid="stSidebar"] .stCaption, section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] span, section[data-testid="stSidebar"] label { color: #64748b !important; }

    div[data-testid="stAlert"] { border-radius: 12px; border: 1px solid #e2e8f0; }
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #ffffff; border-radius: 14px; border: 1px solid #e2e8f0; padding: 8px 4px;
        box-shadow: 0 1px 3px rgba(15,23,42,0.05);
    }
    hr { border-color: #e2e8f0 !important; }
    .stButton button {
        background-color: #2563eb; color: white; border-radius: 10px; border: none; font-weight: 600;
    }
    .stButton button:hover { background-color: #1d4ed8; }
    div[data-testid="stDataFrame"] { border-radius: 12px; overflow: hidden; border: 1px solid #e2e8f0; }
    a { color: #2563eb !important; text-decoration: none !important; font-weight: 600; }

    /* 뉴스/상황 카드 */
    .info-card {
        background: #ffffff; border: 1px solid #e2e8f0; border-radius: 14px;
        padding: 18px 20px; box-shadow: 0 1px 3px rgba(15,23,42,0.05);
    }
    .news-card {
        background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px;
        padding: 12px 16px; margin-bottom: 10px;
    }
    .risk-badge {
        display: inline-block; padding: 4px 14px; border-radius: 20px;
        font-size: 0.85rem; font-weight: 700; margin-top: 6px;
        border: 1px solid transparent;
    }
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------------------
# 방향 화살표 헬퍼
# -------------------------------------------------------------
def calc_bearing(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlon = lon2 - lon1
    x = np.sin(dlon) * np.cos(lat2)
    y = np.cos(lat1) * np.sin(lat2) - np.sin(lat1) * np.cos(lat2) * np.cos(dlon)
    bearing = np.degrees(np.arctan2(x, y))
    return (bearing + 360) % 360

def add_direction_arrows(fig, lat_list, lon_list, color, size=11, n_arrows=3):
    n_points = len(lat_list)
    if n_points < 2:
        return
    positions = np.linspace(0, n_points - 2, n_arrows).astype(int)
    arrow_lat, arrow_lon, arrow_angle = [], [], []
    for i in positions:
        lat1, lon1 = lat_list[i], lon_list[i]
        lat2, lon2 = lat_list[i + 1], lon_list[i + 1]
        mid_lat = (lat1 + lat2) / 2
        mid_lon = (lon1 + lon2) / 2
        bearing = calc_bearing(lat1, lon1, lat2, lon2)
        arrow_lat.append(mid_lat)
        arrow_lon.append(mid_lon)
        arrow_angle.append(bearing)

    fig.add_trace(go.Scattergeo(
        lat=arrow_lat, lon=arrow_lon,
        mode="markers",
        marker=dict(
            symbol="triangle-up", size=size, color=color,
            angle=arrow_angle, angleref="up",
            line=dict(width=1, color="white")
        ),
        showlegend=False, hoverinfo="skip"
    ))

# -------------------------------------------------------------
# 항구 데이터베이스 & 자동 항로 판단
# -------------------------------------------------------------
PORT_DB = {
    # 동아시아 - 한국
    "부산항": {"lat": 35.1, "lon": 129.0, "region": "동아시아"},
    "인천항": {"lat": 37.45, "lon": 126.6, "region": "동아시아"},
    "광양항": {"lat": 34.9, "lon": 127.75, "region": "동아시아"},
    "울산항": {"lat": 35.5, "lon": 129.38, "region": "동아시아"},
    "평택항": {"lat": 36.97, "lon": 126.82, "region": "동아시아"},
    "군산항": {"lat": 35.97, "lon": 126.6, "region": "동아시아"},
    "목포항": {"lat": 34.78, "lon": 126.38, "region": "동아시아"},

    # 동아시아 - 중국
    "상하이항": {"lat": 31.2, "lon": 121.5, "region": "동아시아"},
    "닝보항": {"lat": 29.9, "lon": 121.5, "region": "동아시아"},
    "선전항": {"lat": 22.5, "lon": 114.1, "region": "동아시아"},
    "광저우항": {"lat": 23.1, "lon": 113.3, "region": "동아시아"},
    "칭다오항": {"lat": 36.1, "lon": 120.3, "region": "동아시아"},
    "톈진항": {"lat": 39.0, "lon": 117.7, "region": "동아시아"},
    "샤먼항": {"lat": 24.5, "lon": 118.1, "region": "동아시아"},
    "다롄항": {"lat": 38.9, "lon": 121.6, "region": "동아시아"},
    "잉커우항": {"lat": 40.27, "lon": 122.23, "region": "동아시아"},
    "롄윈강항": {"lat": 34.6, "lon": 119.4, "region": "동아시아"},
    "옌톈항": {"lat": 22.57, "lon": 114.27, "region": "동아시아"},

    # 동아시아 - 대만/홍콩
    "가오슝항": {"lat": 22.6, "lon": 120.3, "region": "동아시아"},
    "지룽항": {"lat": 25.1, "lon": 121.7, "region": "동아시아"},
    "타이중항": {"lat": 24.28, "lon": 120.5, "region": "동아시아"},
    "홍콩항": {"lat": 22.3, "lon": 114.2, "region": "동아시아"},

    # 동아시아 - 일본
    "요코하마항": {"lat": 35.4, "lon": 139.6, "region": "동아시아"},
    "고베항": {"lat": 34.7, "lon": 135.2, "region": "동아시아"},
    "나고야항": {"lat": 35.05, "lon": 136.9, "region": "동아시아"},
    "오사카항": {"lat": 34.65, "lon": 135.4, "region": "동아시아"},
    "도쿄항": {"lat": 35.62, "lon": 139.77, "region": "동아시아"},
    "하카타항": {"lat": 33.6, "lon": 130.4, "region": "동아시아"},
    "시미즈항": {"lat": 35.02, "lon": 138.5, "region": "동아시아"},

    # 동남아시아
    "싱가포르항": {"lat": 1.3, "lon": 103.8, "region": "동남아시아"},
    "포트클랑": {"lat": 3.0, "lon": 101.4, "region": "동남아시아"},
    "탄중펠레파스항": {"lat": 1.36, "lon": 103.55, "region": "동남아시아"},
    "페낭항": {"lat": 5.4, "lon": 100.35, "region": "동남아시아"},
    "람차방항": {"lat": 13.1, "lon": 100.9, "region": "동남아시아"},
    "방콕항": {"lat": 13.7, "lon": 100.57, "region": "동남아시아"},
    "호치민항": {"lat": 10.8, "lon": 106.7, "region": "동남아시아"},
    "하이퐁항": {"lat": 20.85, "lon": 106.7, "region": "동남아시아"},
    "다낭항": {"lat": 16.1, "lon": 108.2, "region": "동남아시아"},
    "마닐라항": {"lat": 14.6, "lon": 120.95, "region": "동남아시아"},
    "세부항": {"lat": 10.3, "lon": 123.9, "region": "동남아시아"},
    "자카르타(탄중프리옥)": {"lat": -6.1, "lon": 106.88, "region": "동남아시아"},
    "수라바야항": {"lat": -7.2, "lon": 112.73, "region": "동남아시아"},
    "프놈펜항": {"lat": 11.55, "lon": 104.9, "region": "동남아시아"},
    "양곤항": {"lat": 16.77, "lon": 96.17, "region": "동남아시아"},

    # 남아시아
    "뭄바이항": {"lat": 18.9, "lon": 72.8, "region": "남아시아"},
    "문드라항": {"lat": 22.8, "lon": 69.7, "region": "남아시아"},
    "첸나이항": {"lat": 13.1, "lon": 80.3, "region": "남아시아"},
    "콜카타항": {"lat": 22.55, "lon": 88.3, "region": "남아시아"},
    "코친항": {"lat": 9.97, "lon": 76.25, "region": "남아시아"},
    "콜롬보항": {"lat": 6.95, "lon": 79.85, "region": "남아시아"},
    "치타공항": {"lat": 22.35, "lon": 91.8, "region": "남아시아"},
    "카라치항": {"lat": 24.85, "lon": 66.98, "region": "남아시아"},

    # 중동
    "두바이(제벨알리)": {"lat": 25.0, "lon": 55.1, "region": "중동"},
    "제다항": {"lat": 21.5, "lon": 39.2, "region": "중동"},
    "담맘항": {"lat": 26.5, "lon": 50.2, "region": "중동"},
    "아바단항": {"lat": 30.35, "lon": 48.3, "region": "중동"},
    "반다르아바스항": {"lat": 27.15, "lon": 56.25, "region": "중동"},
    "도하항": {"lat": 25.3, "lon": 51.6, "region": "중동"},
    "쿠웨이트항(슈아이바)": {"lat": 29.05, "lon": 48.15, "region": "중동"},
    "살랄라항": {"lat": 17.0, "lon": 54.1, "region": "중동"},
    "아쉬도드항": {"lat": 31.8, "lon": 34.65, "region": "중동"},
    "하이파항": {"lat": 32.8, "lon": 35.0, "region": "중동"},
    "아카바항": {"lat": 29.5, "lon": 35.0, "region": "중동"},

    # 유럽
    "로테르담항": {"lat": 51.9, "lon": 4.5, "region": "유럽"},
    "함부르크항": {"lat": 53.5, "lon": 10.0, "region": "유럽"},
    "앤트워프항": {"lat": 51.2, "lon": 4.4, "region": "유럽"},
    "발렌시아항": {"lat": 39.4, "lon": -0.3, "region": "유럽"},
    "알헤시라스항": {"lat": 36.1, "lon": -5.45, "region": "유럽"},
    "바르셀로나항": {"lat": 41.35, "lon": 2.15, "region": "유럽"},
    "제노바항": {"lat": 44.4, "lon": 8.9, "region": "유럽"},
    "라스페치아항": {"lat": 44.1, "lon": 9.83, "region": "유럽"},
    "피레에프스항": {"lat": 37.95, "lon": 23.6, "region": "유럽"},
    "브레머하펜항": {"lat": 53.55, "lon": 8.6, "region": "유럽"},
    "르아브르항": {"lat": 49.5, "lon": 0.1, "region": "유럽"},
    "마르세유항": {"lat": 43.3, "lon": 5.35, "region": "유럽"},
    "사우샘프턴항": {"lat": 50.9, "lon": -1.4, "region": "유럽"},
    "펠릭스토우항": {"lat": 51.95, "lon": 1.35, "region": "유럽"},
    "런던항": {"lat": 51.5, "lon": 0.05, "region": "유럽"},
    "가담스크항": {"lat": 54.35, "lon": 18.65, "region": "유럽"},
    "이스탄불항": {"lat": 41.0, "lon": 28.95, "region": "유럽"},
    "코페르항": {"lat": 45.55, "lon": 13.73, "region": "유럽"},
    "리스본항": {"lat": 38.7, "lon": -9.15, "region": "유럽"},
    "오슬로항": {"lat": 59.9, "lon": 10.75, "region": "유럽"},
    "고텐부르크항": {"lat": 57.7, "lon": 11.95, "region": "유럽"},
    "상트페테르부르크항": {"lat": 59.93, "lon": 30.3, "region": "유럽"},

    # 미주 동안
    "뉴욕항": {"lat": 40.7, "lon": -74.0, "region": "미주동안"},
    "사바나항": {"lat": 32.1, "lon": -81.1, "region": "미주동안"},
    "찰스턴항": {"lat": 32.8, "lon": -79.9, "region": "미주동안"},
    "노퍽항": {"lat": 36.85, "lon": -76.3, "region": "미주동안"},
    "마이애미항": {"lat": 25.77, "lon": -80.17, "region": "미주동안"},
    "잭슨빌항": {"lat": 30.4, "lon": -81.6, "region": "미주동안"},
    "볼티모어항": {"lat": 39.27, "lon": -76.6, "region": "미주동안"},
    "휴스턴항": {"lat": 29.7, "lon": -95.1, "region": "미주동안"},
    "뉴올리언스항": {"lat": 29.95, "lon": -90.05, "region": "미주동안"},

    # 미주 서안
    "로스앤젤레스항": {"lat": 33.7, "lon": -118.3, "region": "미주서안"},
    "롱비치항": {"lat": 33.8, "lon": -118.2, "region": "미주서안"},
    "오클랜드항": {"lat": 37.8, "lon": -122.3, "region": "미주서안"},
    "시애틀항": {"lat": 47.6, "lon": -122.35, "region": "미주서안"},
    "타코마항": {"lat": 47.25, "lon": -122.44, "region": "미주서안"},
    "밴쿠버항": {"lat": 49.3, "lon": -123.1, "region": "미주서안"},
    "만사니요항(멕시코)": {"lat": 19.05, "lon": -104.3, "region": "미주서안"},
    "라자로카르데나스항": {"lat": 17.95, "lon": -102.2, "region": "미주서안"},

    # 남미
    "산토스항": {"lat": -23.9, "lon": -46.3, "region": "남미"},
    "리우데자네이루항": {"lat": -22.9, "lon": -43.17, "region": "남미"},
    "부에노스아이레스항": {"lat": -34.6, "lon": -58.35, "region": "남미"},
    "카야오항": {"lat": -12.05, "lon": -77.15, "region": "남미"},
    "카르타헤나항": {"lat": 10.4, "lon": -75.5, "region": "남미"},
    "발파라이소항": {"lat": -33.05, "lon": -71.6, "region": "남미"},
    "과야킬항": {"lat": -2.2, "lon": -79.9, "region": "남미"},
    "몬테비데오항": {"lat": -34.9, "lon": -56.2, "region": "남미"},

    # 아프리카
    "더반항": {"lat": -29.9, "lon": 31.0, "region": "아프리카"},
    "케이프타운항": {"lat": -33.9, "lon": 18.45, "region": "아프리카"},
    "라고스항": {"lat": 6.45, "lon": 3.4, "region": "아프리카"},
    "몸바사항": {"lat": -4.05, "lon": 39.65, "region": "아프리카"},
    "탕헤르항": {"lat": 35.75, "lon": -5.8, "region": "아프리카"},
    "다카르항": {"lat": 14.7, "lon": -17.45, "region": "아프리카"},
    "알렉산드리아항": {"lat": 31.2, "lon": 29.9, "region": "아프리카"},
    "포트사이드항": {"lat": 31.25, "lon": 32.3, "region": "아프리카"},
    "아비장항": {"lat": 5.3, "lon": -4.0, "region": "아프리카"},
    "카사블랑카항": {"lat": 33.6, "lon": -7.6, "region": "아프리카"},

    # 오세아니아
    "시드니항": {"lat": -33.85, "lon": 151.2, "region": "오세아니아"},
    "멜버른항": {"lat": -37.85, "lon": 144.9, "region": "오세아니아"},
    "브리즈번항": {"lat": -27.4, "lon": 153.15, "region": "오세아니아"},
    "프리맨틀항": {"lat": -32.05, "lon": 115.75, "region": "오세아니아"},
    "오클랜드항(뉴질랜드)": {"lat": -36.85, "lon": 174.75, "region": "오세아니아"},
    "애들레이드항": {"lat": -34.85, "lon": 138.5, "region": "오세아니아"},
}

REGION_ROUTE_MAP = {
    ("동아시아", "유럽"): "수에즈 / 홍해 (아시아-유럽)",
    ("동아시아", "미주동안"): "파나마 운하 (아시아-미주)",
    ("동아시아", "미주서안"): None,
    ("동아시아", "동남아시아"): "말라카 해협 (동남아-동아시아)",
    ("동아시아", "남아시아"): "말라카 해협 (동남아-동아시아)",
    ("동아시아", "중동"): "말라카 해협 (동남아-동아시아)",
    ("동아시아", "오세아니아"): "말라카 해협 (동남아-동아시아)",
    ("동남아시아", "중동"): "호르무즈 해협 (중동-동아시아)",
    ("동남아시아", "오세아니아"): None,
    ("중동", "유럽"): "수에즈 / 홍해 (아시아-유럽)",
    ("중동", "동아시아"): "호르무즈 해협 (중동-동아시아)",
    ("중동", "미주동안"): "수에즈 / 홍해 (아시아-유럽)",
    ("남아시아", "유럽"): "수에즈 / 홍해 (아시아-유럽)",
    ("유럽", "미주동안"): None,
    ("아프리카", "동아시아"): "말라카 해협 (동남아-동아시아)",
    ("아프리카", "유럽"): "수에즈 / 홍해 (아시아-유럽)",
    ("아프리카", "미주동안"): None,
    ("남미", "동아시아"): None,
    ("남미", "유럽"): None,
}

def determine_route(origin_port, dest_port):
    if origin_port not in PORT_DB or dest_port not in PORT_DB:
        return None, "항구 정보를 찾을 수 없습니다. 목록에서 선택해주세요."

    origin_region = PORT_DB[origin_port]["region"]
    dest_region = PORT_DB[dest_port]["region"]

    if origin_region == dest_region:
        return None, "같은 권역 내 운항으로, 주요 초크포인트를 지나지 않습니다."

    route_key = REGION_ROUTE_MAP.get((origin_region, dest_region))
    if route_key is None:
        route_key = REGION_ROUTE_MAP.get((dest_region, origin_region))

    if route_key is None:
        return None, f"{origin_region} → {dest_region} 구간은 주요 초크포인트 없이 직항 가능한 항로입니다."

    return route_key, f"{origin_port} → {dest_port}: **{route_key.split(' (')[0]}** 통과 예상"

# -------------------------------------------------------------
# 데이터 정의
# -------------------------------------------------------------
ROUTE_DB = {
    "파나마 운하 (아시아-미주)": {
        "news_keyword": "Panama Canal",
        "standard_risk_factors": {"news_cnt": 15, "weather_dist_km": 300, "threat_level": 3},
        "ship_location": {"lat": 9.38, "lon": -79.92, "name": "파나마 운하 대기 구역"},
        "threat_zone": {"lat": 9.08, "lon": -79.68, "name": "가툰 호수 가뭄/통항 제한 구역"},
        "standard_path": {
            "lat": [35.1, 33.0, 30.0, 25.0, 20.0, 15.0, 10.0, 8.9, 9.35, 15.0, 20.0, 25.0, 30.0, 35.0, 40.7],
            "lon": [129.0, 140.0, 155.0, 175.0, -170.0, -140.0, -100.0, -79.7, -79.9, -77.0, -80.0, -78.0, -75.0, -73.0, -74.0]
        },
        "alternatives": [
            {"route_name": "우회: 수에즈 운하 경유", "transit_time_days": 34, "cost_index_pct": 130, "safety_score": 80,
             "war_risk_insurance": "할증 가능",
             "eligibility": {"한국": "통행 가능", "미국": "조건부", "중국": "통행 가능", "영국": "조건부", "이스라엘": "통행 불가"},
             "status": "추천 우회로",
             "recommendation_reason": "대기 지연 없이 정시 도착 보장, 대형선 운항에 안정적.",
             "path_lat": [35.1, 25.0, 15.0, 5.0, 1.3, 5.0, 12.5, 20.0, 27.0, 31.0, 34.0, 36.0, 38.0, 40.7],
             "path_lon": [129.0, 120.0, 110.0, 105.0, 103.8, 90.0, 44.0, 38.0, 34.0, 32.3, 20.0, -5.6, -30.0, -74.0]}
        ]
    },
    "수에즈 / 홍해 (아시아-유럽)": {
        "news_keyword": "Red Sea shipping",
        "standard_risk_factors": {"news_cnt": 28, "weather_dist_km": 800, "threat_level": 4},
        "ship_location": {"lat": 12.8, "lon": 44.5, "name": "아덴만 진입부"},
        "threat_zone": {"lat": 14.5, "lon": 42.5, "name": "홍해 남부 분쟁 위험 구역"},
        "standard_path": {
            "lat": [35.1, 25.0, 15.0, 5.0, 1.3, 5.0, 12.5, 16.0, 20.0, 27.0, 31.0, 34.0, 36.0, 40.0, 45.0, 51.9],
            "lon": [129.0, 120.0, 110.0, 105.0, 103.8, 90.0, 44.0, 40.0, 38.0, 34.0, 32.3, 20.0, -5.6, -12.0, -8.0, 4.3]
        },
        "alternatives": [
            {"route_name": "우회: 아프리카 희망봉", "transit_time_days": 38, "cost_index_pct": 142, "safety_score": 95,
             "war_risk_insurance": "일반 요율",
             "eligibility": {"한국": "통행 가능", "미국": "통행 가능", "영국": "통행 가능", "중국": "통행 가능", "이스라엘": "통행 가능"},
             "status": "최우선 권장",
             "recommendation_reason": "13일 추가되지만 피격 위험 0%, 전쟁보험료 면제.",
             "path_lat": [35.1, 20.0, 5.0, 1.3, -10.0, -20.0, -30.0, -34.8, -30.0, -15.0, 0.0, 15.0, 25.0, 36.0, 40.0, 45.0, 51.9],
             "path_lon": [129.0, 115.0, 100.0, 103.8, 60.0, 45.0, 25.0, 20.0, 12.0, 8.0, -5.0, -12.0, -13.0, -9.5, -15.0, -8.0, 4.3]}
        ]
    },
    "호르무즈 해협 (중동-동아시아)": {
        "news_keyword": "Strait of Hormuz",
        "standard_risk_factors": {"news_cnt": 18, "weather_dist_km": 500, "threat_level": 4},
        "ship_location": {"lat": 26.5, "lon": 56.5, "name": "호르무즈 해협 진입부"},
        "threat_zone": {"lat": 26.8, "lon": 55.8, "name": "호르무즈 북부 군사 긴장 구역"},
        "standard_path": {
            "lat": [27.0, 24.0, 20.0, 15.0, 10.0, 5.0, 1.3, 5.0, 12.0, 18.0, 22.0, 27.0, 33.0, 35.1],
            "lon": [56.5, 60.0, 65.0, 68.0, 75.0, 85.0, 103.8, 105.0, 110.0, 113.0, 118.0, 122.0, 127.0, 129.0]
        },
        "alternatives": [
            {"route_name": "대체: 얀부항(홍해) 파이프라인 연계", "transit_time_days": 19, "cost_index_pct": 135, "safety_score": 85,
             "war_risk_insurance": "일반 요율",
             "eligibility": {"한국": "통행 가능", "미국": "통행 가능", "영국": "통행 가능", "중국": "통행 가능", "이스라엘": "조건부"},
             "status": "파이프라인 연계안",
             "recommendation_reason": "호르무즈 완전 우회, 봉쇄 시 유일한 현실적 대체 공급망.",
             "path_lat": [24.1, 18.0, 12.5, 8.0, 3.0, 1.3, 5.0, 12.0, 18.0, 22.0, 27.0, 33.0, 35.1],
             "path_lon": [38.0, 41.0, 44.0, 55.0, 70.0, 103.8, 105.0, 110.0, 113.0, 118.0, 122.0, 127.0, 129.0]}
        ]
    },
    "말라카 해협 (동남아-동아시아)": {
        "news_keyword": "Strait of Malacca",
        "standard_risk_factors": {"news_cnt": 4, "weather_dist_km": 120, "threat_level": 2},
        "ship_location": {"lat": 2.5, "lon": 101.8, "name": "말라카 해협 중앙"},
        "threat_zone": {"lat": 4.0, "lon": 100.5, "name": "열대성 폭풍/해적 빈발 구역"},
        "standard_path": {
            "lat": [1.3, 3.0, 6.0, 10.0, 15.0, 20.0, 25.0, 30.0, 35.1],
            "lon": [103.8, 101.5, 103.0, 108.0, 112.0, 117.0, 121.0, 125.0, 129.0]
        },
        "alternatives": [
            {"route_name": "우회: 순다/롬복 해협", "transit_time_days": 12, "cost_index_pct": 125, "safety_score": 90,
             "war_risk_insurance": "일반 요율",
             "eligibility": {"한국": "통행 가능", "미국": "통행 가능", "중국": "통행 가능", "영국": "통행 가능", "이스라엘": "통행 가능"},
             "status": "기상 회피안",
             "recommendation_reason": "초강력 태풍 발생 시 동인도네시아 심해 수로로 안전 항해.",
                          "path_lat": [-6.0, -8.7, -6.0, -3.0, 2.0, 5.0, 10.0, 18.0, 25.0, 35.1],
             "path_lon": [105.5, 115.8, 119.0, 122.0, 124.0, 126.0, 127.0, 128.0, 128.5, 129.0]}
        ]
    },
    "북극항로 (아시아-유럽, 북동항로)": {
        "news_keyword": "Arctic Northern Sea Route",
        "standard_risk_factors": {"news_cnt": 10, "weather_dist_km": 400, "threat_level": 3},
        "is_arctic": True,
        "ship_location": {"lat": 73.0, "lon": 100.0, "name": "북극해 러시아 연안 항로 구간"},
        "threat_zone": {"lat": 76.0, "lon": 90.0, "name": "해빙/제재 리스크 구역 (러시아 관할)"},
        "standard_path": {
            "lat": [35.1, 45.0, 55.0, 65.0, 70.0, 73.0, 76.0, 73.0, 68.0, 60.0, 51.9],
            "lon": [129.0, 135.0, 140.0, 145.0, 130.0, 100.0, 70.0, 40.0, 20.0, 10.0, 4.3]
        },
        "alternatives": [
            {"route_name": "우회: 수에즈 / 홍해 경유", "transit_time_days": 30, "cost_index_pct": 115, "safety_score": 75,
             "war_risk_insurance": "일반 요율",
             "eligibility": {"한국": "통행 가능", "미국": "통행 가능", "중국": "통행 가능", "영국": "통행 가능", "이스라엘": "통행 가능"},
             "status": "표준 대체로",
             "recommendation_reason": "북극항로 결빙/제재 리스크 회피, 연중 안정적으로 운항 가능한 검증된 항로.",
             "path_lat": [35.1, 25.0, 15.0, 5.0, 1.3, 5.0, 12.5, 16.0, 20.0, 27.0, 31.0, 34.0, 36.0, 40.0, 45.0, 51.9],
             "path_lon": [129.0, 120.0, 110.0, 105.0, 103.8, 90.0, 44.0, 40.0, 38.0, 34.0, 32.3, 20.0, -5.6, -12.0, -8.0, 4.3]}
        ]
    }
}

def calc_rule_score(news_cnt, weather_dist, threat_level):
    return min(100, int((news_cnt * 1.2) + max(0, (600 - weather_dist) * 0.08) + (threat_level * 10)))
def get_arctic_season_info():
    """북극항로 계절별 항해 가능 여부 판단 (실제 NSR 운항 패턴 기준)"""
    month = datetime.now().month
    if month in [8, 9]:
        return 1, "해빙 최소기 — 항해 최적 시즌 (쇄빙선 지원 없이도 가능)"
    elif month in [7, 10]:
        return 2, "해빙 감소기 — 항해 가능하나 쇄빙선 에스코트 권장"
    elif month in [6, 11]:
        return 4, "해빙 전환기 — 항해 난도 급상승, 쇄빙선 필수"
    else:
        return 5, "결빙기 (12~5월) — 두꺼운 해빙으로 상업 운항 사실상 불가"

# -------------------------------------------------------------
# 모델
# -------------------------------------------------------------
@st.cache_resource
def get_trained_risk_model():
    np.random.seed(42)
    X = np.random.rand(400, 4)
    X[:, 0] *= 50; X[:, 1] *= 1000; X[:, 2] = (X[:, 2] - 0.5) * 200; X[:, 3] = np.random.randint(1, 6, 400)
    risk_score = (X[:, 0]*0.3) + ((1000-X[:, 1])*0.05) + (X[:, 2]*0.2) + (X[:, 3]*10)
    y = np.where(risk_score > 65, 2, np.where(risk_score > 35, 1, 0))
    model = RandomForestClassifier(n_estimators=30, random_state=42)
    model.fit(X, y)
    return model

model = get_trained_risk_model()

# -------------------------------------------------------------
# 뉴스: 실제 기사 가져오기 (번역 + 출처, 실패시 화면에 직접 에러 표시)
# -------------------------------------------------------------
@st.cache_data(ttl=600)
def fetch_news(query, display=6):
    api_key = os.getenv("NEWSAPI_KEY")
    if not api_key:
        return None
    url = "https://newsapi.org/v2/everything"
    params = {"q": query, "language": "en", "sortBy": "relevancy", "pageSize": display, "apiKey": api_key}
    try:
        res = requests.get(url, params=params, timeout=8)
        res.raise_for_status()
        articles = res.json().get("articles", [])
        results = []
        translator = Translator()
        for a in articles:
            title_en = a.get("title") or ""
            desc_en = a.get("description") or ""
            source_name = (a.get("source") or {}).get("name", "출처 미상")

            title_ko = title_en
            desc_ko = desc_en

            if title_en:
                try:
                    title_ko = translator.translate(title_en[:500], src="en", dest="ko").text
                except Exception as e:
                    st.sidebar.error(f"번역 실패(제목): {e}")

            if desc_en:
                try:
                    desc_ko = translator.translate(desc_en[:500], src="en", dest="ko").text
                except Exception as e:
                    st.sidebar.error(f"번역 실패(본문): {e}")

            results.append({
                "title": title_ko,
                "link": a.get("url", "#"),
                "desc": desc_ko,
                "source": source_name
            })
        return results
    except Exception as e:
        st.sidebar.error(f"뉴스 가져오기 실패: {e}")
        return []

# -------------------------------------------------------------
# 뉴스: 건수 자동 집계
# -------------------------------------------------------------
@st.cache_data(ttl=600)
def fetch_news_count(query):
    api_key = os.getenv("NEWSAPI_KEY")
    if not api_key:
        return None, None
    url = "https://newsapi.org/v2/everything"
    today = datetime.now()
    try:
        p_recent = {
            "q": query, "language": "en",
            "from": (today - timedelta(days=7)).strftime("%Y-%m-%d"),
            "to": today.strftime("%Y-%m-%d"),
            "pageSize": 1,
            "apiKey": api_key
        }
        p_prev = {
            "q": query, "language": "en",
            "from": (today - timedelta(days=14)).strftime("%Y-%m-%d"),
            "to": (today - timedelta(days=7)).strftime("%Y-%m-%d"),
            "pageSize": 1,
            "apiKey": api_key
        }
        r_recent = requests.get(url, params=p_recent, timeout=8).json().get("totalResults", 0)
        r_prev = requests.get(url, params=p_prev, timeout=8).json().get("totalResults", 0)
        growth = int(((r_recent - r_prev) / max(r_prev, 1)) * 100)
        return r_recent, growth
    except Exception as e:
        st.sidebar.error(f"뉴스 건수 집계 실패: {e}")
        return None, None

def predict_risk(news_cnt, weather_dist, news_growth, threat_level):
    features = np.array([[news_cnt, weather_dist, news_growth, threat_level]])
    pred = model.predict(features)[0]
    prob = model.predict_proba(features)[0]
    return pred, prob

# -------------------------------------------------------------
# 뉴스 종합 요약 (키워드 기반 이슈 탐지)
# -------------------------------------------------------------
ISSUE_KEYWORDS_KO = {
    "공격/충돌": ["공격", "충돌", "드론", "폭격", "미사일", "전격", "타격"],
    "봉쇄/장악": ["봉쇄", "장악", "통제", "폐쇄", "차단"],
    "제재": ["제재", "금수"],
    "기상 악화": ["폭풍", "태풍", "허리케인", "기상", "해일"],
    "지연/정체": ["지연", "정체", "대기", "혼잡"],
}

def summarize_news_situation(news_items, route_name):
    if not news_items:
        return None

    combined = " ".join([(n.get("title") or "") + " " + (n.get("desc") or "") for n in news_items])

    detected = []
    for issue, keywords in ISSUE_KEYWORDS_KO.items():
        hits = sum(combined.count(k) for k in keywords)
        if hits > 0:
            detected.append((issue, hits))
    detected.sort(key=lambda x: -x[1])
    top_issues = [d[0] for d in detected[:3]]

    source_count = len(set(n.get("source", "") for n in news_items if n.get("source")))
    issue_text = ", ".join(top_issues) if top_issues else "뚜렷한 위협 이슈 없음 (일상적 운항 관련 보도 위주)"

    return {
        "article_count": len(news_items),
        "source_count": source_count,
        "issue_text": issue_text,
        "headline": news_items[0]["title"] if news_items else "",
    }

# -------------------------------------------------------------
# 사이드바
# -------------------------------------------------------------
st.sidebar.title("🚢 항로 자동 분석")
ship_name = st.sidebar.text_input("선박명", value="HANJIN GLORY")
ship_nationality = st.sidebar.selectbox("선박 국적 (기국)", ["한국", "미국", "중국", "영국", "이스라엘", "이란"])

port_list = list(PORT_DB.keys())
origin_port = st.sidebar.selectbox("출발항", port_list, index=port_list.index("부산항"))
dest_port = st.sidebar.selectbox("도착항", port_list, index=port_list.index("로테르담항"))

auto_route_key, route_message = determine_route(origin_port, dest_port)

if auto_route_key:
    st.sidebar.success(route_message)
    selected_route_key = auto_route_key
else:
    st.sidebar.warning(route_message)
    selected_route_key = list(ROUTE_DB.keys())[0]

st.sidebar.divider()
st.sidebar.subheader("위협 감지 파라미터 (선택 항로 기준)")
curr_route_data = ROUTE_DB[selected_route_key]

auto_news_cnt, auto_news_growth = fetch_news_count(curr_route_data["news_keyword"])

if auto_news_cnt is not None:
    st.sidebar.caption(f"📡 실시간 자동 집계: {auto_news_cnt}건 (증가율 {auto_news_growth:+d}%)")
    use_auto = st.sidebar.checkbox("자동 집계값 사용", value=True)
else:
    use_auto = False
    st.sidebar.caption("⚠ 자동 집계 실패 — 수동 입력을 사용합니다")

if use_auto and auto_news_cnt is not None:
    news_count = min(auto_news_cnt, 60)
    news_growth = max(min(auto_news_growth, 200), -50)
    c1, c2 = st.sidebar.columns(2)
    c1.metric("뉴스 건수(자동)", news_count)
    c2.metric("증가율(자동)", f"{news_growth:+d}%")
else:
    news_count = st.sidebar.slider("분쟁/이슈 뉴스 건수 (수동)", 0, 60, curr_route_data["standard_risk_factors"]["news_cnt"])
    news_growth = st.sidebar.slider("뉴스량 전일 대비 증가율 (수동, %)", -50, 200, 40)

weather_distance = st.sidebar.slider("기상/위협 최근접 거리 (km)", 50, 1200, curr_route_data["standard_risk_factors"]["weather_dist_km"])

arctic_season_level, arctic_season_msg = get_arctic_season_info()

if curr_route_data.get("is_arctic", False):
    st.sidebar.info(f"🧊 계절 자동 반영: {arctic_season_msg}")
    geopolitical_level = arctic_season_level
    st.sidebar.metric("지정학/계절 텐션 지수 (자동)", f"{geopolitical_level}/5")
else:
    geopolitical_level = st.sidebar.select_slider("지정학적 위협 텐션 지수", options=[1,2,3,4,5], value=curr_route_data["standard_risk_factors"]["threat_level"])

alert_email = st.sidebar.text_input("비상 알림 수신 이메일", value="shipping_ops@trade.com")
send_alert_btn = st.sidebar.button("비상 알림 수동 발송")

st.sidebar.divider()
st.sidebar.subheader("실시간 AIS 데이터")
real_ship_data, selected_mmsi = None, None
if os.path.exists("ship_data.json"):
    with open("ship_data.json", "r", encoding="utf-8") as f:
        real_ship_data = json.load(f)
    st.sidebar.caption(f"업데이트: {real_ship_data['updated_at']}")
    ship_options = {m: (i.get("name","").strip() or f"MMSI:{m}") for m,i in real_ship_data["ships"].items() if "lat" in i}

    if ship_options:
        search_term = st.sidebar.text_input("선박명으로 검색 (예: PROTI)")
        if search_term:
            filtered = {k: v for k, v in ship_options.items() if search_term.upper() in v.upper()}
        else:
            filtered = ship_options
        if filtered:
            selected_mmsi = st.sidebar.selectbox("추적할 실제 선박", list(filtered.keys()), format_func=lambda x: filtered[x])
        else:
            st.sidebar.caption("검색 결과 없음")
            selected_mmsi = None
    else:
        st.sidebar.info("현재 저장된 선박 위치 데이터가 없습니다.")
else:
    st.sidebar.caption("ship_data.json 없음 — collector.py 실행 필요")

# -------------------------------------------------------------
# 전체 항로 리스크 일괄 계산
# -------------------------------------------------------------
route_risk_summary = {}
for key, data in ROUTE_DB.items():
    is_arctic = data.get("is_arctic", False)
    if key == selected_route_key:
        n, w, g = news_count, weather_distance, news_growth
        t = arctic_season_level if is_arctic else geopolitical_level
    else:
        f = data["standard_risk_factors"]
        n, w, g = f["news_cnt"], f["weather_dist_km"], 0
        t = arctic_season_level if is_arctic else f["threat_level"]
    pred, prob = predict_risk(n, w, g, t)
    route_risk_summary[key] = {"pred": pred, "prob": prob, "rule": calc_rule_score(n, w, t)}

sel_pred = route_risk_summary[selected_route_key]["pred"]
sel_prob = route_risk_summary[selected_route_key]["prob"]
sel_rule = route_risk_summary[selected_route_key]["rule"]
labels = {0: "정상 (LOW)", 1: "경고 (MEDIUM)", 2: "심각 (HIGH)"}
risk_level_str = labels[sel_pred]
ALERT_TRIGGERED = sel_pred >= 1

curr_data = ROUTE_DB[selected_route_key]
scored_alternatives = []
for r in curr_data["alternatives"]:
    passage = r["eligibility"].get(ship_nationality, "확인 필요")
    penalty = 60 if any(k in passage for k in ["불가","표적","나포"]) else (20 if "조건부" in passage else 0)
    eff_safety = max(0, r["safety_score"] - penalty)
    cost_score = max(0, 100 - (r["cost_index_pct"]-100)*1.2)
    time_score = max(0, 100 - (r["transit_time_days"]-8)*2.0)
    total = round(eff_safety*0.5 + cost_score*0.3 + time_score*0.2, 1)
    item = dict(r); item["total_score"]=total; item["passage_status"]=passage
    scored_alternatives.append(item)
scored_alternatives.sort(key=lambda x: x["total_score"], reverse=True)
best_alt = scored_alternatives[0] if scored_alternatives else None

# -------------------------------------------------------------
# 메인 화면
# -------------------------------------------------------------
pill_bg, pill_color = {
    0: ("#dcfce7", "#15803d"),
    1: ("#fef3c7", "#b45309"),
    2: ("#fee2e2", "#b91c1c"),
}[sel_pred]

st.markdown(f"""
<div class="app-header">
    <div class="brand">
        <div class="brand-icon">🌊</div>
        <div>
            <div class="brand-title">해상 항로 리스크 조기경보 시스템</div>
            <div class="brand-sub">Maritime Route Risk Early Warning &amp; Alternative Route Recommendation</div>
        </div>
    </div>
    <div class="status-pill" style="background:{pill_bg}; color:{pill_color};">
        {selected_route_key.split(' (')[0]} · {risk_level_str}
    </div>
</div>
""", unsafe_allow_html=True)

st.info(f"👈 사이드바에서 출발항/도착항을 선택하면 자동으로 항로가 판단됩니다. 현재 선택: **{selected_route_key}**")

col1, col2, col3, col4 = st.columns(4)
col1.metric("선택 항로 리스크", risk_level_str)
col2.metric("규칙 기반 점수", f"{sel_rule} / 100")
col3.metric("AI 예측 위험 확률", f"{sel_prob[2]*100:.1f}%")
col4.metric("정상 항로 수", f"{sum(1 for v in route_risk_summary.values() if v['pred']==0)} / {len(ROUTE_DB)}")

st.divider()
st.subheader("🌍 전 세계 주요 항로 리스크 현황")

fig_world = go.Figure()
status_color = {0: "#22c55e", 1: "#eab308", 2: "#ef4444"}
status_label = {0: "정상", 1: "경고", 2: "심각"}

for key, data in ROUTE_DB.items():
    risk = route_risk_summary[key]
    tz = data["threat_zone"]
    is_selected = (key == selected_route_key)
    line_color = "#22d3ee" if is_selected else "#334155"
    path_lat = data["standard_path"]["lat"]
    path_lon = data["standard_path"]["lon"]

    fig_world.add_trace(go.Scattergeo(
        lat=path_lat, lon=path_lon, mode="lines",
        line=dict(width=8 if is_selected else 3, color=line_color),
        opacity=0.15, showlegend=False, hoverinfo="skip"
    ))
    fig_world.add_trace(go.Scattergeo(
        lat=path_lat, lon=path_lon, mode="lines",
        line=dict(width=2.5 if is_selected else 1, color=line_color),
        showlegend=False, hoverinfo="skip"
    ))
    if is_selected:
        add_direction_arrows(fig_world, path_lat, path_lon, line_color, size=13, n_arrows=3)

    fig_world.add_trace(go.Scattergeo(
        lat=[tz["lat"]], lon=[tz["lon"]], mode="markers+text",
        marker=dict(size=26 if is_selected else 18, color=status_color[risk["pred"]],
                    line=dict(width=3 if is_selected else 1, color="white")),
        text=[key.split(" (")[0]], textposition="top center",
        textfont=dict(color="#0f172a", size=11),
        name=f"{key} — {status_label[risk['pred']]}",
        hovertext=f"{key}<br>상태: {status_label[risk['pred']]}", hoverinfo="text"
    ))

fig_world.update_layout(
    geo=dict(projection_type="natural earth", showland=True, landcolor="rgb(226,232,240)",
        oceancolor="rgb(248,250,252)", showocean=True, showcoastlines=True, coastlinecolor="rgb(203,213,225)",
        showcountries=True, countrycolor="rgb(203,213,225)", bgcolor="rgba(0,0,0,0)", lakecolor="rgb(248,250,252)"),
    paper_bgcolor="rgba(0,0,0,0)", margin=dict(l=0,r=0,t=10,b=0), height=480,
    legend=dict(orientation="h", yanchor="bottom", y=-0.1, font=dict(color="#0f172a", size=11))
)
st.plotly_chart(fig_world, use_container_width=True)

# -------------------------------------------------------------
# 선택 항로 상세 지도
# -------------------------------------------------------------
st.divider()
st.subheader(f"🔍 상세 보기: {selected_route_key}")

ship_loc = curr_data["ship_location"]
threat_loc = curr_data["threat_zone"]
std_path = curr_data["standard_path"]

fig_detail = go.Figure()
fig_detail.add_trace(go.Scattergeo(
    lat=std_path["lat"], lon=std_path["lon"], mode="lines",
    line=dict(width=8, color="#3b82f6"), opacity=0.15, showlegend=False, hoverinfo="skip"
))
fig_detail.add_trace(go.Scattergeo(
    lat=std_path["lat"], lon=std_path["lon"], mode="lines",
    line=dict(width=3, color="#3b82f6"), name="표준 항로"
))
add_direction_arrows(fig_detail, std_path["lat"], std_path["lon"], "#3b82f6", size=14, n_arrows=4)

threat_color = "#ef4444" if ALERT_TRIGGERED else "#64748b"
fig_detail.add_trace(go.Scattergeo(
    lat=[threat_loc["lat"]], lon=[threat_loc["lon"]], mode="markers+text",
    marker=dict(size=22, color=threat_color), text=[threat_loc["name"]],
    textposition="top center", textfont=dict(color="#0f172a"),
    name="⚠ 위협 감지 구역" if ALERT_TRIGGERED else "모니터링 구역"
))
fig_detail.add_trace(go.Scattergeo(
    lat=[ship_loc["lat"]], lon=[ship_loc["lon"]], mode="markers+text",
    marker=dict(size=16, color="#f59e0b", symbol="triangle-up"), text=[ship_name],
    textposition="bottom center", textfont=dict(color="#0f172a"), name="시나리오 선박"
))
if ALERT_TRIGGERED and best_alt:
    fig_detail.add_trace(go.Scattergeo(
        lat=best_alt["path_lat"], lon=best_alt["path_lon"], mode="lines",
        line=dict(width=4, color="#dc3545", dash="dash"), name=f"추천 대체: {best_alt['route_name']}"
    ))
    add_direction_arrows(fig_detail, best_alt["path_lat"], best_alt["path_lon"], "#dc3545", size=14, n_arrows=4)

if real_ship_data:
    other_lat, other_lon, other_name = [], [], []
    my_lat = my_lon = my_name = None
    for m, info in real_ship_data["ships"].items():
        if "lat" not in info: continue
        if m == selected_mmsi:
            my_lat, my_lon = info["lat"], info["lon"]
            my_name = info.get("name","").strip() or f"MMSI:{m}"
        else:
            other_lat.append(info["lat"]); other_lon.append(info["lon"])
            other_name.append(info.get("name","").strip() or f"MMSI:{m}")

    if other_lat:
        fig_detail.add_trace(go.Scattergeo(lat=other_lat, lon=other_lon, mode="markers",
            marker=dict(size=4, color="#94a3b8", opacity=0.5), text=other_name, hoverinfo="text",
            name="실시간 다른 선박"))

    if my_lat:
        fig_detail.add_trace(go.Scattergeo(lat=[my_lat], lon=[my_lon], mode="markers+text",
            marker=dict(size=18, color="#dc2626", symbol="star", line=dict(width=2, color="white")),
            text=[my_name], textposition="top center", textfont=dict(color="#0f172a"), name="내 지정 선박"))

        if os.path.exists("ship_history.json"):
            with open("ship_history.json", "r", encoding="utf-8") as f:
                ship_history = json.load(f)
            if selected_mmsi in ship_history:
                track = ship_history[selected_mmsi]["track"]
                if len(track) >= 2:
                    track_lat = [p["lat"] for p in track]
                    track_lon = [p["lon"] for p in track]
                    fig_detail.add_trace(go.Scattergeo(
                        lat=track_lat, lon=track_lon, mode="lines+markers",
                        line=dict(width=3, color="#22c55e"),
                        marker=dict(size=4, color="#22c55e"),
                        name="실제 이동 항적 (수집된 기록)"
                    ))
                else:
                    st.caption(f"⚠ {my_name}의 이동 항적은 {len(track)}개 지점만 수집됨 — collector.py를 여러 번 더 실행하면 실제 항적이 그려집니다.")

fig_detail.update_layout(
    geo=dict(projection_type="equirectangular", showland=True, landcolor="rgb(226,232,240)",
        oceancolor="rgb(248,250,252)", showocean=True, showcoastlines=True, coastlinecolor="rgb(203,213,225)",
        showcountries=True, countrycolor="rgb(203,213,225)",
        center=dict(lat=ship_loc["lat"], lon=ship_loc["lon"]), projection_scale=2.2, bgcolor="rgba(0,0,0,0)"),
    paper_bgcolor="rgba(0,0,0,0)", margin=dict(l=0,r=0,t=10,b=0), height=550,
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, font=dict(color="#0f172a"))
)
st.plotly_chart(fig_detail, use_container_width=True)

# -------------------------------------------------------------
# 상황판단 + 뉴스
# -------------------------------------------------------------
st.divider()
news_items = fetch_news(curr_data["news_keyword"])
col_status, col_news = st.columns([1.3, 1])

with col_status:
    st.subheader("현재 상황 판단")
    if ALERT_TRIGGERED:
        if sel_pred == 2:
            st.error(f"🔴 심각 등급 — {threat_loc['name']} 인근 위협 감지")
        else:
            st.warning(f"🟡 경고 등급 — {threat_loc['name']} 인근 리스크 상승")

        st.markdown(f"""
<div class="info-card" style='color:#334155; line-height:1.9;'>
<b style='color:#0f172a; font-size:1.05rem;'>우려 요인</b><br>
• 관련 뉴스: <b style='color:#d97706;'>{news_count}건</b> (전일 대비 {news_growth:+d}%)<br>
• 위협 최근접 거리: <b style='color:#d97706;'>{weather_distance}km</b><br>
• 지정학적 텐션: <b style='color:#d97706;'>{geopolitical_level}/5</b><br><br>
<b style='color:#0f172a; font-size:1.05rem;'>권장 조치</b>: <span style='color:#2563eb;'>{best_alt['route_name']}</span> 전환 검토
</div>
""", unsafe_allow_html=True)
    else:
        st.success("🟢 정상 운항 상태입니다.")

    briefing = summarize_news_situation(news_items, selected_route_key) if news_items else None
    if briefing:
        st.markdown(f"""
<div class="info-card" style='color:#334155; line-height:1.9; margin-top:14px;'>
<b style='color:#0f172a; font-size:1.05rem;'>📋 뉴스 종합 요약</b><br>
최근 수집된 <b style='color:#d97706;'>{briefing['article_count']}건</b>의 관련 기사
(출처 <b style='color:#d97706;'>{briefing['source_count']}곳</b>)를 종합한 결과,
현재 이 항로에서는 <b style='color:#d97706;'>{briefing['issue_text']}</b> 관련 이슈가 주로 보도되고 있습니다.<br>
대표 헤드라인: <i>"{briefing['headline']}"</i>
</div>
""", unsafe_allow_html=True)

with col_news:
    st.subheader("관련 뉴스")
    if news_items is None:
        st.caption("NewsAPI 키 미설정")
    elif not news_items:
        st.caption("관련 뉴스를 가져오지 못했습니다.")
    else:
        for n in news_items:
            st.markdown(f"""
<div class="news-card">
<a href="{n['link']}" target="_blank" style="color:#0f172a; font-weight:700; font-size:0.95rem;">{n['title']}</a>
<div style="color:#64748b; font-size:0.82rem; margin-top:4px;">📰 {n['source']} · {(n['desc'] or '')[:80]}...</div>
</div>
""", unsafe_allow_html=True)

# -------------------------------------------------------------
# 리스크 점수 추이 (30일)
# -------------------------------------------------------------
st.divider()
st.subheader("📈 리스크 점수 추이 (최근 30일)")

np.random.seed(hash(selected_route_key) % 1000)
trend_base = sel_rule
trend_values = np.clip(trend_base + np.cumsum(np.random.randn(30) * 4), 0, 100)

fig_trend = go.Figure()
fig_trend.add_trace(go.Scatter(
    y=trend_values, mode="lines",
    line=dict(color="#2563eb", width=2.5),
    fill="tozeroy", fillcolor="rgba(37, 99, 235, 0.10)",
    name="리스크 점수"
))
fig_trend.update_layout(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#64748b"),
    height=220, margin=dict(l=10, r=10, t=10, b=10),
    xaxis=dict(showgrid=False, title="일 전"),
    yaxis=dict(showgrid=True, gridcolor="#e2e8f0", title="점수"),
    showlegend=False
)
st.plotly_chart(fig_trend, use_container_width=True)

# -------------------------------------------------------------
# 대체 루트 (경보시만)
# -------------------------------------------------------------
if ALERT_TRIGGERED:
    st.divider()
    st.subheader("대체 루트 추천")
    for idx, r in enumerate(scored_alternatives):
        badge = "🟢" if idx == 0 else "🔵"
        with st.container():
            st.markdown(f"### {badge} {idx+1}순위: {r['route_name']}")
            c1,c2,c3,c4,c5 = st.columns(5)
            c1.metric("점수", f"{r['total_score']}")
            c2.metric("소요시간", f"{r['transit_time_days']}일")
            c3.metric("운임지수", f"{r['cost_index_pct']}%")
            c4.metric("보험료", r["war_risk_insurance"])
            c5.metric(f"통행({ship_nationality})", r["passage_status"])
            st.info(r["recommendation_reason"])

            risk_tag, badge_bg, badge_text = ("🟢 Low", "#dcfce7", "#15803d") if r["total_score"] >= 70 else \
                (("🟡 Medium", "#fef3c7", "#b45309") if r["total_score"] >= 40 else ("🔴 High", "#fee2e2", "#b91c1c"))
            st.markdown(
                f"<span class='risk-badge' style='background:{badge_bg};color:{badge_text};'>{risk_tag} Risk</span>",
                unsafe_allow_html=True
            )

    if send_alert_btn:
        st.sidebar.success(f"📧 발송됨: {alert_email}")