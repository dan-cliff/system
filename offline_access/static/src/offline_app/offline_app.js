/**
 * Offline Access: the offline screens shown at /odoo/offline when the server
 * can't be reached. Read-only views of the records the web client saved on
 * this device (see ../offline_store.js): a list of Offline Models, their
 * records, and each record laid out like its normal form.
 *
 * Plain JavaScript with no Odoo dependencies, so it starts without the web
 * client. Every value is put on the page as text, never as HTML.
 */
import { clearStore, findRecord, getMeta, getModel, getModels, getRecord, getRecords } from "../offline_store.js";

const main = document.getElementById("oa-main");
const titleEl = document.getElementById("oa-title");
const subtitleEl = document.getElementById("oa-subtitle");
const statusEl = document.getElementById("oa-status");
const backEl = document.getElementById("oa-back");
const bannerEl = document.getElementById("oa-banner");
const bannerTextEl = document.getElementById("oa-banner-text");
const APP_NAME = document.body.dataset.appName || "Odoo";
const DB = document.body.dataset.db || "";
const DAY = 24 * 60 * 60 * 1000;

// ── Formatting (dates as dd/mm/yyyy, times as HH:MM) ─────────────────────────

const pad = (n) => String(n).padStart(2, "0");

function formatDate(value) {
    const [y, m, d] = String(value).slice(0, 10).split("-");
    return `${d}/${m}/${y}`;
}

/** Odoo sends timestamps in UTC; show them in this device's time zone. */
function formatDatetime(value) {
    const date = value instanceof Date ? value : new Date(String(value).replace(" ", "T") + "Z");
    if (isNaN(date)) {
        return String(value);
    }
    return `${pad(date.getDate())}/${pad(date.getMonth() + 1)}/${date.getFullYear()} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function htmlToText(value) {
    const doc = new DOMParser().parseFromString(String(value), "text/html");
    for (const br of doc.querySelectorAll("br")) {
        br.replaceWith("\n");
    }
    for (const block of doc.querySelectorAll("p, div, li, h1, h2, h3, h4, tr")) {
        block.append("\n");
    }
    return (doc.body.textContent || "").replace(/\n{3,}/g, "\n\n").trim();
}

function isEmpty(field, value) {
    if (["one2many", "many2many"].includes(field.type)) {
        return !value || !value.count;
    }
    if (field.type === "integer" || field.type === "float" || field.type === "monetary") {
        // Zero is left out like an empty field, so unused sections stay hidden.
        return !value;
    }
    return value === false || value === null || value === undefined || value === "";
}

/** A field's value as text, or "" when there is nothing to show. */
function formatValue(field, value) {
    if (isEmpty(field, value)) {
        return "";
    }
    switch (field.type) {
        case "boolean":
            return value ? "Yes" : "";
        case "date":
            return formatDate(value);
        case "datetime":
            return formatDatetime(value);
        case "selection": {
            const option = (field.selection || []).find(([key]) => key === value);
            return option ? option[1] : String(value);
        }
        case "many2one":
            return Array.isArray(value) ? value[1] || "" : String(value);
        case "float":
            return field.digits !== undefined ? Number(value).toFixed(field.digits) : String(value);
        case "monetary":
            return Number(value).toFixed(2);
        case "html":
            return htmlToText(value);
        case "one2many":
        case "many2many":
            return value.lines.map((line) => line.display_name).join(", ");
        default:
            return String(value);
    }
}

// ── Page helpers ─────────────────────────────────────────────────────────────

function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) {
        if (key === "class") {
            node.className = value;
        } else if (key.startsWith("on")) {
            node.addEventListener(key.slice(2), value);
        } else if (value !== undefined && value !== null && value !== false) {
            node.setAttribute(key, value === true ? "" : value);
        }
    }
    for (const child of children.flat()) {
        if (child !== null && child !== undefined && child !== false) {
            node.append(child instanceof Node ? child : document.createTextNode(String(child)));
        }
    }
    return node;
}

function setHeader(title, back) {
    titleEl.textContent = title;
    document.title = title === APP_NAME ? APP_NAME : `${title} - ${APP_NAME}`;
    backEl.hidden = !back;
    backEl.onclick = back ? () => (window.location.hash = back) : null;
}

function show(...nodes) {
    main.replaceChildren(...nodes);
    window.scrollTo(0, 0);
}

function message(title, text) {
    return el("div", { class: "oa-empty" }, el("h2", {}, title), el("p", {}, text));
}

function updateStatus() {
    const online = navigator.onLine;
    statusEl.textContent = online ? "Online" : "Offline";
    statusEl.classList.toggle("oa-online", online);
    bannerEl.hidden = !online;
    bannerTextEl.textContent = "You're back online.";
}

// ── Screens ──────────────────────────────────────────────────────────────────

async function loadMeta() {
    const meta = await getMeta();
    if (!meta || (DB && meta.db && meta.db !== DB)) {
        return null;
    }
    const age = Date.now() - new Date(meta.last_sync).getTime();
    if (meta.max_offline_days && age > meta.max_offline_days * DAY) {
        await clearStore();
        return { expired: true, ...meta };
    }
    return meta;
}

async function homeScreen(meta) {
    setHeader(APP_NAME, null);
    const models = (await getModels()).filter((model) => model.count);
    if (!models.length) {
        show(message("No records on this device", "Nothing is set up for offline use, or you can't see any of it."));
        return;
    }
    show(
        el(
            "ul",
            { class: "oa-list" },
            models.map((model) =>
                el(
                    "li",
                    {},
                    el(
                        "a",
                        { href: `#m/${model.id}`, class: "oa-row" },
                        el("span", { class: "oa-row-title" }, model.name),
                        el("span", { class: "oa-count" }, model.count)
                    )
                )
            )
        )
    );
}

function sortByServerOrder(model, records) {
    const position = new Map((model.order || []).map((id, index) => [id, index]));
    return records.sort((a, b) => (position.get(a.id) ?? 1e9) - (position.get(b.id) ?? 1e9));
}

function allFields(model) {
    return model.layout.sections.flatMap((section) => section.fields);
}

async function listScreen(modelId) {
    const model = await getModel(modelId);
    if (!model) {
        return homeScreen();
    }
    setHeader(model.name, "#");
    const fieldsByName = Object.fromEntries(allFields(model).map((f) => [f.name, f]));
    const columns = model.layout.list_columns.map((name) => fieldsByName[name]).filter(Boolean);
    const records = sortByServerOrder(model, await getRecords(modelId));
    const rows = records.map((record) => {
        const details = columns
            .map((field) => formatValue(field, record[field.name]))
            .filter((text) => text && text !== record.display_name);
        const text = [record.display_name, ...details].join(" ").toLowerCase();
        return {
            text,
            node: el(
                "li",
                {},
                el(
                    "a",
                    { href: `#r/${model.id}/${record.id}`, class: "oa-row" },
                    el(
                        "span",
                        { class: "oa-row-body" },
                        el("span", { class: "oa-row-title" }, record.display_name || `#${record.id}`),
                        details.length ? el("span", { class: "oa-row-details" }, details.join(" · ")) : null
                    )
                )
            ),
        };
    });
    const list = el("ul", { class: "oa-list" }, rows.map((row) => row.node));
    const empty = el("p", { class: "oa-none", hidden: true }, "No matching records.");
    const search = el("input", {
        type: "search",
        class: "oa-search",
        placeholder: `Search ${model.name}`,
        "aria-label": "Search",
        oninput: () => {
            const terms = search.value.toLowerCase().split(/\s+/).filter(Boolean);
            let shown = 0;
            for (const row of rows) {
                const match = terms.every((term) => row.text.includes(term));
                row.node.hidden = !match;
                shown += match ? 1 : 0;
            }
            empty.hidden = shown > 0;
        },
    });
    show(search, list, empty);
}

async function relatedLink(field, value) {
    if (field.type !== "many2one" || !Array.isArray(value) || !field.relation) {
        return null;
    }
    const found = await findRecord(field.relation, value[0]);
    return found ? `#r/${found.model.id}/${value[0]}` : null;
}

function linesTable(field, value) {
    const wrapper = el("div", { class: "oa-lines" });
    if (field.columns && field.columns.length) {
        wrapper.append(
            el(
                "table",
                {},
                el("thead", {}, el("tr", {}, field.columns.map((c) => el("th", {}, c.string)))),
                el(
                    "tbody",
                    {},
                    value.lines.map((line) =>
                        el(
                            "tr",
                            {},
                            field.columns.map((c) =>
                                el("td", {}, line[c.name] === 0 ? "0" : formatValue(c, line[c.name]))
                            )
                        )
                    )
                )
            )
        );
    } else {
        wrapper.append(
            el("div", { class: "oa-tags" }, value.lines.map((line) => el("span", { class: "oa-tag" }, line.display_name)))
        );
    }
    const missing = value.count - value.lines.length;
    if (missing > 0) {
        wrapper.append(el("p", { class: "oa-none" }, `${missing} more not saved on this device.`));
    }
    return wrapper;
}

async function recordScreen(modelId, recordId) {
    const model = await getModel(modelId);
    const record = model && (await getRecord(modelId, recordId));
    if (!record) {
        return model ? listScreen(modelId) : homeScreen();
    }
    setHeader(record.display_name || model.name, `#m/${model.id}`);
    const nodes = [el("p", { class: "oa-kicker" }, model.name)];
    for (const section of model.layout.sections) {
        const rows = [];
        for (const field of section.fields) {
            const value = record[field.name];
            if (isEmpty(field, value) || (field.type === "boolean" && !value)) {
                continue;
            }
            let content;
            if (["one2many", "many2many"].includes(field.type)) {
                content = linesTable(field, value);
            } else {
                const text = formatValue(field, value);
                const href = await relatedLink(field, value);
                content = href
                    ? el("a", { href }, text)
                    : el("span", { class: field.type === "text" || field.type === "html" ? "oa-multiline" : "" }, text);
            }
            rows.push(el("div", { class: "oa-field" }, el("div", { class: "oa-label" }, field.string), el("div", { class: "oa-value" }, content)));
        }
        if (rows.length) {
            nodes.push(el("section", { class: "oa-section" }, section.title ? el("h2", {}, section.title) : null, rows));
        }
    }
    show(...nodes);
}

async function route() {
    updateStatus();
    let meta;
    try {
        meta = await loadMeta();
    } catch {
        meta = null;
    }
    if (!meta) {
        setHeader(APP_NAME, null);
        subtitleEl.textContent = "";
        show(
            message(
                "No records on this device",
                "Open Odoo while you're online and signed in. Records set up for offline use are then saved on this device."
            )
        );
        return;
    }
    if (meta.expired) {
        setHeader(APP_NAME, null);
        subtitleEl.textContent = "";
        show(
            message(
                "Offline records removed",
                `This device hadn't synced for over ${meta.max_offline_days} days, so its offline records were removed. Open Odoo while online to save them again.`
            )
        );
        return;
    }
    subtitleEl.textContent = `Saved ${formatDatetime(new Date(meta.last_sync))} · ${meta.user_name}`;
    const [screen, ...ids] = window.location.hash.replace(/^#/, "").split("/");
    const numbers = ids.map((id) => parseInt(id, 10));
    if (screen === "m" && numbers[0]) {
        await listScreen(numbers[0]);
    } else if (screen === "r" && numbers[0] && numbers[1]) {
        await recordScreen(numbers[0], numbers[1]);
    } else {
        await homeScreen(meta);
    }
}

window.addEventListener("hashchange", route);
window.addEventListener("online", updateStatus);
window.addEventListener("offline", updateStatus);
route().catch((error) => {
    show(message("Offline records can't be shown", String(error)));
});
