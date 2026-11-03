"""항구 / 해협 / 대체 항로 정적 데이터 (계산 로직 없음)"""
from datetime import datetime

# -------------------------------------------------------------
# 항구 데이터베이스 (경로상 해협 판단은 voyage_route.py)
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

# 시나리오용 항구 추가 (좌표는 항구 위치 근사값)
PORT_DB.update({
    "라스타누라항": {"lat": 26.64, "lon": 50.16, "region": "중동"},
    "얀부항": {"lat": 24.09, "lon": 38.06, "region": "중동"},
    "푸자이라항": {"lat": 25.17, "lon": 56.36, "region": "중동"},
})


# -------------------------------------------------------------
# 경로 좌표 (위도, 경도)
# 지도 표시와 거리 계산에 함께 쓰는 "경유점" 목록입니다.
# 실제 항해 경로가 아니라 주요 해역을 잇는 근사 경로이므로,
# 여기서 계산한 거리는 "경유점 기반 근사값"입니다.
# -------------------------------------------------------------
RAS_TANURA_TO_HORMUZ = [(26.64, 50.16), (27.0, 51.3), (26.6, 53.0), (26.2, 54.8), (26.55, 56.3), (25.0, 57.6)]
GULF_OF_OMAN_TO_SRI_LANKA = [(22.6, 60.3), (12.0, 70.0), (7.0, 77.0), (5.7, 80.6)]
SRI_LANKA_TO_SINGAPORE = [(5.7, 80.6), (6.3, 94.8), (5.0, 98.5), (3.2, 100.6), (2.0, 102.0), (1.2, 103.7), (1.3, 104.4)]
SINGAPORE_TO_TAIWAN_STRAIT = [(1.3, 104.4), (2.5, 105.2), (7.0, 109.0), (12.0, 110.5), (17.0, 113.0), (21.5, 118.0), (24.0, 119.8)]
TAIWAN_STRAIT_TO_KOREA_STRAIT = [(24.0, 119.8), (27.5, 122.5), (31.0, 124.5), (33.0, 127.6), (34.6, 128.9)]
TO_ULSAN = [(34.6, 128.9), (35.0, 129.35), (35.45, 129.45)]
TO_BUSAN = [(34.6, 128.9), (35.05, 129.05)]
# 인도양 → 순다 해협 → 카리마타 해협 → 남중국해
SUNDA = [(5.7, 80.6), (-2.0, 95.0), (-6.6, 104.9), (-6.0, 105.8), (-5.0, 107.0), (-2.8, 108.9), (1.5, 108.0), (7.0, 109.0)]
# 인도양 → 롬복 해협 → 마카사르 해협 → 셀레베스해 → 필리핀 동쪽 → 대한해협
LOMBOK = [(5.7, 80.6), (-2.0, 95.0), (-9.5, 110.0), (-8.9, 115.7), (-7.0, 116.5), (-4.0, 117.8), (-1.0, 118.3),
          (1.5, 119.5), (4.0, 123.0), (5.0, 126.5), (10.0, 128.0), (20.0, 127.0), (28.0, 127.0), (33.0, 128.6),
          (34.5, 129.9)]
YANBU_TO_ARABIAN_SEA = [(24.09, 38.06), (20.0, 39.5), (15.0, 41.8), (12.6, 43.3), (12.2, 46.0), (12.0, 52.3),
                        (8.0, 73.5)]
FUJAIRAH_TO_ARABIAN_SEA = [(25.17, 56.36), (24.3, 58.3), (22.6, 60.3)]
# 미국 걸프(휴스턴) → 대서양 → 희망봉 → 인도양
HOUSTON_TO_CAPE = [(29.7, -95.0), (27.0, -90.0), (24.0, -84.0), (23.5, -80.0), (25.5, -79.6), (28.0, -76.0),
                   (20.0, -55.0), (0.0, -30.0), (-25.0, 0.0), (-35.0, 18.0), (-36.0, 25.0)]
CAPE_TO_SUNDA_APPROACH = [(-36.0, 25.0), (-30.0, 60.0), (-15.0, 95.0), (-6.6, 104.9), (-6.0, 105.8), (-5.0, 107.0),
                          (-2.8, 108.9), (1.5, 108.0), (7.0, 109.0)]

# 동아시아 ↔ 유럽 공통 구간
BUSAN_TO_SINGAPORE = [(35.05, 129.05), (34.6, 128.9)] + list(reversed(TAIWAN_STRAIT_TO_KOREA_STRAIT[:-1])) + \
    list(reversed(SINGAPORE_TO_TAIWAN_STRAIT))
SINGAPORE_TO_SRI_LANKA = list(reversed(SRI_LANKA_TO_SINGAPORE))
SRI_LANKA_TO_ADEN = [(5.7, 80.6), (8.0, 73.5), (12.0, 52.3), (12.2, 46.0)]
ADEN_TO_PORT_SAID = [(12.2, 46.0), (12.6, 43.3), (15.0, 41.8), (20.0, 38.8), (24.0, 36.5), (27.5, 34.0),
                     (29.0, 32.8), (29.95, 32.55), (31.3, 32.3)]
PORT_SAID_TO_GIBRALTAR = [(31.3, 32.3), (33.0, 28.0), (34.4, 24.5), (35.6, 16.0), (37.4, 11.5), (37.6, 5.0),
                          (36.0, -5.6)]
GIBRALTAR_TO_ROTTERDAM = [(36.0, -5.6), (36.8, -9.6), (43.5, -10.0), (48.8, -5.6), (50.0, -2.0), (51.0, 1.5),
                          (51.95, 4.05)]
SINGAPORE_TO_CAPE = [(6.3, 94.8), (-10.0, 80.0), (-28.0, 50.0), (-35.5, 22.0), (-35.0, 18.0)]
CAPE_TO_ROTTERDAM = [(-35.0, 18.0), (-20.0, 5.0), (0.0, -10.0), (14.5, -20.0), (30.0, -14.5), (36.8, -9.6),
                     (43.5, -10.0), (48.8, -5.6), (50.0, -2.0), (51.0, 1.5), (51.95, 4.05)]
# 동아시아 → 파나마 → 미 동안
BUSAN_TO_PANAMA = [(35.05, 129.05), (34.3, 129.0), (32.0, 129.5), (30.5, 132.0), (30.0, 160.0), (25.0, -160.0),
                   (17.0, -120.0), (9.0, -85.0), (8.8, -79.5)]
PANAMA_TO_NEW_YORK = [(8.8, -79.5), (9.4, -79.9), (12.0, -78.5), (19.9, -73.8), (21.95, -72.6), (27.0, -72.0),
                      (35.0, -73.5), (40.45, -73.8)]
GIBRALTAR_TO_NEW_YORK = [(36.0, -5.6), (36.0, -30.0), (40.45, -73.8)]
BUSAN_TO_LA = [(35.05, 129.05), (35.5, 130.0), (38.5, 135.0), (41.3, 139.8), (41.45, 140.7), (41.5, 141.8),
               (42.0, 146.0), (48.0, -170.0), (40.0, -135.0), (33.7, -118.27)]
LA_TO_NEW_YORK_RAIL = [(33.7, -118.27), (34.05, -118.25), (35.1, -106.6), (41.85, -87.65), (40.7, -74.0)]
# 북극항로(북동항로)
BUSAN_TO_ROTTERDAM_NSR = [(35.05, 129.05), (35.5, 130.0), (42.0, 138.0), (45.7, 142.0), (48.0, 150.0),
                          (50.5, 157.5), (60.0, 175.0), (65.8, -169.0), (70.0, -175.0), (72.0, 175.0),
                          (74.5, 150.0), (77.6, 105.0), (76.0, 80.0), (71.0, 58.0), (71.0, 40.0), (71.5, 25.5),
                          (66.0, 8.0), (62.0, 3.0), (56.0, 4.0), (51.95, 4.05)]
COLOMBO_TO_SRI_LANKA_SOUTH = [(6.95, 79.85), (6.0, 79.9), (5.7, 80.6)]

# 육상 파이프라인: 양 끝 시설을 잇는 근사 경로 (실제 매설 경로가 아님)
# 사우디 동서 파이프라인: 아브카이크(동부 처리시설) → 얀부(홍해) / UAE: 하브샨(육상 유전) → 푸자이라(오만만)
PIPE_EAST_WEST = [(25.94, 49.68), (25.2, 46.6), (24.6, 42.5), (24.09, 38.06)]
PIPE_HABSHAN_FUJAIRAH = [(23.85, 53.62), (24.25, 55.3), (25.12, 56.33)]
PIPE_LABEL = "파이프라인 구간(육상, 근사 경로)"
RAIL_LABEL = "철도 구간(육상)"


def _join(*segments):
    """경로 구간을 이어 붙이되, 맞닿는 지점이 중복되면 한 번만 넣음"""
    out = []
    for seg in segments:
        for p in seg:
            if not out or out[-1] != tuple(p):
                out.append(tuple(p))
    return out


# -------------------------------------------------------------
# 해협(감시 대상) + 시나리오(대안 비교) 정의
# weather_points: Open-Meteo 로 파고·풍속을 조회할 해협 주변 좌표
# ais_box: AIS 선박 수/속도를 셀 구역 (위도 최소·최대, 경도 최소·최대)
#
# 대안별 거리: 아래 path 좌표로 계산한 "경유점 기반 근사값" (alternatives.py)
# 대안별 일수: 근사 거리 ÷ 설정 속력(config.toml, 가정값) + 육상 구간 일수(출처 있는 값만)
# references: 비교·검증용 공개 자료 수치 (같은 구간이 아닐 수 있어 계산에 직접 쓰지 않음)
# -------------------------------------------------------------
ROUTE_DB = {
    "호르무즈 해협 (중동-동아시아)": {
        "id": "hormuz",
        "news_keyword": "Strait of Hormuz",
        "ship_location": {"lat": 26.5, "lon": 56.5, "name": "호르무즈 해협 진입부"},
        "threat_zone": {"lat": 26.8, "lon": 55.8, "name": "호르무즈 북부 군사 긴장 구역"},
        "weather_points": [(26.5, 56.4), (25.3, 57.3)],
        "ais_box": {"lat": (25.5, 27.0), "lon": (55.5, 57.5)},
        "scenario": {
            "title": "사우디 라스타누라항 → 울산항 VLCC 원유선",
            "options": [
                {"id": "hormuz_base", "route_name": "현 항로 유지: 라스타누라 → 호르무즈 → 말라카 → 울산",
                 "path": _join(RAS_TANURA_TO_HORMUZ, GULF_OF_OMAN_TO_SRI_LANKA, SRI_LANKA_TO_SINGAPORE,
                               SINGAPORE_TO_TAIWAN_STRAIT, TAIWAN_STRAIT_TO_KOREA_STRAIT, TO_ULSAN),
                 "note": "호르무즈 해협을 그대로 통과. 위험이 높을수록 전쟁위험 보험료 입력값을 올려 비교하세요.",
                 "references": [
                     "MOL 블로그(mol-service.com, 'Vessel speed and sailing days'): 라스타누라→도쿄만 원유선 14노트 약 470시간(19.5일), "
                     "중동발 VLCC 편도 약 20일·왕복 45~50일(선적·하역 포함)",
                 ]},
                {"id": "hormuz_yanbu", "route_name": "사우디 동서 파이프라인 → 얀부항(홍해) 선적",
                 "path": _join(YANBU_TO_ARABIAN_SEA, [(5.7, 80.6)], SRI_LANKA_TO_SINGAPORE,
                               SINGAPORE_TO_TAIWAN_STRAIT, TAIWAN_STRAIT_TO_KOREA_STRAIT, TO_ULSAN),
                 "land_path": PIPE_EAST_WEST, "land_label": PIPE_LABEL,
                 "note": "호르무즈를 피하지만 홍해·바브엘만데브 해협을 지나므로 홍해 위험에 노출됩니다. "
                         "파이프라인 이용료는 공개값이 없어 '기타 비용' 칸에 직접 입력하세요.",
                 "references": [
                     "EIA Today in Energy (2025-06-16): 동서 파이프라인(아브카이크→얀부) 500만 b/d, "
                     "2019년 일시적으로 700만 b/d로 확장",
                     "EIA (2025-06-16): 사우디·UAE 파이프라인으로 호르무즈 우회 가능한 여유 용량 약 260만 b/d 추정",
                 ]},
                {"id": "hormuz_fujairah", "route_name": "UAE 하브샨–푸자이라 파이프라인 → 푸자이라항 선적",
                 "path": _join(FUJAIRAH_TO_ARABIAN_SEA, GULF_OF_OMAN_TO_SRI_LANKA, SRI_LANKA_TO_SINGAPORE,
                               SINGAPORE_TO_TAIWAN_STRAIT, TAIWAN_STRAIT_TO_KOREA_STRAIT, TO_ULSAN),
                 "land_path": PIPE_HABSHAN_FUJAIRAH, "land_label": PIPE_LABEL,
                 "note": "푸자이라는 호르무즈 바깥(오만만)에 있습니다. 다만 이 파이프라인은 UAE 원유(머반)용이므로 "
                         "사우디 원유를 그대로 옮기는 안이 아니라 UAE 원유로 대체 구매하는 안입니다.",
                 "references": [
                     "EIA Today in Energy (2025-06-16): UAE 파이프라인 180만 b/d, 육상 유전 → 오만만 푸자이라 터미널",
                 ]},
                {"id": "hormuz_switch", "route_name": "비중동 원유로 공급처 전환 (예: 미국 걸프 → 희망봉 → 울산)",
                 "path": _join(HOUSTON_TO_CAPE, CAPE_TO_SUNDA_APPROACH, SINGAPORE_TO_TAIWAN_STRAIT[2:],
                               TAIWAN_STRAIT_TO_KOREA_STRAIT, TO_ULSAN),
                 "note": "중동 해협을 모두 피하지만 항해가 크게 길어집니다. 유종·원유 가격 차이는 계산에 없으므로 "
                         "'기타 비용' 칸에 차액을 입력하세요. VLCC는 파나마 운하를 통과할 수 없어 희망봉 경유로 가정했습니다.",
                 "references": []},
            ],
        },
    },
    "수에즈 / 홍해 (아시아-유럽)": {
        "id": "suez",
        "news_keyword": "Red Sea shipping",
        "ship_location": {"lat": 12.8, "lon": 44.5, "name": "아덴만 진입부"},
        "threat_zone": {"lat": 14.5, "lon": 42.5, "name": "홍해 남부 분쟁 위험 구역"},
        "weather_points": [(12.6, 43.4), (14.5, 42.0), (12.3, 46.0)],
        "ais_box": {"lat": (11.5, 16.0), "lon": (41.5, 46.0)},
        "scenario": {
            "title": "부산항 → 로테르담항 컨테이너선",
            "options": [
                {"id": "suez_base", "route_name": "수에즈 통과 (전쟁위험 보험료 감수)",
                 "path": _join(BUSAN_TO_SINGAPORE, SINGAPORE_TO_SRI_LANKA, SRI_LANKA_TO_ADEN, ADEN_TO_PORT_SAID,
                               PORT_SAID_TO_GIBRALTAR, GIBRALTAR_TO_ROTTERDAM),
                 "note": "가장 짧지만 홍해 남부·바브엘만데브 위험 구역을 지납니다. 수에즈 통항료는 '기타 비용'에 입력하세요.",
                 "references": [
                     "Port Economics, Management and Policy (Notteboom·Pallis·Rodrigue), 'Routing Options between "
                     "Shanghai, Rotterdam and New York': 상하이→로테르담 수에즈 경유 약 10,600해리, 16노트·무기항 약 27일",
                 ]},
                {"id": "suez_cape", "route_name": "희망봉 우회",
                 "path": _join(BUSAN_TO_SINGAPORE, SINGAPORE_TO_SRI_LANKA[:2], SINGAPORE_TO_CAPE, CAPE_TO_ROTTERDAM),
                 "note": "홍해를 완전히 피하지만 항해 일수와 연료비가 늘어납니다.",
                 "references": [
                     "Port Economics(같은 자료): 상하이→로테르담 희망봉 경유 13,800해리, 16노트·무기항 약 35일",
                 ]},
            ],
        },
    },
    "말라카 해협 (동남아-동아시아)": {
        "id": "malacca",
        "news_keyword": "Strait of Malacca",
        "ship_location": {"lat": 2.5, "lon": 101.8, "name": "말라카 해협 중앙"},
        "threat_zone": {"lat": 4.0, "lon": 100.5, "name": "열대성 폭풍/해적 빈발 구역"},
        "weather_points": [(4.0, 99.8), (2.3, 101.7), (1.2, 104.0)],
        "ais_box": {"lat": (0.8, 6.0), "lon": (95.5, 104.5)},
        "scenario": {
            "title": "콜롬보항 → 부산항 (인도양 → 동아시아)",
            "options": [
                {"id": "malacca_base", "route_name": "현 항로 유지: 말라카·싱가포르 해협",
                 "path": _join(COLOMBO_TO_SRI_LANKA_SOUTH, SRI_LANKA_TO_SINGAPORE, SINGAPORE_TO_TAIWAN_STRAIT,
                               TAIWAN_STRAIT_TO_KOREA_STRAIT, TO_BUSAN),
                 "note": "가장 짧은 경로. 수심 제한으로 초대형 만재 유조선은 이용이 제한될 수 있습니다.",
                 "references": [
                     "RSIS (2012, 'Maritime Highways of Southeast Asia'): 23만 DWT 초과 유조선은 말라카 수심 제한으로 "
                     "롬복–마카사르 경로를 이용",
                 ]},
                {"id": "malacca_sunda", "route_name": "순다 해협 경유",
                 "path": _join(COLOMBO_TO_SRI_LANKA_SOUTH, SUNDA, SINGAPORE_TO_TAIWAN_STRAIT[3:],
                               TAIWAN_STRAIT_TO_KOREA_STRAIT, TO_BUSAN),
                 "note": "말라카를 피하는 가장 가까운 우회로. 조류·얕은 수심 때문에 대형선 항해가 까다롭습니다.",
                 "references": [
                     "RSIS (2014, CO12024): 순다 해협 최협부 약 13해리, 조류·여울 등으로 말라카보다 불편",
                 ]},
                {"id": "malacca_lombok", "route_name": "롬복 해협 – 마카사르 해협 경유",
                 "path": _join(COLOMBO_TO_SRI_LANKA_SOUTH, LOMBOK, TO_BUSAN[1:]),
                 "note": "수심이 깊어 초대형선도 통과 가능하지만 가장 멀리 돕니다.",
                 "references": [
                     "Wikipedia 'Lombok Strait': 최소 수심 약 250 m",
                     "RSIS (2012): 마카사르 해협 북쪽 입구~남쪽 입구 약 400해리",
                 ]},
            ],
        },
    },
    "파나마 운하 (아시아-미주)": {
        "id": "panama",
        "news_keyword": "Panama Canal",
        "ship_location": {"lat": 9.38, "lon": -79.92, "name": "파나마 운하 대기 구역"},
        "threat_zone": {"lat": 9.08, "lon": -79.68, "name": "가툰 호수 가뭄/통항 제한 구역"},
        "weather_points": [(8.6, -79.4), (9.6, -79.9)],
        "ais_box": {"lat": (8.3, 9.8), "lon": (-80.2, -79.3)},
        "scenario": {
            "title": "부산항 → 뉴욕항 컨테이너선",
            "options": [
                {"id": "panama_base", "route_name": "현 항로 유지: 파나마 운하 경유",
                 "path": _join(BUSAN_TO_PANAMA, PANAMA_TO_NEW_YORK),
                 "note": "파나마 통항료는 '기타 비용'에 입력하세요.",
                 "references": [
                     "Port Economics, 'Transit Times from Shanghai and North American Routing Options': "
                     "상하이→뉴욕 전 구간 해상(all-water) 약 26일",
                     "USDA AMS, 'Impact of Panama Canal Expansion on the U.S. Intermodal System': 파나마 경유 항해 약 21.6일",
                 ]},
                {"id": "panama_suez", "route_name": "수에즈 운하 경유",
                 "path": _join(BUSAN_TO_SINGAPORE, SINGAPORE_TO_SRI_LANKA, SRI_LANKA_TO_ADEN, ADEN_TO_PORT_SAID,
                               PORT_SAID_TO_GIBRALTAR, GIBRALTAR_TO_NEW_YORK),
                 "note": "파나마 통항 제한은 피하지만 홍해 위험 구역을 지납니다.",
                 "references": [
                     "Port Economics(같은 자료): 상하이→뉴욕 수에즈 경유 약 28일",
                     "USDA AMS(같은 자료): 수에즈 경유 항해 약 21.1일 (남·동남아→미 동안 기준)",
                 ]},
                {"id": "panama_rail", "route_name": "미국 서안(LA) 하역 후 철도 운송",
                 "path": BUSAN_TO_LA,
                 "land_path": LA_TO_NEW_YORK_RAIL, "land_label": RAIL_LABEL,
                 # 출처: USDA AMS, 'Impact of Panama Canal Expansion on the U.S. Intermodal System'
                 # - 아시아→미 서안 해상 12.3일 + 서안→동안 철도 6일
                 "land_days": 6,
                 "note": "선박은 LA에서 하역하고 이후 철도로 동부까지 운송합니다. 철도 운임·하역비는 '기타 비용'에 입력하세요.",
                 "references": [
                     "USDA AMS(같은 자료): 아시아→미 서안 해상 12.3일 + 서안→동안 철도 6일",
                     "Port Economics(같은 자료): 상하이→뉴욕 인터모달(서안 경유) 약 22일",
                 ]},
            ],
        },
    },
    "북극항로 (아시아-유럽, 북동항로)": {
        "id": "arctic",
        "news_keyword": "Arctic Northern Sea Route",
        "is_arctic": True,
        "ship_location": {"lat": 73.0, "lon": 100.0, "name": "북극해 러시아 연안 항로 구간"},
        "threat_zone": {"lat": 76.0, "lon": 90.0, "name": "해빙/제재 리스크 구역 (러시아 관할)"},
        "weather_points": [(76.0, 90.0), (72.0, 130.0)],
        "ais_box": {"lat": (70.0, 78.0), "lon": (60.0, 140.0)},
        "scenario": {
            "title": "부산항 → 로테르담항 (북극항로 vs 수에즈)",
            "options": [
                {"id": "arctic_base", "route_name": "현 항로 유지: 북극항로(북동항로)",
                 "path": BUSAN_TO_ROTTERDAM_NSR,
                 "note": "해빙 상태에 따라 쇄빙선 지원이 필요합니다. 지원료는 '기타 비용'에 입력하세요.",
                 "references": []},
                {"id": "arctic_suez", "route_name": "수에즈 / 홍해 경유",
                 "path": _join(BUSAN_TO_SINGAPORE, SINGAPORE_TO_SRI_LANKA, SRI_LANKA_TO_ADEN, ADEN_TO_PORT_SAID,
                               PORT_SAID_TO_GIBRALTAR, GIBRALTAR_TO_ROTTERDAM),
                 "note": "연중 운항 가능하지만 홍해 위험 구역을 지납니다.",
                 "references": [
                     "Port Economics: 상하이→로테르담 수에즈 경유 약 10,600해리, 16노트·무기항 약 27일",
                 ]},
            ],
        },
    },
}

ROUTES_BY_ID = {data["id"]: (key, data) for key, data in ROUTE_DB.items()}

# 세계 지도에 그릴 표준 항로 = 각 시나리오의 '현 항로 유지' 경로
for _data in ROUTE_DB.values():
    _base = _data["scenario"]["options"][0]["path"]
    _data["standard_path"] = {"lat": [p[0] for p in _base], "lon": [p[1] for p in _base]}


def get_arctic_season_info():
    """북극항로 계절별 항해 난이도 → 지정학/계절 지수 (기존 로직 유지, 월별 등급 구분은 가정값)"""
    month = datetime.now().month
    if month in [8, 9]:
        return 1, "해빙 최소기 — 항해 최적 시즌 (쇄빙선 지원 없이도 가능)"
    elif month in [7, 10]:
        return 2, "해빙 감소기 — 항해 가능하나 쇄빙선 에스코트 권장"
    elif month in [6, 11]:
        return 4, "해빙 전환기 — 항해 난도 급상승, 쇄빙선 필수"
    else:
        return 5, "결빙기 (12~5월) — 두꺼운 해빙으로 상업 운항 사실상 불가"
