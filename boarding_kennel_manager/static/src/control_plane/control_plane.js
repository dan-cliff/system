/* Kennel Control Plane: draws a yard's enclosure screen from JSON, opens the task and Care forms on the
   screen, saves them over JSON-RPC, and reloads the page after the configured idle time. */
(function () {
    "use strict";

    const root = document.getElementById("cp-root");
    let data = JSON.parse(document.getElementById("cp-data").textContent);
    const yardId = data.yard.id;
    const base = `/kennel/control-plane/${yardId}`;

    // ------------------------------------------------------------------
    // DOM helpers
    // ------------------------------------------------------------------

    function h(tag, attrs, ...children) {
        const el = document.createElement(tag);
        for (const [key, value] of Object.entries(attrs || {})) {
            if (value === false || value === null || value === undefined) {
                continue;
            }
            if (key === "class") {
                el.className = value;
            } else if (key.startsWith("on")) {
                el.addEventListener(key.slice(2), value);
            } else {
                el.setAttribute(key, value === true ? "" : value);
            }
        }
        for (const child of children.flat()) {
            if (child !== null && child !== undefined && child !== false) {
                el.append(child instanceof Node ? child : document.createTextNode(String(child)));
            }
        }
        return el;
    }

    function svg(path, viewBox = "0 0 24 24") {
        const el = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        el.setAttribute("viewBox", viewBox);
        el.setAttribute("fill", "currentColor");
        el.setAttribute("aria-hidden", "true");
        el.innerHTML = path;
        return el;
    }

    const ICONS = {
        paw: '<ellipse cx="12" cy="16" rx="5" ry="4"/><ellipse cx="5" cy="10.5" rx="2" ry="2.6"/><ellipse cx="9.2" cy="6" rx="2" ry="2.6"/><ellipse cx="14.8" cy="6" rx="2" ry="2.6"/><ellipse cx="19" cy="10.5" rx="2" ry="2.6"/>',
        care: '<path d="M4 3h13l3 3v15H4zM7 8h10v2H7zm0 4h10v2H7zm0 4h6v2H7z"/>',
        medication: '<path d="M10 3h4v4h4v4h-4v4h-4v-4H6V7h4z" transform="translate(0 3)"/>',
        dose: '<path d="M9 16.2 4.8 12l-1.4 1.4L9 19 21 7l-1.4-1.4z"/>',
        observation: '<path d="M12 5C6 5 2 12 2 12s4 7 10 7 10-7 10-7-4-7-10-7zm0 11a4 4 0 1 1 0-8 4 4 0 0 1 0 8z"/>',
    };

    // ------------------------------------------------------------------
    // Server
    // ------------------------------------------------------------------

    async function rpc(url, params) {
        const response = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "same-origin",
            body: JSON.stringify({ jsonrpc: "2.0", method: "call", params }),
        });
        if (response.redirected || response.status === 401 || response.status === 403) {
            window.location.reload(); // signed out: show the login page
            return null;
        }
        const payload = await response.json();
        if (payload.error) {
            throw new Error(payload.error.data?.message || payload.error.message || "Something went wrong.");
        }
        return payload.result;
    }

    async function reloadData() {
        const fresh = await rpc(`${base}/data`, {});
        if (fresh) {
            data = fresh;
            render();
        }
    }

    // ------------------------------------------------------------------
    // Screen
    // ------------------------------------------------------------------

    function yardPanel() {
        const yard = data.yard;
        const logo = data.theme.background === "branding" && data.theme.logo_url
            ? h("img", { class: "cp-yard-logo", src: data.theme.logo_url, alt: yard.company })
            : null;
        return h("section", { class: "cp-panel cp-yard" },
            logo,
            h("div", { class: "cp-yard-main" },
                h("h1", {}, yard.name, yard.code ? h("span", { class: "cp-code" }, yard.code) : null),
                h("div", { class: "cp-yard-meta" },
                    yard.type ? h("span", {}, yard.type) : null,
                    h("span", {}, yard.company),
                    yard.capacity ? h("span", {}, `Holds ${yard.capacity}`) : null,
                    yard.features.length ? h("span", {}, yard.features.join(", ")) : null,
                ),
            ),
            h("div", { class: "cp-clock" }, h("div", { class: "cp-time", id: "cp-time" }), h("div", { class: "cp-date", id: "cp-date" })),
        );
    }

    function fact(label, value, cls) {
        if (!value) {
            return [];
        }
        return [h("dt", {}, label), h("dd", { class: cls || false }, value)];
    }

    function residentCard(r) {
        const photo = r.photo_url
            ? h("img", { class: "cp-photo", src: r.photo_url, alt: r.name })
            : h("div", { class: "cp-photo" }, svg(ICONS.paw));
        const sub = [r.species, r.breed, r.sex, r.age].filter(Boolean).join(" · ");
        return h("article", { class: "cp-resident" },
            photo,
            h("div", { class: "cp-resident-body" },
                h("h2", {}, r.name),
                sub ? h("div", { class: "cp-sub" }, sub) : null,
                h("dl", { class: "cp-facts" },
                    fact("Customer", r.customer),
                    fact("Stay", `${r.arrival} – ${r.departure}`),
                    fact("Food", [r.food, r.owner_supplied_food ? "(owner supplies the food)" : ""].filter(Boolean).join("\n")),
                    fact("Feeding", r.feeding_instructions),
                    fact("Medication", r.medication.join("\n")),
                    fact("Medical", r.medical, "cp-alert"),
                    fact("Behaviour", r.behaviour),
                    fact("Colour", r.colour),
                    fact("Microchip", r.microchip),
                    fact("Vaccinations", r.vaccination_expired
                        ? `${r.vaccinations_due || "Not recorded"} – run out before departure`
                        : r.vaccinations_due, r.vaccination_expired ? "cp-alert" : false),
                ),
            ),
        );
    }

    function residentsPanel() {
        const body = data.residents.length
            ? data.residents.map(residentCard)
            : [h("div", { class: "cp-vacant" }, svg(ICONS.paw), "Yard Vacant")];
        return h("section", { class: "cp-panel cp-residents" },
            data.residents.length ? h("h3", { class: "cp-section-title" }, data.residents.length > 1 ? "Residents" : "Resident") : null,
            body,
        );
    }

    function taskRow(task, done) {
        const classes = ["cp-task", task.overdue && !done ? "cp-overdue" : "", done ? "cp-done" : ""].join(" ");
        return h("button", {
            type: "button", class: classes, disabled: done,
            onclick: done ? null : () => openTask(task),
        },
            h("div", { class: "cp-task-time" }, done ? "✓" : task.due),
            h("div", { class: "cp-task-body" },
                h("div", { class: "cp-task-title" }, task.name),
                h("div", { class: "cp-task-text" }, done
                    ? `Done ${task.done_at}${task.done_by ? ` by ${task.done_by}` : ""}`
                    : task.instructions),
            ),
            h("span", { class: `cp-badge cp-${task.type}` }, task.overdue && !done ? "Overdue" : task.type_label),
        );
    }

    function sidePanel() {
        const vacant = !data.residents.length;
        const tools = [
            ["care", "Care Log Entry", () => openForm(careForm())],
            ["medication", "Medication to Give", () => openForm(medicationForm())],
            ["dose", "Medication Dose", () => openForm(doseForm()), !data.options.medication.length],
            ["observation", "Observation", () => openForm(observationForm())],
        ];
        return h("section", { class: "cp-panel cp-side" },
            h("div", { class: "cp-tasks" },
                h("h3", { class: "cp-section-title" }, `To Do Today · ${data.today}`),
                data.tasks.length
                    ? data.tasks.map((task) => taskRow(task, false))
                    : h("div", { class: "cp-empty" }, vacant ? "No animals in this yard." : "All done for now."),
                data.done.length ? h("h3", { class: "cp-section-title", style: "margin-top: 12px" }, "Completed Today") : null,
                data.done.map((task) => taskRow(task, true)),
            ),
            h("div", { class: "cp-toolbar" },
                tools.map(([icon, label, action, disabled]) => h("button", {
                    type: "button", class: "cp-tool", onclick: action, disabled: vacant || disabled,
                    title: vacant ? "No animals in this yard" : label,
                }, svg(ICONS[icon]), label)),
            ),
        );
    }

    function render() {
        root.replaceChildren(yardPanel(), residentsPanel(), sidePanel());
        tickClock();
    }

    function tickClock() {
        const now = new Date();
        const pad = (n) => String(n).padStart(2, "0");
        const time = document.getElementById("cp-time");
        const date = document.getElementById("cp-date");
        if (time) {
            time.textContent = `${pad(now.getHours())}:${pad(now.getMinutes())}`;
            date.textContent = `${pad(now.getDate())}/${pad(now.getMonth() + 1)}/${now.getFullYear()}`;
        }
    }

    // ------------------------------------------------------------------
    // Forms
    // ------------------------------------------------------------------

    const residentField = () => ({
        name: "resident_id", label: "Animal", type: "select", required: true, options: data.options.residents,
        default: data.options.residents.length === 1 ? data.options.residents[0].id : "",
    });
    const photosField = { name: "photos", label: "Photos", type: "photos" };
    const notesField = { name: "notes", label: "Notes", type: "textarea" };
    const feedFields = (task) => [
        { name: "quantity_given", label: "Food Given", type: "textarea", default: task?.quantity_given || "" },
        { name: "consumption_id", label: "Food Eaten", type: "select", required: true, options: data.options.consumption },
    ];
    const observationFields = () => [
        { name: "observation_type_id", label: "Type", type: "select", options: data.options.observation_type },
        { name: "summary", label: "Summary", type: "text", required: true, placeholder: "e.g. Bright, playful, settled well" },
        { name: "concern", label: "Concern (needs follow-up)", type: "checkbox" },
    ];

    function openTask(task) {
        let fields;
        if (task.type === "feed") {
            fields = feedFields(task);
        } else if (task.type === "medication") {
            fields = [
                { name: "dose_given", label: "Dose Given", type: "text", default: task.dose_given },
                { name: "outcome_id", label: "Outcome", type: "select", required: true, options: data.options.outcome },
            ];
        } else {
            fields = observationFields();
        }
        openForm({
            title: task.name, intro: task.instructions, kind: "task", submitLabel: "Complete",
            fixed: { task_id: task.id }, fields: [...fields, notesField, photosField],
        });
    }

    function careForm() {
        const isFeed = (v) => v.task_type !== "observation";
        return {
            title: "Care Log Entry", kind: "care", submitLabel: "Save",
            intro: "Log a feed or an observation now; it goes on the animal's Care Log.",
            fields: [
                residentField(),
                { name: "task_type", label: "Type", type: "select", required: true, default: "feed",
                  options: [{ id: "feed", name: "Feed" }, { id: "observation", name: "Observation" }] },
                ...feedFields().map((f) => ({ ...f, showIf: isFeed })),
                ...observationFields().map((f) => ({ ...f, showIf: (v) => !isFeed(v) })),
                notesField, photosField,
            ],
        };
    }

    function medicationForm() {
        return {
            title: "Medication to Give", kind: "medication", submitLabel: "Save",
            fields: [
                residentField(),
                { name: "name", label: "Medication", type: "text", required: true },
                { name: "dose", label: "Dose", type: "text", placeholder: "e.g. 1 tablet" },
                { name: "route_id", label: "Route", type: "select", options: data.options.route },
                { name: "frequency_id", label: "Frequency", type: "select", options: data.options.frequency },
                { name: "times", label: "When", type: "text", placeholder: "e.g. with breakfast and dinner" },
                { name: "start_date", label: "Start Date", type: "date" },
                { name: "end_date", label: "End Date", type: "date" },
                { name: "instructions", label: "Instructions", type: "textarea" },
            ],
        };
    }

    function doseForm() {
        return {
            title: "Medication Dose", kind: "dose", submitLabel: "Save",
            fields: [
                { name: "medication_id", label: "Medication", type: "select", required: true, options: data.options.medication,
                  default: data.options.medication.length === 1 ? data.options.medication[0].id : "" },
                { name: "dose_given", label: "Dose Given", type: "text" },
                { name: "outcome_id", label: "Outcome", type: "select", required: true, options: data.options.outcome },
                notesField,
            ],
        };
    }

    function observationForm() {
        return {
            title: "Observation", kind: "observation", submitLabel: "Save",
            fields: [residentField(), ...observationFields(), { name: "details", label: "Details", type: "textarea" }],
        };
    }

    function readPhoto(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve({ name: file.name, data: String(reader.result).split(",")[1] });
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
    }

    function openForm(spec) {
        const values = {};
        const photos = [];
        const inputs = {};
        const errorBox = h("div", { class: "cp-error", hidden: true });
        const form = h("form", { class: "cp-form", novalidate: true });

        for (const field of spec.fields) {
            values[field.name] = field.default ?? (field.type === "checkbox" ? false : "");
        }

        function fieldControl(field) {
            const id = `cp-f-${field.name}`;
            const update = (ev) => {
                values[field.name] = field.type === "checkbox" ? ev.target.checked : ev.target.value;
                refreshVisibility();
            };
            if (field.type === "select") {
                return h("select", { id, onchange: update },
                    h("option", { value: "" }, field.required ? "Choose…" : "—"),
                    field.options.map((o) => h("option", { value: o.id, selected: String(o.id) === String(values[field.name]) }, o.name)));
            }
            if (field.type === "textarea") {
                const el = h("textarea", { id, oninput: update, placeholder: field.placeholder || false });
                el.value = values[field.name];
                return el;
            }
            if (field.type === "checkbox") {
                return h("label", { class: "cp-check" },
                    h("input", { id, type: "checkbox", onchange: update }), field.label);
            }
            if (field.type === "photos") {
                const thumbs = h("div", { class: "cp-thumbs" });
                const input = h("input", {
                    id, type: "file", accept: "image/*", capture: "environment", multiple: true,
                    onchange: async (ev) => {
                        for (const file of ev.target.files) {
                            photos.push(await readPhoto(file));
                            thumbs.append(h("img", { src: URL.createObjectURL(file), alt: file.name }));
                        }
                        ev.target.value = "";
                    },
                });
                return h("div", {}, input, thumbs);
            }
            const el = h("input", {
                id, type: "text", oninput: update,
                placeholder: field.type === "date" ? "dd/mm/yyyy" : (field.placeholder || false),
                inputmode: field.type === "date" ? "numeric" : false,
            });
            el.value = values[field.name];
            return el;
        }

        const rows = spec.fields.map((field) => {
            const control = fieldControl(field);
            inputs[field.name] = control;
            const row = h("div", { class: "cp-field" },
                field.type === "checkbox" ? null
                    : h("label", { for: `cp-f-${field.name}` }, field.label, field.required ? h("span", { class: "cp-req" }, "*") : null),
                control);
            row.field = field;
            return row;
        });
        form.append(...rows);

        function refreshVisibility() {
            for (const row of rows) {
                row.hidden = row.field.showIf ? !row.field.showIf(values) : false;
            }
        }
        refreshVisibility();

        const submit = h("button", { type: "button", class: "cp-btn cp-primary" }, spec.submitLabel || "Save");
        const backdrop = h("div", { class: "cp-modal-backdrop" },
            h("div", { class: "cp-modal", role: "dialog", "aria-modal": "true", "aria-label": spec.title },
                h("header", {}, h("h2", {}, spec.title), spec.intro ? h("p", {}, spec.intro) : null),
                form,
                errorBox,
                h("div", { class: "cp-actions" },
                    h("button", { type: "button", class: "cp-btn", onclick: close }, "Cancel"),
                    submit),
            ));

        function close() {
            backdrop.remove();
        }

        function showError(message) {
            errorBox.textContent = message;
            errorBox.hidden = false;
        }

        submit.addEventListener("click", async () => {
            const missing = rows.filter((row) => !row.hidden && row.field.required && !values[row.field.name]);
            if (missing.length) {
                showError(`Please fill in: ${missing.map((row) => row.field.label).join(", ")}.`);
                return;
            }
            const payload = { ...(spec.fixed || {}) };
            for (const row of rows) {
                if (!row.hidden && row.field.type !== "photos") {
                    payload[row.field.name] = values[row.field.name];
                }
            }
            payload.photos = photos;
            submit.disabled = true;
            try {
                const result = await rpc(`${base}/submit`, { kind: spec.kind, values: payload });
                if (!result) {
                    return;
                }
                if (result.error) {
                    showError(result.error);
                    return;
                }
                data = result.data;
                render();
                close();
                toast("Saved");
            } catch (error) {
                showError(error.message);
            } finally {
                submit.disabled = false;
            }
        });

        document.body.append(backdrop);
        const first = rows.find((row) => !row.hidden && row.field.type !== "photos");
        first?.querySelector("input, select, textarea")?.focus();
    }

    function toast(message) {
        const el = h("div", { class: "cp-toast", role: "status" }, message);
        document.body.append(el);
        setTimeout(() => el.remove(), 2000);
    }

    // ------------------------------------------------------------------
    // Auto refresh: reload once the screen has been idle for the configured minutes (0 = never).
    // ------------------------------------------------------------------

    const idleMinutes = Number(data.theme.refresh_minutes) || 0;
    let idleTimer = null;

    function resetIdle() {
        if (!idleMinutes) {
            return;
        }
        clearTimeout(idleTimer);
        idleTimer = setTimeout(() => window.location.reload(), idleMinutes * 60 * 1000);
    }

    if (idleMinutes) {
        for (const event of ["pointerdown", "pointermove", "keydown", "wheel", "touchstart", "input", "scroll"]) {
            window.addEventListener(event, resetIdle, { passive: true, capture: true });
        }
        resetIdle();
    }
    window.kennelControlPlane = { idleMinutes, reloadData };

    // ------------------------------------------------------------------
    // Start
    // ------------------------------------------------------------------

    render();
    setInterval(tickClock, 15 * 1000);
    if ("serviceWorker" in navigator) {
        navigator.serviceWorker.register("/kennel/control-plane/sw.js", { scope: "/kennel/control-plane/" }).catch(() => {});
    }
})();
