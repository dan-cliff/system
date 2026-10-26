import { Component, markup, onWillStart, onWillUnmount, onWillUpdateProps, useRef, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { TaskList } from "../components/task_list";

const BLOCK_MODEL = "advanced.project.update.block";
const DAY_FILTERS = ["upcoming", "completed"];
// Blocks are laid out on 12 columns.
const COLUMNS = 12;
const MIN_COLUMNS = 3;
const GAP = 12; // px between blocks, as in update_editor.scss

/**
 * The Project Update document editor: text blocks and task widgets
 * (outstanding, upcoming, completed, blocked, ...) dragged in from a palette,
 * reordered by dragging, each task widget with its own filters (phases,
 * assignees, time window, columns). Task lists are live while drafting and
 * frozen when the update is published.
 */
export class UpdateEditor extends Component {
    static template = "advanced_projects.UpdateEditor";
    static components = { TaskList };
    static props = { ...standardWidgetProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.dayFilters = DAY_FILTERS;
        this.state = useState({
            data: null,
            configuring: null,
            dragging: null,
            dropIndex: null,
            busy: false,
            resizing: null,
        });
        this.blocksRef = useRef("blocks");
        onWillUnmount(() => this.stopResize?.());
        onWillStart(() => this.load(this.props));
        onWillUpdateProps((nextProps) => {
            if (nextProps.record.resId !== this.loadedId) {
                return this.load(nextProps);
            }
        });
    }

    get blocks() {
        return this.state.data?.blocks || [];
    }

    blockStyle(block) {
        const width = block.width || COLUMNS;
        return `flex: 0 0 calc((100% + ${GAP}px) * ${width} / ${COLUMNS} - ${GAP}px);`;
    }

    get canEdit() {
        return Boolean(this.state.data?.can_edit) && !this.props.readonly;
    }

    async load(props = this.props) {
        const resId = props.record.resId;
        this.loadedId = resId;
        if (!resId) {
            this.state.data = null;
            return;
        }
        this.state.data = await this.orm.call("advanced.project.update", "get_editor_data", [[resId]]);
    }

    /** New or changed updates are saved first, so blocks have somewhere to go. */
    async ensureSaved() {
        const record = this.props.record;
        if (record.isNew || record.dirty) {
            const saved = await record.save();
            if (!saved) {
                return false;
            }
        }
        if (this.loadedId !== record.resId) {
            await this.load();
        }
        return record.resId;
    }

    async startEditing() {
        await this.ensureSaved();
    }

    // ------------------------------------------------------------------
    // Blocks
    // ------------------------------------------------------------------

    async addBlock(item, index = null) {
        const resId = await this.ensureSaved();
        if (!resId) {
            return;
        }
        const block = await this.orm.call("advanced.project.update", "editor_add_block", [
            [resId],
            item.block_type,
            item.task_filter || false,
            index,
        ]);
        await this.load();
        if (block.block_type === "tasks") {
            this.state.configuring = block.id;
        }
    }

    removeBlock(block) {
        this.dialog.add(ConfirmationDialog, {
            title: _t("Remove Section"),
            body: _t("Remove “%s” from this update?", block.title || _t("this section")),
            confirmLabel: _t("Remove"),
            confirm: async () => {
                await this.orm.unlink(BLOCK_MODEL, [block.id]);
                await this.load();
            },
            cancel: () => {},
        });
    }

    async writeBlock(block, values) {
        await this.orm.write(BLOCK_MODEL, [block.id], values);
        const [fresh] = await this.orm.call(BLOCK_MODEL, "get_editor_values", [[block.id]]);
        const index = this.state.data.blocks.findIndex((b) => b.id === block.id);
        if (index >= 0 && fresh) {
            this.state.data.blocks[index] = fresh;
        }
    }

    onTitleChange(block, ev) {
        const title = ev.target.value;
        if (title !== block.title) {
            this.writeBlock(block, { title });
        }
    }

    onBodyBlur(block, ev) {
        const body = ev.target.innerHTML;
        if (body !== block.body) {
            block.body = body;
            this.orm.write(BLOCK_MODEL, [block.id], { body });
        }
    }

    format(command, value = null) {
        document.execCommand(command, false, value);
    }

    asHtml(html) {
        // sanitized by the server (Html field)
        return markup(html || "");
    }

    toggleConfigure(block) {
        this.state.configuring = this.state.configuring === block.id ? null : block.id;
    }

    setFilter(block, field, value) {
        const values = { [field]: value };
        if (field === "task_filter" && (!block.title || block.title === this.filterLabel(block.task_filter))) {
            // the section was still named after its filter: follow the new one
            values.title = this.filterLabel(value);
        }
        if (field === "task_filter" && !DAY_FILTERS.includes(value)) {
            values.days = 0;
        } else if (field === "task_filter" && !block.days) {
            values.days = 14;
        }
        return this.writeBlock(block, values);
    }

    setNumber(block, field, ev) {
        return this.setFilter(block, field, Math.max(0, parseInt(ev.target.value) || 0));
    }

    toggleMany(block, field, id) {
        const ids = new Set(block[field]);
        if (ids.has(id)) {
            ids.delete(id);
        } else {
            ids.add(id);
        }
        return this.writeBlock(block, { [field]: [[6, 0, [...ids]]] });
    }

    filterLabel(value) {
        return this.state.data.task_filters.find((f) => f.value === value)?.label || value;
    }

    openTask(row) {
        return this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "advanced.project.task",
            res_id: row.id,
            views: [[false, "form"]],
        });
    }

    // ------------------------------------------------------------------
    // Drag and drop (palette items and blocks)
    // ------------------------------------------------------------------

    onPaletteDragStart(ev, item) {
        ev.dataTransfer.effectAllowed = "copy";
        ev.dataTransfer.setData("text/plain", item.label);
        this.state.dragging = { kind: "palette", item };
    }

    onBlockDragStart(ev, block) {
        if (!ev.target.classList?.contains("o_adv_block_grip")) {
            ev.preventDefault();
            return;
        }
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData("text/plain", block.title || "");
        const card = ev.target.closest(".o_adv_block");
        if (card) {
            ev.dataTransfer.setDragImage(card, 20, 20);
        }
        this.state.dragging = { kind: "block", blockId: block.id };
    }

    // ------------------------------------------------------------------
    // Resizing: drag a block's bottom right corner to change its width
    // ------------------------------------------------------------------

    onResizeStart(ev, block) {
        if (!this.canEdit || ev.button !== 0) {
            return;
        }
        ev.preventDefault();
        ev.stopPropagation();
        const container = this.blocksRef.el;
        const card = ev.currentTarget.closest(".o_adv_block");
        if (!container || !card) {
            return;
        }
        const columnWidth = (container.getBoundingClientRect().width + GAP) / COLUMNS;
        const left = card.getBoundingClientRect().left;
        const startWidth = block.width || COLUMNS;
        this.state.resizing = block.id;
        const onMove = (moveEv) => {
            const columns = Math.round((moveEv.clientX - left + GAP) / columnWidth);
            block.width = Math.max(MIN_COLUMNS, Math.min(COLUMNS, columns));
        };
        const stop = () => {
            window.removeEventListener("pointermove", onMove);
            window.removeEventListener("pointerup", stop);
            window.removeEventListener("pointercancel", stop);
            this.stopResize = null;
            this.state.resizing = null;
            if (block.width !== startWidth) {
                this.orm.write(BLOCK_MODEL, [block.id], { width: block.width });
            }
        };
        window.addEventListener("pointermove", onMove);
        window.addEventListener("pointerup", stop);
        window.addEventListener("pointercancel", stop);
        this.stopResize = stop;
    }

    onDragEnd() {
        this.state.dragging = null;
        this.state.dropIndex = null;
    }

    onBlockDragOver(ev, index) {
        if (!this.state.dragging) {
            return;
        }
        ev.preventDefault();
        const rect = ev.currentTarget.getBoundingClientRect();
        const block = this.blocks[index];
        // side-by-side blocks: before or after by the half of the block the pointer is in
        const after = block && (block.width || COLUMNS) < COLUMNS
            ? ev.clientX > rect.left + rect.width / 2
            : ev.clientY > rect.top + rect.height / 2;
        this.state.dropIndex = after ? index + 1 : index;
    }

    onDocumentDragOver(ev) {
        if (!this.state.dragging) {
            return;
        }
        ev.preventDefault();
        // between blocks keep the current drop place; below the last one, drop at the end
        const blocks = ev.currentTarget.querySelectorAll(".o_adv_block");
        const last = blocks[blocks.length - 1];
        if (!last || ev.clientY > last.getBoundingClientRect().bottom) {
            this.state.dropIndex = this.blocks.length;
        }
    }

    async onDrop(ev) {
        ev.preventDefault();
        const dragging = this.state.dragging;
        const index = this.state.dropIndex ?? this.blocks.length;
        this.onDragEnd();
        if (!dragging) {
            return;
        }
        if (dragging.kind === "palette") {
            await this.addBlock(dragging.item, index);
            return;
        }
        const ids = this.blocks.map((b) => b.id);
        const from = ids.indexOf(dragging.blockId);
        ids.splice(from, 1);
        ids.splice(from < index ? index - 1 : index, 0, dragging.blockId);
        await this.orm.call("advanced.project.update", "editor_resequence", [[this.loadedId], ids]);
        await this.load();
    }
}

export const updateEditor = {
    component: UpdateEditor,
};

registry.category("view_widgets").add("advanced_project_update_editor", updateEditor);
