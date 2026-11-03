"""30분마다 1회 실행 (GitHub Actions): 수집 → 해협 신호등 판단 → 운항 감시 → 경보 메일

실행: python monitor.py
결과는 DB(Neon)에 저장되고, Streamlit 화면은 저장된 결과를 읽어 보여 줍니다.
"""
import logging
import tomllib
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import ais  # noqa: E402  (dotenv 로 환경변수를 먼저 읽은 뒤 import)
import db  # noqa: E402
import mailer  # noqa: E402
import rules  # noqa: E402
import signals  # noqa: E402
import voyages  # noqa: E402
from straits import LEVELS, STRAITS  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("monitor")
with open(Path(__file__).resolve().parent / "config.toml", "rb") as f:
    CONFIG = tomllib.load(f)


def collect_strait(sid, official, gdacs, errors):
    """판단에 쓰는 원래 값 (화면에서 기준을 바꿔 다시 판단할 수 있도록 그대로 저장)"""
    th = CONFIG["rules"]
    raw = {"official": official.get(sid, {})}
    windows, material = signals.news_windows(sid)
    raw["news_windows"], raw["news_material"] = windows, material
    try:
        raw["traffic"] = signals.traffic_signal(signals.portwatch_series(STRAITS[sid]["portwatch"]))
    except Exception as e:
        raw["traffic"] = None
        errors[f"traffic:{sid}"] = str(e)
    raw["disasters"] = (None if gdacs is None else
                        signals.disaster_hits(sid, gdacs, th["disaster_tc_km"], th["disaster_eq_km"]))
    return raw


def strait_alert(sid, ev, state):
    if not voyages.should_send(state, sid, ev["level"] or 0, CONFIG["alerts"]["cooldown_hours"]):
        return
    target, recipients = f"strait:{sid}", mailer.default_recipients()
    if not (mailer.configured() and recipients):
        db.log_alert(target, ev["level"], "not_configured", "메일 설정 또는 수신자 없음")
        return
    lv = LEVELS[ev["level"]]["label"]
    body = "\n".join([f"[항로 조기경보] {STRAITS[sid]['name']}: {lv}", ""] +
                     [f"- {r['text']}" + (f" ({r['url']})" if r.get("url") else "") for r in ev["reasons"]] +
                     ["", "대시보드: https://maritime-route-risk.streamlit.app/"])
    try:
        mailer.send(f"[해협 경보] {STRAITS[sid]['name']} {lv}", body, recipients)
        db.log_alert(target, ev["level"], "sent", ", ".join(recipients))
    except Exception as e:
        db.log_alert(target, ev["level"], "failed", str(e))


def main():
    errors = {}
    for name, step in (("ais", lambda: ais.collect(CONFIG["ais"]["global_seconds"], CONFIG["ais"]["tracked_seconds"])),
                       ("gdelt", signals.update_gdelt)):
        try:
            step()
        except Exception as e:
            log.exception("%s 실패", name)
            errors[name] = str(e)
    try:
        gdacs = signals.gdacs_events()
    except Exception as e:
        log.exception("GDACS 실패")
        gdacs, errors["gdacs"] = None, str(e)
    official = signals.load_official()

    state, _ = db.load_blob("strait_alert_state")
    state = state or {}
    for sid in STRAITS:
        raw = collect_strait(sid, official, gdacs, errors)
        ev = rules.evaluate(raw, CONFIG["rules"])
        db.save_status(sid, ev["level"], {"raw": raw, "eval": ev,
                                          "errors": {k: v for k, v in errors.items() if ":" not in k or k.endswith(sid)}})
        log.info("%s: %s — %s", sid, LEVELS[ev["level"]]["label"], rules.headline(ev))
        strait_alert(sid, ev, state)
    db.save_blob("strait_alert_state", state)

    voyages.check_all(CONFIG["alerts"]["cooldown_hours"], CONFIG["ais"]["position_max_age_hours"],
                      CONFIG["voyage"]["max_detour_ratio"])
    db.prune()


if __name__ == "__main__":
    main()
