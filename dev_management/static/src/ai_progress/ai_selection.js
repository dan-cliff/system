import { Component, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

import { DevAiPromptDialog, runAiJob } from "./ai_progress";

// Elements that start a new block: a selection containing one spans several paragraphs.
const BLOCK_SELECTOR = "p, li, ul, ol, h1, h2, h3, h4, h5, h6, table, blockquote, pre, div";
const CONTEXT_BEFORE = 2000;
const CONTEXT_AFTER = 1000;

function nodePath(root, node) {
    const path = [];
    while (node && node !== root) {
        path.unshift(Array.prototype.indexOf.call(node.parentNode.childNodes, node));
        node = node.parentNode;
    }
    return node === root ? path : null;
}

function resolvePath(root, path) {
    return path.reduce((node, index) => node && node.childNodes[index], root);
}

/**
 * Select text in one of the form's text fields (rich text, plain text, or the text of a
 * list line such as an acceptance criterion) and a floating AI button appears next to it.
 * The button asks what to do with the selection, sends the selection, the text around it
 * and the instruction to the AI (see dev.ai.mixin `selection_edit`) with the progress
 * overlay, and puts the AI's rework in place of the selection.
 *
 * <widget name="dev_ai_selection" options="{'fields': ['description', 'criterion_ids']}"/>
 */
export class DevAiSelectionAssistant extends Component {
    static template = "dev_management.AiSelectionAssistant";
    static props = {
        ...standardWidgetProps,
        fields: { type: Array, element: String },
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        this.rootRef = useRef("root");
        this.state = useState({ visible: false, top: 0, left: 0 });
        this.target = null;
        this.timer = null;
        this.onSelectionChange = () => {
            clearTimeout(this.timer);
            this.timer = setTimeout(() => this.update(), 120);
        };
        this.hide = () => {
            this.state.visible = false;
        };
        onMounted(() => {
            document.addEventListener("selectionchange", this.onSelectionChange);
            document.addEventListener("select", this.onSelectionChange, true);
            document.addEventListener("keyup", this.onSelectionChange, true);
            document.addEventListener("mouseup", this.onSelectionChange, true);
            window.addEventListener("scroll", this.hide, true);
        });
        onWillUnmount(() => {
            clearTimeout(this.timer);
            document.removeEventListener("selectionchange", this.onSelectionChange);
            document.removeEventListener("select", this.onSelectionChange, true);
            document.removeEventListener("keyup", this.onSelectionChange, true);
            document.removeEventListener("mouseup", this.onSelectionChange, true);
            window.removeEventListener("scroll", this.hide, true);
        });
    }

    get formEl() {
        return this.rootRef.el?.closest(".o_form_view, .o_form_renderer");
    }

    /** The field (and, for a list line, its text field) a DOM element belongs to, if it's enabled. */
    fieldOf(el) {
        const widget = el.closest(".o_field_widget[name]");
        if (!widget) {
            return null;
        }
        const outer = widget.parentElement?.closest(".o_field_widget[name]");
        const field = outer ? outer.getAttribute("name") : widget.getAttribute("name");
        const subfield = outer ? widget.getAttribute("name") : null;
        return this.props.fields.includes(field) ? { field, subfield } : null;
    }

    update() {
        const form = this.formEl;
        if (!form || this.dialogOpen) {
            return this.hide();
        }
        const active = document.activeElement;
        let target = null;
        if (active && form.contains(active) && (active.tagName === "TEXTAREA" || active.type === "text")) {
            const { selectionStart: start, selectionEnd: end, value } = active;
            if (end > start && value.slice(start, end).trim()) {
                const field = this.fieldOf(active);
                if (field) {
                    target = { kind: "text", el: active, start, end, ...field };
                    const box = active.getBoundingClientRect();
                    target.anchor = { top: box.top, bottom: box.bottom, right: box.right - 20 };
                }
            }
        } else {
            const selection = document.getSelection();
            if (selection && selection.rangeCount && !selection.isCollapsed) {
                const range = selection.getRangeAt(0);
                const container = range.commonAncestorContainer;
                const element = container.nodeType === Node.ELEMENT_NODE ? container : container.parentElement;
                const editable = element?.closest(".odoo-editor-editable");
                if (editable && form.contains(editable) && range.toString().trim()) {
                    const field = this.fieldOf(editable);
                    if (field && !field.subfield) {
                        target = { kind: "html", editable, range: range.cloneRange(), ...field };
                        // Anchor at the end of the selection: the editor's own toolbar sits above it.
                        const lines = range.getClientRects();
                        const last = lines.length ? lines[lines.length - 1] : range.getBoundingClientRect();
                        target.anchor = { top: last.top, bottom: last.bottom, right: last.right };
                    }
                }
            }
        }
        if (!target) {
            return this.hide();
        }
        this.target = target;
        const { top, bottom, right } = target.anchor;
        const size = 34;
        const below = bottom + 6;
        this.state.top = below + size < window.innerHeight ? below : Math.max(4, top - size - 6);
        this.state.left = Math.max(4, Math.min(right + 4, window.innerWidth - size - 4));
        this.state.visible = true;
    }

    /** Freeze the selection now: the editor or the form may change before the AI answers. */
    snapshot() {
        const target = this.target;
        if (target.kind === "text") {
            const value = target.el.value;
            return {
                kind: "text",
                field: target.field,
                subfield: target.subfield,
                selectedText: value.slice(target.start, target.end),
                kwargs: {
                    field: target.field,
                    subfield: target.subfield,
                    selected_text: value.slice(target.start, target.end),
                    before: value.slice(Math.max(0, target.start - CONTEXT_BEFORE), target.start),
                    after: value.slice(target.end, target.end + CONTEXT_AFTER),
                    old_value: value,
                    start: target.start,
                    end: target.end,
                },
            };
        }
        const { editable, range } = target;
        const startPath = nodePath(editable, range.startContainer);
        const endPath = nodePath(editable, range.endContainer);
        if (!startPath || !endPath) {
            return null;
        }
        // Work on a copy of the editor's content, with the selection mapped onto it.
        const clone = editable.cloneNode(true);
        const cloneRange = document.createRange();
        cloneRange.setStart(resolvePath(clone, startPath), range.startOffset);
        cloneRange.setEnd(resolvePath(clone, endPath), range.endOffset);
        const fragment = range.cloneContents();
        const holder = document.createElement("div");
        holder.appendChild(fragment.cloneNode(true));
        const beforeRange = document.createRange();
        beforeRange.setStart(editable, 0);
        beforeRange.setEnd(range.startContainer, range.startOffset);
        const afterRange = document.createRange();
        afterRange.setStart(range.endContainer, range.endOffset);
        afterRange.setEnd(editable, editable.childNodes.length);
        const selectedText = range.toString();
        return {
            kind: "html",
            field: target.field,
            clone,
            cloneRange,
            selectedText,
            kwargs: {
                field: target.field,
                selected_text: selectedText,
                selected_html: holder.innerHTML,
                before: beforeRange.toString().slice(-CONTEXT_BEFORE),
                after: afterRange.toString().slice(0, CONTEXT_AFTER),
                is_html: true,
                multi_block: Boolean(holder.querySelector(BLOCK_SELECTOR)),
            },
        };
    }

    onButtonMousedown(ev) {
        // Keep the text selected while the button is clicked.
        ev.preventDefault();
    }

    open() {
        const snapshot = this.target && this.snapshot();
        this.hide();
        if (!snapshot) {
            return;
        }
        this.dialogOpen = true;
        this.dialog.add(
            DevAiPromptDialog,
            {
                title: _t("Rework the selected text with AI"),
                help: _t("Say what the AI should do with the selected text: rewrite, expand, shorten, correct, make it more technical..."),
                placeholder: _t("e.g. Make this more specific and add the error cases"),
                selectedText: snapshot.selectedText.length > 600
                    ? `${snapshot.selectedText.slice(0, 600)}…`
                    : snapshot.selectedText,
                onSubmit: (prompt) => this.run(snapshot, prompt),
            },
            { onClose: () => (this.dialogOpen = false) }
        );
    }

    run(snapshot, prompt) {
        const record = this.props.record;
        return runAiJob({
            record,
            orm: this.orm,
            notification: this.notification,
            job: "selection_edit",
            kwargs: { ...snapshot.kwargs, prompt },
            title: _t("Reworking the selected text with AI"),
            apply: async (result) => {
                if (snapshot.kind !== "html") {
                    // The server wrote the new text: show it.
                    return record.load();
                }
                const { clone, cloneRange } = snapshot;
                const replacement = cloneRange.createContextualFragment(result.html || "");
                cloneRange.deleteContents();
                cloneRange.insertNode(replacement);
                for (const el of clone.querySelectorAll("[placeholder], .o-we-hint")) {
                    el.removeAttribute("placeholder");
                    el.classList.remove("o-we-hint");
                }
                await record.update({ [snapshot.field]: clone.innerHTML });
                await record.save();
            },
        });
    }
}

registry.category("view_widgets").add("dev_ai_selection", {
    component: DevAiSelectionAssistant,
    extractProps: ({ options }) => ({ fields: options.fields || [] }),
});
