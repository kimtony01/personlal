"""해상 항로망: 주요 해역 경유점과 그 사이 항로로 이루어진 그래프

- 어떤 출발항·도착항이든 최단 해상 경로(경유점 목록)와 거리를 계산합니다.
- 항로(간선)에는 감시 해협(strait)과 통과 수로 이름(passage) 태그가 붙어 있어,
  특정 해협·구간을 빼고 다시 찾으면 그대로 '대체 노선'이 됩니다.
- 좌표와 연결은 주요 상선 항로를 단순화한 근사값입니다. 거리 = 경유점 사이 대권거리의 합.
"""
import heapq
import math

from ports import PORT_DB

EARTH_RADIUS_NM = 3440.065

# ------------------------------------------------------------------
# 경유점 (위도, 경도, 이름)
# ------------------------------------------------------------------
NODES = {
    # 동아시아
    "KS": (34.6, 129.0, "대한해협"), "YS": (36.0, 123.5, "황해"), "BH": (38.6, 120.3, "발해만 입구"),
    "ECS": (31.0, 124.5, "동중국해"), "TWN": (24.0, 119.8, "대만해협"), "LUZ": (20.5, 121.2, "루손해협"),
    "SCSN": (21.6, 115.0, "남중국해 북부(주강 하구)"), "JPS": (33.3, 135.3, "기이 수도 앞바다"),
    "TKY": (34.7, 139.9, "도쿄만 앞바다"), "JSEA": (38.5, 134.0, "동해(일본해)"), "TSG": (41.5, 141.7, "쓰가루 해협"),
    "KYUS": (30.8, 130.3, "규슈 남단"),
    # 동남아시아
    "SCSM": (12.0, 111.0, "남중국해 중부"), "TON": (19.8, 107.4, "통킹만"), "VTU": (9.6, 107.6, "붕따우 앞바다"),
    "GOT": (11.0, 101.5, "타이만"), "SGE": (1.3, 104.4, "싱가포르 해협 동쪽"), "SGW": (1.9, 102.4, "말라카 해협 남부"),
    "MALN": (5.6, 97.6, "말라카 해협 북쪽 입구"), "MNL": (14.3, 120.2, "마닐라 앞바다"),
    "SCSS": (5.5, 108.5, "남중국해 남부"), "KAR": (-2.6, 108.9, "카리마타 해협"), "JAVA": (-5.6, 110.5, "자바해"),
    "SUN": (-6.2, 105.4, "순다 해협"), "LOM": (-8.8, 115.8, "롬복 해협"), "BALI": (-7.0, 116.5, "발리해"),
    "MAK": (-2.0, 118.3, "마카사르 해협"), "CELS": (3.8, 121.5, "셀레베스해"), "MIN": (5.5, 126.8, "민다나오 동남쪽"),
    "PHE": (15.0, 128.0, "필리핀해"),
    # 인도양
    "SL": (5.7, 80.6, "스리랑카 남쪽"), "BOB": (14.5, 86.5, "벵골만"), "CMR": (7.2, 77.0, "코모린곶 앞바다"),
    "ARS": (16.0, 66.0, "아라비아해"), "ROH": (22.6, 60.3, "라스알하드 앞바다"), "GOO": (25.0, 57.6, "오만만"),
    "HRM": (26.5, 56.4, "호르무즈 해협"), "PGC": (26.4, 53.3, "페르시아만 중부"), "PGN": (28.4, 50.0, "페르시아만 북부"),
    "SOC": (12.0, 52.3, "소코트라 서쪽"), "ADEN": (12.2, 46.0, "아덴만"), "BAB": (12.6, 43.3, "바브엘만데브 해협"),
    "RSS": (15.5, 41.6, "홍해 남부"), "RSC": (21.0, 38.6, "홍해 중부"), "RSN": (27.2, 34.4, "홍해 북부"),
    "SUZ": (29.9, 32.6, "수에즈 남쪽 입구"), "PSD": (31.4, 32.4, "포트사이드 앞바다"),
    "IO8": (8.0, 73.5, "8도 해협"), "MOM": (-4.6, 40.6, "몸바사 앞바다"), "IOSE": (-10.0, 80.0, "인도양 남동부"),
    "MDGS": (-28.0, 48.0, "마다가스카르 남쪽"), "FRE": (-32.0, 114.6, "프리맨틀 앞바다"),
    # 아프리카 남부·대서양
    "DUR": (-30.3, 31.8, "더반 앞바다"), "AGL": (-36.0, 23.5, "아굴라스곶 남쪽"), "CAP": (-34.8, 17.8, "희망봉 앞바다"),
    "SATL": (-15.0, 3.0, "남대서양 동부"), "GOG": (3.5, 3.0, "기니만"), "DKR": (14.6, -17.9, "다카르 앞바다"),
    "CNR": (30.0, -14.5, "카나리아 제도 북쪽"),
    # 유럽
    "GIB": (36.0, -5.6, "지브롤터 해협"), "SVN": (36.8, -9.5, "상비센테곶"), "FIN": (43.5, -9.9, "피니스테레곶"),
    "USH": (48.7, -5.6, "우에상 섬 앞바다"), "ENG": (50.1, -1.0, "영국해협"), "DOV": (51.1, 1.6, "도버 해협"),
    "NSS": (52.3, 3.6, "북해 남부"), "GB": (54.0, 7.6, "독일만"), "SKA": (57.9, 9.8, "스카게라크"),
    "BAL": (55.4, 15.0, "발트해 남부"), "BALN": (58.6, 19.8, "발트해 북부"), "GOF": (59.9, 27.5, "핀란드만"),
    "MW": (38.6, 4.5, "서지중해"), "LIG": (43.6, 8.5, "리구리아해"), "SIC": (37.3, 11.6, "시칠리아 해협"),
    "ION": (35.2, 19.5, "이오니아해"), "CRT": (34.6, 24.5, "크레타 남쪽"), "AEG": (37.3, 24.3, "에게해"),
    "MAR": (40.7, 28.0, "마르마라해"), "EMED": (32.8, 30.5, "지중해 동부"), "ADR": (41.5, 17.5, "아드리아해 남부"),
    "ADRN": (44.8, 13.0, "아드리아해 북부"),
    # 미주
    "NYK": (40.2, -73.4, "뉴욕 앞바다"), "CHS": (36.9, -75.6, "체서피크만 입구"), "CHA": (32.0, -79.6, "찰스턴 앞바다"),
    "FLS": (25.0, -79.9, "플로리다 해협"), "MSR": (28.7, -89.2, "미시시피강 하구"), "HOU": (28.6, -94.3, "휴스턴 앞바다"),
    "YUC": (21.8, -85.9, "유카탄 해협"), "WIN": (19.9, -73.9, "윈드워드 해협"), "CAR": (13.5, -77.0, "카리브해 중부"),
    "PCN": (9.6, -79.9, "파나마 운하 카리브해 쪽"), "PCP": (8.6, -79.5, "파나마 운하 태평양 쪽"),
    "GUY": (10.5, -58.0, "남미 북동부 앞바다"), "NEB": (-6.0, -33.5, "브라질 동북단"),
    "SANT": (-24.5, -45.5, "산투스 앞바다"), "PLA": (-35.5, -55.5, "라플라타강 하구"), "HORN": (-56.8, -67.0, "케이프혼"),
    "GYE": (-3.0, -81.5, "과야킬 앞바다"), "CAL": (-12.1, -77.6, "카야오 앞바다"), "VAL": (-33.0, -72.0, "발파라이소 앞바다"),
    "MZN": (18.5, -104.8, "만사니요 앞바다"), "LAX": (33.5, -118.6, "LA 앞바다"), "SFO": (37.6, -123.0, "샌프란시스코 앞바다"),
    "JDF": (48.4, -125.0, "후안데푸카 해협 입구"), "ALU": (48.0, -170.0, "알류샨 남쪽 북태평양"),
    "HAW": (21.0, -156.0, "하와이 앞바다"), "AZO": (37.0, -30.0, "아조레스 근해"),
    # 오세아니아
    "SYD": (-34.0, 151.6, "시드니 앞바다"), "BNE": (-27.0, 153.9, "브리즈번 앞바다"), "MEL": (-38.7, 144.4, "멜버른 앞바다"),
    "ADL": (-35.6, 137.8, "애들레이드 앞바다"), "AKL": (-36.4, 175.4, "오클랜드 앞바다"),
    "SOL": (-8.0, 152.5, "솔로몬해"), "PAL": (5.0, 135.0, "팔라우 근해"),
}

# ------------------------------------------------------------------
# 항로 (경유점, 경유점, 태그). strait = 감시 해협 id, passage = 우회로 이름(대체 노선 다양화용)
# ------------------------------------------------------------------
_E = [
    # 동아시아
    ("KS", "YS"), ("YS", "BH"), ("YS", "ECS"), ("KS", "ECS"), ("ECS", "TWN"), ("TWN", "SCSN"),
    ("ECS", "LUZ"), ("LUZ", "SCSN"), ("KS", "JPS"), ("KS", "KYUS"), ("KYUS", "ECS"), ("KYUS", "JPS"),
    ("JPS", "TKY"), ("KS", "JSEA"), ("JSEA", "TSG"), ("TKY", "TSG"), ("LUZ", "PHE"), ("PHE", "TKY"),
    ("PHE", "MIN"), ("ECS", "PHE"),
    # 동남아시아
    ("SCSN", "SCSM"), ("SCSN", "TON"), ("TON", "SCSM"), ("SCSM", "VTU"), ("SCSM", "SCSS"), ("VTU", "SCSS"),
    ("SCSS", "GOT"), ("VTU", "GOT"), ("SCSS", "SGE"), ("SCSM", "MNL"), ("MNL", "LUZ"),
    ("SCSS", "KAR"), ("KAR", "JAVA"), ("JAVA", "BALI"), ("BALI", "MAK"), ("MAK", "CELS"), ("CELS", "MIN"),
    ("MIN", "PAL"), ("PAL", "PHE"), ("PAL", "SOL"),
    # 인도양
    ("SL", "CMR"), ("BOB", "MALN"), ("CMR", "IO8"), ("IO8", "ARS"), ("ARS", "ROH"), ("SL", "BOB"), ("ROH", "GOO"),
    ("IO8", "SOC"), ("ARS", "SOC"), ("SOC", "ADEN"), ("SL", "IOSE"), ("IOSE", "MDGS"), ("MDGS", "DUR"),
    ("SOC", "MOM"), ("MOM", "MDGS"), ("IOSE", "FRE"), ("FRE", "MDGS"),
    ("RSS", "RSC"), ("RSC", "RSN"), ("RSN", "SUZ"),
    # 아프리카·대서양
    ("DUR", "AGL"), ("AGL", "CAP"), ("CAP", "SATL"), ("SATL", "GOG"), ("SATL", "DKR"), ("GOG", "DKR"),
    ("DKR", "CNR"), ("CNR", "SVN"), ("CAP", "SANT"), ("SATL", "NEB"),
    # 유럽
    ("GIB", "SVN"), ("SVN", "FIN"), ("FIN", "USH"), ("USH", "ENG"), ("ENG", "DOV"), ("DOV", "NSS"),
    ("NSS", "GB"), ("NSS", "SKA"), ("GB", "SKA"), ("SKA", "BAL"), ("BAL", "BALN"), ("BALN", "GOF"),
    ("GIB", "MW"), ("MW", "LIG"), ("MW", "SIC"), ("LIG", "SIC"), ("SIC", "ION"), ("ION", "CRT"), ("ION", "ADR"),
    ("ADR", "ADRN"), ("CRT", "AEG"), ("AEG", "MAR"), ("CRT", "EMED"), ("ION", "EMED"), ("EMED", "PSD"),
    # 대서양 횡단
    ("NYK", "AZO"), ("AZO", "GIB"), ("NYK", "USH"), ("CHS", "AZO"), ("FLS", "AZO"),
    # 미주 동안·카리브
    ("NYK", "CHS"), ("CHS", "CHA"), ("CHA", "FLS"), ("FLS", "MSR"), ("MSR", "HOU"), ("FLS", "YUC"),
    ("YUC", "MSR"), ("YUC", "HOU"), ("YUC", "CAR"), ("CHS", "WIN"), ("NYK", "WIN"), ("WIN", "CAR"), ("CAR", "PCN"),
    ("CAR", "GUY"), ("WIN", "GUY"), ("GUY", "NEB"), ("NEB", "SANT"), ("SANT", "PLA"), ("PLA", "HORN"),
    ("GUY", "DKR"), ("NEB", "DKR"),
    # 미주 서안·태평양
    ("PCP", "GYE"), ("GYE", "CAL"), ("CAL", "VAL"), ("VAL", "HORN"), ("PCP", "MZN"), ("MZN", "LAX"),
    ("LAX", "SFO"), ("SFO", "JDF"), ("TSG", "ALU"), ("TKY", "ALU"), ("ALU", "JDF"), ("ALU", "SFO"), ("ALU", "LAX"),
    ("TKY", "HAW"), ("HAW", "LAX"), ("HAW", "SFO"), ("HAW", "PCP"), ("PHE", "HAW"),
    # 오세아니아
    ("SYD", "BNE"), ("SYD", "MEL"), ("MEL", "ADL"), ("ADL", "FRE"), ("SYD", "AKL"), ("BNE", "SOL"),
    ("AKL", "HAW"), ("AKL", "VAL"),
]
EDGES = [(a, b, {}) for a, b in _E] + [
    # 감시 해협
    ("PGC", "HRM", {"strait": "hormuz"}), ("HRM", "GOO", {"strait": "hormuz"}), ("PGN", "PGC", {}),
    ("ADEN", "BAB", {"strait": "suez"}), ("BAB", "RSS", {"strait": "suez"}), ("SUZ", "PSD", {"strait": "suez"}),
    ("SL", "MALN", {"strait": "malacca"}), ("MALN", "SGW", {"strait": "malacca"}), ("SGW", "SGE", {"strait": "malacca"}),
    ("PCN", "PCP", {"strait": "panama"}),
    # 우회 수로 (대체 노선 다양화용 이름)
    ("IOSE", "SUN", {"passage": "순다 해협"}), ("SUN", "JAVA", {"passage": "순다 해협"}),
    ("IOSE", "LOM", {"passage": "롬복 해협"}), ("LOM", "BALI", {"passage": "롬복 해협"}),
    ("MDGS", "AGL", {"passage": "희망봉"}), ("IOSE", "AGL", {"passage": "희망봉"}),
]

# 항구가 가장 가까운 경유점과 잘못 연결되는 경우(육지를 가로지르는 경우) 직접 지정
PORT_NODE_OVERRIDE = {
    "인천항": "YS", "평택항": "YS", "군산항": "YS", "목포항": "YS", "광양항": "KS", "부산항": "KS", "울산항": "KS",
    "칭다오항": "YS", "롄윈강항": "YS", "톈진항": "BH", "다롄항": "BH", "잉커우항": "BH",
    "상하이항": "ECS", "닝보항": "ECS", "샤먼항": "TWN", "가오슝항": "TWN", "타이중항": "TWN", "지룽항": "ECS",
    "하카타항": "KS", "오사카항": "JPS", "고베항": "JPS", "나고야항": "JPS", "요코하마항": "TKY", "도쿄항": "TKY",
    "시미즈항": "TKY", "세부항": "MNL", "수라바야항": "JAVA", "자카르타(탄중프리옥)": "JAVA", "방콕항": "GOT",
    "람차방항": "GOT", "프놈펜항": "GOT", "양곤항": "BOB", "포트클랑": "SGW", "페낭항": "MALN",
    "싱가포르항": "SGE", "탄중펠레파스항": "SGE",
    "선전항": "SCSN", "광저우항": "SCSN", "옌톈항": "SCSN", "홍콩항": "SCSN", "호치민항": "VTU", "하이퐁항": "TON",
    "다낭항": "SCSM", "마닐라항": "MNL",
    "콜카타항": "BOB", "치타공항": "BOB", "첸나이항": "BOB", "코친항": "CMR", "콜롬보항": "SL",
    "뭄바이항": "ARS", "문드라항": "ARS", "카라치항": "ARS",
    "라스타누라항": "PGN", "담맘항": "PGN", "쿠웨이트항(슈아이바)": "PGN", "아바단항": "PGN", "도하항": "PGC",
    "두바이(제벨알리)": "PGC", "반다르아바스항": "HRM", "푸자이라항": "GOO", "살랄라항": "SOC",
    "제다항": "RSC", "얀부항": "RSC", "아카바항": "RSN", "아쉬도드항": "EMED", "하이파항": "EMED",
    "알렉산드리아항": "EMED", "포트사이드항": "PSD", "몸바사항": "MOM", "더반항": "DUR", "케이프타운항": "CAP",
    "라고스항": "GOG", "아비장항": "GOG", "다카르항": "DKR", "카사블랑카항": "CNR", "탕헤르항": "GIB",
    "이스탄불항": "MAR", "피레에프스항": "AEG", "코페르항": "ADRN", "제노바항": "LIG", "라스페치아항": "LIG",
    "마르세유항": "LIG", "바르셀로나항": "MW", "발렌시아항": "MW", "알헤시라스항": "GIB", "리스본항": "SVN",
    "로테르담항": "NSS", "앤트워프항": "NSS", "함부르크항": "GB", "브레머하펜항": "GB", "르아브르항": "ENG",
    "사우샘프턴항": "ENG", "펠릭스토우항": "DOV", "런던항": "DOV", "가담스크항": "BAL", "오슬로항": "SKA",
    "고텐부르크항": "SKA", "상트페테르부르크항": "GOF",
    "뉴욕항": "NYK", "볼티모어항": "CHS", "노퍽항": "CHS", "찰스턴항": "CHA", "사바나항": "CHA", "잭슨빌항": "CHA",
    "마이애미항": "FLS", "휴스턴항": "HOU", "뉴올리언스항": "MSR",
    "로스앤젤레스항": "LAX", "롱비치항": "LAX", "오클랜드항": "SFO", "시애틀항": "JDF", "타코마항": "JDF",
    "밴쿠버항": "JDF", "만사니요항(멕시코)": "MZN", "라자로카르데나스항": "MZN",
    "산토스항": "SANT", "리우데자네이루항": "SANT", "부에노스아이레스항": "PLA", "몬테비데오항": "PLA",
    "카르타헤나항": "CAR", "카야오항": "CAL", "발파라이소항": "VAL", "과야킬항": "GYE",
    "시드니항": "SYD", "브리즈번항": "BNE", "멜버른항": "MEL", "애들레이드항": "ADL", "프리맨틀항": "FRE",
    "오클랜드항(뉴질랜드)": "AKL",
}


def haversine_nm(p1, p2):
    lat1, lon1, lat2, lon2 = map(math.radians, (p1[0], p1[1], p2[0], p2[1]))
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_NM * math.asin(math.sqrt(a))


def _pos(node):
    return NODES[node][:2]


def _graph(banned_straits=(), banned_passages=(), banned_edges=()):
    g = {}
    for a, b, tag in EDGES:
        if tag.get("strait") in banned_straits or tag.get("passage") in banned_passages:
            continue
        if (a, b) in banned_edges or (b, a) in banned_edges:
            continue
        w = haversine_nm(_pos(a), _pos(b))
        g.setdefault(a, []).append((b, w, tag))
        g.setdefault(b, []).append((a, w, tag))
    return g


def port_node(port):
    if port in PORT_NODE_OVERRIDE:
        return PORT_NODE_OVERRIDE[port]
    p = PORT_DB[port]
    return min(NODES, key=lambda n: haversine_nm((p["lat"], p["lon"]), _pos(n)))


def nearest_node(lat, lon, k=3):
    return sorted(NODES, key=lambda n: haversine_nm((lat, lon), _pos(n)))[:k]


def find_route(start, dest_port, banned_straits=(), banned_passages=(), banned_edges=()):
    """start: 항구 이름 또는 (lat, lon) 현재 위치. 경로가 없으면 None

    반환: {"points": [(lat, lon, 이름)...], "nodes": [...], "distance_nm", "straits": [순서대로], "passages": [...],
           "edges": [(a, b)...]}
    """
    g = _graph(banned_straits, banned_passages, banned_edges)
    dest_node = port_node(dest_port)
    d = PORT_DB[dest_port]
    if isinstance(start, str):
        s = PORT_DB[start]
        start_pt = (s["lat"], s["lon"], start)
        starts = [(port_node(start), 0.0)]
    else:
        start_pt = (start[0], start[1], "현재 위치")
        # 현재 위치는 가까운 경유점 3곳 중 경로가 가장 짧아지는 쪽으로 연결
        starts = [(n, haversine_nm(start, _pos(n))) for n in nearest_node(*start)]

    queue = [(w, n, [n], []) for n, w in starts if n in g or n == dest_node]
    heapq.heapify(queue)
    best = {}
    while queue:
        cost, node, path, tags = heapq.heappop(queue)
        if node == dest_node:
            break
        if best.get(node, math.inf) <= cost:
            continue
        best[node] = cost
        for nxt, w, tag in g.get(node, []):
            if nxt not in path:
                heapq.heappush(queue, (cost + w, nxt, path + [nxt], tags + [tag]))
    else:
        return None

    points = [start_pt] + [(*_pos(n), NODES[n][2]) for n in path] + [(d["lat"], d["lon"], dest_port)]
    distance = sum(haversine_nm(points[i], points[i + 1]) for i in range(len(points) - 1))
    straits, passages = [], []
    for t in tags:
        if t.get("strait") and t["strait"] not in straits:
            straits.append(t["strait"])
        if t.get("passage") and t["passage"] not in passages:
            passages.append(t["passage"])
    return {"points": points, "nodes": path, "distance_nm": round(distance), "straits": straits,
            "passages": passages, "edges": list(zip(path, path[1:]))}


def sample_route(points, step_nm=250):
    """경로를 step_nm 간격으로 나눈 지점 목록. seg = points 기준 구간 번호(points[seg] → points[seg+1])"""
    samples, travelled = [], 0.0
    next_mark = step_nm / 2
    for seg_index, ((la1, lo1, n1), (la2, lo2, n2)) in enumerate(zip(points, points[1:])):
        seg = haversine_nm((la1, lo1), (la2, lo2))
        while next_mark <= travelled + seg and seg > 0:
            f = (next_mark - travelled) / seg
            lat, lon = _interpolate(la1, lo1, la2, lo2, f)
            samples.append({"lat": round(lat, 3), "lon": round(lon, 3), "dist_nm": round(next_mark),
                            "near": n1 if f < 0.5 else n2, "seg": seg_index})
            next_mark += step_nm
        travelled += seg
    return samples


def _interpolate(lat1, lon1, lat2, lon2, f):
    """대권 위의 중간점"""
    p1, l1, p2, l2 = map(math.radians, (lat1, lon1, lat2, lon2))
    d = 2 * math.asin(math.sqrt(math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin((l2 - l1) / 2) ** 2))
    if d == 0:
        return lat1, lon1
    a, b = math.sin((1 - f) * d) / math.sin(d), math.sin(f * d) / math.sin(d)
    x = a * math.cos(p1) * math.cos(l1) + b * math.cos(p2) * math.cos(l2)
    y = a * math.cos(p1) * math.sin(l1) + b * math.cos(p2) * math.sin(l2)
    z = a * math.sin(p1) + b * math.sin(p2)
    return math.degrees(math.atan2(z, math.hypot(x, y))), math.degrees(math.atan2(y, x))
