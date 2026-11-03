"""
해상 항로 리스크 자동 점검 + 이메일 알림 스크립트
--------------------------------------------------
GitHub Actions에서 주기적으로 실행됩니다 (project.py와 별개로 동작).
모든 항로의 뉴스 건수를 NewsAPI로 조회해서 규칙 기반 리스크 점수를 계산하고,
임계치(45점)를 넘는 항로가 하나라도 있으면 Gmail로 알림 메일을 보냅니다.

필요한 환경변수 (GitHub Secrets로 설정):
  NEWSAPI_KEY        - NewsAPI.org API 키
  GMAIL_ADDRESS       - 보내는 사람 Gmail 주소
  GMAIL_APP_PASSWORD  - Gmail 앱 비밀번호 (16자리, 공백 없이)
  ALERT_EMAIL         - 알림 받을 이메일 주소
"""

import os
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta

import requests

NEWSAPI_KEY = os.getenv("NEWSAPI_KEY")
GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
ALERT_EMAIL = os.getenv("ALERT_EMAIL")

RISK_THRESHOLD = 45

# project.py의 ROUTE_DB에서 이메일 판단에 필요한 부분만 축약
ROUTE_DB = {
    "파나마 운하 (아시아-미주)": {
        "news_keyword": "Panama Canal",
        "standard_risk_factors": {"news_cnt": 15, "weather_dist_km": 300, "threat_level": 3},
        "is_arctic": False,
    },
    "수에즈 / 홍해 (아시아-유럽)": {
        "news_keyword": "Red Sea shipping",
        "standard_risk_factors": {"news_cnt": 28, "weather_dist_km": 800, "threat_level": 4},
        "is_arctic": False,
    },
    "호르무즈 해협 (중동-동아시아)": {
        "news_keyword": "Strait of Hormuz",
        "standard_risk_factors": {"news_cnt": 18, "weather_dist_km": 500, "threat_level": 4},
        "is_arctic": False,
    },
    "말라카 해협 (동남아-동아시아)": {
        "news_keyword": "Strait of Malacca",
        "standard_risk_factors": {"news_cnt": 4, "weather_dist_km": 120, "threat_level": 2},
        "is_arctic": False,
    },
    "북극항로 (아시아-유럽, 북동항로)": {
        "news_keyword": "Arctic Northern Sea Route",
        "standard_risk_factors": {"news_cnt": 10, "weather_dist_km": 400, "threat_level": 3},
        "is_arctic": True,
    },
}


def get_arctic_season_info():
    month = datetime.now().month
    if month in [8, 9]:
        return 1, "해빙 최소기 — 항해 최적 시즌"
    elif month in [7, 10]:
        return 2, "해빙 감소기 — 쇄빙선 에스코트 권장"
    elif month in [6, 11]:
        return 4, "해빙 전환기 — 항해 난도 급상승"
    else:
        return 5, "결빙기 (12~5월) — 상업 운항 사실상 불가"


def calc_rule_score(news_cnt, weather_dist, threat_level):
    return min(100, int((news_cnt * 1.2) + max(0, (600 - weather_dist) * 0.08) + (threat_level * 10)))


def fetch_news_count(query):
    if not NEWSAPI_KEY:
        return None
    url = "https://newsapi.org/v2/everything"
    today = datetime.now()
    try:
        params = {
            "q": query, "language": "en",
            "from": (today - timedelta(days=7)).strftime("%Y-%m-%d"),
            "to": today.strftime("%Y-%m-%d"),
            "pageSize": 1,
            "apiKey": NEWSAPI_KEY,
        }
        res = requests.get(url, params=params, timeout=10).json()
        return res.get("totalResults", 0)
    except Exception as e:
        print(f"뉴스 건수 조회 실패 ({query}): {e}")
        return None


def send_alert_email(triggered_routes):
    if not (GMAIL_ADDRESS and GMAIL_APP_PASSWORD and ALERT_EMAIL):
        print("이메일 발송 설정이 없어 건너뜁니다 (GMAIL_ADDRESS / GMAIL_APP_PASSWORD / ALERT_EMAIL 확인).")
        return

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"[해상 항로 리스크 자동 경보] {now_str} 기준\n"]
    for r in triggered_routes:
        lines.append(f"⚠ {r['route']} — 리스크 점수 {r['score']}/100 (뉴스 {r['news_cnt']}건)")
    lines.append("\n대시보드에서 상세 확인: (Streamlit Cloud URL을 여기에 적어두세요)")
    body = "\n".join(lines)

    msg = MIMEText(body)
    msg["Subject"] = f"🚨 해상 항로 리스크 경보 — {len(triggered_routes)}개 항로 임계치 초과"
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = ALERT_EMAIL

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_ADDRESS, [ALERT_EMAIL], msg.as_string())
        print(f"알림 이메일 발송 완료 → {ALERT_EMAIL}")
    except Exception as e:
        print(f"이메일 발송 실패: {e}")


def main():
    arctic_level, arctic_msg = get_arctic_season_info()
    triggered = []

    for name, data in ROUTE_DB.items():
        f = data["standard_risk_factors"]
        news_cnt = fetch_news_count(data["news_keyword"])
        if news_cnt is None:
            news_cnt = f["news_cnt"]

        threat_level = arctic_level if data.get("is_arctic") else f["threat_level"]
        score = calc_rule_score(news_cnt, f["weather_dist_km"], threat_level)

        print(f"{name}: 뉴스 {news_cnt}건 / 텐션 {threat_level} / 점수 {score}")

        if score >= RISK_THRESHOLD:
            triggered.append({"route": name, "score": score, "news_cnt": news_cnt})

    if triggered:
        print(f"임계치 초과 항로 {len(triggered)}건 감지 — 이메일 발송 시도")
        send_alert_email(triggered)
    else:
        print("모든 항로 정상 범위 — 이메일 발송 없음")


if __name__ == "__main__":
    main()