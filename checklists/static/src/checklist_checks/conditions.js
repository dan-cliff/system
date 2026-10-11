/**
 * Conditional display on the checklist form: the answer rules of a line
 * (copied from its question), evaluated live against the other lines'
 * answers. Mirrors evaluate_rule in models/checklist_question_condition.py;
 * the Current User and Checklist filters come evaluated from the server
 * (condition_context).
 */
const { DateTime } = luxon;

const SINGLE_OPTION_TYPES = ["buttons", "select", "radio", "slider"];
const MULTI_OPTION_TYPES = ["multi_select", "multi_checkbox"];
const TEXT_TYPES = ["text", "text_area", "phone", "email", "website"];
const TEXT_FIELDS = {
    text: "value_text",
    text_area: "value_text_area",
    phone: "value_phone",
    email: "value_email",
    website: "value_url",
};

/** A line's answer in the form the rules compare. */
export function answerOf(line) {
    const data = line.data;
    const kind = data.question_type;
    if (SINGLE_OPTION_TYPES.includes(kind)) {
        return data.value_option_id ? data.value_option_id.id : false;
    }
    if (MULTI_OPTION_TYPES.includes(kind)) {
        return data.value_option_ids ? [...data.value_option_ids.currentIds] : [];
    }
    if (TEXT_TYPES.includes(kind)) {
        return data[TEXT_FIELDS[kind]] || "";
    }
    switch (kind) {
        case "number":
            return data.value_number || 0;
        case "integer":
            return data.value_integer || 0;
        case "date":
            return data.value_date ? data.value_date.startOf("day") : false;
        case "datetime":
            return data.value_datetime ? data.value_datetime.startOf("day") : false;
        case "boolean":
            return Boolean(data.value_boolean);
        case "geolocation":
            return Boolean(data.value_latitude || data.value_longitude);
        case "image":
            return Boolean(data.value_image);
        case "file":
            return Boolean(data.value_file);
        case "many2one":
            return data.value_reference ? data.value_reference.resId : false;
        case "many2many":
            return Array.isArray(data.value_reference_ids) ? data.value_reference_ids : [];
    }
    return false;
}

function isAnswered(kind, answer) {
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

export function evaluateRule(rule, answer) {
    const kind = rule.question_type;
    const { operator } = rule;
    const value = rule.value || "";
    const options = rule.option_ids || [];
    const answered = isAnswered(kind, answer);
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
        const wanted = DateTime.fromFormat(value.trim(), "dd/MM/yyyy");
        if (!wanted.isValid || !answer) {
            return operator === "ne" && !answer;
        }
        return compare(operator, answer.toMillis(), wanted.toMillis());
    }
    if (TEXT_TYPES.includes(kind)) {
        const text = (answer || "").trim().toLowerCase();
        const wanted = value.trim().toLowerCase();
        return operator === "contains" ? text.includes(wanted) : compare(operator, text, wanted);
    }
    return false;
}

/** Ids of the lines to show: the unconditional ones and those whose conditions hold. */
export function visibleLineIds(lines) {
    const byQuestion = new Map();
    for (const line of lines) {
        if (line.data.question_id) {
            byQuestion.set(line.data.question_id.id, line);
        }
    }
    const cache = new Map();
    const isVisible = (line, seen) => {
        if (!line.data.conditional) {
            return true;
        }
        if (cache.has(line.id)) {
            return cache.get(line.id);
        }
        const results = [];
        for (const rule of line.data.condition_rules || []) {
            const source = byQuestion.get(rule.question_id);
            results.push(
                Boolean(source) &&
                    !seen.has(source.id) &&
                    isVisible(source, new Set([...seen, source.id])) &&
                    evaluateRule(rule, answerOf(source))
            );
        }
        const context = line.data.condition_context || {};
        for (const key of ["user", "record"]) {
            if (key in context) {
                results.push(Boolean(context[key]));
            }
        }
        const visible =
            !results.length ||
            (line.data.condition_logic === "any" ? results.some(Boolean) : results.every(Boolean));
        cache.set(line.id, visible);
        return visible;
    };
    return new Set(lines.filter((line) => isVisible(line, new Set([line.id]))).map((l) => l.id));
}
