import { whenReady } from "@odoo/owl";
import { visibleLineIds } from "@checklists/checklist_checks/conditions";

/**
 * Public Link form (views/checklist_public_templates.xml): shows the
 * conditional questions whose conditions hold, as the checklist form does
 * (same rules: checklist_checks/conditions.js), and runs the Slider and
 * GeoLocation answers.
 */
const { DateTime } = luxon;

const SINGLE_OPTION_TYPES = ["buttons", "select", "radio", "slider"];
const MULTI_OPTION_TYPES = ["multi_select", "multi_checkbox"];
const TEXT_FIELDS = {
    text: "value_text",
    text_area: "value_text_area",
    phone: "value_phone",
    email: "value_email",
    website: "value_url",
};

function values(form, name) {
    return new FormData(form).getAll(name).filter((value) => typeof value !== "string" || value !== "");
}

/** A question's answer, shaped like a checklist line's data (see answerOf). */
function lineData(form, question) {
    const name = `q_${question.id}`;
    const kind = question.question_type;
    const [value] = values(form, name);
    const data = { ...question, question_id: { id: question.id } };
    if (SINGLE_OPTION_TYPES.includes(kind)) {
        data.value_option_id = value ? { id: parseInt(value, 10) } : false;
    } else if (MULTI_OPTION_TYPES.includes(kind)) {
        data.value_option_ids = { currentIds: values(form, name).map((v) => parseInt(v, 10)) };
    } else if (kind in TEXT_FIELDS) {
        data[TEXT_FIELDS[kind]] = value || "";
    } else if (kind === "number" || kind === "integer") {
        data[`value_${kind}`] = parseFloat(value) || 0;
    } else if (kind === "date" || kind === "datetime") {
        const parsed = value && DateTime.fromFormat(value, kind === "date" ? "dd/MM/yyyy" : "dd/MM/yyyy HH:mm");
        data[`value_${kind}`] = parsed && parsed.isValid ? parsed : false;
    } else if (kind === "boolean") {
        data.value_boolean = Boolean(value);
    } else if (kind === "geolocation") {
        data.value_latitude = parseFloat(values(form, `${name}_lat`)[0]) || 0;
        data.value_longitude = parseFloat(values(form, `${name}_lng`)[0]) || 0;
    } else if (kind === "image" || kind === "file") {
        data[`value_${kind}`] = Boolean(value && value.size);
    } else if (kind === "many2one") {
        data.value_reference = value ? { resId: parseInt(value, 10) } : false;
    } else if (kind === "many2many") {
        data.value_reference_ids = values(form, name).map((v) => parseInt(v, 10));
    }
    return { id: question.id, data };
}

function applyConditions(form, questions) {
    const shown = visibleLineIds(questions.map((question) => lineData(form, question)));
    for (const item of form.querySelectorAll(".o_checklist_public_item")) {
        item.classList.toggle("d-none", !shown.has(parseInt(item.dataset.questionId, 10)));
    }
}

function setupSlider(slider, onChange) {
    const options = JSON.parse(slider.dataset.options || "[]");
    const hidden = slider.querySelector("input[type=hidden]");
    const range = slider.querySelector("input[type=range]");
    const label = slider.querySelector(".o_checklist_public_slider_value");
    range.addEventListener("input", () => {
        const [id, name] = options[parseInt(range.value, 10)] || [];
        hidden.value = id || "";
        label.textContent = name || "";
        label.classList.remove("text-muted");
        onChange();
    });
}

function setupGeolocation(geo, onChange) {
    const status = geo.querySelector(".o_checklist_public_geo_status");
    geo.querySelector(".o_checklist_public_geo_button").addEventListener("click", () => {
        if (!navigator.geolocation) {
            status.textContent = "This device can't share its location.";
            return;
        }
        status.textContent = "Finding your location…";
        navigator.geolocation.getCurrentPosition(
            ({ coords }) => {
                geo.querySelector(".o_checklist_public_lat").value = coords.latitude.toFixed(7);
                geo.querySelector(".o_checklist_public_lng").value = coords.longitude.toFixed(7);
                status.textContent = "";
                onChange();
            },
            (error) => {
                status.textContent = error.message || "The location couldn't be found.";
            },
            { enableHighAccuracy: true, timeout: 15000 }
        );
    });
}

whenReady(() => {
    const form = document.querySelector(".o_checklist_public_form");
    if (!form) {
        return;
    }
    const questions = JSON.parse(form.dataset.checklist || "[]");
    const update = () => applyConditions(form, questions);
    form.querySelector(".o_checklist_public_tz").value =
        Intl.DateTimeFormat().resolvedOptions().timeZone || "";
    form.querySelectorAll(".o_checklist_public_slider").forEach((slider) => setupSlider(slider, update));
    form.querySelectorAll(".o_checklist_public_geo").forEach((geo) => setupGeolocation(geo, update));
    form.addEventListener("input", update);
    form.addEventListener("change", update);
    update();
});
