"""해상 항로 리스크 조기경보 시스템 실행 파일 (Flask)

예전 Streamlit 버전은 Flask 앱(app.py)과 기능별 모듈로 옮겨졌습니다.
이 파일을 실행해도 `python app.py` 와 똑같이 Flask 서버와 스케줄러가 시작됩니다.

    python project.py        → http://127.0.0.1:5000
"""
import os

from app import app

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true"))
