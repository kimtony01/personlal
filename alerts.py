"""알림: 판정 등급이 올라갔을 때만 담당자에게 이메일 발송 (해협별 대기 시간 적용)"""
import smtplib
import ssl

import requests
from datetime import datetime, timedelta
from email.message import EmailMessage

import db
import settings
from alternatives import comparison_payload
from risk import LEVEL_LABEL
from settings import CONFIG


def should_alert(strait_id, prev_level, new_level):
    """(보낼지 여부, 보내지 않는 이유)"""
    if prev_level is None or new_level <= prev_level:
        return False, None
    last = db.last_sent_alert(strait_id)
    if last:
        sent_at = datetime.strptime(last["sent_at"], "%Y-%m-%d %H:%M:%S")
        in_cooldown = datetime.now() - sent_at < timedelta(hours=CONFIG["alerts"]["cooldown_hours"])
        # 대기 시간 안이라도 직전 알림보다 높은 등급이면 보냄
        if in_cooldown and new_level <= (last["to_level"] or 0):
            return False, f"대기 시간 중 (마지막 발송 {last['sent_at']})"
    return True, None


def build_message(route_key, route, prev_level, new_level, score, contributions, news):
    strait_name = route_key.split(" (")[0]
    lines = [
        f"[해상 항로 리스크 조기경보] {strait_name}: {LEVEL_LABEL[prev_level]} → {LEVEL_LABEL[new_level]}",
        "",
        f"해협: {route_key}",
        f"판정 등급: {LEVEL_LABEL[new_level]} (규칙 점수 {score} / 100)",
        f"계산 시각: {db.now_str()}",
        "",
        "■ 지표별 기여도",
    ]
    for c in contributions:
        avail = "" if c["available"] else " (데이터 없음)"
        lines.append(f"  - {c['label']}: {c['points']} / {c['max']}점 — {c['detail']}{avail}")

    lines += ["", "■ 주요 기사"]
    articles = (news or {}).get("top_articles") or []
    if articles:
        for a in articles:
            ko = a.get("title_ko") or a["title_en"]
            lines.append(f"  - {ko}")
            lines.append(f"    원문: {a['title_en']} ({a['source']}, {a['published_at']}) {a['url']}")
    else:
        lines.append("  - 수집된 기사 없음")

    payload = comparison_payload(route["id"])
    lines += ["", f"■ 대체 항로 순위 ({route['scenario']['title']}) — 비용값은 {payload['basis_label']}"]
    for r in payload["rows"]:
        rank = f"{r['rank']}위" if r["rank"] else "제외"
        lines.append(f"  {rank}. {r['route_name']}: 총 {r['total_usd']:,} USD, "
                     f"약 {r['total_days']}일 (거리 약 {r['distance_nm']:,}해리, 경유점 기반 근사값)")
    lines += ["", "※ 점수 가중치·기준점과 비용 기본값에는 가정값이 포함되어 있습니다. 자세한 내용은 README를 참고하세요."]
    subject = f"[리스크 경보] {strait_name} {LEVEL_LABEL[new_level]} 등급 (점수 {score})"
    return subject, "\n".join(lines)


def _send_brevo(subject, body, recipients):
    res = requests.post("https://api.brevo.com/v3/smtp/email", timeout=30,
                        headers={"api-key": settings.BREVO_API_KEY},
                        json={"sender": {"email": settings.SMTP_FROM}, "to": [{"email": r} for r in recipients],
                              "subject": subject, "textContent": body})
    if not res.ok:
        raise RuntimeError(f"Brevo {res.status_code}: {res.text[:200]}")


def send_email(subject, body, recipients=None):
    if settings.BREVO_API_KEY:
        return _send_brevo(subject, body, recipients or settings.ALERT_RECIPIENTS)
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM
    msg["To"] = ", ".join(recipients or settings.ALERT_RECIPIENTS)
    msg.set_content(body)

    if settings.SMTP_SECURITY == "ssl":
        server = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, context=ssl.create_default_context(),
                                  timeout=30)
    else:
        server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30)
    with server:
        if settings.SMTP_SECURITY == "starttls":
            server.starttls(context=ssl.create_default_context())
        if settings.SMTP_USER and settings.SMTP_PASSWORD:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.send_message(msg)


def notify_if_escalated(route_key, route, prev_level, new_level, score, contributions, news):
    strait_id = route["id"]
    if not CONFIG["alerts"].get("strait_alerts", False):
        return  # 해협 단위 메일은 꺼져 있음 (운항 단위 경고는 voyages.py)
    ok, reason = should_alert(strait_id, prev_level, new_level)
    if not ok:
        if reason:
            db.log_alert(strait_id, prev_level, new_level, "suppressed", reason)
        return
    if not settings.smtp_configured():
        db.log_alert(strait_id, prev_level, new_level, "not_configured",
                     "SMTP_HOST / SMTP_FROM(또는 SMTP_USER) / ALERT_RECIPIENTS 를 .env 에 설정하세요")
        return
    subject, body = build_message(route_key, route, prev_level, new_level, score, contributions, news)
    try:
        send_email(subject, body)
        db.log_alert(strait_id, prev_level, new_level, "sent", ", ".join(settings.ALERT_RECIPIENTS))
    except Exception as e:
        db.log_alert(strait_id, prev_level, new_level, "failed", str(e))


def send_test_alert(route_id="hormuz"):
    """SMTP 설정 확인용: 저장된 최신 계산값으로 실제 경보와 같은 형식의 메일을 보냄 (등급 변화와 무관)"""
    from route_data import ROUTES_BY_ID
    route_key, route = ROUTES_BY_ID[route_id]
    latest = db.latest_risk(route_id)
    if not latest:
        raise RuntimeError("저장된 위험 계산 결과가 없습니다. 서버를 한 번 실행한 뒤 다시 시도하세요.")
    subject, body = build_message(route_key, route, latest["level"], latest["level"], latest["score"],
                                  latest["contributions"], db.latest_news(route_id))
    send_email("[테스트] " + subject, "※ 설정 확인용 테스트 메일입니다. 실제 등급 변화는 없습니다.\n\n" + body)


if __name__ == "__main__":
    # 메일 설정 확인: python alerts.py --test
    import sys
    if "--test" in sys.argv:
        if not settings.smtp_configured():
            sys.exit("SMTP_HOST / SMTP_FROM / ALERT_RECIPIENTS 가 .env 에 없습니다.")
        send_test_alert()
        print("테스트 메일 발송 완료:", ", ".join(settings.ALERT_RECIPIENTS))
