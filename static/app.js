(function () {
    var sidebar = document.getElementById("sidebar");
    var SCROLL_KEY = "risk-app-scroll";

    // 페이지를 다시 불러온 뒤 스크롤 위치 복원
    try {
        var saved = JSON.parse(sessionStorage.getItem(SCROLL_KEY) || "null");
        if (saved && saved.path === location.pathname) {
            sidebar.scrollTop = saved.sidebar;
            window.scrollTo(0, saved.page);
        }
        sessionStorage.removeItem(SCROLL_KEY);
    } catch (e) { /* 저장소 사용 불가 시 무시 */ }

    function rememberScroll() {
        try {
            sessionStorage.setItem(SCROLL_KEY, JSON.stringify(
                { path: location.pathname, sidebar: sidebar.scrollTop, page: window.scrollY }));
        } catch (e) { /* 무시 */ }
    }

    // 사이드바 검색 폼: 선택 박스는 바뀌면 바로, 텍스트는 Enter 로 제출
    document.querySelectorAll("form.auto-submit").forEach(function (form) {
        form.addEventListener("submit", rememberScroll);
        form.querySelectorAll("select").forEach(function (el) {
            el.addEventListener("change", function () { rememberScroll(); form.submit(); });
        });
    });
    var geoForm = document.getElementById("geo-form");
    if (geoForm) geoForm.addEventListener("submit", rememberScroll);

    // 슬라이더 숫자 표시
    document.querySelectorAll('input[type="range"]').forEach(function (el) {
        var out = el.parentElement.querySelector("output");
        el.addEventListener("input", function () { out.textContent = el.value; });
    });

    // 차트
    var config = { responsive: true, displaylogo: false, modeBarButtonsToRemove: ["select2d", "lasso2d"] };
    Object.keys(window.FIGURES).forEach(function (id) {
        var fig = window.FIGURES[id];
        if (document.getElementById(id)) Plotly.newPlot(id, fig.data, fig.layout, config);
    });

    // ---------------------------------------------------------
    // 대체 항로 비교: 입력값을 fetch 로 보내 저장 + 재계산
    // ---------------------------------------------------------
    var panel = document.getElementById("cost-panel");
    if (!panel) return;
    var scenarioId = panel.dataset.scenario;
    var rowsEl = document.getElementById("cost-rows");
    var statusEl = document.getElementById("cost-status");
    var basisEl = document.getElementById("cost-basis");
    var headlineEl = document.getElementById("cost-headline");
    var colors = window.ROUTE_COLORS || {};
    var data = window.COST_DATA;
    var timer = null;

    function esc(s) {
        return String(s).replace(/[&<>"']/g, function (c) {
            return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
        });
    }
    function money(v) {
        var sign = v < 0 ? "-" : "", a = Math.abs(v);
        if (a >= 1e6) return sign + "$" + (a / 1e6).toFixed(2) + "M";
        if (a >= 1e3) return sign + "$" + Math.round(a / 1e3) + "K";
        return sign + "$" + Math.round(a);
    }
    function signed(v, fmt) {
        if (v === 0) return "±0";
        return (v > 0 ? "+" : "-") + fmt(Math.abs(v));
    }

    function render() {
        var base = data.rows.filter(function (r) { return r.is_base; })[0];
        var best = data.rows[0];

        // 한 줄 결론
        if (best.is_base) {
            headlineEl.innerHTML = "현재 입력값으로는 <b>현 항로 유지</b>가 가장 저렴합니다.";
        } else {
            headlineEl.innerHTML = "가장 저렴한 대안: <b>" + esc(best.route_name) + "</b> — 현 항로보다 " +
                (best.delta_usd <= 0 ? money(-best.delta_usd) + " 절감" : money(best.delta_usd) + " 추가") +
                ", " + (best.delta_days <= 0 ? Math.abs(best.delta_days) + "일 단축" : best.delta_days + "일 추가") + ".";
        }

        rowsEl.innerHTML = data.rows.map(function (r) {
            var breakdown = "용선료 " + money(r.charter_usd) + " · 연료비 " + money(r.fuel_usd) +
                " · 보험료 " + money(r.insurance_usd) + " · 기타 " + money(r.extra_usd);
            var days = r.total_days + "일" + (r.land_days ? ' <span class="muted">(철도 ' + r.land_days + "일 포함)</span>" : "");
            var diff = r.is_base ? '<span class="muted">기준</span>'
                : signed(r.delta_usd, money) + ' <span class="muted">/ ' + signed(r.delta_days, function (d) { return d + "일"; }) + "</span>";
            return '<tr class="' + (r.rank === 1 ? "best" : "") + '">' +
                "<td>" + r.rank + "</td>" +
                '<td class="left"><span class="swatch" style="background:' + esc(colors[r.id] || "#8a8984") + '"></span>' +
                esc(r.route_name) + (r.is_base ? ' <span class="tag">현 항로</span>' : "") +
                '<div class="muted small">약 ' + r.distance_nm.toLocaleString("ko-KR") + "해리</div></td>" +
                "<td>" + days + "</td>" +
                '<td title="' + esc(breakdown) + '"><b>' + money(r.total_usd) + "</b></td>" +
                "<td>" + diff + "</td></tr>";
        }).join("");

        basisEl.innerHTML = data.updated_at
            ? "비용값: " + esc(data.basis_label) + " · 총비용에 마우스를 올리면 내역이 보입니다."
            : "⚠ 비용값은 아직 <b>가정값</b>입니다 — 아래 '비용 가정 바꾸기'에 실제 시세를 넣으세요.";
    }

    function collectInputs() {
        var inputs = { options: {} };
        panel.querySelectorAll("input[data-field]").forEach(function (el) {
            if (el.dataset.option) {
                inputs.options[el.dataset.option] = inputs.options[el.dataset.option] || {};
                inputs.options[el.dataset.option][el.dataset.field] = el.value;
            } else {
                inputs[el.dataset.field] = el.value;
            }
        });
        return inputs;
    }

    function save() {
        statusEl.textContent = "저장 중…";
        fetch("/api/costs/" + encodeURIComponent(scenarioId), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ inputs: collectInputs() })
        }).then(function (res) {
            if (!res.ok) throw new Error("HTTP " + res.status);
            return res.json();
        }).then(function (json) {
            data = json;
            render();
            statusEl.textContent = "✓ 저장됨";
        }).catch(function (err) {
            statusEl.textContent = "⚠ 저장 실패: " + err.message;
        });
    }

    // 입력이 멈추고 0.6초 뒤 저장 (입력칸은 다시 그리지 않으므로 커서가 유지됨)
    panel.addEventListener("input", function (e) {
        if (e.target.matches("input[type=number]")) {
            clearTimeout(timer);
            timer = setTimeout(save, 600);
        }
    });

    render();
})();
