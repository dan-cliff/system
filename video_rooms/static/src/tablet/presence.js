/** Door screen (Presence): a big, clear room status, today's bookings, Book Now and
 *  check-in, laid out as designed in the Room Designer. Never shows joining details. */
import { $, boot, h } from "./common.js";

const ROUTE = "/video_rooms/presence/action";
const STATUS = { available: "Available", soon: "Booked soon", in_use: "In use", dnd: "In use" };
let ctl = null;

export async function start() {
    ctl = await boot({ statePath: "/video_rooms/presence/state", every: 8000, render });
}

function render(s, { offline = false } = {}) {
    const layout = s.layout || {};
    const colors = layout.colors || {};
    const st = s.availability;
    const colour = colors[st] || "#0FA585";
    const light = layout.theme === "light";
    const show = layout.show || {};
    const root = h("div", {
        class: `vr-presence ${light ? "light" : ""} ${layout.orient === "portrait" ? "portrait" : ""} ${offline ? "is-offline" : ""}`,
        style: light ? { borderTop: `18px solid ${colour}` } : { background: colour },
    });
    const parts = {
        name: () => h("div", { class: "p-row" }, h("span", { class: "p-name" }, s.name), show.clock ? h("span", { class: "p-clock" }, s.now) : null),
        status: () => h("div", { class: "p-status", style: light ? { color: colour } : {} }, STATUS[st] || ""),
        current: () => {
            if (s.current) {
                return h("div", { class: "p-sm" }, s.current.title, s.current.organiser ? ` · ${s.current.organiser}` : "");
            }
            if (st === "soon" && s.next) {
                return h("div", { class: "p-sm" }, `${s.next.start} ${s.next.title}`);
            }
            return h("div", { class: "p-sm" }, s.next ? `Free until ${s.next.start}` : "Free for the rest of the day");
        },
        timeleft: () => (s.current ? h("div", { class: "p-sm" }, `Until ${s.current.end} · ${s.minutes_left} min left`)
            : st === "soon" && s.next ? h("div", { class: "p-sm" }, `Starts at ${s.next.start}`) : null),
        dnd: () => (s.dnd?.active ? h("div", { class: "p-dnd" }, "Do not disturb – emergencies only",
            h("div", { class: "p-sm" }, [s.dnd.message, s.dnd.until ? `until ${s.dnd.until}` : ""].filter(Boolean).join(" · "))) : null),
        today: () => h("div", { class: "p-list" }, (s.today || []).length
            ? s.today.map((m) => h("div", { class: s.current && s.current.id === m.id ? "is-now" : "" }, h("b", {}, `${m.start}–${m.end}`), " ", m.title))
            : h("div", {}, "No bookings today.")),
        booknow: () => bookNow(s),
        meta: () => h("div", { class: "p-meta" }, s.capacity ? h("span", {}, `${s.capacity} seats`) : null, s.temperature ? h("span", {}, s.temperature) : null),
        clock: () => null,
    };
    for (const key of layout.order || Object.keys(parts)) {
        if (show[key] && parts[key]) {
            const node = parts[key]();
            if (node) {
                root.append(node);
            }
        }
    }
    if (offline) {
        root.append(h("div", { class: "p-offline" }, "Offline – showing the last known status"));
    }
    $("#app").replaceChildren(root);
}

function bookNow(s) {
    const items = [];
    const cur = s.current;
    if (cur && s.checkin?.required && !cur.checked_in) {
        items.push(h("button", { class: "p-btn", onclick: () => ctl.act(ROUTE, "checkin") }, "Check in"));
    }
    if ((s.book_now || []).length) {
        const limit = s.next ? ` (until ${s.next.start} at the latest)` : "";
        items.push(...s.book_now.map((m) => h("button", { class: "p-btn", onclick: () => ctl.act(ROUTE, "book_now", { minutes: m }) },
            `Book ${m} min`)));
        if (limit) {
            items.push(h("span", { class: "p-sm" }, limit));
        }
    }
    return items.length ? h("div", { class: "p-book" }, items) : null;
}
