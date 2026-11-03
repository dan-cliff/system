import { Component, markup, onWillStart, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

/** Lists the text blocks: search, filter by category, preview, then add or replace. */
export class TextBlockDialog extends Component {
    static template = "product_text_blocks.TextBlockDialog";
    static components = { Dialog };
    static props = { close: Function, blocks: Array, plainText: Boolean, hasContent: Boolean, onPick: Function };

    setup() {
        this.state = useState({ search: "", categoryId: false, selectedId: this.props.blocks[0]?.id || false });
        this.categories = [];
        const seen = new Set();
        for (const block of this.props.blocks) {
            if (block.category_id && !seen.has(block.category_id)) {
                seen.add(block.category_id);
                this.categories.push({ id: block.category_id, name: block.category });
            }
        }
    }

    get filtered() {
        const term = this.state.search.trim().toLowerCase();
        return this.props.blocks.filter(
            (block) =>
                (!this.state.categoryId || block.category_id === this.state.categoryId) &&
                (!term || `${block.name} ${block.preview}`.toLowerCase().includes(term))
        );
    }

    get selected() {
        return this.filtered.find((block) => block.id === this.state.selectedId) || this.filtered[0] || false;
    }

    previewHtml(block) {
        return markup(block.content || "");
    }

    pick(mode) {
        const block = this.selected;
        if (!block) {
            return;
        }
        this.props.close();
        this.props.onPick(block.id, mode);
    }
}

/**
 * "Insert Text Block" button above a description field:
 * <widget name="text_block_insert" options="{'field': 'description_ecommerce'}"/>
 * Rich text fields get the block's formatting; plain text fields its text.
 */
export class TextBlockInsert extends Component {
    static template = "product_text_blocks.InsertButton";
    static props = { ...standardWidgetProps, field: { type: String } };

    setup() {
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
    }

    get fieldInfo() {
        return this.props.record.fields[this.props.field];
    }

    get plainText() {
        return this.fieldInfo?.type !== "html";
    }

    get currentValue() {
        return String(this.props.record.data[this.props.field] || "");
    }

    get hasContent() {
        const value = this.currentValue;
        return Boolean(this.plainText ? value.trim() : value.replace(/<[^>]*>/g, "").trim());
    }

    async onClick() {
        const company = this.props.record.data.company_id;
        const blocks = await this.orm.call("text.block", "text_block_list", [], {
            company_id: (company && company.id) || false,
        });
        if (!blocks.length) {
            this.notification.add(
                _t("There are no text blocks yet. Add them in Inventory › Configuration › Products › Text Blocks."),
                { type: "warning" }
            );
            return;
        }
        this.dialog.add(TextBlockDialog, {
            blocks,
            plainText: this.plainText,
            hasContent: this.hasContent,
            onPick: (blockId, mode) => this.insert(blockId, mode),
        });
    }

    async insert(blockId, mode) {
        const value = await this.orm.call("text.block", "text_block_value", [[blockId]], {
            as_text: this.plainText,
        });
        let result;
        if (mode === "replace" || !this.hasContent) {
            result = value;
        } else if (this.plainText) {
            result = `${this.currentValue.replace(/\s+$/, "")}\n\n${value}`;
        } else {
            result = `${this.currentValue}${value}`;
        }
        await this.props.record.update({ [this.props.field]: this.plainText ? result : markup(result) });
    }
}

registry.category("view_widgets").add("text_block_insert", {
    component: TextBlockInsert,
    extractProps: ({ options }) => ({ field: options.field }),
});
