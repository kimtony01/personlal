"""환경변수(.env)와 설정 파일(config.toml)을 읽어 다른 모듈에 제공"""
import os
import tomllib
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

with open(BASE_DIR / "config.toml", "rb") as f:
    CONFIG = tomllib.load(f)

# ---- 비밀값: .env / 환경변수 ----
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY")
AISSTREAM_API_KEY = os.getenv("AISSTREAM_API_KEY")

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM = os.getenv("SMTP_FROM") or SMTP_USER
# starttls(기본, 587) / ssl(465) / none
SMTP_SECURITY = os.getenv("SMTP_SECURITY", "starttls").lower()
# SMTP 포트가 막힌 곳(예: Render 무료)에서는 Brevo HTTP API 로 발송. 있으면 SMTP 대신 사용
BREVO_API_KEY = os.getenv("BREVO_API_KEY")
ALERT_RECIPIENTS = [a.strip() for a in os.getenv("ALERT_RECIPIENTS", "").split(",") if a.strip()]

# ---- 경로 ----
# 있으면 Postgres 사용 (배포용). 없으면 아래 SQLite 파일
DATABASE_URL = os.getenv("DATABASE_URL")
DB_PATH = Path(os.getenv("RISK_DB_PATH", BASE_DIR / "risk_monitor.db"))
SHIP_DATA_PATH = BASE_DIR / "ship_data.json"
SHIP_HISTORY_PATH = BASE_DIR / "ship_history.json"

# 0 이면 웹 서버만 띄우고 스케줄러는 실행하지 않음 (예: 별도 프로세스로 돌릴 때)
SCHEDULER_ENABLED = os.getenv("SCHEDULER_ENABLED", "1") != "0"


def smtp_configured():
    return bool((SMTP_HOST or BREVO_API_KEY) and SMTP_FROM and ALERT_RECIPIENTS)
