# 해상 항로 조기경보

https://maritime-route-risk.streamlit.app/

주요 해협(호르무즈·수에즈/홍해·말라카·파나마·북극항로)의 위험을 **신호등**으로 보여 주고,
등록한 선박의 남은 항로에 위험 해협이 있으면 **대체 항로와 함께 메일**로 알립니다.

## 판단 방식 — 점수를 더하지 않고, 근거가 있는 규칙으로

| 신호 | 출처 | 🔴 심각 | 🟡 주의 |
|---|---|---|---|
| 공식 판단 | 미국 MARAD MSCI, JMIC/UKMTO, Lloyd's JWC (`official_status.toml` 에서 직접 관리) | MSCI Alert, JMIC Critical·Severe | MSCI Advisory, JMIC High·Substantial, JWC 신규 지정(30일 이내) |
| 뉴스 사건 | GDELT 15분 공개 파일 — 해협 반경 안의 위협·공격·봉쇄 사건 수 | (뉴스만으로는 올리지 않음) | 최근 24시간 사건 수가 이 해협 과거 기록 중 상위 5% 이상, 2일 연속 |
| 실제 통항량 | IMF PortWatch (위성 AIS, 주 1회 갱신) | 작년 같은 시기보다 30% 이상 감소 | 15% 이상 감소 |
| 운항 불가 재해 | GDACS (EU·UN 재난경보) | 열대저기압·지진 Red (해협 근처) | Orange |

- 하나라도 해당하면 그 등급. 기준값은 `config.toml`, 화면 사이드바에서 바꿔 볼 수 있음(메일은 기본값으로 판단)
- 일반 파도·바람은 보지 않음 (운항이 불가능한 재해만)
- 평소 통항이 하루 10척 미만인 곳(예: 베링해협)은 몇 척 차이로 비율이 흔들려 통항 판단에서 제외
- 공식 판단 표의 날짜가 45일보다 오래되면 '갱신 필요'로 표시하고 판단에서 뺌

## 구조

| 파일 | 역할 |
|---|---|
| `project.py` | Streamlit 화면 (신호등 → 지도·추적 선박·대체 항로 → 뉴스 → 판단 근거·기록) |
| `monitor.py` | 30분마다 실행: AIS 수신 → 신호 수집 → 해협 판단 → 운항 감시 → 경보 메일 |
| `signals.py` / `rules.py` | 신호 수집 / 판단 규칙 (화면과 메일이 같은 규칙 사용) |
| `voyages.py` | 등록 선박: 위치(오래되면 속력으로 추정) → 남은 항로 → 앞으로 지날 해협 → 대체 항로 |
| `ais.py` | aisstream.io 선박 위치 수신 |
| `sea_network.py`, `ports.py` | 해상 항로망(경유점 그래프)과 항구 좌표 |
| `db.py` | Neon Postgres (없으면 로컬 SQLite `monitor.db`) |
| `backfill_gdelt.py` | 처음 1회: 뉴스 사건의 과거 기록 채우기 `python backfill_gdelt.py 30` |

## 설정

- **GitHub Actions Secrets**: `DATABASE_URL`, `AISSTREAM_API_KEY`, `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, `ALERT_EMAIL`
- **Streamlit Cloud Secrets**: `DATABASE_URL`, `NEWSAPI_KEY`, `ALERT_RECIPIENTS`(선박 등록 화면의 기본 메일)
- 공식 경보가 새로 나오면 `official_status.toml` 의 해당 해협 값과 날짜를 고쳐 커밋

## 한계

조기 경보 도구입니다. 위험을 맞힌다는 보장이 아니라 평소와 다른 움직임을 먼저 알려 줍니다.
사전 정보가 없는 단발성 사건은 미리 잡을 수 없고, 무료 AIS 는 먼 바다에서 위치가 늦게 들어옵니다.
