"""저장소: 수집 지표, 위험 점수 기록, 지정학 지수 수정값, 비용 입력값, 알림 기록

DATABASE_URL 환경변수가 있으면 Postgres(배포용, 예: Neon), 없으면 로컬 SQLite 파일을 씁니다.
쿼리는 두 DB 모두에서 도는 문법만 쓰고, 자리표시자 ? 는 Postgres 일 때 %s 로 바꿉니다.
"""
import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from decimal import Decimal

from settings import DATABASE_URL, DB_PATH

USE_PG = bool(DATABASE_URL)

_init_lock = threading.Lock()
_initialized = False

SCHEMA = """
CREATE TABLE IF NOT EXISTS news_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strait_id TEXT NOT NULL,
    collected_at TEXT NOT NULL,
    count_7d INTEGER, count_prev7d INTEGER, count_30d INTEGER,
    sample_size INTEGER, strong_count INTEGER,
    keyword_multiplier REAL, strong_share REAL,
    issue_hits TEXT, top_articles TEXT, error TEXT
);
CREATE TABLE IF NOT EXISTS risk_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strait_id TEXT NOT NULL,
    computed_at TEXT NOT NULL,
    level INTEGER NOT NULL, score REAL NOT NULL,
    indicators TEXT NOT NULL,      -- 원 지표값 (JSON)
    contributions TEXT NOT NULL,   -- 지표별 기여 점수 (JSON)
    errors TEXT
);
CREATE TABLE IF NOT EXISTS ais_snapshots (
    strait_id TEXT NOT NULL,
    snapshot_time TEXT NOT NULL,
    ship_count INTEGER, avg_speed REAL,
    PRIMARY KEY (strait_id, snapshot_time)
);
CREATE TABLE IF NOT EXISTS geo_overrides (
    strait_id TEXT PRIMARY KEY,
    level INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cost_inputs (
    scenario_id TEXT PRIMARY KEY,
    inputs TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alert_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strait_id TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    from_level INTEGER, to_level INTEGER,
    status TEXT NOT NULL,          -- sent / failed / suppressed / not_configured
    detail TEXT
);
CREATE TABLE IF NOT EXISTS voyages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ship_name TEXT NOT NULL,
    mmsi TEXT,
    origin TEXT NOT NULL,
    dest TEXT NOT NULL,
    speed_kn REAL NOT NULL,
    daily_cost_usd REAL,
    recipients TEXT NOT NULL,
    created_at TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    last_eval TEXT,                -- 마지막 평가 결과 (JSON)
    last_eval_at TEXT,
    alert_state TEXT               -- 이슈별 마지막 등급·알림 기록 (JSON)
);
CREATE TABLE IF NOT EXISTS kv_store (
    name TEXT PRIMARY KEY,         -- Postgres 사용 시 AIS 스냅샷·항적 (로컬은 json 파일)
    data TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS voyage_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    voyage_id INTEGER NOT NULL,
    sent_at TEXT NOT NULL,
    level INTEGER, issues TEXT,
    status TEXT NOT NULL,          -- sent / failed / not_configured
    detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_risk_strait_time ON risk_snapshots(strait_id, computed_at);
CREATE INDEX IF NOT EXISTS idx_news_strait_time ON news_snapshots(strait_id, collected_at);
"""


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


_pool = None


def _pg_schema():
    return (SCHEMA.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
            .replace(" REAL", " DOUBLE PRECISION"))


class _PgConn:
    """psycopg 연결을 sqlite3 처럼 쓰기 위한 얇은 래퍼 (? → %s)"""

    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, params=()):
        return self.conn.execute(sql.replace("?", "%s"), params)


@contextmanager
def _connect_pg():
    global _pool, _initialized
    if _pool is None:
        with _init_lock:
            if _pool is None:
                from psycopg.rows import dict_row
                from psycopg_pool import ConnectionPool
                # min_size=0: 쉬는 동안 연결을 닫아 두어 Neon 이 절전(무료 사용 시간 절약)할 수 있게 함
                _pool = ConnectionPool(DATABASE_URL, open=True, min_size=0, max_size=4, max_idle=120,
                                       kwargs={"row_factory": dict_row}, check=ConnectionPool.check_connection)
    with _pool.connection() as conn:
        if not _initialized:
            with _init_lock:
                for stmt in _pg_schema().split(";"):
                    if stmt.strip():
                        conn.execute(stmt)
                _initialized = True
        yield _PgConn(conn)  # 블록이 정상 종료되면 commit, 예외면 rollback


@contextmanager
def connect():
    if USE_PG:
        with _connect_pg() as c:
            yield c
        return
    global _initialized
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        if not _initialized:
            with _init_lock:
                conn.executescript(SCHEMA)
                conn.execute("PRAGMA journal_mode=WAL")
                _initialized = True
        yield conn
        conn.commit()
    finally:
        conn.close()


def _row(row, json_fields=()):
    if row is None:
        return None
    d = dict(row)
    for k in json_fields:
        if d.get(k):
            d[k] = json.loads(d[k])
    return d


# ---------------- 뉴스 ----------------
def save_news_snapshot(strait_id, data):
    with connect() as c:
        c.execute(
            """INSERT INTO news_snapshots (strait_id, collected_at, count_7d, count_prev7d, count_30d,
               sample_size, strong_count, keyword_multiplier, strong_share, issue_hits, top_articles, error)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (strait_id, now_str(), data.get("count_7d"), data.get("count_prev7d"), data.get("count_30d"),
             data.get("sample_size"), data.get("strong_count"), data.get("keyword_multiplier"),
             data.get("strong_share"), json.dumps(data.get("issue_hits") or {}, ensure_ascii=False),
             json.dumps(data.get("top_articles") or [], ensure_ascii=False), data.get("error")))


def latest_news(strait_id, successful_only=True):
    q = "SELECT * FROM news_snapshots WHERE strait_id=?"
    if successful_only:
        q += " AND error IS NULL"
    q += " ORDER BY collected_at DESC, id DESC LIMIT 1"
    with connect() as c:
        return _row(c.execute(q, (strait_id,)).fetchone(), ("issue_hits", "top_articles"))


# ---------------- 위험 점수 ----------------
def save_risk_snapshot(strait_id, level, score, indicators, contributions, errors):
    with connect() as c:
        c.execute(
            """INSERT INTO risk_snapshots (strait_id, computed_at, level, score, indicators, contributions, errors)
               VALUES (?,?,?,?,?,?,?)""",
            (strait_id, now_str(), level, score, json.dumps(indicators, ensure_ascii=False),
             json.dumps(contributions, ensure_ascii=False), json.dumps(errors, ensure_ascii=False)))


def latest_risk(strait_id):
    with connect() as c:
        row = c.execute("SELECT * FROM risk_snapshots WHERE strait_id=? ORDER BY computed_at DESC, id DESC LIMIT 1",
                        (strait_id,)).fetchone()
    return _row(row, ("indicators", "contributions", "errors"))


def risk_history(strait_id, days):
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    with connect() as c:
        rows = c.execute("""SELECT computed_at, level, score, contributions FROM risk_snapshots
                            WHERE strait_id=? AND computed_at>=? ORDER BY computed_at""",
                         (strait_id, since)).fetchall()
    return [_row(r, ("contributions",)) for r in rows]


# ---------------- AIS ----------------
def save_ais_snapshot(strait_id, snapshot_time, ship_count, avg_speed):
    """같은 스냅샷(ship_data.json의 updated_at)은 한 번만 저장. 새로 저장했으면 True"""
    with connect() as c:
        cur = c.execute("INSERT INTO ais_snapshots VALUES (?,?,?,?) ON CONFLICT DO NOTHING",
                        (strait_id, snapshot_time, ship_count, avg_speed))
        return cur.rowcount > 0


def ais_baseline(strait_id, before, days=30):
    """before 이전 days일 동안의 평균 선박 수 / 평균 속도와 기록 수"""
    since = (datetime.strptime(before, "%Y-%m-%d %H:%M:%S") - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    with connect() as c:
        row = c.execute("""SELECT AVG(ship_count) AS cnt, AVG(avg_speed) AS spd, COUNT(*) AS n FROM ais_snapshots
                           WHERE strait_id=? AND snapshot_time<? AND snapshot_time>=?""",
                        (strait_id, before, since)).fetchone()
    # Postgres 의 AVG 는 Decimal 을 돌려주므로 float 로 맞춤
    return {k: float(v) if isinstance(v, Decimal) else v for k, v in dict(row).items()}


# ---------------- 지정학 지수 수정값 ----------------
def get_geo_override(strait_id):
    with connect() as c:
        return _row(c.execute("SELECT * FROM geo_overrides WHERE strait_id=?", (strait_id,)).fetchone())


def set_geo_override(strait_id, level):
    with connect() as c:
        c.execute("""INSERT INTO geo_overrides VALUES (?,?,?) ON CONFLICT (strait_id)
                     DO UPDATE SET level=excluded.level, updated_at=excluded.updated_at""",
                  (strait_id, level, now_str()))


def clear_geo_override(strait_id):
    with connect() as c:
        c.execute("DELETE FROM geo_overrides WHERE strait_id=?", (strait_id,))


# ---------------- 비용 입력값 ----------------
def get_cost_inputs(scenario_id):
    with connect() as c:
        return _row(c.execute("SELECT * FROM cost_inputs WHERE scenario_id=?", (scenario_id,)).fetchone(),
                    ("inputs",))


def save_cost_inputs(scenario_id, inputs):
    with connect() as c:
        c.execute("""INSERT INTO cost_inputs VALUES (?,?,?) ON CONFLICT (scenario_id)
                     DO UPDATE SET inputs=excluded.inputs, updated_at=excluded.updated_at""",
                  (scenario_id, json.dumps(inputs, ensure_ascii=False), now_str()))


# ---------------- 알림 기록 ----------------
def log_alert(strait_id, from_level, to_level, status, detail=None):
    with connect() as c:
        c.execute("INSERT INTO alert_log (strait_id, sent_at, from_level, to_level, status, detail) VALUES (?,?,?,?,?,?)",
                  (strait_id, now_str(), from_level, to_level, status, detail))


def last_sent_alert(strait_id):
    with connect() as c:
        return _row(c.execute("""SELECT * FROM alert_log WHERE strait_id=? AND status='sent'
                                 ORDER BY sent_at DESC, id DESC LIMIT 1""", (strait_id,)).fetchone())


def recent_alerts(limit=10):
    with connect() as c:
        return [dict(r) for r in c.execute("SELECT * FROM alert_log ORDER BY sent_at DESC, id DESC LIMIT ?",
                                           (limit,)).fetchall()]


# ---------------- 운항 ----------------
def add_voyage(ship_name, mmsi, origin, dest, speed_kn, daily_cost_usd, recipients):
    with connect() as c:
        cur = c.execute("""INSERT INTO voyages (ship_name, mmsi, origin, dest, speed_kn, daily_cost_usd, recipients,
                           created_at, alert_state) VALUES (?,?,?,?,?,?,?,?,'{}') RETURNING id""",
                        (ship_name, mmsi, origin, dest, speed_kn, daily_cost_usd, recipients, now_str()))
        return cur.fetchone()["id"]


def get_voyage(voyage_id):
    with connect() as c:
        return _row(c.execute("SELECT * FROM voyages WHERE id=?", (voyage_id,)).fetchone(),
                    ("last_eval", "alert_state"))


def list_voyages(active_only=True):
    q = "SELECT * FROM voyages" + (" WHERE active=1" if active_only else "") + " ORDER BY id DESC"
    with connect() as c:
        return [_row(r, ("last_eval", "alert_state")) for r in c.execute(q).fetchall()]


def save_voyage_eval(voyage_id, evaluation, alert_state):
    with connect() as c:
        c.execute("UPDATE voyages SET last_eval=?, last_eval_at=?, alert_state=? WHERE id=?",
                  (json.dumps(evaluation, ensure_ascii=False), now_str(),
                   json.dumps(alert_state, ensure_ascii=False), voyage_id))


def end_voyage(voyage_id):
    with connect() as c:
        c.execute("UPDATE voyages SET active=0 WHERE id=?", (voyage_id,))


def log_voyage_alert(voyage_id, level, issues, status, detail=None):
    with connect() as c:
        c.execute("INSERT INTO voyage_alerts (voyage_id, sent_at, level, issues, status, detail) VALUES (?,?,?,?,?,?)",
                  (voyage_id, now_str(), level, issues, status, detail))


def voyage_alerts(voyage_id, limit=5):
    with connect() as c:
        return [dict(r) for r in c.execute("""SELECT * FROM voyage_alerts WHERE voyage_id=?
                                              ORDER BY sent_at DESC, id DESC LIMIT ?""", (voyage_id, limit)).fetchall()]


# ---------------- JSON 묶음 (Postgres 사용 시 AIS 스냅샷·항적) ----------------
def load_blob(name):
    with connect() as c:
        row = c.execute("SELECT data FROM kv_store WHERE name=?", (name,)).fetchone()
    return json.loads(row["data"]) if row else None


def save_blob(name, obj):
    with connect() as c:
        c.execute("""INSERT INTO kv_store VALUES (?,?,?) ON CONFLICT (name)
                     DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at""",
                  (name, json.dumps(obj, ensure_ascii=False), now_str()))
