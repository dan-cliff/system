/* Machine status page for display screens. Plain JavaScript so it runs well
 * on a Node (Raspberry Pi). Fetches the board's data every few seconds and draws
 * it in the board's layout: a grid of machine cards, a list, or one
 * machine at a time. */
(function () {
    "use strict";

    const root = document.getElementById("board");
    const dataUrl = document.body.dataset.url;

    const STATUS_ORDER = ["stitching", "waiting", "paused", "error", "idle", "offline"];
    const STATUS_LABELS = {
        stitching: "Stitching",
        waiting: "Waiting to Start",
        paused: "Paused",
        error: "Error",
        idle: "Idle",
        offline: "Offline",
    };

    const state = {
        data: null,
        lastOk: 0,
        reload: null,
        focusIndex: 0,
        focusTimer: null,
        fetchTimer: null,
        problem: "",
    };

    function esc(value) {
        return String(value === undefined || value === null ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function num(value) {
        return Number(value || 0).toLocaleString("en-GB");
    }

    // ── Clock (in the board's time zone, dd/mm/yyyy) ────────────────────
    function clockParts(tz) {
        const now = new Date();
        const options = { timeZone: tz || undefined };
        try {
            const time = now.toLocaleTimeString("en-GB", { ...options, hour: "2-digit", minute: "2-digit" });
            const date = now.toLocaleDateString("en-GB", {
                ...options, weekday: "long", day: "2-digit", month: "2-digit", year: "numeric",
            });
            return { time, date };
        } catch {
            return { time: now.toLocaleTimeString("en-GB").slice(0, 5), date: now.toLocaleDateString("en-GB") };
        }
    }

    function tickClock() {
        const clock = document.getElementById("clock");
        if (clock && state.data) {
            const parts = clockParts(state.data.board.tz);
            clock.innerHTML = `<div class="clock-time">${esc(parts.time)}</div><div class="clock-date">${esc(parts.date)}</div>`;
        }
        const stale = document.getElementById("stale");
        if (stale && state.data) {
            const limit = (state.data.board.refresh_seconds * 3 + 10) * 1000;
            stale.hidden = Date.now() - state.lastOk < limit;
        }
    }

    // ── Pieces of a machine card ────────────────────────────────────────
    function pill(status, label) {
        return `<span class="pill status-${esc(status)}">${esc(label || STATUS_LABELS[status] || status)}</span>`;
    }

    function jobBlock(machine, show) {
        const job = machine.job;
        const run = machine.stitchout;
        let html = `<div class="job">`;
        if (show.preview && job.preview_url) {
            html += `<img class="preview" src="${esc(job.preview_url)}" alt=""/>`;
        }
        html += `<div class="job-text">`;
        if (show.job) {
            html += `<div class="job-ref">${esc(job.name)}<span class="piece"> · piece ${esc(run.piece)} of ${esc(job.qty)}</span></div>`;
            if (job.title) {
                html += `<div class="job-title">${esc(job.title)}</div>`;
            }
        }
        if (show.customer && job.customer) {
            html += `<div class="job-line customer">${esc(job.customer)}</div>`;
        }
        const details = [];
        if (show.product) {
            details.push((job.product ? `${esc(job.product)} · ` : "") + `${esc(job.qty_done)} of ${esc(job.qty)} done`);
        }
        if (show.job && job.deadline) {
            details.push(`<span class="${job.overdue ? "overdue" : ""}">Due ${esc(job.deadline)}</span>`);
        }
        if (details.length) {
            html += `<div class="job-line">${details.join(" · ")}</div>`;
        }
        if (show.operator && job.operator) {
            html += `<div class="job-line">${esc(job.operator)}</div>`;
        }
        html += `</div></div>`;
        return html;
    }

    function progressBlock(machine, show) {
        const run = machine.stitchout;
        let html = "";
        if (show.errors && run.state === "error" && run.error_message) {
            html += `<div class="error-banner">⚠ ${esc(run.error_message)}</div>`;
        }
        if (show.progress) {
            html += `<div class="bar status-${esc(machine.status)}">
                <div class="bar-fill" style="width:${Math.max(0, Math.min(100, run.progress))}%"></div>
                <div class="bar-label">${esc(Math.round(run.progress))}%${run.live ? "" : " (est.)"}</div>
            </div>`;
        }
        const stats = [];
        if (show.stitches) {
            stats.push(["Stitches", `${num(run.stitch)} / ${num(run.total_stitches)}`]);
        }
        if (show.colour && run.color_count) {
            const swatch = run.color_hex ? `<span class="swatch" style="background:${esc(run.color_hex)}"></span>` : "";
            stats.push(["Colour", `${swatch}${esc(run.color_number)} of ${esc(run.color_count)}`, esc(run.color_name)]);
        }
        if (show.eta) {
            stats.push(["Remaining", esc(run.remaining)]);
            stats.push(["ETA", esc(run.eta)]);
        }
        if (stats.length) {
            html += `<div class="stats">${stats.map(([label, value, sub]) => `
                <div class="stat"><div class="stat-label">${label}</div><div class="stat-value">${value}</div>${sub ? `<div class="stat-sub">${sub}</div>` : ""}</div>`).join("")}</div>`;
        }
        return html;
    }

    function queueBlock(machine, show) {
        if (!show.queue || !machine.queue.length) {
            return "";
        }
        const items = machine.queue.map((job) => {
            const bits = [job.customer, `${job.pieces} pcs`, job.time].filter(Boolean).map(esc).join(" · ");
            return `<li><span class="queue-ref">${esc(job.name)}</span> ${esc(job.title)} <span class="queue-meta">${bits}</span></li>`;
        });
        return `<div class="queue"><div class="queue-title">Next</div><ol>${items.join("")}</ol></div>`;
    }

    function card(machine, show, extraClass) {
        let html = `<section class="card status-${esc(machine.status)} ${extraClass || ""}">
            <header class="card-head">
                <div><div class="machine-name">${esc(machine.name)}</div><div class="machine-model">${esc(machine.model)}</div></div>
                ${pill(machine.status, machine.status_label)}
            </header>`;
        if (machine.job) {
            html += jobBlock(machine, show) + progressBlock(machine, show);
        } else {
            const message = machine.status === "offline" ? machine.message || "Not connected" : "Nothing on the machine";
            html += `<div class="idle-message">${esc(message)}</div>`;
        }
        html += queueBlock(machine, show);
        return html + `</section>`;
    }

    // ── Layouts ─────────────────────────────────────────────────────────
    function gridColumns(count, configured) {
        if (configured) {
            return configured;
        }
        if (count <= 1) return 1;
        if (count <= 4) return 2;
        if (count <= 9) return 3;
        return 4;
    }

    function renderGrid(data) {
        const machines = data.machines;
        const columns = gridColumns(machines.length, data.board.columns);
        const rows = Math.max(1, Math.ceil(machines.length / columns));
        return `<main class="grid" style="grid-template-columns:repeat(${columns},1fr);grid-template-rows:repeat(${rows},1fr)">
            ${machines.map((m) => card(m, data.board.show)).join("")}</main>`;
    }

    function renderList(data) {
        const show = data.board.show;
        const head = ["Machine", "Status"];
        if (show.job) head.push("Job");
        if (show.customer) head.push("Customer");
        if (show.progress) head.push("Progress");
        if (show.colour) head.push("Colour");
        if (show.eta) head.push("Remaining", "ETA");
        if (show.queue) head.push("Next");
        const rows = data.machines.map((m) => {
            const run = m.stitchout;
            const job = m.job;
            const cells = [
                `<div class="machine-name">${esc(m.name)}</div>`,
                pill(m.status, m.status_label) + (show.errors && run && run.state === "error" ? `<div class="list-error">${esc(run.error_message)}</div>` : ""),
            ];
            if (show.job) cells.push(job ? `<div class="job-ref">${esc(job.name)}</div><div class="job-title">${esc(job.title)}</div>` : `<span class="muted">${esc(m.status === "offline" ? m.message || "Not connected" : "-")}</span>`);
            if (show.customer) cells.push(job ? esc(job.customer) : "");
            if (show.progress) cells.push(run ? `<div class="bar status-${esc(m.status)}"><div class="bar-fill" style="width:${run.progress}%"></div><div class="bar-label">${Math.round(run.progress)}%</div></div>` : "");
            if (show.colour) cells.push(run && run.color_count ? `<span class="swatch" style="background:${esc(run.color_hex)}"></span>${esc(run.color_number)}/${esc(run.color_count)} ${esc(run.color_name)}` : "");
            if (show.eta) cells.push(run ? esc(run.remaining) : "", run ? esc(run.eta) : "");
            if (show.queue) cells.push(m.queue.map((q) => esc(q.name)).join(", "));
            return `<tr class="status-${esc(m.status)}">${cells.map((c) => `<td>${c}</td>`).join("")}</tr>`;
        });
        return `<main class="list"><table><thead><tr>${head.map((h) => `<th>${h}</th>`).join("")}</tr></thead>
            <tbody>${rows.join("")}</tbody></table></main>`;
    }

    function renderFocus(data) {
        const machines = data.machines;
        if (!machines.length) {
            return "";
        }
        state.focusIndex %= machines.length;
        const current = machines[state.focusIndex];
        const strip = machines.map((m, index) => `
            <div class="strip-item ${index === state.focusIndex ? "current" : ""} status-${esc(m.status)}">
                <span class="strip-name">${esc(m.name)}</span>${pill(m.status, m.status_label)}
            </div>`).join("");
        return `<main class="focus">${card(current, data.board.show, "big")}<nav class="strip">${strip}</nav></main>`;
    }

    // ── Page ────────────────────────────────────────────────────────────
    function header(data) {
        const board = data.board;
        const show = board.show;
        if (!show.header) {
            return "";
        }
        let summary = "";
        if (show.summary) {
            summary = STATUS_ORDER.filter((s) => data.summary[s])
                .map((s) => `<span class="pill status-${s}">${data.summary[s]} ${esc(STATUS_LABELS[s])}</span>`).join("");
        }
        return `<header class="board-head">
            ${board.logo_url ? `<img class="logo" src="${esc(board.logo_url)}" alt=""/>` : ""}
            <h1>${esc(board.title)}</h1>
            <div class="summary">${summary}</div>
            ${show.clock ? `<div id="clock" class="clock"></div>` : ""}
        </header>`;
    }

    function render() {
        const data = state.data;
        const board = data.board;
        document.body.className = `theme-${board.theme} layout-${board.layout}`;
        document.documentElement.style.fontSize = `${(1.3 * board.font_scale) / 100}vh`;
        let body;
        if (!data.machines.length) {
            body = `<div class="board-message">No machines on this board.</div>`;
        } else if (board.layout === "list") {
            body = renderList(data);
        } else if (board.layout === "focus") {
            body = renderFocus(data);
        } else {
            body = renderGrid(data);
        }
        root.innerHTML = `${header(data)}${body}
            <div id="stale" class="stale" hidden>Connection to Odoo lost - showing the status from ${esc(data.updated)}</div>`;
        tickClock();
        scheduleFocus();
    }

    function scheduleFocus() {
        const data = state.data;
        if (!data || data.board.layout !== "focus" || data.machines.length < 2) {
            clearInterval(state.focusTimer);
            state.focusTimer = null;
            return;
        }
        if (!state.focusTimer) {
            state.focusTimer = setInterval(() => {
                state.focusIndex += 1;
                render();
            }, data.board.rotate_seconds * 1000);
        }
    }

    function showMessage(title, detail) {
        root.innerHTML = `<div class="board-message"><div>${esc(title)}</div><div class="board-detail">${esc(detail || "")}</div></div>`;
    }

    async function refresh() {
        let wait = 10;
        try {
            const separator = dataUrl.includes("?") ? "&" : "?";
            const response = await fetch(`${dataUrl}${separator}w=${window.innerWidth}&h=${window.innerHeight}`, {
                cache: "no-store",
                credentials: "same-origin",
            });
            const data = await response.json().catch(() => ({}));
            if (data.switch_page) {
                // The screen was set to show something else (e.g. a Live Sales Counter).
                window.location.reload();
                return;
            }
            if (!response.ok || data.status !== "ok") {
                const message = data.message || `Odoo answered ${response.status}.`;
                if (state.data && response.status >= 500) {
                    tickClock(); // keep showing the last status, marked stale
                } else {
                    showMessage("This screen can't show the machine status", message);
                    state.data = null;
                }
                wait = 15;
            } else {
                if (state.reload !== null && data.reload !== state.reload) {
                    window.location.reload();
                    return;
                }
                state.reload = data.reload;
                state.data = data;
                state.lastOk = Date.now();
                render();
                wait = data.board.refresh_seconds;
            }
        } catch {
            tickClock();
        }
        clearTimeout(state.fetchTimer);
        state.fetchTimer = setTimeout(refresh, wait * 1000);
    }

    setInterval(tickClock, 1000);
    refresh();
})();
