"""저장소: 신호 기록, 선박 위치, 등록 운항, 알림 기록

DATABASE_URL 환경변수가 있으면 Postgres(Neon), 없으면 로컬 SQLite 파일(monitor.db)을 씁니다.
GitHub Actions(수집)와 Streamlit(화면)이 같은 Neon DB 를 봅니다.
쿼리는 두 DB 모두에서 도는 문법만 쓰고, 자리표시자 ? 는 Postgres 일 때 %s 로 바꿉니다.
"""
import atexit
import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

DATABASE_URL = os.getenv("DATABASE_URL")
USE_PG = bool(DATABASE_URL)
SQLITE_PATH = Path(os.getenv("MONITOR_DB_PATH", Path(__file__).resolve().parent / "monitor.db"))

_lock = threading.Lock()
_initialized = False
_pool = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS gdelt_hourly (
    strait_id TEXT NOT NULL,
    hour TEXT NOT NULL,            -- UTC 'YYYY-MM-DD HH'
    events INTEGER NOT NULL,       -- 갈등 사건 수 (QuadClass 3·4)
    material INTEGER NOT NULL,     -- 그중 물리적 충돌 (QuadClass 4)
    goldstein REAL NOT NULL,       -- Goldstein 척도 합 (음수일수록 갈등)
    PRIMARY KEY (strait_id, hour)
);
CREATE TABLE IF NOT EXISTS strait_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strait_id TEXT NOT NULL,
    computed_at TEXT NOT NULL,
    level INTEGER,
    data TEXT NOT NULL             -- 판단 근거 전체 (JSON)
);
CREATE TABLE IF NOT EXISTS kv_store (
    name TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ships (
    mmsi TEXT PRIMARY KEY,
    name TEXT, lat REAL, lon REAL, sog REAL, cog REAL, heading REAL,
    destination TEXT,
    seen_at TEXT
);
CREATE TABLE IF NOT EXISTS tracks (
    mmsi TEXT NOT NULL,
    seen_at TEXT NOT NULL,
    lat REAL NOT NULL, lon REAL NOT NULL, sog REAL, cog REAL,
    PRIMARY KEY (mmsi, seen_at)
);
CREATE TABLE IF NOT EXISTS voyages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ship_name TEXT NOT NULL,
    mmsi TEXT,
    origin TEXT NOT NULL,
    dest TEXT NOT NULL,
    speed_kn REAL NOT NULL,
    recipients TEXT NOT NULL,
    created_at TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    last_eval TEXT,
    alert_state TEXT
);
CREATE TABLE IF NOT EXISTS alert_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target TEXT NOT NULL,          -- 'strait:hormuz' / 'voyage:3'
    sent_at TEXT NOT NULL,
    level INTEGER,
    status TEXT NOT NULL,          -- sent / failed / not_configured
    detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_status_strait_time ON strait_status(strait_id, computed_at);
CREATE INDEX IF NOT EXISTS idx_ships_name ON ships(name);
"""


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _pg_schema():
    return (SCHEMA.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
            .replace(" REAL", " DOUBLE PRECISION"))


class _PgConn:
    """psycopg 연결을 sqlite3 처럼 쓰기 위한 얇은 래퍼 (? → %s)"""

    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, params=()):
        return self.conn.execute(sql.replace("?", "%s"), params)

    def executemany(self, sql, rows):
        with self.conn.cursor() as cur:
            cur.executemany(sql.replace("?", "%s"), rows)


@contextmanager
def _connect_pg():
    global _pool, _initialized
    if _pool is None:
        with _lock:
            if _pool is None:
                from psycopg.rows import dict_row
                from psycopg_pool import ConnectionPool
                # min_size=0: 쉬는 동안 연결을 닫아 Neon 이 절전(무료 사용 시간 절약)할 수 있게 함
                _pool = ConnectionPool(DATABASE_URL, open=True, min_size=0, max_size=4, max_idle=120,
                                       kwargs={"row_factory": dict_row}, check=ConnectionPool.check_connection)
                atexit.register(_pool.close)
    with _pool.connection() as conn:
        if not _initialized:
            with _lock:
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
    conn = sqlite3.connect(SQLITE_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        if not _initialized:
            with _lock:
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


# ---------------- JSON 묶음 (캐시·진행 상태) ----------------
def load_blob(name):
    with connect() as c:
        row = c.execute("SELECT data, updated_at FROM kv_store WHERE name=?", (name,)).fetchone()
    return (json.loads(row["data"]), row["updated_at"]) if row else (None, None)


def save_blob(name, obj):
    with connect() as c:
        c.execute("""INSERT INTO kv_store VALUES (?,?,?) ON CONFLICT (name)
                     DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at""",
                  (name, json.dumps(obj, ensure_ascii=False), now_str()))


# ---------------- GDELT 시간별 사건 수 ----------------
def add_gdelt_counts(rows):
    """rows: [(strait_id, hour, events, material, goldstein)] — 같은 시간대는 더함"""
    with connect() as c:
        c.executemany("""INSERT INTO gdelt_hourly VALUES (?,?,?,?,?) ON CONFLICT (strait_id, hour) DO UPDATE SET
                         events=gdelt_hourly.events+excluded.events, material=gdelt_hourly.material+excluded.material,
                         goldstein=gdelt_hourly.goldstein+excluded.goldstein""", rows)


def gdelt_hours(strait_id, since_hour):
    with connect() as c:
        rows = c.execute("SELECT hour, events, material, goldstein FROM gdelt_hourly WHERE strait_id=? AND hour>=? "
                         "ORDER BY hour", (strait_id, since_hour)).fetchall()
    return [dict(r) for r in rows]


# ---------------- 해협 신호등 기록 ----------------
def save_status(strait_id, level, data):
    with connect() as c:
        c.execute("INSERT INTO strait_status (strait_id, computed_at, level, data) VALUES (?,?,?,?)",
                  (strait_id, now_str(), level, json.dumps(data, ensure_ascii=False)))


def latest_status(strait_id):
    with connect() as c:
        row = c.execute("SELECT * FROM strait_status WHERE strait_id=? ORDER BY computed_at DESC, id DESC LIMIT 1",
                        (strait_id,)).fetchone()
    return _row(row, ("data",))


def status_history(strait_id, days=30):
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    with connect() as c:
        rows = c.execute("SELECT computed_at, level FROM strait_status WHERE strait_id=? AND computed_at>=? "
                         "ORDER BY computed_at", (strait_id, since)).fetchall()
    return [dict(r) for r in rows]


# ---------------- 선박 위치 ----------------
def upsert_ships(rows):
    """rows: [(mmsi, name, lat, lon, sog, cog, heading, destination, seen_at)] — 비어 있는 값은 기존 값 유지"""
    with connect() as c:
        c.executemany("""INSERT INTO ships VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT (mmsi) DO UPDATE SET
                         name=COALESCE(NULLIF(excluded.name, ''), ships.name),
                         lat=COALESCE(excluded.lat, ships.lat), lon=COALESCE(excluded.lon, ships.lon),
                         sog=COALESCE(excluded.sog, ships.sog), cog=COALESCE(excluded.cog, ships.cog),
                         heading=COALESCE(excluded.heading, ships.heading),
                         destination=COALESCE(NULLIF(excluded.destination, ''), ships.destination),
                         seen_at=CASE WHEN excluded.lat IS NULL THEN ships.seen_at ELSE excluded.seen_at END""", rows)


def add_tracks(rows):
    """rows: [(mmsi, seen_at, lat, lon, sog, cog)]"""
    with connect() as c:
        c.executemany("INSERT INTO tracks VALUES (?,?,?,?,?,?) ON CONFLICT DO NOTHING", rows)


def get_ship(mmsi):
    with connect() as c:
        return _row(c.execute("SELECT * FROM ships WHERE mmsi=?", (mmsi,)).fetchone())


def search_ships(text, limit=20):
    q = f"%{text.strip().upper()}%"
    with connect() as c:
        rows = c.execute("SELECT * FROM ships WHERE UPPER(name) LIKE ? OR mmsi LIKE ? ORDER BY seen_at DESC LIMIT ?",
                         (q, q, limit)).fetchall()
    return [dict(r) for r in rows]


def get_tracks(mmsi, limit=200):
    with connect() as c:
        rows = c.execute("SELECT * FROM tracks WHERE mmsi=? ORDER BY seen_at DESC LIMIT ?", (mmsi, limit)).fetchall()
    return [dict(r) for r in reversed(rows)]


def prune(ship_days=30, track_days=90, gdelt_days=400, status_days=35):
    """오래된 기록 정리 (무료 DB 용량 유지)"""
    def ago(d, fmt="%Y-%m-%d %H:%M:%S"):
        return (datetime.now() - timedelta(days=d)).strftime(fmt)
    with connect() as c:
        c.execute("DELETE FROM ships WHERE seen_at < ? AND mmsi NOT IN (SELECT mmsi FROM voyages WHERE active=1 "
                  "AND mmsi IS NOT NULL)", (ago(ship_days),))
        c.execute("DELETE FROM tracks WHERE seen_at < ?", (ago(track_days),))
        c.execute("DELETE FROM gdelt_hourly WHERE hour < ?", (ago(gdelt_days, "%Y-%m-%d %H"),))
        c.execute("DELETE FROM strait_status WHERE computed_at < ?", (ago(status_days),))


# ---------------- 운항 ----------------
def add_voyage(ship_name, mmsi, origin, dest, speed_kn, recipients):
    with connect() as c:
        cur = c.execute("""INSERT INTO voyages (ship_name, mmsi, origin, dest, speed_kn, recipients, created_at, alert_state)
                           VALUES (?,?,?,?,?,?,?,'{}') RETURNING id""",
                        (ship_name, mmsi, origin, dest, speed_kn, recipients, now_str()))
        return cur.fetchone()["id"]


def get_voyage(voyage_id):
    with connect() as c:
        return _row(c.execute("SELECT * FROM voyages WHERE id=?", (voyage_id,)).fetchone(), ("last_eval", "alert_state"))


def list_voyages(active_only=True):
    q = "SELECT * FROM voyages" + (" WHERE active=1" if active_only else "") + " ORDER BY id DESC"
    with connect() as c:
        return [_row(r, ("last_eval", "alert_state")) for r in c.execute(q).fetchall()]


def save_voyage_eval(voyage_id, evaluation, alert_state=None):
    with connect() as c:
        if alert_state is None:
            c.execute("UPDATE voyages SET last_eval=? WHERE id=?",
                      (json.dumps(evaluation, ensure_ascii=False), voyage_id))
        else:
            c.execute("UPDATE voyages SET last_eval=?, alert_state=? WHERE id=?",
                      (json.dumps(evaluation, ensure_ascii=False), json.dumps(alert_state, ensure_ascii=False),
                       voyage_id))


def end_voyage(voyage_id):
    with connect() as c:
        c.execute("UPDATE voyages SET active=0 WHERE id=?", (voyage_id,))


def tracked_mmsis():
    with connect() as c:
        rows = c.execute("SELECT DISTINCT mmsi FROM voyages WHERE active=1 AND mmsi IS NOT NULL").fetchall()
    return [r["mmsi"] for r in rows]


# ---------------- 알림 기록 ----------------
def log_alert(target, level, status, detail=None):
    with connect() as c:
        c.execute("INSERT INTO alert_log (target, sent_at, level, status, detail) VALUES (?,?,?,?,?)",
                  (target, now_str(), level, status, detail))


def recent_alerts(target, limit=5):
    with connect() as c:
        rows = c.execute("SELECT * FROM alert_log WHERE target=? ORDER BY sent_at DESC, id DESC LIMIT ?",
                         (target, limit)).fetchall()
    return [dict(r) for r in rows]
