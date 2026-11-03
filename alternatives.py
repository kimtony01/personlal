"""대체 항로 비교: 거리·일수 계산과 사용자 입력 비용값으로 총비용·순위 산출

총비용 = 해상 일수 × (일일 용선료 + 일일 연료 소모량 × 연료 단가)
       + 선체가액 × 전쟁위험 보험료율
       + 기타 비용(운하 통항료, 파이프라인 이용료, 철도비 등)
"""
import math
from datetime import datetime

import db
from route_data import ROUTES_BY_ID
from settings import CONFIG

EARTH_RADIUS_NM = 3440.065

# 화면 입력칸 정의 (시나리오 공통)
SCENARIO_FIELDS = [
    ("charter_usd_day", "일일 용선료 (USD/일)"),
    ("fuel_usd_t", "연료 단가 (USD/톤)"),
    ("fuel_t_day", "일일 연료 소모량 (톤/일)"),
    ("hull_value_usd", "선체가액 (USD, 보험료 계산용)"),
]
# 대안별 입력칸
OPTION_FIELDS = [
    ("war_risk_pct", "전쟁위험 보험료율 (%)"),
    ("extra_usd", "기타 비용 (USD)"),
]


def haversine_nm(p1, p2):
    lat1, lon1, lat2, lon2 = map(math.radians, (*p1, *p2))
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_NM * math.asin(math.sqrt(a))


def path_distance_nm(path):
    return sum(haversine_nm(a, b) for a, b in zip(path, path[1:]))


def default_inputs(scenario_id):
    cfg = CONFIG["scenario"][scenario_id]
    return {
        **{k: cfg[k] for k, _ in SCENARIO_FIELDS},
        "options": {oid: dict(v) for oid, v in cfg["options"].items()},
    }


def load_inputs(scenario_id):
    """마지막 저장값(있으면) 또는 config.toml 가정값. (입력값, 저장일시 or None)"""
    saved = db.get_cost_inputs(scenario_id)
    inputs = default_inputs(scenario_id)
    if not saved:
        return inputs, None
    stored = saved["inputs"]
    for k, _ in SCENARIO_FIELDS:
        if k in stored:
            inputs[k] = stored[k]
    for oid, vals in stored.get("options", {}).items():
        if oid in inputs["options"]:
            inputs["options"][oid].update(vals)
    return inputs, saved["updated_at"]


def sanitize_inputs(scenario_id, raw):
    """요청으로 받은 값 검증: 숫자이고 0 이상인 값만 반영"""
    base = default_inputs(scenario_id)

    def num(v, fallback):
        try:
            v = float(v)
        except (TypeError, ValueError):
            return fallback
        return v if math.isfinite(v) and v >= 0 else fallback

    clean = {k: num(raw.get(k), base[k]) for k, _ in SCENARIO_FIELDS}
    clean["options"] = {}
    raw_opts = raw.get("options") or {}
    for oid, defaults in base["options"].items():
        vals = raw_opts.get(oid) or {}
        clean["options"][oid] = {k: num(vals.get(k), defaults[k]) for k, _ in OPTION_FIELDS}
    return clean


def compare(scenario_id, inputs):
    """대안별 거리·일수·비용 계산 후 총비용 오름차순 순위. 현 항로 대비 차이도 함께 계산"""
    _, route = ROUTES_BY_ID[scenario_id]
    speed = CONFIG["scenario"][scenario_id]["speed_kn"]
    daily_ship_cost = inputs["charter_usd_day"] + inputs["fuel_t_day"] * inputs["fuel_usd_t"]

    rows = []
    for i, opt in enumerate(route["scenario"]["options"]):
        o_in = inputs["options"][opt["id"]]
        dist = path_distance_nm(opt["path"])
        sea_days = dist / (speed * 24)
        land_days = opt.get("land_days", 0)
        insurance = inputs["hull_value_usd"] * o_in["war_risk_pct"] / 100
        rows.append({
            "id": opt["id"], "route_name": opt["route_name"], "note": opt["note"],
            "references": opt.get("references", []),
            "distance_nm": round(dist), "sea_days": round(sea_days, 1),
            "land_days": land_days, "total_days": round(sea_days + land_days, 1),
            "charter_usd": round(sea_days * inputs["charter_usd_day"]),
            "fuel_usd": round(sea_days * inputs["fuel_t_day"] * inputs["fuel_usd_t"]),
            "insurance_usd": round(insurance), "extra_usd": round(o_in["extra_usd"]),
            "total_usd": round(sea_days * daily_ship_cost + insurance + o_in["extra_usd"]),
            "war_risk_pct": o_in["war_risk_pct"],
            "is_base": i == 0,
        })

    base = rows[0]
    for r in rows:
        r["delta_usd"] = r["total_usd"] - base["total_usd"]
        r["delta_days"] = round(r["total_days"] - base["total_days"], 1)
    ranked = sorted(rows, key=lambda r: r["total_usd"])
    for rank, r in enumerate(ranked, 1):
        r["rank"] = rank
    return ranked


def comparison_payload(scenario_id):
    inputs, updated_at = load_inputs(scenario_id)
    return {
        "scenario_id": scenario_id,
        "speed_kn": CONFIG["scenario"][scenario_id]["speed_kn"],
        "inputs": inputs,
        "updated_at": updated_at,
        "basis_label": basis_label(updated_at),
        "rows": compare(scenario_id, inputs),
    }


def basis_label(updated_at):
    if not updated_at:
        return "저장된 입력값 없음 — config.toml 가정값 기준"
    d = datetime.strptime(updated_at, "%Y-%m-%d %H:%M:%S")
    return f"{d.month}월 {d.day}일 입력값 기준"
