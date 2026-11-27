/** Room Console: the tablet on the meeting-room table. Anyone in the room can use it;
 *  setup (identify screens, restart the display) is behind the room's admin PIN. */
import { $, boot, h, sheet, toast } from "./common.js";
import { icon } from "./icons.js";

const ROUTE = "/video_rooms/console/action";
const LABELS = {
    join: "Join", mic: "Microphone", camera: "Camera", volume: "Volume", share: "Share", layout: "Call layout",
    leave: "Leave call", dnd: "Do not disturb", ptz: "Camera presets", tv: "Screens", lighting: "Lighting",
    climate: "Air conditioning", blinds: "Blinds", glass: "Window film", scenes: "Room presets",
};
const HA_TILES = { lighting: "lighting", climate: "climate", blinds: "cover", glass: "glass", scenes: "scene" };
let ctl = null;
let pinUnlocked = false;

export async function start() {
    ctl = await boot({
        statePath: "/video_rooms/console/state",
        // Snappy while a call is joining or running; relaxed when idle.
        every: (state) => (state && (state.call || state.display?.call_state) ? 1500 : 4000),
        render,
    });
}

const act = (action, params) => ctl.act(ROUTE, action, params);
const inCall = (s) => Boolean(s.call || ["prejoin", "lobby", "in_call"].includes(s.display?.call_state));

function render(s, { offline = false } = {}) {
    const app = $("#app");
    const page = inCall(s) ? "call" : "idle";
    const layout = s.layout || {};
    const cols = layout.cols || 6;
    const rows = layout.rows || 4;
    const tiles = (layout[page] || []).filter((t) => tileAvailable(t.type, s));
    const grid = h("div", { class: "vr-grid", style: { gridTemplateColumns: `repeat(${cols}, 1fr)`, gridTemplateRows: `repeat(${rows}, 1fr)` } },
        tiles.map((t) => h("div", { class: "vr-cell", style: { gridColumn: `${t.x + 1} / span ${t.w}`, gridRow: `${t.y + 1} / span ${t.h}` } }, tile(t.type, s))));
    app.replaceChildren(h("div", { class: `vr-console ${offline ? "is-offline" : ""}` }, header(s), banner(s), grid));
}

function tileAvailable(type, s) {
    if (HA_TILES[type]) {
        return (s.controls || []).some((c) => c.panel === HA_TILES[type]);
    }
    return true;
}

function header(s) {
    const status = { available: "Available", soon: "Booked soon", in_use: "In use", dnd: "Do not disturb" }[s.availability] || "";
    return h("header", { class: "vr-head" },
        h("div", {}, h("h1", {}, s.name), h("span", { class: `vr-pill st-${s.availability}` }, status)),
        h("div", { class: "vr-head-right" },
            s.display?.online ? null : h("span", { class: "vr-pill st-warn" }, "Room display offline"),
            h("span", { class: "vr-clock" }, s.now),
            h("button", { class: "vr-icon-btn", "aria-label": "Setup", onclick: () => openSetup(s) }, icon("gear"))));
}

function banner(s) {
    const items = [];
    if (s.display?.error) {
        items.push(h("div", { class: "vr-banner bad" }, s.display.error));
    }
    if (s.call && s.call.state === "lobby") {
        items.push(h("div", { class: "vr-banner info" }, `Waiting in the ${s.call.platform} lobby for the host to let the room in…`));
    } else if (s.call && s.call.state === "joining") {
        items.push(h("div", { class: "vr-banner info" }, `Joining the ${s.call.platform} call…`));
    }
    const cur = s.current;
    if (cur && s.checkin?.required && !cur.checked_in) {
        items.push(h("div", { class: "vr-banner warn" }, `Check in to "${cur.title}" within ${s.checkin.minutes} minutes or the room is released.`,
            h("button", { class: "vr-btn", onclick: () => act("checkin") }, "Check in")));
    }
    if (s.dnd?.active) {
        items.push(h("div", { class: "vr-banner dnd" }, `Do not disturb${s.dnd.until ? ` until ${s.dnd.until}` : ""}${s.dnd.message ? ` · ${s.dnd.message}` : ""}`,
            h("button", { class: "vr-btn", onclick: () => act("dnd", { active: false }) }, "Turn off")));
    }
    return h("div", { class: "vr-banners" }, items);
}

function tile(type, s) {
    const d = s.display || {};
    const button = (label, ico, onclick, cls = "", pressed = null) =>
        h("button", { class: `vr-tile ${cls}`, onclick, "aria-pressed": pressed == null ? false : String(pressed) }, icon(ico), h("span", {}, label));
    switch (type) {
        case "join":
            return joinTile(s);
        case "mic":
            return button(d.mic === false ? "Mic off" : "Mic on", d.mic === false ? "mic_off" : "mic", () => act("mic", { value: d.mic === false }), d.mic === false ? "is-off" : "", d.mic !== false);
        case "camera":
            return button(d.camera === false ? "Camera off" : "Camera on", d.camera === false ? "camera_off" : "camera", () => act("camera", { value: d.camera === false }), d.camera === false ? "is-off" : "", d.camera !== false);
        case "volume":
            return volumeTile(d);
        case "share":
            return button(d.sharing ? "Sharing" : "Share", "share", () => openShare(s), d.sharing ? "is-on" : "");
        case "layout":
            return button("Call layout", "layout", () => openLayout());
        case "leave":
            return button("Leave call", "leave", () => confirmLeave(), "hot", null);
        case "dnd":
            return button(s.dnd?.active ? "Do not disturb: on" : "Do not disturb", "dnd", () => openDnd(s), s.dnd?.active ? "dnd is-on" : "dnd");
        case "tv":
            return h("div", { class: "vr-tile vr-split" }, icon("tv"), h("span", {}, "Screens"),
                h("div", { class: "vr-row" }, h("button", { class: "vr-btn", onclick: () => act("tv", { value: true }) }, "On"),
                    h("button", { class: "vr-btn", onclick: () => act("tv", { value: false }) }, "Off")));
        case "ptz":
            return h("div", { class: "vr-tile vr-split" }, icon("ptz"), h("span", {}, "Camera presets"),
                h("div", { class: "vr-row" }, [1, 2, 3, 4].map((n) => h("button", { class: "vr-btn", onclick: () => act("device", { kind: "ptz", value: n }) }, String(n)))));
        default:
            if (HA_TILES[type]) {
                return haTile(type, s);
            }
            return button(LABELS[type] || type, type, () => {});
    }
}

function joinTile(s) {
    const list = s.today || [];
    return h("div", { class: "vr-tile vr-join" },
        h("div", { class: "vr-join-head" }, icon("today"), h("span", {}, "Today"),
            h("button", { class: "vr-btn primary", onclick: () => openJoinLink(s) }, "Join by link")),
        h("ul", { class: "vr-meetings" }, list.length ? list.map((m) => h("li", { class: s.current && s.current.id === m.id ? "is-now" : "" },
            h("span", { class: "vr-time" }, `${m.start}–${m.end}`),
            h("span", { class: "vr-title" }, m.title, m.platform ? h("small", {}, m.platform) : null),
            m.can_join ? h("button", { class: "vr-btn primary", onclick: () => act("join_booking", { meeting_id: m.id }) }, "Join") : null))
            : h("li", { class: "vr-empty" }, "No bookings today.")));
}

function volumeTile(d) {
    const value = Number.isFinite(d.volume) ? d.volume : 60;
    const slider = h("input", { type: "range", min: 0, max: 100, step: 5, value, "aria-label": "Volume" });
    slider.addEventListener("change", () => act("volume", { value: Number(slider.value) }));
    return h("div", { class: "vr-tile vr-split" }, icon("volume"), h("span", {}, `Volume ${value}%`), slider);
}

function haTile(type, s) {
    const controls = (s.controls || []).filter((c) => c.panel === HA_TILES[type]);
    return h("div", { class: "vr-tile vr-split ha" }, icon(type), h("span", {}, LABELS[type]),
        h("div", { class: "vr-row wrap" }, controls.map((c) => h("button", {
            class: `vr-btn ${c.on ? "is-on" : ""}`, onclick: () => act("device", { control_id: c.id, value: !c.on }),
        }, c.label || c.name))));
}

function confirmLeave() {
    const box = h("div", { class: "vr-stack" }, h("p", {}, "Leave the call for everyone in this room?"),
        h("div", { class: "vr-row" }, h("button", { class: "vr-btn hot", onclick: () => { s.close(); act("leave"); } }, "Leave call"),
            h("button", { class: "vr-btn", onclick: () => s.close() }, "Stay")));
    const s = sheet("Leave call", box);
}

function openJoinLink(state) {
    const url = h("input", { type: "url", placeholder: "Paste the meeting link", class: "vr-input", autocomplete: "off" });
    const platform = h("select", { class: "vr-input" }, (state.platforms || []).filter((p) => p.by_id).map((p) => h("option", { value: p.id }, p.name)));
    const code = h("input", { type: "text", placeholder: "Meeting ID", class: "vr-input", autocomplete: "off" });
    const pass = h("input", { type: "text", placeholder: "Passcode (if any)", class: "vr-input", autocomplete: "off" });
    const go = async () => {
        const params = url.value.trim() ? { url: url.value.trim() } : { platform_id: Number(platform.value), code: code.value, passcode: pass.value };
        const result = await act("join_link", params);
        if (result.ok) {
            box.close();
        }
    };
    const box = sheet("Join a meeting", h("div", { class: "vr-stack" },
        h("label", {}, "Meeting link"), url,
        h("p", { class: "vr-muted" }, "Or, without a link:"),
        h("div", { class: "vr-row" }, platform, code, pass),
        h("button", { class: "vr-btn primary big", onclick: go }, "Join")));
    url.focus();
}

function openShare(s) {
    const d = s.display || {};
    const origin = location.origin;
    const body = h("div", { class: "vr-stack" },
        h("div", { class: "vr-choice" },
            h("h3", {}, "Laptop cable (HDMI)"),
            h("p", {}, d.hdmi ? "Plug the laptop into the room's HDMI cable, then:" : "The HDMI capture isn't connected on the room PC."),
            h("button", { class: "vr-btn primary", disabled: !d.hdmi, onclick: () => act("share", { value: "hdmi" }) }, "Share the laptop")),
        h("div", { class: "vr-choice" },
            h("h3", {}, "Wireless"),
            h("p", {}, "On the laptop, open ", h("b", {}, `${origin}/video_rooms/share`), " and type the code ", h("b", { class: "vr-code" }, d.share_code || "–"), ".")),
        h("div", { class: "vr-choice" },
            h("h3", {}, "From the laptop itself"),
            h("p", {}, "Join the same meeting on the laptop with its microphone and speakers off, and share from there.")),
        d.sharing ? h("button", { class: "vr-btn hot big", onclick: () => act("share", { value: "stop" }) }, "Stop sharing") : null);
    sheet("Share a screen", body);
}

function openLayout() {
    const choose = (value) => { act("layout", { value }); box.close(); };
    const box = sheet("Call layout", h("div", { class: "vr-row wrap" },
        [["gallery", "Gallery"], ["speaker", "Speaker"], ["content", "Shared content"]].map(([v, l]) => h("button", { class: "vr-btn big", onclick: () => choose(v) }, l))));
}

function openDnd(s) {
    if (s.dnd?.active) {
        act("dnd", { active: false });
        return;
    }
    const message = h("input", { type: "text", class: "vr-input", placeholder: "Message on the door (optional), e.g. Interview in progress", maxlength: 80 });
    const on = (minutes) => { act("dnd", { active: true, minutes, message: message.value }); box.close(); };
    const box = sheet("Do not disturb", h("div", { class: "vr-stack" },
        h("p", {}, "The door shows that only emergencies may interrupt. It turns off by itself at the end of the booking or call, or after 4 hours at the most."),
        message,
        h("div", { class: "vr-row wrap" },
            h("button", { class: "vr-btn dnd big", onclick: () => on(null) }, s.current ? `Until ${s.current.end}` : "Until I turn it off"),
            [30, 60, 120].map((m) => h("button", { class: "vr-btn big", onclick: () => on(m) }, m < 60 ? `${m} minutes` : `${m / 60} hour${m > 60 ? "s" : ""}`)))));
}

function openSetup(s) {
    const pin = h("input", { type: "password", inputmode: "numeric", class: "vr-input", placeholder: "Admin PIN" });
    const run = async (action) => {
        const result = await act(action, { pin: pin.value });
        if (result.ok) {
            pinUnlocked = true;
        }
    };
    const body = h("div", { class: "vr-stack" },
        h("p", { class: "vr-muted" }, `${s.tablet || "This tablet"} · ${s.name}`),
        s.has_pin ? pin : h("p", {}, "Set a Console Admin PIN on the room in Odoo to use setup here."),
        h("div", { class: "vr-row wrap" },
            h("button", { class: "vr-btn big", disabled: !s.has_pin, onclick: () => run("identify") }, "Identify screens"),
            h("button", { class: "vr-btn big", disabled: !s.has_pin, onclick: () => run("restart") }, "Restart room display")),
        h("p", { class: "vr-muted" }, "Screens and layouts are set in Odoo: Video Rooms › Rooms › Room Designer."),
        pinUnlocked ? h("p", { class: "vr-muted" }, "Setup unlocked.") : null);
    sheet("Setup", body);
}
