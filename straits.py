"""감시 해협 정의: 위치, 데이터 출처별 이름

- radius_km: 이 반경 안에서 일어난 GDELT 갈등 사건을 그 해협의 '뉴스 사건'으로 셈
- portwatch: IMF PortWatch 해협 이름 (통항량 비교)
- news_keyword: 뉴스 목록(NewsAPI) 검색어 — 제목·요약에서만 찾음
- sea_network.py 의 해협 id(hormuz, suez, malacca, panama)와 같은 id 를 씀. 북극항로는 항로망에 없음
"""

STRAITS = {
    "hormuz": {
        "name": "호르무즈 해협", "region": "중동 원유", "lat": 26.6, "lon": 56.3, "radius_km": 350,
        "portwatch": "Strait of Hormuz", "news_keyword": '"Strait of Hormuz"',
    },
    "suez": {
        "name": "수에즈·홍해", "region": "아시아-유럽", "lat": 13.5, "lon": 42.8, "radius_km": 600,
        "portwatch": "Bab el-Mandeb Strait",
        "news_keyword": '("Red Sea" OR "Suez Canal" OR "Bab el-Mandeb") AND (ship OR shipping OR vessel OR Houthi)',
    },
    "malacca": {
        "name": "말라카 해협", "region": "동남아 관문", "lat": 2.5, "lon": 101.5, "radius_km": 400,
        "portwatch": "Malacca Strait", "news_keyword": '"Strait of Malacca" OR "Malacca Strait"',
    },
    "panama": {
        "name": "파나마 운하", "region": "아시아-미주", "lat": 9.1, "lon": -79.7, "radius_km": 250,
        "portwatch": "Panama Canal", "news_keyword": '"Panama Canal"',
    },
    "arctic": {
        "name": "북극항로", "region": "북극해", "lat": 74.0, "lon": 110.0, "radius_km": 1500,
        "portwatch": "Bering Strait", "news_keyword": '"Northern Sea Route"',
    },
}

LEVELS = {
    0: {"label": "정상", "icon": "🟢", "color": "#16a34a", "bg": "#dcfce7"},
    1: {"label": "주의", "icon": "🟡", "color": "#b45309", "bg": "#fef3c7"},
    2: {"label": "심각", "icon": "🔴", "color": "#dc2626", "bg": "#fee2e2"},
    None: {"label": "확인 중", "icon": "⚪", "color": "#64748b", "bg": "#f1f5f9"},
}
