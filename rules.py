"""신호등 판단 규칙 — 점수를 더하지 않고, 아래 규칙 중 가장 높은 등급을 씀

심각(2): 공식 Alert·Critical 등급 / 통항 crit% 이상 감소 / 재해 Red
주의(1): 공식 Advisory·High 등급 / JWC 신규 지정 / 뉴스 사건 이상 신호가 N일 연속 / 통항 warn% 이상 감소 / 재해 Orange
정상(0): 그 외
뉴스만으로는 '주의'까지만 올림 (기사 자동 분류에는 오차가 있어 단독으로 '심각'을 판단하기엔 근거가 약함)
"""
from datetime import date, timedelta

JMIC_LEVELS = {"critical": 2, "severe": 2, "high": 1, "substantial": 1, "elevated": 1,
               "moderate": 0, "low": 0, "normal": 0}
LAYERS = {"official": "공식 판단", "news": "뉴스 사건", "traffic": "실제 통항량", "disaster": "운항 불가 재해"}


def _age_days(d):
    try:
        return (date.today() - date.fromisoformat(d)).days
    except (TypeError, ValueError):
        return None


def _quantile(values, q):
    v = sorted(values)
    if not v:
        return None
    i = (len(v) - 1) * q
    lo, hi = int(i), min(int(i) + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (i - lo)


def news_eval(windows, top_pct, consecutive, min_days, min_events=3):
    """windows: 24시간 단위 사건 수 목록 (최근 24시간이 앞, 빠진 구간은 None)

    최근 구간이 '과거 하루 기록' 중 상위 top_pct% 안에 들면 이상. 최근부터 연속 이상 일수를 셈
    """
    if not windows or windows[0] is None:
        return {"available": False, "note": "최근 24시간 뉴스 데이터 없음"}
    baseline = [w for w in windows[consecutive:] if w is not None]
    if len(baseline) < min_days:
        return {"available": False, "note": f"기준 기록 수집 중 ({len(baseline)}/{min_days}일)",
                "events": windows[0]}
    median = _quantile(baseline, 0.5)
    threshold = max(_quantile(baseline, 1 - top_pct / 100), median, min_events)
    streak = 0
    for w in windows[:consecutive + 3]:
        if w is None or w < threshold or w <= median:
            break
        streak += 1
    cur = windows[0]
    rank = sum(1 for b in baseline if b >= cur) / len(baseline) * 100   # 상위 몇 %
    return {"available": True, "events": cur, "median": round(median, 1),
            "threshold": round(threshold, 1), "ratio": round(cur / median, 1) if median else None,
            "top_rank_pct": round(max(rank, 100 / len(baseline)), 1), "streak": streak,
            "baseline_days": len(baseline)}


def evaluate(raw, th, enabled=None):
    """raw: monitor.collect_strait() 결과 / th: config.toml [rules] (또는 화면 슬라이더 값)

    반환: {"level": 0~2 또는 None, "reasons": [{"level", "layer", "text", "url"}], "layers": {...}}
    """
    enabled = enabled or {k: True for k in LAYERS}
    reasons, layers = [], {}

    # ① 공식 판단
    if enabled.get("official"):
        o, items = raw.get("official") or {}, []
        max_age = th["official_max_age_days"]
        if o.get("msci_level"):
            age = _age_days(o.get("msci_date"))
            lv = {"alert": 2, "advisory": 1}.get(o["msci_level"].lower())
            items.append({"name": "미국 MSCI", "value": f"{o['msci_level'].title()} {o.get('msci_ref', '')}".strip(),
                          "date": o.get("msci_date"), "url": o.get("msci_url"),
                          "stale": age is None or age > max_age, "level": lv})
        if o.get("jmic_level"):
            age = _age_days(o.get("jmic_date"))
            items.append({"name": "JMIC/UKMTO", "value": o["jmic_level"].title(), "date": o.get("jmic_date"),
                          "url": o.get("jmic_url"), "stale": age is None or age > max_age,
                          "level": JMIC_LEVELS.get(o["jmic_level"].lower())})
        if o.get("jwc_listed"):
            age = _age_days(o.get("jwc_since"))
            new = age is not None and age <= 30
            items.append({"name": "Lloyd's JWC", "value": f"전쟁위험 지정 해역 ({o.get('jwc_ref', '')})",
                          "date": o.get("jwc_since"), "url": o.get("jwc_url"), "stale": False,
                          "level": 1 if new else None, "context": not new})
        for it in items:
            if it["level"] and not it["stale"]:
                reasons.append({"level": it["level"], "layer": "official", "url": it["url"],
                                "text": f"{it['name']} {it['value']} 발표 ({it['date']})"})
        layers["official"] = {"available": bool(items), "items": items}

    # ② 뉴스 사건
    if enabled.get("news"):
        n = news_eval(raw.get("news_windows"), th["news_top_pct"], th["news_consecutive_days"],
                      th["news_min_baseline_days"])
        layers["news"] = n
        if n["available"] and n["streak"] >= th["news_consecutive_days"]:
            reasons.append({"level": 1, "layer": "news", "url": None,
                            "text": f"갈등 뉴스 사건이 {n['streak']}일 연속 평소의 {n['ratio']}배 "
                                    f"(최근 {n['baseline_days']}일 중 상위 {n['top_rank_pct']:g}%)"})

    # ③ 실제 통항량
    if enabled.get("traffic"):
        t = raw.get("traffic")
        layers["traffic"] = dict(t, available=True) if t else {"available": False, "note": "통항 데이터 없음"}
        if t and t["base_avg"] < th["traffic_min_daily"]:
            layers["traffic"] = dict(t, available=False,
                                     note=f"평소 통항이 하루 {t['base_avg']}척으로 적어 비율 판단에서 제외")
        elif t:
            drop = -t["change_pct"]
            lv = 2 if drop >= th["traffic_crit_pct"] else (1 if drop >= th["traffic_warn_pct"] else 0)
            if lv:
                reasons.append({"level": lv, "layer": "traffic", "url": "https://portwatch.imf.org",
                                "text": f"통항량이 작년 같은 시기보다 {drop:.0f}% 감소 "
                                        f"(하루 {t['base_avg']}척 → {t['recent_avg']}척, {t['latest_date']}까지)"})

    # ④ 운항 불가 재해
    if enabled.get("disaster"):
        hits = raw.get("disasters")
        layers["disaster"] = {"available": hits is not None, "hits": hits or []}
        for h in hits or []:
            lv = 2 if h["alert"] == "Red" else 1
            kind = "열대저기압" if h["type"] == "TC" else "지진·쓰나미"
            reasons.append({"level": lv, "layer": "disaster", "url": h.get("url"),
                            "text": f"{kind} {h['alert']} 경보: {h['name']} (해협에서 {h['km']}km)"})

    if not any(v.get("available") for v in layers.values()):
        return {"level": None, "reasons": [], "layers": layers}
    reasons.sort(key=lambda r: -r["level"])
    return {"level": max([r["level"] for r in reasons], default=0), "reasons": reasons, "layers": layers}


def headline(ev):
    """신호등 아래 한 줄 설명"""
    if ev["level"] is None:
        return "데이터 수집 중"
    if not ev["reasons"]:
        return "특이 신호 없음"
    top = ev["reasons"][0]["text"]
    more = len(ev["reasons"]) - 1
    return top + (f" 외 {more}건" if more else "")
