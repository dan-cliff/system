/**
 * Room Designer editor (DOM, mounted by the OWL client action in room_designer.js).
 * Ported from the agreed prototype (video_rooms/prototype/room_designer.html):
 * Screens (room plan with four walls), Console layout (tablet tile grid) and the
 * door screen (Presence) layout. The client action loads and saves the data.
 */

const WALLS = {
    front: { label: "Front wall", cols: 4, rows: 2 },
    left: { label: "Left wall", cols: 3, rows: 2 },
    right: { label: "Right wall", cols: 3, rows: 2 },
    back: { label: "Back wall (door)", cols: 4, rows: 2 },
};
const SHOWS = { call: "Call", mirror: "Mirror", shared: "Shared content", info: "Room info" };
const MAX_SCREENS = 4;
const TILE_TYPES = [
    { t: "join", label: "Join / Today", w: 2, h: 2, cls: "go" },
    { t: "mic", label: "Microphone", w: 1, h: 1 },
    { t: "camera", label: "Camera", w: 1, h: 1 },
    { t: "volume", label: "Volume", w: 2, h: 1 },
    { t: "share", label: "Share", w: 1, h: 1 },
    { t: "layout", label: "Call layout", w: 1, h: 1 },
    { t: "leave", label: "Leave call", w: 1, h: 1, cls: "hot" },
    { t: "dnd", label: "Do not disturb", w: 1, h: 1, cls: "dnd" },
    { t: "ptz", label: "Camera presets", w: 2, h: 1, needs: "ptz" },
    { t: "tv", label: "Screens on/off", w: 1, h: 1 },
    { t: "lighting", label: "Lighting", w: 2, h: 1, needs: "lighting", cls: "ha" },
    { t: "climate", label: "Air conditioning", w: 1, h: 1, needs: "climate", cls: "ha" },
    { t: "blinds", label: "Blinds", w: 1, h: 1, needs: "blinds", cls: "ha" },
    { t: "glass", label: "Window film", w: 1, h: 1, needs: "glass", cls: "ha" },
    { t: "scenes", label: "Room presets", w: 2, h: 1, needs: "scenes", cls: "ha" },
];
const TT = Object.fromEntries(TILE_TYPES.map((x) => [x.t, x]));
const HAS = [["lighting", "Lighting"], ["climate", "Air conditioning"], ["blinds", "Blinds"], ["glass", "Smart window film"],
    ["scenes", "Room presets"], ["ptz", "PTZ camera"]];
const BLOCKS = { name: "Room name", status: "Status", current: "Current booking", timeleft: "Time left",
    dnd: "Do-not-disturb banner", today: "Today's bookings", booknow: "Book Now and check-in", meta: "Seats and temperature",
    clock: "Clock" };
const STATUS = { available: "Available", soon: "Booked soon", in_use: "In use", dnd: "In use" };
const P = {
    join: '<rect x="3" y="5" width="18" height="16" rx="2"/><rect x="3" y="5" width="18" height="5" rx="2"/>',
    mic: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M6 11a6 6 0 0012 0M12 17v4" fill="none" stroke="currentColor" stroke-width="2"/>',
    camera: '<rect x="3" y="7" width="13" height="10" rx="2"/><path d="M16 11l5-3v8l-5-3z"/>',
    volume: '<path d="M4 9h4l5-4v14l-5-4H4z"/><path d="M16 9a4 4 0 010 6" fill="none" stroke="currentColor" stroke-width="2"/>',
    share: '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8" stroke="currentColor" stroke-width="2"/>',
    layout: '<rect x="3" y="4" width="8" height="7" rx="1.5"/><rect x="13" y="4" width="8" height="7" rx="1.5"/><rect x="3" y="13" width="8" height="7" rx="1.5"/><rect x="13" y="13" width="8" height="7" rx="1.5"/>',
    leave: '<path d="M3 13c5-5 13-5 18 0l-3 3-3-2v-2a9 9 0 00-6 0v2l-3 2z"/>',
    dnd: '<circle cx="12" cy="12" r="9"/><rect x="7" y="10.5" width="10" height="3" rx="1.5" fill="#fff"/>',
    ptz: '<circle cx="12" cy="11" r="6"/><circle cx="12" cy="11" r="2.5" fill="#fff"/>',
    tv: '<rect x="3" y="5" width="18" height="12" rx="2"/><path d="M9 20h6" stroke="currentColor" stroke-width="2"/>',
    lighting: '<path d="M12 3a6 6 0 00-3.5 10.9V17h7v-3.1A6 6 0 0012 3z"/><rect x="9" y="18.5" width="6" height="2.5" rx="1"/>',
    climate: '<rect x="10" y="3" width="4" height="12" rx="2"/><circle cx="12" cy="17" r="4"/>',
    blinds: '<rect x="4" y="3" width="16" height="3" rx="1"/><rect x="4" y="8" width="16" height="3" rx="1"/><rect x="4" y="13" width="16" height="3" rx="1"/>',
    glass: '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M4 21L20 5" stroke="#fff" stroke-width="2"/>',
    scenes: '<path d="M12 3l2.6 5.6 6 .7-4.5 4.1 1.2 6L12 16.4 6.7 19.4l1.2-6L3.4 9.3l6-.7z"/>',
};
const icon = (k) => `<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">${P[k] || ""}</svg>`;
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const uid = () => "n" + Math.random().toString(36).slice(2, 9);

function h(tag, attrs = {}, ...kids) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
        if (v === false || v == null) {
            continue;
        }
        if (k === "class") {
            e.className = v;
        } else if (k === "style") {
            e.style.cssText = v;
        } else if (k.startsWith("on")) {
            e.addEventListener(k.slice(2), v);
        } else {
            e.setAttribute(k, v === true ? "" : v);
        }
    }
    for (const k of kids.flat()) {
        if (k != null && k !== false) {
            e.append(k.nodeType ? k : document.createTextNode(k));
        }
    }
    return e;
}

/**
 * Mount the editor in ``root``. ``data`` is what video.room.designer_load returns;
 * ``api`` = {notify(message, type), identify(), saveTemplate(kind, name, layout), followTemplate(kind, id), changed()}.
 * Returns {getData()}.
 */
export function mountDesigner(root, data, api) {
    const R = structuredClone(data);
    R.console = R.console || { cols: 6, rows: 4, call: [], idle: [] };
    R.console.cols = R.console.cols || 6;
    R.console.rows = R.console.rows || 4;
    R.console.call = R.console.call || [];
    R.console.idle = R.console.idle || [];
    let tab = "screens";
    let selScreen = null;
    let selTile = null;
    let cpage = "call";
    let pstate = "available";
    const C_COLS = () => R.console.cols;
    const C_ROWS = () => R.console.rows;
    const changed = () => api.changed?.();
    const toast = (msg, type = "info") => api.notify(msg, type);

    root.replaceChildren();
    root.classList.add("o_vr_designer");
    const tabs = h("nav", { class: "vrd-tabs", role: "tablist" });
    const views = {
        screens: h("section", { class: "vrd-work" }),
        console: h("section", { class: "vrd-work" }),
        presence: h("section", { class: "vrd-work" }),
    };
    for (const [key, label] of [["screens", "Screens"], ["console", "Console layout"], ["presence", "Door screen"]]) {
        tabs.append(h("button", { type: "button", role: "tab", "data-tab": key, "aria-selected": String(key === tab),
            onclick: () => { tab = key; render(); } }, label));
    }
    root.append(tabs, ...Object.values(views));

    function render() {
        for (const b of tabs.querySelectorAll("button")) {
            b.setAttribute("aria-selected", String(b.dataset.tab === tab));
        }
        for (const [key, el] of Object.entries(views)) {
            el.hidden = key !== tab;
        }
        if (tab === "screens") {
            renderScreens();
        } else if (tab === "console") {
            renderConsole();
        } else {
            renderPresence();
        }
    }

    // ── Screens ──────────────────────────────────────────────────────────
    const wallScreens = (w) => R.screens.filter((s) => s.wall === w);
    const numberOf = (s) => R.screens.indexOf(s) + 1;

    function renderScreens() {
        const plan = h("div", { class: "vrd-plan" });
        const inspector = h("aside", { class: "vrd-panel" });
        const head = h("div", { class: "vrd-row vrd-between" },
            h("p", { class: "vrd-hint" }, "Up to 4 screens, one per output on the room PC. Drag a screen to move it, even onto another wall; drag its corner to resize. Double-click an empty spot to add one. Call screens on the same wall join into one canvas."),
            h("div", { class: "vrd-row" },
                h("button", { type: "button", class: "btn btn-secondary btn-sm", onclick: () => addScreen("front") }, "Add screen"),
                h("button", { type: "button", class: "btn btn-secondary btn-sm", onclick: identify, disabled: !R.has_display }, "Identify screens")));
        views.screens.replaceChildren(h("div", { class: "vrd-panel" }, head, plan), inspector);
        drawPlan(plan);
        drawInspector(inspector);
    }

    function identify() {
        const plan = views.screens.querySelector(".vrd-plan");
        plan.classList.add("identify");
        setTimeout(() => plan.classList.remove("identify"), 8000);
        api.identify();
    }

    function drawPlan(plan) {
        plan.replaceChildren();
        const mk = (w) => {
            const W = WALLS[w];
            const grid = h("div", { class: "vrd-wall-grid", "data-wall": w,
                style: `aspect-ratio:${W.cols * 16} / ${W.rows * 9};background-size:${100 / W.cols}% ${100 / W.rows}%` });
            grid.addEventListener("dblclick", (e) => {
                if (e.target !== grid) {
                    return;
                }
                const r = grid.getBoundingClientRect();
                addScreen(w, Math.floor(((e.clientX - r.left) / r.width) * W.cols), Math.floor(((e.clientY - r.top) / r.height) * W.rows));
            });
            const calls = wallScreens(w).filter((s) => s.content === "call");
            if (calls.length > 1) {
                const x0 = Math.min(...calls.map((s) => s.x));
                const y0 = Math.min(...calls.map((s) => s.y));
                const x1 = Math.max(...calls.map((s) => s.x + s.w));
                const y1 = Math.max(...calls.map((s) => s.y + s.h));
                grid.append(h("div", { class: "vrd-canvas", style: `left:${(x0 / W.cols) * 100}%;top:${(y0 / W.rows) * 100}%;width:${((x1 - x0) / W.cols) * 100}%;height:${((y1 - y0) / W.rows) * 100}%` },
                    h("span", {}, `One call canvas · ${calls.length} screens`)));
            }
            for (const s of wallScreens(w)) {
                const mirror = R.screens.find((x) => String(x.id) === String(s.mirrorOf));
                const el = h("div", { class: `vrd-scr ${s.content}${s.id === selScreen ? " sel" : ""}`,
                    style: `left:${(s.x / W.cols) * 100}%;top:${(s.y / W.rows) * 100}%;width:${(s.w / W.cols) * 100}%;height:${(s.h / W.rows) * 100}%` },
                h("div", { class: "face", tabindex: 0, role: "button", "aria-label": `Screen ${numberOf(s)} ${s.name}` },
                    h("span", { class: "num" }, String(numberOf(s))), h("span", { class: "nm" }, s.name),
                    h("span", { class: "kind" }, s.content === "mirror" ? `Mirror of ${mirror ? numberOf(mirror) : "?"}` : SHOWS[s.content])),
                h("span", { class: "rs", "aria-hidden": "true" }));
                el.querySelector(".face").addEventListener("keydown", (e) => {
                    if (e.key === "Enter" || e.key === " ") {
                        selScreen = s.id;
                        renderScreens();
                    }
                });
                dragScreen(el, s);
                grid.append(el);
            }
            return h("div", { class: "vrd-wall", style: `grid-area:${w}` },
                h("div", { class: "vrd-row vrd-between" }, h("h3", {}, W.label),
                    h("button", { type: "button", class: "btn btn-light btn-sm", "aria-label": `Add a screen to the ${W.label.toLowerCase()}`, onclick: () => addScreen(w) }, "+")),
                grid);
        };
        plan.append(mk("front"), mk("left"),
            h("div", { class: "vrd-table-area" }, h("div", { class: "vrd-table" }, h("span", { class: "vrd-mark" }, h("i"), "Console tablet"))),
            mk("right"));
        const back = mk("back");
        back.append(h("div", { class: "vrd-row vrd-between" }, h("span", { class: "vrd-hint" }, "Door"),
            h("span", { class: "vrd-mark" }, h("i"), "Door tablet (outside)")));
        plan.append(back);
    }

    function addScreen(wall, x, y) {
        if (R.screens.length >= MAX_SCREENS) {
            toast("A room can have up to 4 screens, from the room PC's own outputs. More screens need video wall controllers, which aren't supported yet.", "warning");
            return;
        }
        const W = WALLS[wall];
        const free = (cx, cy) => !wallScreens(wall).some((s) => cx >= s.x && cx < s.x + s.w && cy >= s.y && cy < s.y + s.h);
        if (x == null || !free(x, y)) {
            x = null;
            outer: for (let yy = 0; yy < W.rows; yy++) {
                for (let xx = 0; xx < W.cols; xx++) {
                    if (free(xx, yy)) {
                        x = xx;
                        y = yy;
                        break outer;
                    }
                }
            }
        }
        if (x == null) {
            toast(`The ${W.label.toLowerCase()} is full. Make a screen smaller or use another wall.`, "warning");
            return;
        }
        const used = new Set(R.screens.map((s) => s.output));
        const s = { id: uid(), name: `${W.label.split(" ")[0]} screen ${wallScreens(wall).length + 1}`, wall,
            x: clamp(x, 0, W.cols - 1), y: clamp(y, 0, W.rows - 1), w: 1, h: 1, content: "call", mirrorOf: "",
            output: R.outputs.find((o) => !used.has(o)) || "" };
        R.screens.push(s);
        selScreen = s.id;
        changed();
        renderScreens();
    }

    function dragScreen(el, s) {
        el.addEventListener("pointerdown", (e) => {
            const resizing = e.target.classList.contains("rs");
            e.preventDefault();
            selScreen = s.id;
            const startWall = s.wall;
            const r0 = el.parentElement.getBoundingClientRect();
            const W0 = WALLS[s.wall];
            const offX = Math.floor(((e.clientX - r0.left) / r0.width) * W0.cols) - s.x;
            const offY = Math.floor(((e.clientY - r0.top) / r0.height) * W0.rows) - s.y;
            const gridOf = (w) => views.screens.querySelector(`.vrd-wall-grid[data-wall="${w}"]`);
            // Listeners on window: the plan is redrawn while dragging, which replaces this element.
            const move = (ev) => {
                if (resizing) {
                    const W = WALLS[s.wall];
                    const r = gridOf(s.wall).getBoundingClientRect();
                    s.w = clamp(Math.ceil(((ev.clientX - r.left) / r.width) * W.cols) - s.x, 1, W.cols - s.x);
                    s.h = clamp(Math.ceil(((ev.clientY - r.top) / r.height) * W.rows) - s.y, 1, W.rows - s.y);
                } else {
                    const under = document.elementsFromPoint(ev.clientX, ev.clientY).find((n) => n.classList?.contains("vrd-wall-grid"));
                    if (!under) {
                        return;
                    }
                    const w = under.dataset.wall;
                    const W = WALLS[w];
                    const r = under.getBoundingClientRect();
                    if (w !== s.wall) {
                        s.wall = w;
                        s.w = Math.min(s.w, W.cols);
                        s.h = Math.min(s.h, W.rows);
                    }
                    s.x = clamp(Math.floor(((ev.clientX - r.left) / r.width) * W.cols) - (w === startWall ? offX : 0), 0, W.cols - s.w);
                    s.y = clamp(Math.floor(((ev.clientY - r.top) / r.height) * W.rows) - (w === startWall ? offY : 0), 0, W.rows - s.h);
                }
                drawPlan(views.screens.querySelector(".vrd-plan"));
            };
            const up = () => {
                window.removeEventListener("pointermove", move);
                window.removeEventListener("pointerup", up);
                window.removeEventListener("pointercancel", up);
                changed();
                renderScreens();
            };
            window.addEventListener("pointermove", move);
            window.addEventListener("pointerup", up);
            window.addEventListener("pointercancel", up);
            drawInspector(views.screens.querySelector("aside"));
        });
    }

    function warnings() {
        const out = [];
        const sc = R.screens;
        if (!sc.length) {
            out.push("No screens yet. Add the room's screens and choose what each one shows.");
        } else if (!sc.some((s) => s.content === "call")) {
            out.push("No screen shows the call. Set at least one screen to Call.");
        }
        const seen = {};
        for (const s of sc) {
            if (!s.output) {
                out.push(`Screen ${numberOf(s)} (${s.name}) has no output.`);
            } else {
                (seen[s.output] = seen[s.output] || []).push(numberOf(s));
            }
        }
        for (const [o, n] of Object.entries(seen)) {
            if (n.length > 1) {
                out.push(`${o} is used by screens ${n.join(" and ")}. Each output drives one screen.`);
            }
        }
        if (sc.length > R.outputs.length) {
            out.push(`${sc.length} screens but the room PC has ${R.outputs.length} outputs. Use a PC with an output per screen.`);
        }
        for (const s of sc) {
            if (s.content === "mirror") {
                const m = sc.find((x) => String(x.id) === String(s.mirrorOf));
                if (!m) {
                    out.push(`Screen ${numberOf(s)} mirrors nothing. Choose a screen to copy.`);
                } else if (m.content === "mirror") {
                    out.push(`Screen ${numberOf(s)} mirrors another mirror. Point it at the original.`);
                }
            }
        }
        if (sc.some((s) => s.content === "shared")) {
            out.push("Shared content uses companion mode: the host admits a second guest. Without it these screens mirror the call.");
        }
        for (const w of Object.keys(WALLS)) {
            const ws = wallScreens(w);
            for (let i = 0; i < ws.length; i++) {
                for (let j = i + 1; j < ws.length; j++) {
                    const a = ws[i];
                    const b = ws[j];
                    if (a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h) {
                        out.push(`Screens ${numberOf(a)} and ${numberOf(b)} overlap on the ${WALLS[w].label.toLowerCase()}.`);
                    }
                }
            }
        }
        return out;
    }

    function drawInspector(box) {
        box.replaceChildren();
        const s = R.screens.find((x) => x.id === selScreen);
        const used = new Set(R.screens.map((x) => x.output));
        box.append(h("h3", {}, R.outputs_reported ? "Outputs on the room PC" : "Outputs (not reported yet)"),
            h("div", { class: "vrd-outputs" }, R.outputs.map((o) => h("span", { class: used.has(o) ? "used" : "" }, o))));
        if (!R.outputs_reported) {
            box.append(h("p", { class: "vrd-hint" }, "Once the Room Display is paired and running, it reports its real outputs here."));
        }
        if (s) {
            const f = (label, ctl) => h("div", { class: "vrd-field" }, h("label", { for: ctl.id }, label), ctl);
            const name = h("input", { type: "text", id: "vrdName", class: "form-control", value: s.name });
            name.addEventListener("input", () => { s.name = name.value; changed(); drawPlan(views.screens.querySelector(".vrd-plan")); });
            const out = h("select", { id: "vrdOut", class: "form-select" }, h("option", { value: "" }, "Not connected"),
                R.outputs.map((o) => h("option", { value: o, selected: o === s.output }, o + (used.has(o) && o !== s.output ? " (in use)" : ""))));
            out.addEventListener("change", () => { s.output = out.value; changed(); renderScreens(); });
            const shows = h("select", { id: "vrdShows", class: "form-select" }, Object.entries(SHOWS).map(([k, v]) => h("option", { value: k, selected: k === s.content }, v)));
            shows.addEventListener("change", () => { s.content = shows.value; changed(); renderScreens(); });
            const kids = [h("h2", {}, `Screen ${numberOf(s)}`), f("Name", name), f("Output", out), f("Shows", shows)];
            if (s.content === "mirror") {
                const m = h("select", { id: "vrdMirror", class: "form-select" }, h("option", { value: "" }, "Choose a screen"),
                    R.screens.filter((x) => x.id !== s.id).map((x) => h("option", { value: x.id, selected: String(x.id) === String(s.mirrorOf) }, `${numberOf(x)} · ${x.name}`)));
                m.addEventListener("change", () => { s.mirrorOf = m.value; changed(); renderScreens(); });
                kids.push(f("Mirror of", m));
            }
            kids.push(h("p", { class: "vrd-hint" }, `Position: ${WALLS[s.wall].label.toLowerCase()}, column ${s.x + 1}, row ${s.y + 1}, ${s.w}×${s.h} cells.`),
                h("button", { type: "button", class: "btn btn-outline-danger btn-sm", onclick: () => {
                    R.screens = R.screens.filter((x) => x.id !== s.id);
                    R.screens.forEach((x) => { if (String(x.mirrorOf) === String(s.id)) { x.mirrorOf = ""; } });
                    selScreen = null;
                    changed();
                    renderScreens();
                } }, "Remove screen"));
            box.append(...kids);
        } else {
            box.append(h("p", { class: "vrd-hint" }, "Select a screen to edit its name, output and what it shows."));
        }
        const ws = warnings();
        box.append(h("h3", {}, "Checks"), h("ul", { class: "vrd-warns" }, ws.length ? ws.map((w) => h("li", {}, w)) : h("li", { class: "ok" }, "Layout looks good.")));
    }

    // ── Console ──────────────────────────────────────────────────────────
    const supported = (type) => !TT[type]?.needs || R.has[TT[type].needs];
    const overlaps = (a, list) => list.some((b) => b.id !== a.id && a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h);

    function renderConsole() {
        const tiles = R.console[cpage];
        const seg = h("div", { class: "btn-group" }, [["call", "In a call"], ["idle", "Idle"]].map(([k, l]) =>
            h("button", { type: "button", class: `btn btn-sm ${cpage === k ? "btn-primary" : "btn-secondary"}`, "aria-pressed": String(cpage === k),
                onclick: () => { cpage = k; selTile = null; renderConsole(); } }, l)));
        const scr = h("div", { class: "vrd-device-screen", style: "aspect-ratio: 16 / 10" },
            h("div", { class: "vrd-cgrid", style: `background-size:${100 / C_COLS()}% ${100 / C_ROWS()}%` }));
        for (const tl of tiles) {
            const T = TT[tl.type];
            if (!T) {
                continue;
            }
            const el = h("div", { class: `vrd-tile ${T.cls || ""}${tl.id === selTile ? " sel" : ""}${supported(tl.type) ? "" : " unsupported"}`,
                style: `left:${(tl.x / C_COLS()) * 100}%;top:${(tl.y / C_ROWS()) * 100}%;width:${(tl.w / C_COLS()) * 100}%;height:${(tl.h / C_ROWS()) * 100}%` });
            const face = h("div", { class: "face" });
            face.innerHTML = icon(tl.type);
            face.append(h("span", {}, T.label));
            el.append(face, h("button", { type: "button", class: "x", "aria-label": `Hide ${T.label}`, onclick: (e) => {
                e.stopPropagation();
                R.console[cpage] = tiles.filter((x) => x.id !== tl.id);
                changed();
                renderConsole();
            } }, "×"), h("span", { class: "rs", "aria-hidden": "true" }));
            dragTile(el, tl, tiles, scr);
            scr.append(el);
        }
        const pal = h("div", { class: "vrd-palette" });
        for (const T of TILE_TYPES) {
            const placed = tiles.some((x) => x.type === T.t);
            const ok = supported(T.t);
            const b = h("button", { type: "button", disabled: placed || !ok, title: !ok ? "The room doesn't have this" : placed ? "Already on this page" : `Add ${T.label}` });
            b.innerHTML = icon(T.t);
            b.append(T.label);
            b.addEventListener("click", () => addTile(T.t));
            pal.append(b);
        }
        const has = h("ul", { class: "vrd-has" }, HAS.map(([k, l]) => h("li", { class: R.has[k] ? "yes" : "no" }, `${R.has[k] ? "✓" : "–"} ${l}`)));
        views.console.replaceChildren(
            h("div", { class: "vrd-panel" }, h("div", { class: "vrd-row vrd-between" }, seg, h("p", { class: "vrd-hint" }, "Drag tiles to arrange, drag a corner to resize, × to hide.")),
                h("div", { class: "vrd-device" }, scr)),
            h("aside", { class: "vrd-panel" }, h("h3", {}, "Add a tile"), pal,
                h("h3", {}, "This room has"), has,
                h("p", { class: "vrd-hint" }, "Home Assistant controls come from the room's Room Controls; the PTZ camera from its Devices tab."),
                templateBox("console")));
    }

    function addTile(type) {
        const list = R.console[cpage];
        const T = TT[type];
        for (const [w, hh] of [[T.w, T.h], [1, 1]]) {
            for (let y = 0; y <= C_ROWS() - hh; y++) {
                for (let x = 0; x <= C_COLS() - w; x++) {
                    const c = { id: uid(), type, x, y, w, h: hh };
                    if (!overlaps(c, list)) {
                        list.push(c);
                        selTile = c.id;
                        changed();
                        renderConsole();
                        return;
                    }
                }
            }
        }
        toast("No room left on this page. Hide or shrink a tile first.", "warning");
    }

    function dragTile(el, tl, list, scr) {
        el.addEventListener("pointerdown", (e) => {
            if (e.target.closest(".x")) {
                return;
            }
            e.preventDefault();
            const resizing = e.target.classList.contains("rs");
            selTile = tl.id;
            el.setPointerCapture(e.pointerId);
            const r = scr.getBoundingClientRect();
            const cell = (ev) => [Math.floor(((ev.clientX - r.left) / r.width) * C_COLS()), Math.floor(((ev.clientY - r.top) / r.height) * C_ROWS())];
            const [cx0, cy0] = cell(e);
            const ox = cx0 - tl.x;
            const oy = cy0 - tl.y;
            const move = (ev) => {
                const [cx, cy] = cell(ev);
                const c = { ...tl };
                if (resizing) {
                    c.w = clamp(cx - tl.x + 1, 1, C_COLS() - tl.x);
                    c.h = clamp(cy - tl.y + 1, 1, C_ROWS() - tl.y);
                } else {
                    c.x = clamp(cx - ox, 0, C_COLS() - tl.w);
                    c.y = clamp(cy - oy, 0, C_ROWS() - tl.h);
                }
                if (!overlaps(c, list)) {
                    Object.assign(tl, c);
                    el.style.left = `${(tl.x / C_COLS()) * 100}%`;
                    el.style.top = `${(tl.y / C_ROWS()) * 100}%`;
                    el.style.width = `${(tl.w / C_COLS()) * 100}%`;
                    el.style.height = `${(tl.h / C_ROWS()) * 100}%`;
                }
            };
            const up = () => {
                el.removeEventListener("pointermove", move);
                el.removeEventListener("pointerup", up);
                el.removeEventListener("pointercancel", up);
                changed();
                renderConsole();
            };
            el.addEventListener("pointermove", move);
            el.addEventListener("pointerup", up);
            el.addEventListener("pointercancel", up);
        });
    }

    // ── Templates ────────────────────────────────────────────────────────
    function templateBox(kind) {
        const list = R.templates.filter((t) => t.kind === kind);
        const sel = h("select", { class: "form-select form-select-sm", "aria-label": "Template" },
            list.length ? list.map((t) => h("option", { value: t.id }, t.name)) : h("option", { value: "" }, "No templates yet"));
        const name = h("input", { type: "text", class: "form-control form-control-sm", placeholder: "Template name, e.g. Standard meeting room" });
        const current = kind === "console" ? R.console_template : R.presence_template;
        return h("div", { class: "vrd-templates" }, h("h3", {}, "Layout templates"),
            current ? h("p", { class: "vrd-hint" }, `This room follows "${current}". Publishing your changes gives it its own layout.`) : null,
            h("div", { class: "vrd-row" }, sel,
                h("button", { type: "button", class: "btn btn-secondary btn-sm", disabled: !list.length, onclick: () => {
                    const t = list.find((x) => String(x.id) === sel.value);
                    if (t) {
                        if (kind === "console") {
                            R.console = structuredClone(t.layout);
                        } else {
                            R.presence = structuredClone(t.layout);
                        }
                        changed();
                        render();
                        toast(`Copied "${t.name}". Publish to use it in this room.`);
                    }
                } }, "Copy"),
                h("button", { type: "button", class: "btn btn-secondary btn-sm", disabled: !list.length, onclick: () => {
                    const t = list.find((x) => String(x.id) === sel.value);
                    if (t) {
                        api.followTemplate(kind, t.id);
                    }
                } }, "Follow")),
            h("div", { class: "vrd-row" }, name, h("button", { type: "button", class: "btn btn-secondary btn-sm", onclick: async () => {
                if (!name.value.trim()) {
                    toast("Give the template a name first.", "warning");
                    return;
                }
                const saved = await api.saveTemplate(kind, name.value.trim(), kind === "console" ? R.console : R.presence);
                R.templates = R.templates.filter((t) => t.id !== saved.id).concat(saved);
                render();
                toast(`Saved the template "${saved.name}".`, "success");
            } }, "Save as template")));
    }

    // ── Presence (door screen) ───────────────────────────────────────────
    function renderPresence() {
        const p = R.presence;
        const scr = h("div", { class: "vrd-device-screen", style: `aspect-ratio:${p.orient === "portrait" ? "3 / 4" : "4 / 3"}` });
        const st = pstate;
        const col = p.colors[st] || "#0FA585";
        const pres = h("div", { class: `vrd-pres ${p.theme === "light" ? "light" : ""}`, style: p.theme === "light" ? `background:#fff;border-top:14px solid ${col}` : `background:${col}` });
        const title = p.privacy === "booked" ? "Booked" : "Supplier review · Sam Hughes";
        const parts = {
            name: () => h("div", { class: "p-row" }, h("span", { class: "p-name" }, R.name), p.show.clock ? h("span", { class: "p-sm" }, "10:42") : null),
            status: () => h("div", { class: "p-status", style: p.theme === "light" ? `color:${col}` : "" }, STATUS[st]),
            current: () => (st === "in_use" || st === "dnd" ? h("div", { class: "p-sm" }, title)
                : st === "soon" ? h("div", { class: "p-sm" }, `10:50 ${p.privacy === "booked" ? "Booked" : "Weekly sync"}`) : h("div", { class: "p-sm" }, "Free until 14:00")),
            timeleft: () => (st === "in_use" || st === "dnd" ? h("div", { class: "p-sm" }, "Until 11:30 · 48 min left") : st === "soon" ? h("div", { class: "p-sm" }, "Starts at 10:50") : null),
            dnd: () => (st === "dnd" ? h("div", { class: "p-dnd" }, "Do not disturb – emergencies only", h("div", { class: "p-sm" }, "Interview in progress · until 11:30")) : null),
            today: () => h("div", { class: "p-list" }, [["09:00–09:30", "Stand-up"], ["10:50–11:30", "Weekly sync"], ["14:00–15:00", "Customer call"]].map(([tm, n]) => h("div", {}, h("b", {}, tm), " ", p.privacy === "booked" ? "Booked" : n))),
            booknow: () => (st === "available" || st === "soon" ? h("div", { class: "p-book" }, (st === "soon" ? ["Book until 10:50"] : ["Book 15 min", "30 min", "60 min"]).map((x) => h("span", {}, x))) : null),
            meta: () => h("div", { class: "p-sm" }, `${R.capacity || 8} seats`),
            clock: () => null,
        };
        for (const k of p.order) {
            if (p.show[k] && parts[k]) {
                const n = parts[k]();
                if (n) {
                    pres.append(n);
                }
            }
        }
        scr.append(pres);
        const seg = h("div", { class: "btn-group" }, [["available", "Available"], ["soon", "Booked soon"], ["in_use", "In use"], ["dnd", "Do not disturb"]].map(([k, l]) =>
            h("button", { type: "button", class: `btn btn-sm ${pstate === k ? "btn-primary" : "btn-secondary"}`, onclick: () => { pstate = k; renderPresence(); } }, l)));
        const blocks = h("ul", { class: "vrd-blocks" });
        p.order.forEach((k, i) => {
            const cb = h("input", { type: "checkbox", id: `vrd-blk-${k}`, class: "form-check-input", checked: !!p.show[k] });
            cb.addEventListener("change", () => { p.show[k] = cb.checked ? 1 : 0; changed(); renderPresence(); });
            const mv = (d) => {
                const j = i + d;
                if (j < 0 || j >= p.order.length) {
                    return;
                }
                [p.order[i], p.order[j]] = [p.order[j], p.order[i]];
                changed();
                renderPresence();
            };
            blocks.append(h("li", {}, h("label", { for: `vrd-blk-${k}` }, cb, BLOCKS[k] || k),
                h("button", { type: "button", class: "btn btn-light btn-sm", "aria-label": `Move ${BLOCKS[k]} up`, onclick: () => mv(-1) }, "↑"),
                h("button", { type: "button", class: "btn btn-light btn-sm", "aria-label": `Move ${BLOCKS[k]} down`, onclick: () => mv(1) }, "↓")));
        });
        const select = (label, key, options) => {
            const s = h("select", { class: "form-select form-select-sm", id: `vrd-${key}` }, options.map(([v, l]) => h("option", { value: v, selected: p[key] === v }, l)));
            s.addEventListener("change", () => { p[key] = s.value; changed(); renderPresence(); });
            return h("div", { class: "vrd-field" }, h("label", { for: `vrd-${key}` }, label), s);
        };
        const swatches = h("div", { class: "vrd-swatches" }, [["available", "Available"], ["soon", "Booked soon"], ["in_use", "In use"], ["dnd", "Do not disturb"]].map(([k, l]) => {
            const inp = h("input", { type: "color", id: `vrd-col-${k}`, value: p.colors[k] });
            inp.addEventListener("input", () => { p.colors[k] = inp.value; changed(); renderPresence(); });
            return h("label", { for: `vrd-col-${k}` }, inp, l);
        }));
        views.presence.replaceChildren(
            h("div", { class: "vrd-panel" }, h("div", { class: "vrd-row vrd-between" }, seg, h("p", { class: "vrd-hint" }, "Preview as the door tablet shows it (sample bookings).")),
                h("div", { class: `vrd-device ${p.orient === "portrait" ? "portrait" : ""}` }, scr)),
            h("aside", { class: "vrd-panel" }, h("h3", {}, "Blocks"), blocks,
                select("Theme", "theme", [["dark", "Full colour"], ["light", "Light"]]),
                select("Orientation", "orient", [["landscape", "Landscape"], ["portrait", "Portrait"]]),
                select("Bookings show", "privacy", [["title", "Title and organiser"], ["booked", "\"Booked\" only"]]),
                h("h3", {}, "Status colours"), swatches, templateBox("presence")));
    }

    render();
    return {
        getData() {
            return { screens: R.screens, console: R.console, presence: R.presence };
        },
    };
}
