import asyncio
import websockets
import json
from datetime import datetime

import db
from collectors import load_ship_history
from settings import AISSTREAM_API_KEY as API_KEY, SHIP_DATA_PATH, SHIP_HISTORY_PATH

BOUNDING_BOX = [[-90, -180], [90, 180]]


async def _stream(seconds, mmsis=None):
    """AISStream 을 seconds 초 동안 구독해서 {mmsi: {name, destination, lat, lon, speed}} 반환.
    mmsis 를 주면 그 선박들만 구독 (FiltersShipMMSI, 최대 200척)"""
    ships_data = {}

    async with websockets.connect("wss://stream.aisstream.io/v0/stream") as websocket:
        subscribe_message = {
            "APIKey": API_KEY,
            "BoundingBoxes": [BOUNDING_BOX],
            "FilterMessageTypes": ["PositionReport", "ShipStaticData"]
        }
        if mmsis:
            subscribe_message["FiltersShipMMSI"] = [str(m) for m in mmsis][:200]
        await websocket.send(json.dumps(subscribe_message))

        try:
            async with asyncio.timeout(seconds):
                async for message_json in websocket:
                    message = json.loads(message_json)

                    if "error" in message:
                        print("에러 발생:", message)
                        continue

                    if "MetaData" not in message:
                        continue

                    msg_type = message["MessageType"]
                    mmsi = str(message["MetaData"]["MMSI"])

                    if mmsi not in ships_data:
                        ships_data[mmsi] = {}

                    if msg_type == "ShipStaticData":
                        data = message["Message"]["ShipStaticData"]
                        ships_data[mmsi]["name"] = data.get("Name", "").strip()
                        ships_data[mmsi]["destination"] = data.get("Destination", "").strip()

                    if msg_type == "PositionReport":
                        data = message["Message"]["PositionReport"]
                        ships_data[mmsi]["lat"] = data.get("Latitude")
                        ships_data[mmsi]["lon"] = data.get("Longitude")
                        ships_data[mmsi]["speed"] = data.get("Sog")

        except asyncio.TimeoutError:
            pass

        except Exception as e:
            print(f"연결 중 오류 발생 (그래도 지금까지 모은 데이터는 저장합니다): {e}")

    return ships_data


def _append_history(ships_data, now_str):
    history = load_ship_history()

    for mmsi, info in ships_data.items():
        if info.get("lat") is None or info.get("lon") is None:
            continue
        if mmsi not in history:
            history[mmsi] = {"name": info.get("name", ""), "track": []}
        history[mmsi]["track"].append({
            "lat": info["lat"], "lon": info["lon"], "time": now_str, "speed": info.get("speed")
        })
        history[mmsi]["track"] = history[mmsi]["track"][-50:]
        if info.get("name"):
            history[mmsi]["name"] = info["name"]

    _save("ship_history", SHIP_HISTORY_PATH, history)
    return history


def _save(name, path, obj):
    """Postgres 사용 시 DB 에, 아니면 json 파일에 저장"""
    if db.USE_PG:
        db.save_blob(name, obj)
        return
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


async def collect_and_save(seconds=120):
    """전 세계 선박 표본 수집 → ship_data.json(스냅샷) 교체 + ship_history.json 누적"""
    ships_data = await _stream(seconds)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    history = _append_history(ships_data, now_str)

    result = {
        "updated_at": now_str,
        "ships": ships_data
    }
    _save("ship_data", SHIP_DATA_PATH, result)

    print(f"저장 완료: {len(ships_data)}척, {now_str}")
    print(f"이력 누적 선박 수: {len(history)}척")


async def collect_tracked(mmsis, seconds=90):
    """등록된 운항 선박만 따로 구독 → 항적 기록에 추가 (스냅샷은 교체하지 않음). 위치를 받은 MMSI 목록 반환"""
    ships_data = await _stream(seconds, mmsis)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _append_history(ships_data, now_str)
    return [m for m, i in ships_data.items() if i.get("lat") is not None]


if __name__ == "__main__":
    asyncio.run(collect_and_save())
