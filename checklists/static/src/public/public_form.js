/**
 * Public checklist form (views/checklist_public_templates.xml): plain script,
 * no Odoo assets.
 *
 * - Conditional display: the answer rules of each conditional question,
 *   evaluated live (mirrors static/src/checklist_checks/conditions.js and
 *   evaluate_rule in models/checklist_question_condition.py). Hidden
 *   questions' inputs are disabled, so their answers aren't sent.
 * - Date / datetime fields typed as dd/mm/yyyy (HH:MM), with a picker button.
 * - GeoLocation: "Use my current location".
 * - Email or phone number: one of them is required.
 */
(function () {
    "use strict";

    const form = document.getElementById("cl_public_form");
    if (!form) {
        return;
    }
    const conditions = JSON.parse(form.dataset.conditions || "{}");
    const types = JSON.parse(form.dataset.types || "{}");

    const SINGLE_OPTION_TYPES = ["buttons", "select", "radio", "slider"];
    const MULTI_OPTION_TYPES = ["multi_select", "multi_checkbox"];
    const TEXT_TYPES = ["text", "text_area", "phone", "email", "website"];

    const pad = (n) => String(n).padStart(2, "0");

    // The visitor's time zone, for datetime answers (unless the link sets one).
    const tzInput = form.querySelector("input[name='_tz']");
    if (tzInput && !tzInput.value) {
        try {
            tzInput.value = Intl.DateTimeFormat().resolvedOptions().timeZone || "";
        } catch {
            // Server falls back to UTC.
        }
    }

    function questionNode(id) {
        return form.querySelector(`.cl-question[data-question="${id}"]`);
    }

    /** dd/mm/yyyy [HH:MM] -> start of that day (ms), or false. */
    function parseDay(text) {
        const match = /^(\d{1,2})\/(\d{1,2})\/(\d{4})/.exec((text || "").trim());
        if (!match) {
            return false;
        }
        const date = new Date(Number(match[3]), Number(match[2]) - 1, Number(match[1]));
        return isNaN(date) ? false : date.getTime();
    }

    /** A question's answer in the form the rules compare. */
    function answerOf(id) {
        const node = questionNode(id);
        const kind = types[id];
        if (!node || node.hidden) {
            return undefined;
        }
        const inputs = [...node.querySelectorAll("input, select, textarea")].filter(
            (input) => !input.classList.contains("cl-native")
        );
        if (SINGLE_OPTION_TYPES.includes(kind)) {
            const select = node.querySelector("select");
            const chosen = select ? select.value : (inputs.find((i) => i.checked) || {}).value;
            return chosen ? Number(chosen) : false;
        }
        if (MULTI_OPTION_TYPES.includes(kind)) {
            return inputs.filter((i) => i.checked).map((i) => Number(i.value));
        }
        if (kind === "many2one" || kind === "many2many") {
            const ids = (node.dataset.ids || "").split(",").filter(Boolean).map(Number);
            return kind === "many2one" ? ids[0] || false : ids;
        }
        const input = inputs[0];
        if (!input) {
            return false;
        }
        if (TEXT_TYPES.includes(kind)) {
            return input.value || "";
        }
        switch (kind) {
            case "number":
            case "integer":
                return parseFloat(input.value) || 0;
            case "date":
            case "datetime":
                return parseDay(input.value);
            case "boolean":
                return input.checked;
            case "geolocation":
            case "image":
            case "file":
                return Boolean(input.type === "file" ? input.files.length : input.value);
        }
        return false;
    }

    function isAnswered(answer) {
        if (Array.isArray(answer)) {
            return answer.length > 0;
        }
        return answer !== false && answer !== null && answer !== undefined && answer !== "" && answer !== 0;
    }

    function compare(operator, a, b) {
        switch (operator) {
            case "eq":
                return a === b;
            case "ne":
                return a !== b;
            case "gt":
                return a > b;
            case "lt":
                return a < b;
        }
        return false;
    }

    function evaluateRule(rule, answer) {
        const kind = rule.question_type;
        const { operator } = rule;
        const value = rule.value || "";
        const options = rule.option_ids || [];
        const answered = isAnswered(answer);
        if (operator === "set") {
            return answered;
        }
        if (operator === "not_set") {
            return !answered;
        }
        if (SINGLE_OPTION_TYPES.includes(kind) || MULTI_OPTION_TYPES.includes(kind)) {
            const chosen = Array.isArray(answer) ? answer : answer ? [answer] : [];
            const overlap = chosen.some((id) => options.includes(id));
            if (operator === "in" || operator === "eq") {
                return overlap;
            }
            if (operator === "not_in" || operator === "ne") {
                return !overlap;
            }
            if (operator === "contains") {
                return options.every((id) => chosen.includes(id));
            }
            return false;
        }
        if (kind === "boolean") {
            const wanted = ["1", "true", "yes", "y"].includes(value.trim().toLowerCase());
            return operator === "eq" ? answer === wanted : operator === "ne" ? answer !== wanted : false;
        }
        if (kind === "number" || kind === "integer") {
            const number = parseFloat(value.replace(/,/g, "").trim());
            return isNaN(number) ? false : compare(operator, answer || 0, number);
        }
        if (kind === "date" || kind === "datetime") {
            const wanted = parseDay(value);
            if (wanted === false || !answer) {
                return operator === "ne" && !answer;
            }
            return compare(operator, answer, wanted);
        }
        if (TEXT_TYPES.includes(kind)) {
            const text = (answer || "").trim().toLowerCase();
            const wanted = value.trim().toLowerCase();
            return operator === "contains" ? text.includes(wanted) : compare(operator, text, wanted);
        }
        return false;
    }

    function isVisible(id, seen) {
        const condition = conditions[id];
        if (!condition) {
            return true;
        }
        const results = [];
        for (const rule of condition.rules || []) {
            const source = String(rule.question_id);
            results.push(
                source in types &&
                    !seen.has(source) &&
                    isVisible(source, new Set([...seen, source])) &&
                    evaluateRule(rule, answerOf(source))
            );
        }
        for (const key of ["user", "record"]) {
            if (key in (condition.context || {})) {
                results.push(Boolean(condition.context[key]));
            }
        }
        if (!results.length) {
            return true;
        }
        return condition.logic === "any" ? results.some(Boolean) : results.every(Boolean);
    }

    function setShown(node, shown) {
        node.hidden = !shown;
        if (node.dataset.locked) {
            return;
        }
        for (const input of node.querySelectorAll("input, select, textarea")) {
            input.disabled = !shown;
        }
    }

    function refresh() {
        // Show everything first so answers of shown questions can be read,
        // then hide in order (rules only look at questions that are shown).
        for (const id of Object.keys(conditions)) {
            const node = questionNode(id);
            if (node) {
                setShown(node, true);
            }
        }
        for (const id of Object.keys(conditions)) {
            const node = questionNode(id);
            if (node) {
                setShown(node, isVisible(id, new Set([id])));
            }
        }
    }

    // ── Dates ────────────────────────────────────────────────────────────
    for (const wrapper of form.querySelectorAll(".cl-date")) {
        const text = wrapper.querySelector("input[type='text']");
        const native = wrapper.querySelector(".cl-native");
        const button = wrapper.querySelector(".cl-date-pick");
        if (!text || !native || !button) {
            continue;
        }
        button.addEventListener("click", () => {
            if (native.showPicker) {
                native.showPicker();
            } else {
                native.focus();
            }
        });
        native.addEventListener("change", () => {
            const match = /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?/.exec(native.value);
            if (!match) {
                return;
            }
            text.value = `${match[3]}/${match[2]}/${match[1]}` + (match[4] ? ` ${match[4]}:${match[5]}` : "");
            text.dispatchEvent(new Event("change", { bubbles: true }));
        });
    }

    // ── GeoLocation ──────────────────────────────────────────────────────
    for (const wrapper of form.querySelectorAll(".cl-geo")) {
        const button = wrapper.querySelector(".cl-geo-button");
        const input = wrapper.querySelector("input[type='hidden']");
        const display = wrapper.querySelector(".cl-geo-value");
        if (!button) {
            continue;
        }
        if (!navigator.geolocation) {
            button.disabled = true;
            display.textContent = "Location isn't available on this device.";
            continue;
        }
        button.addEventListener("click", () => {
            button.disabled = true;
            display.textContent = "Finding your location...";
            navigator.geolocation.getCurrentPosition(
                (position) => {
                    const { latitude, longitude } = position.coords;
                    input.value = `${latitude.toFixed(7)},${longitude.toFixed(7)}`;
                    display.textContent = `${latitude.toFixed(6)}, ${longitude.toFixed(6)}`;
                    button.disabled = false;
                    refresh();
                },
                () => {
                    display.textContent = "Your location couldn't be found. Check the browser allows it.";
                    button.disabled = false;
                },
                { enableHighAccuracy: true, timeout: 20000 }
            );
        });
    }

    // ── Validation ───────────────────────────────────────────────────────
    const email = form.querySelector("input[name='email']");
    const phone = form.querySelector("input[name='phone']");
    const contactError = document.getElementById("cl_contact_error");

    function checkContact() {
        const missing = !email.value.trim() && !phone.value.trim();
        email.setCustomValidity(missing ? "Enter your email address or phone number." : "");
        return !missing;
    }

    for (const input of [email, phone]) {
        input.addEventListener("input", () => {
            if (checkContact()) {
                contactError.hidden = true;
            }
        });
    }

    for (const input of form.querySelectorAll(".cl-date input[type='text']")) {
        input.addEventListener("input", () => input.setCustomValidity(""));
    }

    form.addEventListener("submit", (event) => {
        let valid = checkContact();
        if (!valid) {
            contactError.hidden = false;
        }
        for (const input of form.querySelectorAll(".cl-date input[type='text']:not(:disabled)")) {
            const value = input.value.trim();
            const ok =
                !value ||
                (input.dataset.kind === "date"
                    ? /^\d{1,2}\/\d{1,2}\/\d{4}$/.test(value)
                    : /^\d{1,2}\/\d{1,2}\/\d{4} \d{1,2}:\d{2}$/.test(value));
            input.setCustomValidity(
                ok ? "" : input.dataset.kind === "date" ? "Enter the date as dd/mm/yyyy." : "Enter it as dd/mm/yyyy HH:MM."
            );
            valid = valid && ok;
        }
        if (!valid || !form.checkValidity()) {
            event.preventDefault();
            form.reportValidity();
            return;
        }
        const button = form.querySelector(".cl-submit");
        button.disabled = true;
        button.textContent = "Submitting...";
    });

    // Typed dates take two-digit days and months: 1/2/2026 -> 01/02/2026.
    for (const input of form.querySelectorAll(".cl-date input[type='text']")) {
        input.addEventListener("blur", () => {
            const match = /^(\d{1,2})\/(\d{1,2})\/(\d{4})(.*)$/.exec(input.value.trim());
            if (match) {
                input.value = `${pad(match[1])}/${pad(match[2])}/${match[3]}${match[4]}`;
            }
        });
    }

    form.addEventListener("change", refresh);
    form.addEventListener("input", refresh);
    refresh();
})();
