import { visibleLineIds } from "@checklists/checklist_checks/conditions";
import { registry } from "@web/core/registry";
import { Interaction } from "@web/public/interaction";

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

/**
 * The online screening questionnaire: shows each question only while its
 * Conditional Display holds (the Checklists rules, evaluated as the
 * applicant answers) and fills in GeoLocation answers.
 */
export class TalentQuestionnaire extends Interaction {
    static selector = ".o_talent_questionnaire";
    dynamicContent = {
        "input, select, textarea": {
            "t-on-change": this.refreshVisibility,
            "t-on-input": this.refreshVisibility,
        },
        ".o_talent_q_geo_button": { "t-on-click": this.onShareLocation },
    };

    start() {
        this.refreshVisibility();
    }

    refreshVisibility() {
        const lines = [...this.el.querySelectorAll(".o_talent_q_line")].map((node) => ({
            id: Number(node.dataset.lineId),
            node,
            data: this.lineData(node),
        }));
        const visible = visibleLineIds(lines);
        for (const line of lines) {
            line.node.classList.toggle("d-none", !visible.has(line.id));
        }
    }

    lineData(node) {
        const kind = node.dataset.type;
        const questionId = Number(node.dataset.questionId);
        const data = {
            question_type: kind,
            question_id: questionId ? { id: questionId } : false,
            conditional: node.dataset.conditional === "1",
            condition_logic: node.dataset.logic,
            condition_rules: JSON.parse(node.dataset.rules || "[]"),
            condition_context: JSON.parse(node.dataset.context || "{}"),
        };
        const name = `line_${node.dataset.lineId}`;
        const field = node.querySelector(`[name="${name}"]:not([type="hidden"])`);
        const checked = [...node.querySelectorAll(`[name="${name}"]:checked`)].map((input) => Number(input.value));
        if (SINGLE_OPTION_TYPES.includes(kind)) {
            const id = kind === "select" ? Number(field?.value) : checked[0];
            data.value_option_id = id ? { id } : false;
        } else if (MULTI_OPTION_TYPES.includes(kind)) {
            data.value_option_ids = { currentIds: checked };
        } else if (kind in TEXT_FIELDS) {
            data[TEXT_FIELDS[kind]] = field?.value || "";
        } else if (kind === "number") {
            data.value_number = parseFloat(field?.value) || 0;
        } else if (kind === "integer") {
            data.value_integer = parseInt(field?.value) || 0;
        } else if (kind === "date" || kind === "datetime") {
            const format = kind === "date" ? "d/M/yyyy" : "d/M/yyyy H:mm";
            const value = field?.value ? DateTime.fromFormat(field.value.trim(), format) : false;
            data[kind === "date" ? "value_date" : "value_datetime"] = value && value.isValid ? value : false;
        } else if (kind === "boolean") {
            data.value_boolean = Boolean(field?.checked);
        } else if (kind === "geolocation") {
            data.value_latitude = parseFloat(node.querySelector(".o_talent_q_lat")?.value) || 0;
            data.value_longitude = parseFloat(node.querySelector(".o_talent_q_lng")?.value) || 0;
        } else if (kind === "image" || kind === "file") {
            const answered = Boolean(field?.files?.length) || field?.dataset.hasValue === "1";
            data[kind === "image" ? "value_image" : "value_file"] = answered;
        }
        return data;
    }

    onShareLocation(ev) {
        const node = ev.currentTarget.closest(".o_talent_q_line");
        const text = node.querySelector(".o_talent_q_geo_text");
        if (!navigator.geolocation) {
            text.textContent = "Your browser can't share your location.";
            return;
        }
        text.textContent = "Finding your location…";
        navigator.geolocation.getCurrentPosition(
            (position) => {
                const { latitude, longitude } = position.coords;
                node.querySelector(".o_talent_q_lat").value = latitude;
                node.querySelector(".o_talent_q_lng").value = longitude;
                text.textContent = `${latitude.toFixed(5)}, ${longitude.toFixed(5)}`;
                this.refreshVisibility();
            },
            () => {
                text.textContent = "Your location could not be found.";
            },
            { enableHighAccuracy: true, timeout: 15000 }
        );
    }
}

registry.category("public.interactions").add("modern_recruitment_checklists.questionnaire", TalentQuestionnaire);
