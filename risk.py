"""위험 판정: 규칙 기반 점수(0~100) 하나로 정상·경고·심각 판정

점수 = Σ (지표 정규화값 0~1 × 지표 최대 기여 점수)
가중치(최대 기여 점수)와 기준점은 config.toml 에 있으며 모두 가정값입니다.
"""
import re

LEVEL_LABEL = {0: "정상", 1: "경고", 2: "심각"}
LEVEL_LABEL_EN = {0: "정상 (LOW)", 1: "경고 (MEDIUM)", 2: "심각 (HIGH)"}
LEVEL_COLOR = {0: "#22c55e", 1: "#eab308", 2: "#ef4444"}


def _linear(x, start, full):
    """x 가 start 이하면 0, full 이상이면 1, 사이는 직선 (start > full 이면 '줄어들수록 위험')"""
    if x is None:
        return None
    if full == start:
        return 1.0 if x >= full else 0.0
    return max(0.0, min(1.0, (x - start) / (full - start)))


def _word_pattern(words):
    """단어 단위 일치 + 간단한 어미 허용 (seize → seized, attack → attacks). 'mine' 이 'mineral' 에 걸리지 않게 함"""
    return re.compile(r"\b(" + "|".join(re.escape(w) for w in words) + r")(?:s|es|d|ed|ing)?\b", re.IGNORECASE)


# -------------------------------------------------------------
# 기사 키워드 분석
# -------------------------------------------------------------
def analyze_articles(articles, news_cfg):
    strong_re = _word_pattern(news_cfg["strong_keywords"])
    issue_res = {label: _word_pattern(words) for label, words in news_cfg["issue_keywords"].items()}
    strong_weight = news_cfg["strong_keyword_weight"]

    items, issue_hits = [], {label: 0 for label in issue_res}
    for a in articles:
        title = (a.get("title") or "").strip()
        desc = (a.get("description") or "").strip()
        if not title or title == "[Removed]":
            continue
        text = f"{title} {desc}"
        matched = sorted({m.lower() for m in strong_re.findall(text)})
        for label, pat in issue_res.items():
            issue_hits[label] += len(pat.findall(text))
        items.append({
            "title_en": title[:300], "desc_en": desc[:400],
            "url": a.get("url") or "#", "source": (a.get("source") or {}).get("name") or "출처 미상",
            "published_at": (a.get("publishedAt") or "")[:10],
            "strong_keywords": matched,
            "weight": strong_weight if matched else 1.0,
        })

    n = len(items)
    strong_count = sum(1 for i in items if i["strong_keywords"])
    multiplier = sum(i["weight"] for i in items) / n if n else 1.0
    top = sorted(items, key=lambda i: (bool(i["strong_keywords"]), i["published_at"]), reverse=True)
    return {
        "sample_size": n, "strong_count": strong_count,
        "strong_share": strong_count / n if n else 0.0,
        "keyword_multiplier": round(multiplier, 3),
        "issue_hits": {k: v for k, v in sorted(issue_hits.items(), key=lambda kv: -kv[1]) if v > 0},
        "top_articles": top[:news_cfg["top_articles"]],
    }


def recommend_geo_level(strong_share, news_cfg):
    """강한 키워드 기사 비율 → 지정학 위협 지수 추천값 1~5"""
    if strong_share is None:
        return None
    level = 1
    for bound in news_cfg["geo_share_bounds"]:
        if strong_share >= bound:
            level += 1
    return level


# -------------------------------------------------------------
# 원 지표 계산
# -------------------------------------------------------------
def news_indicators(news):
    """뉴스 스냅샷 → 상대값(30일 평균 대비), 증가율(%)"""
    if not news:
        return None, None
    c7, cp, c30 = news["count_7d"], news["count_prev7d"], news["count_30d"]
    recent_daily = c7 / 7 * (news["keyword_multiplier"] or 1.0)
    baseline_daily = c30 / 30
    ratio = recent_daily / baseline_daily if baseline_daily > 0 else 0.0
    growth = (c7 - cp) / max(cp, 1) * 100
    return round(ratio, 3), round(growth, 1)


def ais_drop_ratio(current_count, current_speed, baseline, ais_cfg):
    """현재/평소 비율 중 더 많이 줄어든 쪽. 평소 기록이 부족하면 None"""
    if current_count is None or not baseline or (baseline.get("n") or 0) < ais_cfg["min_history"]:
        return None
    ratios = []
    if baseline.get("cnt"):
        ratios.append(current_count / baseline["cnt"])
    if baseline.get("spd") and current_speed is not None:
        ratios.append(current_speed / baseline["spd"])
    return round(min(ratios), 3) if ratios else None


# -------------------------------------------------------------
# 점수 / 판정
# -------------------------------------------------------------
def compute_score(ind, cfg):
    """ind: news_ratio, news_growth_pct, wave_max_m, wind_max_kn, geo_level, ais_ratio
    반환: (점수, 등급, 기여도 목록)"""
    w, nc, wc, ac = cfg["score"], cfg["news"], cfg["weather"], cfg["ais"]

    wave_n = _linear(ind.get("wave_max_m"), wc["wave_start_m"], wc["wave_full_m"])
    wind_n = _linear(ind.get("wind_max_kn"), wc["wind_start_kn"], wc["wind_full_kn"])
    weather_parts = [v for v in (wave_n, wind_n) if v is not None]

    def fmt(v, spec):
        return "데이터 없음" if v is None else format(v, spec)

    rows = [
        ("news_volume", "뉴스 건수(30일 평균 대비)",
         _linear(ind.get("news_ratio"), 1.0, nc["volume_full_ratio"]),
         f"평소 대비 {fmt(ind.get('news_ratio'), '.2f')}배 (강한 키워드 가중 포함)"),
        ("news_growth", "뉴스 증가율",
         _linear(ind.get("news_growth_pct"), 0, nc["growth_full_pct"]),
         f"전주 대비 {fmt(ind.get('news_growth_pct'), '+.0f')}%"),
        ("weather", "기상 위협",
         max(weather_parts) if weather_parts else None,
         f"최대 파고 {fmt(ind.get('wave_max_m'), '.1f')} m · 최대 풍속 {fmt(ind.get('wind_max_kn'), '.0f')} kn"),
        ("geopolitical", "지정학 위협 지수",
         (ind["geo_level"] - 1) / 4 if ind.get("geo_level") else None,
         f"{ind.get('geo_level') or '-'}/5"),
        ("ais_drop", "AIS 통항량 감소",
         _linear(ind.get("ais_ratio"), ac["drop_start_ratio"], ac["drop_full_ratio"]),
         "평소 기록 부족" if ind.get("ais_ratio") is None else f"평소 대비 {ind['ais_ratio']*100:.0f}%"),
    ]
    contributions = []
    for key, label, norm, detail in rows:
        if not w.get(key):
            continue  # 가중치 0 = 비활성 지표
        contributions.append({
            "key": key, "label": label, "max": w[key], "detail": detail,
            "available": norm is not None,
            "points": round((norm or 0.0) * w[key], 1),
        })
    score = round(sum(c["points"] for c in contributions), 1)
    return score, level_for(score, cfg), contributions


def level_for(score, cfg):
    t = cfg["thresholds"]
    if score >= t["critical"]:
        return 2
    if score >= t["warning"]:
        return 1
    return 0
