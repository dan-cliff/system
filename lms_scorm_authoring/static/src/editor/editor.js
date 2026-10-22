/** @odoo-module **/

import {
    Component, markup, onMounted, onWillStart, onWillUnmount, onWillUpdateProps, useRef, useState,
} from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { Dialog } from "@web/core/dialog/dialog";
import { aiProgress } from "../ai_progress/ai_progress";

const GRID = 8;
const AUTOSAVE_MS = 2500;
const MAX_UPLOAD = 150 * 1024 * 1024;
const QUESTION_TYPES = ["mcq", "mrq", "truefalse", "fillblank", "matching", "sequence", "survey"];
// Items learners can interact with, so they can be marked Required
const INTERACTIVE_TYPES = ["video", "audio", "button", "hotspot", "embed", "tabs", "accordion",
    "flipcard", "labeled_graphic", "results", ...QUESTION_TYPES];

const PALETTE = [
    {
        group: _t("Content"),
        items: [
            { type: "text", label: _t("Text"), icon: "fa-font" },
            { type: "heading", label: _t("Heading"), icon: "fa-header" },
            { type: "image", label: _t("Picture"), icon: "fa-picture-o" },
            { type: "video", label: _t("Video"), icon: "fa-video-camera" },
            { type: "audio", label: _t("Audio"), icon: "fa-volume-up" },
            { type: "shape", label: _t("Shape"), icon: "fa-square" },
            { type: "line", label: _t("Line"), icon: "fa-minus" },
            { type: "button", label: _t("Button"), icon: "fa-hand-pointer-o" },
            { type: "hotspot", label: _t("Hotspot"), icon: "fa-bullseye" },
            { type: "embed", label: _t("Web Page"), icon: "fa-globe" },
        ],
    },
    {
        group: _t("Interactions"),
        items: [
            { type: "tabs", label: _t("Tabs"), icon: "fa-folder-o" },
            { type: "accordion", label: _t("Accordion"), icon: "fa-bars" },
            { type: "flipcard", label: _t("Flip Card"), icon: "fa-clone" },
            { type: "labeled_graphic", label: _t("Labelled Graphic"), icon: "fa-map-marker" },
        ],
    },
    {
        group: _t("Questions"),
        items: [
            { type: "mcq", label: _t("Multiple Choice"), icon: "fa-dot-circle-o" },
            { type: "mrq", label: _t("Multiple Response"), icon: "fa-check-square-o" },
            { type: "truefalse", label: _t("True / False"), icon: "fa-adjust" },
            { type: "fillblank", label: _t("Fill in the Blank"), icon: "fa-i-cursor" },
            { type: "matching", label: _t("Matching"), icon: "fa-exchange" },
            { type: "sequence", label: _t("Sequence"), icon: "fa-sort-amount-asc" },
            { type: "survey", label: _t("Survey"), icon: "fa-bar-chart" },
            { type: "results", label: _t("Results"), icon: "fa-trophy" },
        ],
    },
];
const TYPE_LABELS = Object.fromEntries(PALETTE.flatMap((g) => g.items.map((i) => [i.type, i.label])));
TYPE_LABELS.text = _t("Text");

const SLIDE_LAYOUTS = [
    { key: "blank", label: _t("Blank") },
    { key: "title", label: _t("Title") },
    { key: "content", label: _t("Title and Text") },
    { key: "image", label: _t("Title and Picture") },
    { key: "question", label: _t("Question") },
    { key: "results", label: _t("Results") },
];

function uid() {
    return "e" + Math.random().toString(36).slice(2, 12);
}

function clone(value) {
    return JSON.parse(JSON.stringify(value));
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text || "";
    return div.innerHTML;
}

function defaultElement(type, branding) {
    const primary = branding.primary_color || "#1f6feb";
    const base = { id: uid(), type, x: 0, y: 0, w: 400, h: 200, z: 1, rotation: 0, required: false,
                   scored: false, props: {}, style: {} };
    const items = (n, title) => Array.from({ length: n }, (_v, i) => ({
        title: `${title} ${i + 1}`, html: `<p>${_t("Content for")} ${title.toLowerCase()} ${i + 1}</p>` }));
    const question = (props, extra = {}) => Object.assign(base, {
        w: 720, h: 400, required: true, scored: true,
        props: Object.assign({ prompt: `<p>${_t("Type your question here")}</p>`, attempts: 2, shuffle: true,
                               points: 1, feedback_correct: "", feedback_incorrect: "" }, props),
    }, extra);
    switch (type) {
        case "text":
            return Object.assign(base, { w: 520, h: 140, props: { html: `<p>${_t("Double-click to edit this text")}</p>`, valign: "top" },
                                         style: { fontSize: 24 } });
        case "heading":
            return Object.assign(base, { type: "text", w: 900, h: 90,
                                         props: { html: `<p>${_t("Slide heading")}</p>`, valign: "middle", role: "title" },
                                         style: { fontSize: 44, bold: true } });
        case "image":
            return Object.assign(base, { w: 480, h: 320, props: { attachment_id: false, alt: "", fit: "contain" } });
        case "video":
            return Object.assign(base, { w: 640, h: 360, props: { attachment_id: false, url: "", autoplay: false } });
        case "audio":
            return Object.assign(base, { w: 380, h: 60, props: { attachment_id: false, url: "", autoplay: false } });
        case "shape":
            return Object.assign(base, { w: 260, h: 160, props: { shape: "rect" }, style: { background: primary, radius: 8 } });
        case "line":
            return Object.assign(base, { type: "shape", w: 400, h: 16, props: { shape: "line" },
                                         style: { borderColor: primary, borderWidth: 3 } });
        case "button":
            return Object.assign(base, { w: 220, h: 56, props: { label: _t("Next"), action: "next" },
                                         style: { fontSize: 18, radius: 6 } });
        case "hotspot":
            return Object.assign(base, { w: 120, h: 120, required: true,
                                         props: { action: "popup", popup_title: _t("Did you know?"),
                                                  popup_text: `<p>${_t("Add the details here.")}</p>`, pulse: true } });
        case "embed":
            return Object.assign(base, { w: 720, h: 420, props: { url: "" } });
        case "tabs":
            return Object.assign(base, { w: 760, h: 380, required: true, props: { items: items(3, _t("Tab")) } });
        case "accordion":
            return Object.assign(base, { w: 680, h: 400, required: true, props: { items: items(3, _t("Section")) } });
        case "flipcard":
            return Object.assign(base, { w: 300, h: 220, required: true,
                                         props: { front_html: `<p><strong>${_t("Term")}</strong></p>`,
                                                  back_html: `<p>${_t("Explanation")}</p>`, back_background: "" },
                                         style: { fontSize: 22 } });
        case "labeled_graphic":
            return Object.assign(base, { w: 760, h: 460, required: true, props: {
                attachment_id: false, alt: "",
                markers: [
                    { x: 30, y: 40, title: _t("Point 1"), text: `<p>${_t("Details")}</p>` },
                    { x: 65, y: 60, title: _t("Point 2"), text: `<p>${_t("Details")}</p>` },
                ] } });
        case "mcq":
            return question({ options: [
                { text: _t("Correct answer"), correct: true },
                { text: _t("Wrong answer"), correct: false },
                { text: _t("Wrong answer"), correct: false },
            ] });
        case "mrq":
            return question({ prompt: `<p>${_t("Select all that apply")}</p>`, options: [
                { text: _t("Correct answer"), correct: true },
                { text: _t("Correct answer"), correct: true },
                { text: _t("Wrong answer"), correct: false },
                { text: _t("Wrong answer"), correct: false },
            ] });
        case "truefalse":
            return question({ shuffle: false, attempts: 1, options: [
                { text: _t("True"), correct: true },
                { text: _t("False"), correct: false },
            ] });
        case "fillblank":
            return question({ answers: [_t("answer")], case_sensitive: false }, { h: 260 });
        case "matching":
            return question({ pairs: [
                { left: _t("Item 1"), right: _t("Match 1") },
                { left: _t("Item 2"), right: _t("Match 2") },
                { left: _t("Item 3"), right: _t("Match 3") },
            ] });
        case "sequence":
            return question({ prompt: `<p>${_t("Put these steps in order")}</p>`,
                              items: [_t("First"), _t("Second"), _t("Third"), _t("Fourth")] });
        case "survey":
            return question({ prompt: `<p>${_t("How confident do you feel?")}</p>`, shuffle: false, attempts: 0,
                              options: [_t("Not at all"), _t("A little"), _t("Fairly"), _t("Very")]
                                  .map((text) => ({ text, correct: false })) }, { scored: false, h: 260 });
        case "results":
            return Object.assign(base, { w: 640, h: 340, props: { pass_html: "", fail_html: "", allow_retry: true } });
    }
    return base;
}

// ----------------------------------------------------------------------
// Rich text: formatting applies to the words selected in whichever rich
// text box (data-rich) the cursor was last in, so the size and colour
// pickers, which take the focus, still format the right words.
// ----------------------------------------------------------------------
const TEXT_SIZES = [10, 12, 14, 16, 18, 20, 24, 28, 32, 36, 40, 48, 56, 64, 72, 96];
const richSelection = { range: null, editable: null };

function rememberSelection() {
    const selection = window.getSelection();
    if (!selection.rangeCount) {
        return;
    }
    const range = selection.getRangeAt(0);
    const node = range.commonAncestorContainer;
    const editable = (node.nodeType === 1 ? node : node.parentElement)?.closest("[data-rich]");
    if (editable && editable.isContentEditable) {
        richSelection.range = range.cloneRange();
        richSelection.editable = editable;
    }
}

function applyFormat(command, value = null) {
    const editable = richSelection.editable;
    if (!editable || !editable.isConnected || !editable.isContentEditable) {
        return false;
    }
    editable.focus();
    if (richSelection.range) {
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(richSelection.range);
    }
    document.execCommand("styleWithCSS", false, command !== "fontSize");
    if (command === "fontSize") {
        // execCommand only knows sizes 1-7: mark the words with 7, then set the real size
        document.execCommand("fontSize", false, "7");
        const spans = [];
        for (const font of editable.querySelectorAll('font[size="7"]')) {
            const span = document.createElement("span");
            span.style.fontSize = `${value}px`;
            span.append(...font.childNodes);
            font.replaceWith(span);
            spans.push(span);
        }
        if (spans.length) {
            // Keep the same words selected for the next format
            const range = document.createRange();
            range.setStartBefore(spans[0]);
            range.setEndAfter(spans[spans.length - 1]);
            const selection = window.getSelection();
            selection.removeAllRanges();
            selection.addRange(range);
        }
    } else {
        document.execCommand(command, false, value);
    }
    rememberSelection();
    editable.dispatchEvent(new Event("input", { bubbles: true }));
    return true;
}

class FormatToolbar extends Component {
    static template = "lms_scorm_authoring.FormatToolbar";
    static props = { compact: { type: Boolean, optional: true } };

    setup() {
        this.sizes = TEXT_SIZES;
    }

    onMouseDown(ev) {
        // Keep the cursor in the text box for the buttons (pickers need the focus)
        if (ev.target.closest("button")) {
            ev.preventDefault();
        }
    }

    apply(command, value = null) {
        applyFormat(command, value);
    }

    applySize(ev) {
        if (ev.target.value) {
            applyFormat("fontSize", ev.target.value);
        }
        ev.target.value = "";
    }

    link() {
        const url = window.prompt(_t("Link address (https://…)"), "https://");
        if (url && /^(https?:|mailto:)/i.test(url)) {
            applyFormat("createLink", url);
        }
    }
}

/** A rich text box for the properties panel. */
class RichText extends Component {
    static template = "lms_scorm_authoring.RichText";
    static components = { FormatToolbar };
    static props = {
        value: { type: String, optional: true },
        onChange: Function,
        readonly: { type: Boolean, optional: true },
    };

    setup() {
        this.editable = useRef("editable");
        onMounted(() => {
            this.editable.el.innerHTML = this.props.value || "";
        });
        onWillUpdateProps((next) => {
            const el = this.editable.el;
            // Leave the box alone while someone is typing in it
            if (el && document.activeElement !== el && (next.value || "") !== el.innerHTML) {
                el.innerHTML = next.value || "";
            }
        });
        onWillUnmount(() => clearTimeout(this.timer));
    }

    onInput() {
        clearTimeout(this.timer);
        this.timer = setTimeout(() => this.commit(), 600);
    }

    commit() {
        clearTimeout(this.timer);
        const el = this.editable.el;
        if (!el || this.props.readonly) {
            return;
        }
        const value = el.textContent.trim() || el.querySelector("img") ? el.innerHTML : "";
        if (value !== (this.props.value || "")) {
            this.props.onChange(value);
        }
    }
}

/** What the author wants the AI to write. */
class AiCourseDialog extends Component {
    static template = "lms_scorm_authoring.AiCourseDialog";
    static components = { Dialog };
    static props = { hasSlides: Boolean, provider: String, onGenerate: Function, close: Function };

    setup() {
        this.state = useState({
            prompt: "",
            includeChecks: true,
            includeExam: true,
            minutes: 15,
            replace: false,
            error: "",
        });
    }

    set(field, value) {
        this.state[field] = value;
        this.state.error = "";
    }

    generate() {
        const prompt = this.state.prompt.trim();
        const minutes = parseInt(this.state.minutes, 10);
        if (!prompt) {
            this.state.error = _t("Describe what the course should teach.");
            return;
        }
        if (!(minutes >= 5 && minutes <= 240)) {
            this.state.error = _t("The course length must be between 5 and 240 minutes.");
            return;
        }
        this.props.close();
        this.props.onGenerate({
            prompt,
            include_checks: this.state.includeChecks,
            include_exam: this.state.includeExam,
            minutes,
            replace: this.state.replace,
        });
    }
}

export class ScormEditor extends Component {
    static template = "lms_scorm_authoring.Editor";
    static components = { FormatToolbar, RichText };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        this.stageArea = useRef("stageArea");
        this.palette = PALETTE;
        this.layouts = SLIDE_LAYOUTS;
        this.typeLabels = TYPE_LABELS;
        this.questionTypes = QUESTION_TYPES;
        const params = this.props.action.params || {};
        const context = this.props.action.context || {};
        this.courseId = Number(params.course_id ||
            (context.active_model === "lms.scorm.course" || !context.active_model ? context.active_id : 0));
        this.startSlideId = params.slide_id ? Number(params.slide_id) : null;

        this.state = useState({
            loading: true,
            saving: false,
            dirty: false,
            lastSaved: "",
            course: null,
            slides: [],
            comments: [],
            current: 0,
            selectedId: null, // the item the properties panel shows
            selectedIds: [], // every selected item (Shift/Ctrl-click or drag a box)
            marquee: null,
            editingId: null,
            panel: "item",
            zoom: "fit",
            scale: 0.5,
            showLayouts: false,
            commentMode: false,
            pendingPin: null,
            newComment: "",
            replyTo: null,
            replyText: "",
            showResolved: false,
            uploading: false,
        });
        this.deleted = [];
        this.changes = 0;
        this.undoStack = [];
        this.redoStack = [];
        this.clipboard = null;
        this.drag = null;

        this._onKeydown = this.onKeydown.bind(this);
        this._onPointerMove = this.onPointerMove.bind(this);
        this._onPointerUp = this.onPointerUp.bind(this);
        this._onBeforeUnload = (ev) => {
            if (this.state.dirty) {
                ev.preventDefault();
                ev.returnValue = "";
            }
        };

        onWillStart(() => this.load());
        onMounted(() => {
            document.addEventListener("keydown", this._onKeydown);
            document.addEventListener("selectionchange", rememberSelection);
            window.addEventListener("beforeunload", this._onBeforeUnload);
            this.resizeObserver = new ResizeObserver(() => this.fit());
            if (this.stageArea.el) {
                this.resizeObserver.observe(this.stageArea.el);
            }
            this.fit();
        });
        onWillUnmount(() => {
            document.removeEventListener("keydown", this._onKeydown);
            document.removeEventListener("selectionchange", rememberSelection);
            window.removeEventListener("beforeunload", this._onBeforeUnload);
            document.removeEventListener("pointermove", this._onPointerMove);
            document.removeEventListener("pointerup", this._onPointerUp);
            this.resizeObserver?.disconnect();
            clearTimeout(this.autosaveTimer);
            if (this.state.dirty && this.canEdit) {
                // Leaving the editor: keep the work
                this.save(true);
            }
        });
    }

    // ------------------------------------------------------------------
    // Loading and saving
    // ------------------------------------------------------------------
    async load() {
        if (!this.courseId) {
            this.action.doAction("lms_scorm_authoring.action_lms_scorm_course", { clearBreadcrumbs: true });
            return;
        }
        const data = await this.orm.call("lms.scorm.course", "editor_load", [[this.courseId]]);
        this.state.course = data;
        this.state.slides = data.slides;
        this.state.comments = data.comments;
        if (this.startSlideId) {
            const index = data.slides.findIndex((s) => s.id === this.startSlideId);
            this.state.current = Math.max(index, 0);
        }
        if (!data.slides.length && data.permissions.can_edit) {
            this.state.slides.push(this.newSlide("title"));
            this.state.dirty = true;
        }
        if (data.branding.font_url && !document.querySelector(`link[href="${data.branding.font_url}"]`)) {
            const link = document.createElement("link");
            link.rel = "stylesheet";
            link.href = data.branding.font_url;
            document.head.appendChild(link);
        }
        if (!data.permissions.can_edit) {
            this.state.panel = data.permissions.can_comment ? "comments" : "slide";
        }
        this.state.loading = false;
    }

    get canEdit() {
        return !!this.state.course?.permissions.can_edit;
    }

    get readonly() {
        return !this.canEdit;
    }

    get slide() {
        return this.state.slides[this.state.current];
    }

    /** Select these items (ids or one id); the last one is shown in the panel. */
    select(ids) {
        const list = (Array.isArray(ids) ? ids : [ids]).filter(Boolean);
        this.state.selectedIds = list;
        this.state.selectedId = list.length ? list[list.length - 1] : null;
    }

    isSelected(el) {
        return this.state.selectedIds.includes(el.id);
    }

    get selectedEls() {
        const ids = this.state.selectedIds;
        return this.slide ? this.slide.elements.filter((el) => ids.includes(el.id)) : [];
    }

    get multiSelected() {
        return this.state.selectedIds.length > 1;
    }

    get selected() {
        if (!this.slide || !this.state.selectedId) {
            return null;
        }
        return this.slide.elements.find((el) => el.id === this.state.selectedId) || null;
    }

    get sortedElements() {
        return this.slide ? [...this.slide.elements].sort((a, b) => (a.z || 0) - (b.z || 0)) : [];
    }

    get otherSlides() {
        return this.state.slides.map((s, i) => ({ id: s.id, label: `${i + 1}. ${s.name}` }))
            .filter((s) => s.id !== this.slide?.id);
    }

    get slideComments() {
        if (!this.slide) {
            return [];
        }
        return this.state.comments.filter((c) => c.slide_id === this.slide.id && !c.parent_id &&
                                                  (this.state.showResolved || !c.resolved));
    }

    replies(comment) {
        return this.state.comments.filter((c) => c.parent_id === comment.id);
    }

    isGated(slide) {
        return Boolean(slide.gate_pass_score || slide.gate_min_seconds ||
                       (slide.gate_require_interactions && slide.elements.some((e) => e.required)));
    }

    openCommentCount(slide) {
        return this.state.comments.filter((c) => c.slide_id === slide.id && !c.parent_id && !c.resolved).length;
    }

    pinNumber(comment) {
        return this.slideComments.indexOf(comment) + 1;
    }

    markDirty() {
        if (!this.canEdit) {
            return;
        }
        this.state.dirty = true;
        this.changes += 1;
        clearTimeout(this.autosaveTimer);
        this.autosaveTimer = setTimeout(() => {
            if (!this.drag && !this.state.editingId) {
                this.save(true);
            }
        }, AUTOSAVE_MS);
    }

    async save(silent = false) {
        if (!this.canEdit || this.state.saving) {
            return;
        }
        this.commitTextEdit();
        clearTimeout(this.autosaveTimer);
        this.state.saving = true;
        const changesAtStart = this.changes;
        try {
            const payload = { slides: clone(this.state.slides), deleted: this.deleted };
            const result = await this.orm.call("lms.scorm.course", "editor_save", [[this.courseId], payload]);
            const map = result.key_map;
            // Swap temporary ids for saved ones without losing edits made meanwhile
            for (const slide of this.state.slides) {
                const newId = map[String(slide.id)];
                if (newId && newId !== slide.id) {
                    slide.id = newId;
                }
                for (const el of slide.elements) {
                    if (el.props.target_slide && map[String(el.props.target_slide)]) {
                        el.props.target_slide = map[String(el.props.target_slide)];
                    }
                }
                if (slide.gate_fail_slide_id && map[String(slide.gate_fail_slide_id)]) {
                    slide.gate_fail_slide_id = map[String(slide.gate_fail_slide_id)];
                }
            }
            this.deleted = [];
            // Still dirty if something changed while saving
            this.state.dirty = this.changes !== changesAtStart;
            const now = new Date();
            this.state.lastSaved = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
            if (!silent) {
                this.notification.add(_t("Saved"), { type: "success" });
            }
        } catch (error) {
            this.state.dirty = true;
            throw error;
        } finally {
            this.state.saving = false;
        }
    }

    // ------------------------------------------------------------------
    // Undo / redo
    // ------------------------------------------------------------------
    snapshot() {
        if (!this.canEdit) {
            return;
        }
        this.undoStack.push(JSON.stringify({ slides: this.state.slides, current: this.state.current, deleted: this.deleted }));
        if (this.undoStack.length > 60) {
            this.undoStack.shift();
        }
        this.redoStack = [];
    }

    restoreSnapshot(text) {
        const data = JSON.parse(text);
        this.state.slides = data.slides;
        this.deleted = data.deleted;
        this.state.current = Math.min(data.current, data.slides.length - 1);
        this.select(null);
        this.state.editingId = null;
        this.markDirty();
    }

    undo() {
        if (!this.undoStack.length) {
            return;
        }
        this.redoStack.push(JSON.stringify({ slides: this.state.slides, current: this.state.current, deleted: this.deleted }));
        this.restoreSnapshot(this.undoStack.pop());
    }

    redo() {
        if (!this.redoStack.length) {
            return;
        }
        this.undoStack.push(JSON.stringify({ slides: this.state.slides, current: this.state.current, deleted: this.deleted }));
        this.restoreSnapshot(this.redoStack.pop());
    }

    // ------------------------------------------------------------------
    // Slides
    // ------------------------------------------------------------------
    newSlide(layout = "blank") {
        const course = this.state.course;
        const slide = {
            id: "n" + uid(),
            name: _t("New Slide"),
            notes: "",
            hide_in_menu: false,
            background_color: "",
            background_attachment_id: false,
            gate_require_interactions: true,
            gate_min_seconds: 0,
            gate_pass_score: 0,
            gate_max_attempts: 0,
            gate_fail_slide_id: false,
            elements: [],
        };
        const W = course.width;
        const H = course.height;
        const place = (el, x, y, w, h) => Object.assign(el, { x: Math.round(x), y: Math.round(y), w: Math.round(w), h: Math.round(h) });
        const heading = (y = H * 0.08) => place(defaultElement("heading", course.branding), W * 0.06, y, W * 0.88, 90);
        if (layout === "title") {
            const title = heading(H * 0.32);
            title.style.fontSize = 56;
            title.props.html = `<p style="text-align:center">${_t("Course title")}</p>`;
            const sub = place(defaultElement("text", course.branding), W * 0.15, H * 0.32 + 110, W * 0.7, 80);
            sub.props.html = `<p style="text-align:center">${_t("Subtitle")}</p>`;
            slide.elements.push(title, sub);
            slide.name = _t("Title");
        } else if (layout === "content") {
            const body = place(defaultElement("text", course.branding), W * 0.06, H * 0.08 + 110, W * 0.88, H * 0.6);
            body.props.html = `<ul><li>${_t("First point")}</li><li>${_t("Second point")}</li><li>${_t("Third point")}</li></ul>`;
            slide.elements.push(heading(), body);
        } else if (layout === "image") {
            const body = place(defaultElement("text", course.branding), W * 0.06, H * 0.08 + 110, W * 0.42, H * 0.6);
            const image = place(defaultElement("image", course.branding), W * 0.52, H * 0.08 + 110, W * 0.42, H * 0.6);
            slide.elements.push(heading(), body, image);
        } else if (layout === "question") {
            const q = place(defaultElement("mcq", course.branding), W * 0.1, H * 0.08 + 100, W * 0.8, H * 0.66);
            const title = heading();
            title.props.html = `<p>${_t("Knowledge check")}</p>`;
            slide.elements.push(title, q);
            slide.name = _t("Knowledge check");
        } else if (layout === "results") {
            const title = heading();
            title.props.html = `<p style="text-align:center">${_t("Your results")}</p>`;
            const results = place(defaultElement("results", course.branding), W * 0.2, H * 0.08 + 110, W * 0.6, H * 0.55);
            slide.elements.push(title, results);
            slide.name = _t("Results");
        }
        slide.elements.forEach((el, i) => { el.z = i + 1; });
        return slide;
    }

    selectSlide(index) {
        this.commitTextEdit();
        this.state.current = index;
        this.select(null);
        this.state.pendingPin = null;
        this.state.commentMode = false;
        if (this.state.panel === "item") {
            this.state.panel = this.canEdit ? "slide" : this.state.panel;
        }
    }

    addSlide(layout) {
        this.snapshot();
        const slide = this.newSlide(layout);
        this.state.slides.splice(this.state.current + 1, 0, slide);
        this.state.showLayouts = false;
        this.selectSlide(this.state.current + 1);
        this.markDirty();
    }

    duplicateSlide(index) {
        this.snapshot();
        const copy = clone(this.state.slides[index]);
        copy.id = "n" + uid();
        copy.name = `${copy.name} (${_t("copy")})`;
        copy.elements.forEach((el) => { el.id = uid(); });
        this.state.slides.splice(index + 1, 0, copy);
        this.selectSlide(index + 1);
        this.markDirty();
    }

    deleteSlide(index) {
        const slide = this.state.slides[index];
        this.dialog.add(ConfirmationDialog, {
            body: _t("Delete the slide \"%s\" and everything on it?", slide.name),
            cancel: () => {},
            confirm: () => {
                this.snapshot();
                if (typeof slide.id === "number") {
                    this.deleted.push(slide.id);
                }
                this.state.slides.splice(index, 1);
                this.state.current = Math.max(0, Math.min(this.state.current, this.state.slides.length - 1));
                this.select(null);
                this.markDirty();
            },
        });
    }

    moveSlide(index, delta) {
        const target = index + delta;
        if (target < 0 || target >= this.state.slides.length) {
            return;
        }
        this.snapshot();
        const [slide] = this.state.slides.splice(index, 1);
        this.state.slides.splice(target, 0, slide);
        this.state.current = target;
        this.markDirty();
    }

    onSlideDragStart(ev, index) {
        if (!this.canEdit) {
            ev.preventDefault();
            return;
        }
        ev.dataTransfer.setData("application/x-scorm-slide", String(index));
        ev.dataTransfer.effectAllowed = "move";
    }

    onSlideDrop(ev, index) {
        const from = ev.dataTransfer.getData("application/x-scorm-slide");
        if (from === "") {
            return;
        }
        ev.preventDefault();
        this.moveSlide(Number(from), index - Number(from));
    }

    // ------------------------------------------------------------------
    // Stage geometry
    // ------------------------------------------------------------------
    fit() {
        const area = this.stageArea.el;
        const course = this.state.course;
        if (!area || !course) {
            return;
        }
        if (this.state.zoom !== "fit") {
            this.state.scale = Number(this.state.zoom);
            return;
        }
        const rect = area.getBoundingClientRect();
        const scale = Math.min((rect.width - 48) / course.width, (rect.height - 48) / course.height);
        this.state.scale = Math.max(0.15, Math.min(scale, 2));
    }

    setZoom(ev) {
        this.state.zoom = ev.target.value;
        this.fit();
    }

    get stageStyle() {
        const course = this.state.course;
        const slide = this.slide;
        const brand = course.branding;
        let style = `width:${course.width}px;height:${course.height}px;transform:scale(${this.state.scale});` +
            `background:${slide?.background_color || brand.slide_color};color:${brand.text_color};` +
            `font-family:${brand.font_family};--brand-primary:${brand.primary_color};` +
            `--brand-secondary:${brand.secondary_color};--brand-button-text:${brand.button_text_color};`;
        if (slide?.background_attachment_id) {
            style += `background-image:url('/web/content/${slide.background_attachment_id}');background-size:cover;background-position:center;`;
        }
        return style;
    }

    get stageFrameStyle() {
        const course = this.state.course;
        return `width:${course.width * this.state.scale}px;height:${course.height * this.state.scale}px;`;
    }

    thumbStyle(slide) {
        const course = this.state.course;
        const scale = 168 / course.width;
        let style = `width:${course.width}px;height:${course.height}px;transform:scale(${scale});` +
            `background:${slide.background_color || course.branding.slide_color};color:${course.branding.text_color};` +
            `font-family:${course.branding.font_family};--brand-primary:${course.branding.primary_color};` +
            `--brand-button-text:${course.branding.button_text_color};`;
        if (slide.background_attachment_id) {
            style += `background-image:url('/web/content/${slide.background_attachment_id}');background-size:cover;`;
        }
        return style;
    }

    thumbFrameStyle() {
        const course = this.state.course;
        return `height:${Math.round((168 / course.width) * course.height)}px;`;
    }

    elementStyle(el) {
        let style = `left:${el.x}px;top:${el.y}px;width:${el.w}px;height:${el.h}px;z-index:${el.z || 1};`;
        if (el.rotation) {
            style += `transform:rotate(${el.rotation}deg);`;
        }
        return style;
    }

    boxStyle(el) {
        const s = el.style || {};
        const parts = [];
        if (s.fontSize) { parts.push(`font-size:${s.fontSize}px`); }
        if (s.color) { parts.push(`color:${s.color}`); }
        if (s.fontFamily) { parts.push(`font-family:${s.fontFamily}`); }
        if (s.bold) { parts.push("font-weight:bold"); }
        if (s.italic) { parts.push("font-style:italic"); }
        if (s.background && el.type !== "button") { parts.push(`background:${s.background}`); }
        if (s.borderWidth && !(el.type === "shape" && el.props.shape === "line")) {
            parts.push(`border:${s.borderWidth}px solid ${s.borderColor || "#000"}`);
        }
        if (s.radius) { parts.push(`border-radius:${Math.min(s.radius, 9999)}px`); }
        if (s.opacity !== undefined && s.opacity !== "" && s.opacity !== null) { parts.push(`opacity:${s.opacity}`); }
        if (s.padding) { parts.push(`padding:${s.padding}px`); }
        if (s.shadow) { parts.push("box-shadow:0 6px 18px rgba(0,0,0,.18)"); }
        if (el.type === "shape" && el.props.shape === "ellipse") { parts.push("border-radius:50%"); }
        if (el.type === "shape" && el.props.shape === "line") {
            parts.push(`border-top:${s.borderWidth || 2}px solid ${s.borderColor || "#333"};height:0;top:50%;position:absolute;left:0;right:0`);
        }
        if (el.type === "shape" && el.props.shape !== "line" && !s.background && !s.borderWidth) {
            parts.push("background:var(--brand-primary)");
        }
        return parts.join(";");
    }

    buttonStyle(el) {
        const s = el.style || {};
        return `background:${s.background || "var(--brand-primary)"};color:${s.color || "var(--brand-button-text)"};` +
            `font-size:${s.fontSize || 18}px;border-radius:${s.radius || 6}px;`;
    }

    html(value) {
        return markup(value || "");
    }

    mediaUrl(id) {
        return id ? `/web/content/${id}` : "";
    }

    videoThumb(el) {
        const m = /(?:youtube\.com\/(?:watch\?v=|embed\/|shorts\/)|youtu\.be\/)([\w-]{6,})/.exec(el.props.url || "");
        return m ? `https://img.youtube.com/vi/${m[1]}/hqdefault.jpg` : "";
    }

    // ------------------------------------------------------------------
    // Adding items
    // ------------------------------------------------------------------
    addElement(type, x = null, y = null, askForFile = true) {
        if (!this.canEdit || !this.slide) {
            return null;
        }
        this.snapshot();
        const course = this.state.course;
        const el = defaultElement(type, course.branding);
        el.w = Math.min(el.w, course.width);
        el.h = Math.min(el.h, course.height);
        const cx = x === null ? course.width / 2 : x;
        const cy = y === null ? course.height / 2 : y;
        el.x = this.snap(Math.max(0, Math.min(cx - el.w / 2, course.width - el.w)));
        el.y = this.snap(Math.max(0, Math.min(cy - el.h / 2, course.height - el.h)));
        el.z = Math.max(0, ...this.slide.elements.map((e) => e.z || 0)) + 1;
        this.slide.elements.push(el);
        this.select(el.id);
        this.state.panel = "item";
        this.markDirty();
        if (askForFile && ["image", "labeled_graphic"].includes(type)) {
            this.pickFile("image/*", (att) => {
                el.props.attachment_id = att.id;
                this.markDirty();
            });
        }
        return el;
    }

    onPaletteDragStart(ev, type) {
        ev.dataTransfer.setData("application/x-scorm-item", type);
        ev.dataTransfer.effectAllowed = "copy";
    }

    stagePoint(ev) {
        const rect = this.stageArea.el.querySelector(".o_scorm_stage").getBoundingClientRect();
        return { x: (ev.clientX - rect.left) / this.state.scale, y: (ev.clientY - rect.top) / this.state.scale };
    }

    onStageDragOver(ev) {
        if (!this.canEdit) {
            return;
        }
        const types = Array.from(ev.dataTransfer.types || []);
        if (types.includes("application/x-scorm-item") || types.includes("Files")) {
            ev.preventDefault();
            ev.dataTransfer.dropEffect = "copy";
        }
    }

    async onStageDrop(ev) {
        if (!this.canEdit) {
            return;
        }
        const type = ev.dataTransfer.getData("application/x-scorm-item");
        const point = this.stagePoint(ev);
        if (type) {
            ev.preventDefault();
            this.addElement(type, point.x, point.y);
            return;
        }
        const files = Array.from(ev.dataTransfer.files || []);
        if (!files.length) {
            return;
        }
        ev.preventDefault();
        for (const file of files) {
            const kind = file.type.startsWith("image/") ? "image" : file.type.startsWith("video/") ? "video"
                : file.type.startsWith("audio/") ? "audio" : null;
            if (!kind) {
                this.notification.add(_t("%s is not a picture, video or audio file.", file.name), { type: "warning" });
                continue;
            }
            const att = await this.upload(file);
            if (att) {
                const el = this.addElement(kind, point.x, point.y, false);
                el.props.attachment_id = att.id;
                this.markDirty();
            }
        }
    }

    // ------------------------------------------------------------------
    // Uploads
    // ------------------------------------------------------------------
    pickFile(accept, callback) {
        const input = document.createElement("input");
        input.type = "file";
        input.accept = accept;
        input.addEventListener("change", async () => {
            const file = input.files[0];
            if (file) {
                const att = await this.upload(file);
                if (att) {
                    callback(att);
                }
            }
        });
        input.click();
    }

    async upload(file) {
        if (file.size > MAX_UPLOAD) {
            this.notification.add(_t("%s is too large (150 MB maximum).", file.name), { type: "danger" });
            return null;
        }
        this.state.uploading = true;
        try {
            const data = await new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = () => resolve(reader.result.split(",")[1]);
                reader.onerror = reject;
                reader.readAsDataURL(file);
            });
            return await this.orm.call("lms.scorm.course", "editor_upload_asset",
                                       [[this.courseId], file.name, data, file.type || false]);
        } finally {
            this.state.uploading = false;
        }
    }

    uploadFor(el, accept, key = "attachment_id") {
        this.pickFile(accept, (att) => {
            this.snapshot();
            el.props[key] = att.id;
            if (key === "attachment_id" && el.props.url !== undefined) {
                el.props.url = "";
            }
            this.markDirty();
        });
    }

    uploadBackground() {
        this.pickFile("image/*", (att) => {
            this.snapshot();
            this.slide.background_attachment_id = att.id;
            this.markDirty();
        });
    }

    // ------------------------------------------------------------------
    // Selecting, moving and resizing
    // ------------------------------------------------------------------
    snap(value) {
        return Math.round(value / GRID) * GRID;
    }

    onStagePointerDown(ev) {
        if (this.state.commentMode) {
            const p = this.stagePoint(ev);
            const course = this.state.course;
            this.state.pendingPin = {
                pos_x: Math.round((p.x / course.width) * 1000) / 10,
                pos_y: Math.round((p.y / course.height) * 1000) / 10,
                element_id: this.state.selectedId || false,
            };
            this.state.commentMode = false;
            this.state.panel = "comments";
            return;
        }
        if (ev.target.closest(".o_scorm_el") || !ev.target.closest(".o_scorm_stage_frame") || ev.button !== 0) {
            if (!ev.target.closest(".o_scorm_el")) {
                this.clearSelection();
            }
            return;
        }
        this.commitTextEdit();
        // Drag a box on the empty slide to select the items it touches
        const start = this.stagePoint(ev);
        this.drag = {
            marquee: true,
            start,
            additive: ev.shiftKey || ev.ctrlKey || ev.metaKey,
            initial: [...this.state.selectedIds],
            startX: ev.clientX,
            startY: ev.clientY,
            moved: false,
        };
        document.addEventListener("pointermove", this._onPointerMove);
        document.addEventListener("pointerup", this._onPointerUp);
    }

    clearSelection() {
        this.commitTextEdit();
        this.select(null);
        if (this.state.panel === "item") {
            this.state.panel = "slide";
        }
    }

    updateMarquee(ev) {
        const drag = this.drag;
        const point = this.stagePoint(ev);
        const box = {
            x: Math.min(drag.start.x, point.x),
            y: Math.min(drag.start.y, point.y),
            w: Math.abs(point.x - drag.start.x),
            h: Math.abs(point.y - drag.start.y),
        };
        this.state.marquee = box;
        const hit = this.slide.elements.filter((el) =>
            el.x < box.x + box.w && el.x + el.w > box.x && el.y < box.y + box.h && el.y + el.h > box.y
        ).map((el) => el.id);
        const ids = drag.additive ? [...new Set([...drag.initial, ...hit])] : hit;
        this.select(ids);
        if (ids.length) {
            this.state.panel = "item";
        }
    }

    get marqueeStyle() {
        const m = this.state.marquee;
        return m ? `left:${m.x}px;top:${m.y}px;width:${m.w}px;height:${m.h}px;` : "";
    }

    onElementPointerDown(ev, el, handle = null) {
        if (this.state.commentMode) {
            return;
        }
        ev.stopPropagation();
        if (this.state.editingId === el.id && !handle) {
            return; // typing in the text box
        }
        if (this.state.editingId && this.state.editingId !== el.id) {
            this.commitTextEdit();
        }
        this.state.panel = "item";
        if (!handle && (ev.shiftKey || ev.ctrlKey || ev.metaKey)) {
            // Add to / take out of the selection
            const ids = this.state.selectedIds.filter((id) => id !== el.id);
            this.select(this.isSelected(el) ? ids : [...ids, el.id]);
            if (!this.state.selectedIds.length) {
                this.state.panel = "slide";
            }
            return;
        }
        if (!this.isSelected(el) || handle) {
            this.select(el.id);
        } else {
            // Keep the group, show this one in the panel
            this.select([...this.state.selectedIds.filter((id) => id !== el.id), el.id]);
        }
        if (!this.canEdit || ev.button !== 0) {
            return;
        }
        ev.preventDefault();
        this.drag = {
            el,
            handle,
            startX: ev.clientX,
            startY: ev.clientY,
            orig: { x: el.x, y: el.y, w: el.w, h: el.h },
            // Every selected item moves together
            group: handle ? [] : this.selectedEls.map((item) => ({ item, x: item.x, y: item.y, w: item.w, h: item.h })),
            moved: false,
            snapshotTaken: false,
            free: ev.altKey,
        };
        document.addEventListener("pointermove", this._onPointerMove);
        document.addEventListener("pointerup", this._onPointerUp);
    }

    onPointerMove(ev) {
        const drag = this.drag;
        if (!drag) {
            return;
        }
        const dx = (ev.clientX - drag.startX) / this.state.scale;
        const dy = (ev.clientY - drag.startY) / this.state.scale;
        if (!drag.moved && Math.abs(dx) < 2 && Math.abs(dy) < 2) {
            return;
        }
        if (drag.marquee) {
            drag.moved = true;
            this.updateMarquee(ev);
            return;
        }
        if (!drag.snapshotTaken) {
            this.snapshot();
            drag.snapshotTaken = true;
        }
        drag.moved = true;
        const snap = ev.altKey ? (v) => Math.round(v) : (v) => this.snap(v);
        const { el, orig, handle } = drag;
        const course = this.state.course;
        if (!handle) {
            // Snap the item being dragged, and move the rest of the group by the same amount
            const x = snap(Math.max(-orig.w + 16, Math.min(orig.x + dx, course.width - 16)));
            const y = snap(Math.max(-orig.h + 16, Math.min(orig.y + dy, course.height - 16)));
            const moveX = x - orig.x;
            const moveY = y - orig.y;
            for (const g of drag.group) {
                g.item.x = Math.max(-g.w + 16, Math.min(g.x + moveX, course.width - 16));
                g.item.y = Math.max(-g.h + 16, Math.min(g.y + moveY, course.height - 16));
            }
            el.x = x;
            el.y = y;
            return;
        }
        let { x, y, w, h } = orig;
        if (handle.includes("e")) { w = orig.w + dx; }
        if (handle.includes("s")) { h = orig.h + dy; }
        if (handle.includes("w")) { w = orig.w - dx; x = orig.x + dx; }
        if (handle.includes("n")) { h = orig.h - dy; y = orig.y + dy; }
        if (ev.shiftKey && orig.h) {
            // Keep proportions
            const ratio = orig.w / orig.h;
            if (handle.length === 2) {
                h = w / ratio;
                if (handle.includes("n")) { y = orig.y + orig.h - h; }
            }
        }
        const min = 12;
        if (w < min) { if (handle.includes("w")) { x -= min - w; } w = min; }
        if (h < min) { if (handle.includes("n")) { y -= min - h; } h = min; }
        Object.assign(el, { x: snap(x), y: snap(y), w: snap(w) || min, h: snap(h) || min });
    }

    onPointerUp() {
        document.removeEventListener("pointermove", this._onPointerMove);
        document.removeEventListener("pointerup", this._onPointerUp);
        const drag = this.drag;
        this.drag = null;
        if (drag?.marquee) {
            this.state.marquee = null;
            if (!drag.moved && !drag.additive) {
                this.clearSelection();
            }
            return;
        }
        if (drag?.moved) {
            this.markDirty();
        }
    }

    onElementDblClick(el) {
        if (!this.canEdit) {
            return;
        }
        if (el.type === "text" || el.type === "button") {
            this.startTextEdit(el);
        } else if (["image", "video", "audio"].includes(el.type) && !el.props.attachment_id && !el.props.url) {
            this.uploadFor(el, `${el.type}/*`);
        }
    }

    // Text boxes and button labels are edited in place; OWL leaves the
    // content of the contenteditable alone, so it is filled once and read
    // back on commit (clicking elsewhere, Escape, saving, changing slide).
    startTextEdit(el) {
        this.snapshot();
        this.select(el.id);
        this.state.editingId = el.id;
        this.state.panel = "item";
        setTimeout(() => {
            const node = document.querySelector(`.o_scorm_text_edit[data-id="${el.id}"]`);
            if (node) {
                node.innerHTML = el.type === "button" ? this.buttonHtml(el) : el.props.html || "";
                node.focus();
                const range = document.createRange();
                range.selectNodeContents(node);
                const sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(range);
            }
        });
    }

    commitTextEdit() {
        const id = this.state.editingId;
        if (!id) {
            return;
        }
        const node = document.querySelector(`.o_scorm_text_edit[data-id="${id}"]`);
        const el = this.state.slides.flatMap((s) => s.elements).find((e) => e.id === id);
        this.state.editingId = null;
        if (!node || !el) {
            return;
        }
        if (el.type === "button") {
            if (node.innerHTML !== this.buttonHtml(el)) {
                this.applyButtonLabel(el, node.innerHTML);
                this.markDirty();
            }
        } else if (el.props.html !== node.innerHTML) {
            el.props.html = node.innerHTML;
            this.markDirty();
        }
    }

    /** A button's label as HTML (older buttons only have plain text). */
    buttonHtml(el) {
        return el.props.label_html || escapeHtml(el.props.label || "");
    }

    applyButtonLabel(el, html) {
        const div = document.createElement("div");
        div.innerHTML = html;
        el.props.label_html = html;
        // Plain text kept for screen readers and older players
        el.props.label = div.textContent.trim();
    }

    setButtonLabel(el, html) {
        this.snapshot();
        this.applyButtonLabel(el, html);
        this.markDirty();
    }

    // ------------------------------------------------------------------
    // Item actions
    // ------------------------------------------------------------------
    deleteSelected() {
        const els = this.selectedEls;
        if (!els.length || !this.canEdit) {
            return;
        }
        this.snapshot();
        this.slide.elements = this.slide.elements.filter((e) => !els.includes(e));
        this.select(null);
        this.state.editingId = null;
        this.state.panel = "slide";
        this.markDirty();
    }

    /** Copies of items, offset so they don't sit exactly on top of each other. */
    pasteElements(items, offset) {
        let z = Math.max(0, ...this.slide.elements.map((e) => e.z || 0));
        const ordered = [...items].sort((a, b) => (a.z || 0) - (b.z || 0));
        const newIds = new Map();
        const copies = ordered.map((item) => {
            const copy = clone(item);
            copy.id = uid();
            copy.x += offset;
            copy.y += offset;
            copy.z = ++z;
            newIds.set(item.id, copy.id);
            return copy;
        });
        // "Show a hidden item" actions copied together with their target point at the copy
        for (const copy of copies) {
            if (copy.props?.target_element && newIds.has(copy.props.target_element)) {
                copy.props.target_element = newIds.get(copy.props.target_element);
            }
        }
        this.slide.elements.push(...copies);
        this.select(copies.map((copy) => copy.id));
        this.state.panel = "item";
        this.markDirty();
    }

    duplicateSelected() {
        const els = this.selectedEls;
        if (!els.length || !this.canEdit) {
            return;
        }
        this.snapshot();
        this.pasteElements(els, 24);
    }

    copySelected() {
        if (this.selectedEls.length) {
            this.clipboard = { slideId: this.slide.id, items: clone(this.selectedEls) };
        }
    }

    paste() {
        if (!this.clipboard || !this.canEdit) {
            return;
        }
        this.snapshot();
        this.pasteElements(this.clipboard.items, this.clipboard.slideId === this.slide.id ? 24 : 0);
    }

    selectAll() {
        if (this.slide) {
            this.select(this.sortedElements.map((el) => el.id));
            this.state.panel = "item";
        }
    }

    arrange(direction) {
        const els = this.selectedEls;
        if (!els.length) {
            return;
        }
        this.snapshot();
        let ordered = this.sortedElements;
        if (els.length > 1 || direction === "front" || direction === "back") {
            const rest = ordered.filter((e) => !els.includes(e));
            const group = ordered.filter((e) => els.includes(e));
            ordered = direction === "back" || direction === "backward" ? [...group, ...rest] : [...rest, ...group];
        } else {
            const el = els[0];
            const index = ordered.indexOf(el);
            ordered.splice(index, 1);
            if (direction === "forward") { ordered.splice(Math.min(index + 1, ordered.length), 0, el); }
            else { ordered.splice(Math.max(index - 1, 0), 0, el); }
        }
        ordered.forEach((e, i) => { e.z = i + 1; });
        this.markDirty();
    }

    /** One item lines up with the slide; several line up with each other. */
    align(where) {
        const els = this.selectedEls;
        if (!els.length) {
            return;
        }
        this.snapshot();
        const course = this.state.course;
        const box = els.length > 1 ? {
            left: Math.min(...els.map((e) => e.x)),
            right: Math.max(...els.map((e) => e.x + e.w)),
            top: Math.min(...els.map((e) => e.y)),
            bottom: Math.max(...els.map((e) => e.y + e.h)),
        } : { left: 0, right: course.width, top: 0, bottom: course.height };
        for (const el of els) {
            if (where === "left") { el.x = box.left; }
            if (where === "center") { el.x = Math.round((box.left + box.right - el.w) / 2); }
            if (where === "right") { el.x = box.right - el.w; }
            if (where === "top") { el.y = box.top; }
            if (where === "middle") { el.y = Math.round((box.top + box.bottom - el.h) / 2); }
            if (where === "bottom") { el.y = box.bottom - el.h; }
        }
        this.markDirty();
    }

    /** Spread three or more items out evenly across or down. */
    distribute(axis) {
        const els = this.selectedEls;
        if (els.length < 3) {
            return;
        }
        this.snapshot();
        const pos = axis === "x" ? "x" : "y";
        const size = axis === "x" ? "w" : "h";
        const sorted = [...els].sort((a, b) => a[pos] - b[pos]);
        const first = sorted[0];
        const last = sorted[sorted.length - 1];
        const used = sorted.reduce((sum, e) => sum + e[size], 0);
        const gap = (last[pos] + last[size] - first[pos] - used) / (sorted.length - 1);
        let next = first[pos];
        for (const el of sorted) {
            el[pos] = Math.round(next);
            next += el[size] + gap;
        }
        this.markDirty();
    }

    // Generic setters bound from the properties panel
    setProp(el, key, value) {
        this.snapshot();
        el.props[key] = value;
        this.markDirty();
    }

    setStyle(el, key, value) {
        this.snapshot();
        if (value === "" || value === null || value === undefined) {
            delete el.style[key];
        } else {
            el.style[key] = value;
        }
        this.markDirty();
    }

    setGeom(el, key, value) {
        this.snapshot();
        el[key] = Math.round(Number(value) || 0);
        this.markDirty();
    }

    setFlag(el, key, value) {
        this.snapshot();
        el[key] = value;
        this.markDirty();
    }

    setSlide(key, value) {
        this.snapshot();
        this.slide[key] = value;
        this.markDirty();
    }

    toggleLayouts() {
        this.state.showLayouts = !this.state.showLayouts;
    }

    setPanel(panel) {
        this.state.panel = panel;
    }

    setShowResolved(value) {
        this.state.showResolved = value;
    }

    setNewComment(value) {
        this.state.newComment = value;
    }

    setReplyText(value) {
        this.state.replyText = value;
    }

    startReply(comment) {
        this.state.replyTo = comment ? comment.id : null;
        this.state.replyText = "";
    }

    setMediaUrl(el, value) {
        this.snapshot();
        el.props.url = value;
        if (value) {
            el.props.attachment_id = false;
        }
        this.markDirty();
    }

    /** Saved slides have numeric ids, new ones a temporary text id. */
    slideKey(value) {
        if (!value) {
            return false;
        }
        return /^\d+$/.test(value) ? Number(value) : value;
    }

    numberValue(ev) {
        return ev.target.value === "" ? 0 : Number(ev.target.value);
    }

    // Lists inside items (options, tabs, markers, pairs, sequence items, answers)
    listAdd(el, key, item) {
        this.snapshot();
        el.props[key] = [...(el.props[key] || []), item];
        this.markDirty();
    }

    listRemove(el, key, index) {
        this.snapshot();
        el.props[key].splice(index, 1);
        this.markDirty();
    }

    listMove(el, key, index, delta) {
        const list = el.props[key];
        const target = index + delta;
        if (target < 0 || target >= list.length) {
            return;
        }
        this.snapshot();
        const [item] = list.splice(index, 1);
        list.splice(target, 0, item);
        this.markDirty();
    }

    listSet(el, key, index, field, value) {
        this.snapshot();
        const list = el.props[key];
        if (field === null) {
            list[index] = value;
        } else {
            list[index][field] = value;
        }
        this.markDirty();
    }

    setCorrect(el, index, checked) {
        this.snapshot();
        const options = el.props.options;
        if (el.type === "mrq") {
            options[index].correct = checked;
        } else {
            options.forEach((o, i) => { o.correct = i === index; });
        }
        this.markDirty();
    }

    elementsForReveal() {
        return (this.slide?.elements || []).filter((e) => e.id !== this.state.selectedId)
            .map((e) => ({ id: e.id, label: `${this.typeLabels[e.type] || e.type}${e.hidden ? " (" + _t("hidden") + ")" : ""}` }));
    }

    isInteractive(el) {
        return INTERACTIVE_TYPES.includes(el.type);
    }

    isQuestion(el) {
        return QUESTION_TYPES.includes(el.type);
    }

    requiredHint(el) {
        return {
            video: _t("Watched to the end"),
            audio: _t("Listened to the end"),
            button: _t("Clicked"),
            hotspot: _t("Clicked"),
            embed: _t("Clicked into"),
            tabs: _t("Every tab opened"),
            accordion: _t("Every section opened"),
            flipcard: _t("Flipped"),
            labeled_graphic: _t("Every marker opened"),
            results: _t("Results shown"),
        }[el.type] || _t("Answered (correctly, or attempts used up)");
    }

    get requiredCount() {
        return (this.slide?.elements || []).filter((e) => e.required).length;
    }

    get questionCount() {
        return (this.slide?.elements || []).filter((e) => QUESTION_TYPES.includes(e.type) && e.type !== "survey").length;
    }

    // ------------------------------------------------------------------
    // Comments (hidden from learners)
    // ------------------------------------------------------------------
    startComment() {
        if (typeof this.slide.id !== "number") {
            if (!this.canEdit) {
                return;
            }
            this.save(true).then(() => this.startComment());
            return;
        }
        this.state.commentMode = true;
        this.state.pendingPin = null;
    }

    cancelComment() {
        this.state.commentMode = false;
        this.state.pendingPin = null;
        this.state.newComment = "";
    }

    async addComment() {
        const text = this.state.newComment.trim();
        if (!text) {
            return;
        }
        const pin = this.state.pendingPin || { pos_x: 0, pos_y: 0, element_id: false };
        const comment = await this.orm.call("lms.scorm.course", "editor_add_comment", [
            [this.courseId], this.slide.id, text, pin.element_id, pin.pos_x, pin.pos_y, false]);
        this.state.comments.push(comment);
        this.cancelComment();
    }

    async addReply(comment) {
        const text = this.state.replyText.trim();
        if (!text) {
            return;
        }
        const reply = await this.orm.call("lms.scorm.course", "editor_add_comment", [
            [this.courseId], comment.slide_id, text, false, 0, 0, comment.id]);
        this.state.comments.push(reply);
        this.state.replyTo = null;
        this.state.replyText = "";
    }

    async toggleResolved(comment) {
        const updated = await this.orm.call("lms.scorm.course", "editor_resolve_comment", [
            [this.courseId], comment.id, !comment.resolved]);
        Object.assign(comment, updated);
    }

    focusComment(comment) {
        if (comment.element_id) {
            this.select(comment.element_id);
        }
        this.state.panel = "comments";
    }

    // ------------------------------------------------------------------
    // Toolbar actions
    // ------------------------------------------------------------------
    async preview(fromSlide = false) {
        if (this.state.dirty) {
            await this.save(true);
        }
        let url = `/scorm_authoring/${this.courseId}/preview/index.html`;
        if (fromSlide) {
            url += `?slide=${this.state.current + 1}`;
        }
        window.open(url, "_blank");
    }

    // ------------------------------------------------------------------
    // Generate with AI
    // ------------------------------------------------------------------
    openAiDialog() {
        const course = this.state.course;
        if (!this.canEdit || !course.ai_available) {
            return;
        }
        this.dialog.add(AiCourseDialog, {
            hasSlides: this.state.slides.some((s) => s.elements.length),
            provider: course.ai_provider || "AI",
            onGenerate: (options) => this.generateWithAi(options),
        });
    }

    async generateWithAi(options) {
        const extras = [];
        if (options.include_checks) {
            extras.push(_t("knowledge checks"));
        }
        if (options.include_exam) {
            extras.push(_t("a final exam"));
        }
        aiProgress.start(_t("Generating your course"), [
            _t("Saving the course"),
            _t("Checking what is needed"),
            _t("Asking the AI to write the course"),
            _t("Building the slides"),
            _t("Updating the editor"),
        ]);
        try {
            this.commitTextEdit();
            if (this.state.dirty) {
                await this.save(true);
            }
            aiProgress.next();
            const plan = await this.orm.call("lms.scorm.course", "editor_ai_check", [[this.courseId], options]);
            const asking = _t(
                "Asking %(provider)s to write about %(slides)s slides on \"%(topic)s\" for a %(minutes)s-minute course%(extras)s",
                {
                    provider: plan.provider,
                    slides: plan.content_slides,
                    topic: plan.topic,
                    minutes: plan.minutes,
                    extras: extras.length ? ` ${_t("with")} ${extras.join(` ${_t("and")} `)}` : "",
                }
            );
            aiProgress.next(plan.fallback ? `${asking} (${_t("%s if that fails", plan.fallback)})` : asking);
            const written = await this.orm.call("lms.scorm.course", "editor_ai_write", [[this.courseId], options]);
            aiProgress.next(_t("Building the slides from %s's course", written.provider));
            const data = await this.orm.call("lms.scorm.course", "editor_ai_apply", [
                [this.courseId], written.answer, options]);
            aiProgress.next();
            const firstNew = options.replace ? 0 : this.state.slides.length;
            this.state.course = data;
            this.state.slides = data.slides;
            this.state.comments = data.comments;
            this.deleted = [];
            this.undoStack = [];
            this.redoStack = [];
            this.state.dirty = false;
            this.selectSlide(Math.min(firstNew, Math.max(data.slides.length - 1, 0)));
            const result = data.ai_result;
            let message = _t("%s slides added. Check the content before publishing.", result.slides);
            if (result.require_pass) {
                message += " " + _t("Learners now need to pass the final exam to complete the course.");
            }
            this.notification.add(message, { type: "success", title: _t("Course generated") });
            if (result.warnings.length) {
                this.notification.add(result.warnings.join("\n"), { type: "warning", sticky: true });
            }
        } catch (error) {
            const message = error?.data?.message || error?.message || String(error);
            this.notification.add(message, { type: "danger", title: _t("The course could not be generated"), sticky: true });
        } finally {
            aiProgress.stop();
        }
    }

    async importPresentation() {
        if (this.state.dirty) {
            await this.save(true);
        }
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "lms.scorm.import.wizard",
            views: [[false, "form"]],
            target: "new",
            context: { default_course_id: this.courseId },
        }, {
            onClose: async () => {
                const data = await this.orm.call("lms.scorm.course", "editor_load", [[this.courseId]]);
                this.state.course = data;
                this.state.slides = data.slides;
                this.state.comments = data.comments;
                this.state.current = Math.min(this.state.current, Math.max(data.slides.length - 1, 0));
                this.state.dirty = false;
                this.undoStack = [];
                this.redoStack = [];
                this.fit();
            },
        });
    }

    async backToCourse() {
        if (this.state.dirty) {
            await this.save(true);
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "lms.scorm.course",
            res_id: this.courseId,
            views: [[false, "form"]],
            target: "current",
        }, { clearBreadcrumbs: false });
    }

    onKeydown(ev) {
        const tag = ev.target.tagName;
        const typing = /INPUT|TEXTAREA|SELECT/.test(tag) || ev.target.isContentEditable;
        const mod = ev.ctrlKey || ev.metaKey;
        if (mod && ev.key.toLowerCase() === "s") {
            ev.preventDefault();
            this.save();
            return;
        }
        if (ev.key === "Escape") {
            if (this.state.editingId) {
                this.commitTextEdit();
            } else if (this.state.commentMode) {
                this.cancelComment();
            } else {
                this.select(null);
            }
            return;
        }
        if (typing || !this.canEdit) {
            return;
        }
        if (mod && ev.key.toLowerCase() === "z") {
            ev.preventDefault();
            if (ev.shiftKey) { this.redo(); } else { this.undo(); }
            return;
        }
        if (mod && ev.key.toLowerCase() === "y") {
            ev.preventDefault();
            this.redo();
            return;
        }
        if (mod && ev.key.toLowerCase() === "a") {
            ev.preventDefault();
            this.selectAll();
            return;
        }
        if (mod && ev.key.toLowerCase() === "v") {
            ev.preventDefault();
            this.paste();
            return;
        }
        const els = this.selectedEls;
        if (!els.length) {
            return;
        }
        if (mod && ev.key.toLowerCase() === "d") {
            ev.preventDefault();
            this.duplicateSelected();
        } else if (mod && ev.key.toLowerCase() === "c") {
            this.copySelected();
        } else if (ev.key === "Delete" || ev.key === "Backspace") {
            ev.preventDefault();
            this.deleteSelected();
        } else if (ev.key.startsWith("Arrow")) {
            ev.preventDefault();
            this.snapshot();
            const step = ev.shiftKey ? 10 : 1;
            for (const el of els) {
                if (ev.key === "ArrowLeft") { el.x -= step; }
                if (ev.key === "ArrowRight") { el.x += step; }
                if (ev.key === "ArrowUp") { el.y -= step; }
                if (ev.key === "ArrowDown") { el.y += step; }
            }
            this.markDirty();
        } else if (ev.key === "Enter" && els.length === 1 && ["text", "button"].includes(els[0].type)) {
            ev.preventDefault();
            this.startTextEdit(els[0]);
        }
    }
}

registry.category("actions").add("lms_scorm_authoring.editor", ScormEditor);
