/** Room Board: the live status of several rooms, full screen on a PC or tablet. */
import { $, boot, h, sheet } from "./common.js";

const ST = { available: ["Available", "var(--ok)"], soon: ["Booked soon", "var(--soon)"], in_use: ["In use", "var(--busy)"], dnd: ["Do not disturb", "var(--dnd)"] };
let ctl = null;

export async function start() {
    ctl = await boot({ statePath: "/video_rooms/board/state", every: 10000, render });
}

function render(b, { offline = false } = {}) {
    const root = h("div", { class: `vr-board ${b.theme === "light" ? "light" : ""} ${offline ? "is-offline" : ""}` },
        h("header", { class: "b-head" }, h("h1", {}, b.name), h("span", {}, `${b.now} · ${b.date}`)));
    if (!b.rooms.length) {
        root.append(h("p", {}, "No rooms on this board yet."));
    }
    if (b.view === "tiles" || b.view === "tiles_timeline") {
        root.append(h("div", { class: "b-tiles", style: { gridTemplateColumns: `repeat(${b.columns || 4}, minmax(0, 1fr))` } }, b.rooms.map((r) => roomTile(b, r))));
    }
    if (b.view === "list") {
        root.append(h("table", { class: "b-list" }, h("tr", {}, h("th", {}, "Room"), h("th", {}, "Status"), h("th", {}, "Now"), h("th", {}, "Next")),
            b.rooms.map((r) => h("tr", {}, h("td", {}, r.name), h("td", {}, h("i", { class: "b-dot", style: { background: ST[r.availability][1] } }), ST[r.availability][0]),
                h("td", {}, r.current ? `${r.current.title} until ${r.current.end}` : "–"), h("td", {}, r.next ? `${r.next.start} ${r.next.title}` : "–")))));
    }
    if (b.view === "timeline" || b.view === "tiles_timeline") {
        root.append(timeline(b));
    }
    if (offline) {
        root.append(h("div", { class: "p-offline" }, "Offline – showing the last known status"));
    }
    $("#app").replaceChildren(root);
}

function roomTile(b, r) {
    const [label, colour] = ST[r.availability] || ST.available;
    const lines = [];
    if (b.show.current && r.current) {
        lines.push(`${r.current.title} · until ${r.current.end}`);
    }
    if (b.show.dnd && r.dnd?.active) {
        lines.push("Emergencies only");
    }
    if (b.show.next) {
        lines.push(r.next ? `Next: ${r.next.start} ${r.next.title}` : "No more bookings today");
    }
    if (b.show.platform && r.call?.platform) {
        lines.push(`${r.call.platform} call`);
    }
    if (b.show.capacity && r.capacity) {
        lines.push(`${r.capacity} seats`);
    }
    return h("div", { class: "b-tile", style: { borderLeftColor: colour } },
        h("b", {}, r.name), h("span", { class: "b-st", style: { color: colour } }, label),
        lines.map((l) => h("span", { class: "b-ln" }, l)),
        b.book_now && (r.book_now || []).length ? h("button", { class: "b-book", onclick: () => book(r) }, "Book now") : null);
}

function book(room) {
    const box = sheet(`Book ${room.name}`, h("div", { class: "vr-row wrap" }, room.book_now.map((m) => h("button", {
        class: "vr-btn big", onclick: async () => { box.close(); await ctl.act("/video_rooms/board/action", "book_now", { room_id: room.id, minutes: m }); },
    }, `${m} minutes`))));
}

function timeline(b) {
    const H0 = 8;
    const H1 = 18;
    const pct = (ts) => {
        const d = new Date(ts.replace(" ", "T") + "Z");
        const hours = d.getHours() + d.getMinutes() / 60;
        return Math.max(0, Math.min(100, ((hours - H0) / (H1 - H0)) * 100));
    };
    const now = new Date();
    const nowPct = Math.max(0, Math.min(100, ((now.getHours() + now.getMinutes() / 60 - H0) / (H1 - H0)) * 100));
    const axis = h("div", { class: "t-axis" });
    for (let hr = H0; hr <= H1; hr += 2) {
        axis.append(h("span", { style: { left: `${((hr - H0) / (H1 - H0)) * 100}%` } }, String(hr).padStart(2, "0")));
    }
    return h("div", { class: "b-timeline" }, h("span"), axis, b.rooms.map((r) => [
        h("span", { class: "t-name" }, r.name),
        h("div", { class: "t-bar" }, (r.today || []).map((m) => h("span", {
            class: r.current && r.current.id === m.id ? "is-now" : "",
            style: { left: `${pct(m.start_ts)}%`, width: `${Math.max(0.5, pct(m.end_ts) - pct(m.start_ts))}%` },
            title: `${m.start}–${m.end} ${m.title}`,
        })), h("i", { class: "t-now", style: { left: `${nowPct}%` } })),
    ]));
}
