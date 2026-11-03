"""로컬 SQLite(risk_monitor.db)와 AIS json 파일을 Postgres(Neon)로 1회 복사

실행: DATABASE_URL 을 넣고 실행 (PowerShell)
  $env:DATABASE_URL="postgresql://..."; python migrate_to_pg.py
대상 테이블이 비어 있을 때만 복사합니다 (두 번 실행해도 중복되지 않음).
"""
import json
import sqlite3
import sys

import db
from settings import DB_PATH, SHIP_DATA_PATH, SHIP_HISTORY_PATH

TABLES = ["news_snapshots", "risk_snapshots", "ais_snapshots", "geo_overrides", "cost_inputs",
          "alert_log", "voyages", "voyage_alerts"]
SERIAL_TABLES = ["news_snapshots", "risk_snapshots", "alert_log", "voyages", "voyage_alerts"]


def main():
    if not db.USE_PG:
        sys.exit("DATABASE_URL 이 없습니다.")
    src = sqlite3.connect(DB_PATH)
    src.row_factory = sqlite3.Row
    with db.connect() as c:
        for t in TABLES:
            if c.execute(f"SELECT COUNT(*) AS n FROM {t}").fetchone()["n"]:
                print(f"{t}: 이미 데이터가 있어 건너뜀")
                continue
            rows = src.execute(f"SELECT * FROM {t}").fetchall()
            if rows:
                cols = rows[0].keys()
                sql = f"INSERT INTO {t} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})"
                c.conn.cursor().executemany(sql.replace("?", "%s"), [tuple(r) for r in rows])
            print(f"{t}: {len(rows)}건")
        # id 를 직접 넣었으므로 다음 자동 번호를 맞춤
        for t in SERIAL_TABLES:
            c.execute(f"SELECT setval(pg_get_serial_sequence('{t}', 'id'), COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM {t}")
    for name, path in (("ship_data", SHIP_DATA_PATH), ("ship_history", SHIP_HISTORY_PATH)):
        if path.exists() and db.load_blob(name) is None:
            with open(path, encoding="utf-8") as f:
                db.save_blob(name, json.load(f))
            print(f"{name}: 복사")


if __name__ == "__main__":
    main()
