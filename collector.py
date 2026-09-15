import asyncio
import websockets
import json
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("AISSTREAM_API_KEY")
print("API KEY:", API_KEY)

BOUNDING_BOX = [[-90, -180], [90, 180]]

async def collect_and_save():
    ships_data = {}

    async with websockets.connect("wss://stream.aisstream.io/v0/stream") as websocket:
        subscribe_message = {
            "APIKey": API_KEY,
            "BoundingBoxes": [BOUNDING_BOX],
            "FilterMessageTypes": ["PositionReport", "ShipStaticData"]
        }
        print("전송하는 구독 메시지:", json.dumps(subscribe_message))
        await websocket.send(json.dumps(subscribe_message))

        try:
            async with asyncio.timeout(120):
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

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ---- 위치 이력 누적 저장 ----
    history = {}
    if os.path.exists("ship_history.json"):
        try:
            with open("ship_history.json", "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = {}

    for mmsi, info in ships_data.items():
        if "lat" not in info or "lon" not in info:
            continue
        if mmsi not in history:
            history[mmsi] = {"name": info.get("name", ""), "track": []}
        history[mmsi]["track"].append({
            "lat": info["lat"], "lon": info["lon"], "time": now_str
        })
        history[mmsi]["track"] = history[mmsi]["track"][-50:]
        if info.get("name"):
            history[mmsi]["name"] = info["name"]

    with open("ship_history.json", "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    # ---- 현재 스냅샷 저장 ----
    result = {
        "updated_at": now_str,
        "ships": ships_data
    }
    with open("ship_data.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"저장 완료: {len(ships_data)}척, {now_str}")
    print(f"이력 누적 선박 수: {len(history)}척")

if __name__ == "__main__":
    asyncio.run(collect_and_save())