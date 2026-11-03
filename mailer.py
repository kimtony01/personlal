"""경보 메일 발송 (Gmail SMTP 기본: SMTP_USER = Gmail 주소, SMTP_PASSWORD = 앱 비밀번호)"""
import os
import smtplib
import ssl
from email.message import EmailMessage


def configured():
    return bool(os.getenv("SMTP_USER") and os.getenv("SMTP_PASSWORD"))


def default_recipients():
    return [a.strip() for a in os.getenv("ALERT_RECIPIENTS", "").split(",") if a.strip()]


def send(subject, body, recipients):
    msg = EmailMessage()
    sender = os.getenv("SMTP_FROM") or os.getenv("SMTP_USER")
    msg["Subject"], msg["From"], msg["To"] = subject, sender, ", ".join(recipients)
    msg.set_content(body)
    with smtplib.SMTP(os.getenv("SMTP_HOST", "smtp.gmail.com"), int(os.getenv("SMTP_PORT", "587")), timeout=30) as s:
        s.starttls(context=ssl.create_default_context())
        s.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD"))
        s.send_message(msg)
