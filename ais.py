"""AIS 선박 위치 수신 (aisstream.io 웹소켓)

- 전 세계 표본: 선박 이름 검색용 목록(ships)을 최신으로 유지
- 등록 선박: MMSI 로 따로 구독해 위치를 더 확실히 받고 항적(tracks)에 기록
"""
import asyncio
import json
import logging
import os
from datetime import datetime

import websockets

import db

log = logging.getLogger("ais")
STREAM_URL = "wss://stream.aisstream.io/v0/stream"


async def _stream(seconds, mmsis=None):
    """{mmsi: {name, destination, lat, lon, sog, cog, heading, seen_at}}"""
    ships = {}
    sub = {"APIKey": os.getenv("AISSTREAM_API_KEY"), "BoundingBoxes": [[[-90, -180], [90, 180]]],
           "FilterMessageTypes": ["PositionReport", "ShipStaticData"]}
    if mmsis:
        sub["FiltersShipMMSI"] = [str(m) for m in mmsis][:50]
    async with websockets.connect(STREAM_URL) as ws:
        await ws.send(json.dumps(sub))
        try:
            async with asyncio.timeout(seconds):
                async for raw in ws:
                    msg = json.loads(raw)
                    meta = msg.get("MetaData")
                    if not meta:
                        continue
                    s = ships.setdefault(str(meta["MMSI"]), {})
                    if meta.get("ShipName", "").strip():
                        s["name"] = meta["ShipName"].strip()
                    if msg["MessageType"] == "PositionReport":
                        p = msg["Message"]["PositionReport"]
                        s.update(lat=p.get("Latitude"), lon=p.get("Longitude"),
                                 sog=p.get("Sog") if (p.get("Sog") or 0) < 102.3 else None,   # 102.3 = 값 없음
                                 cog=p.get("Cog") if (p.get("Cog") or 0) < 360 else None,
                                 heading=p.get("TrueHeading") if (p.get("TrueHeading") or 0) < 360 else None,
                                 seen_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    elif msg["MessageType"] == "ShipStaticData":
                        d = msg["Message"]["ShipStaticData"]
                        s["name"] = (d.get("Name") or s.get("name") or "").strip()
                        s["destination"] = (d.get("Destination") or "").strip()
        except TimeoutError:
            pass
    return ships


def _save(ships, track=False):
    rows = [(m, s.get("name", ""), s.get("lat"), s.get("lon"), s.get("sog"), s.get("cog"), s.get("heading"),
             s.get("destination", ""), s.get("seen_at") or db.now_str()) for m, s in ships.items()]
    db.upsert_ships(rows)
    if track:
        db.add_tracks([(m, s["seen_at"], s["lat"], s["lon"], s.get("sog"), s.get("cog"))
                       for m, s in ships.items() if s.get("lat") is not None])


def collect(global_seconds, tracked_seconds):
    if not os.getenv("AISSTREAM_API_KEY"):
        log.info("AISSTREAM_API_KEY 없음 — AIS 수신 건너뜀")
        return
    ships = asyncio.run(_stream(global_seconds))
    _save(ships)
    log.info("AIS 전 세계 표본: %d척 (위치 %d척)", len(ships), sum(1 for s in ships.values() if s.get("lat")))
    mmsis = db.tracked_mmsis()
    if mmsis:
        got = asyncio.run(_stream(tracked_seconds, mmsis))
        _save(got, track=True)
        log.info("등록 선박 %d척 중 %d척 위치 수신", len(mmsis), sum(1 for s in got.values() if s.get("lat")))
        # 전 세계 표본에 잡힌 등록 선박도 항적에 남김
        _save({m: s for m, s in ships.items() if m in mmsis and s.get("lat") is not None}, track=True)
