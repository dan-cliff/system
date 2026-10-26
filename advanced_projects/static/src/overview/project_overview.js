import { Component, markup, onMounted, onPatched, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";
import { loadCSS, loadJS } from "@web/core/assets";
import { _t } from "@web/core/l10n/translation";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { FormViewDialog } from "@web/views/view_dialogs/form_view_dialog";
import { TaskList } from "../components/task_list";

const GRIDSTACK_JS = "/advanced_projects/static/lib/gridstack/gridstack-all.js";
const GRIDSTACK_CSS = "/advanced_projects/static/lib/gridstack/gridstack.min.css";
const COLUMNS = 12;
const CELL_HEIGHT = 70;
const SAVE_DELAY = 500;

/**
 * A project's Overview: a header with the project's key facts and links to
 * its Tasks, Gantt chart, Updates and Team, then its widgets on a 12-column
 * grid (gridstack.js, like Custom Dashboards). In Customize mode widgets are
 * dragged in from the palette (or clicked to add them at the bottom), moved
 * by their header, resized from their edges and corner, configured and
 * removed; the layout is saved per project as it changes.
 */
export class ProjectOverview extends Component {
    static template = "advanced_projects.ProjectOverview";
    static components = { Layout, TaskList };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.gridRef = useRef("grid");
        this.paletteRef = useRef("palette");
        this.grid = null;
        this.saveTimer = null;
        this.paletteReady = false;
        this.display = { controlPanel: {} };
        this.projectId =
            this.props.action.params?.project_id || this.props.action.context?.active_id || false;
        this.state = useState({
            data: null,
            editing: false,
        });
        onWillStart(() => Promise.all([loadJS(GRIDSTACK_JS), loadCSS(GRIDSTACK_CSS), this.load()]));
        onMounted(() => this.initGrid());
        onPatched(() => {
            this.initGrid();
            this.syncGridItems();
            this.setupPalette();
        });
        onWillUnmount(() => {
            this.flushSave();
            this.grid?.destroy(false);
            this.grid = null;
        });
    }

    async load() {
        if (!this.projectId) {
            return;
        }
        this.state.data = await this.orm.call("advanced.project", "get_overview_data", [[this.projectId]]);
    }

    get project() {
        return this.state.data?.project;
    }

    get widgets() {
        return this.state.data?.widgets || [];
    }

    // ------------------------------------------------------------------
    // Navigation
    // ------------------------------------------------------------------

    async openProjectAction(method, args = []) {
        const action = await this.orm.call("advanced.project", method, [[this.projectId], ...args]);
        await this.action.doAction(action);
    }

    openTasks(viewType = "kanban") {
        return this.openProjectAction("action_open_tasks", [viewType]);
    }

    openFilteredTasks(taskFilter, days = 14) {
        return this.openProjectAction("action_open_tasks_filtered", [taskFilter, days]);
    }

    openRecord(resModel, resId) {
        return this.action.doAction({
            type: "ir.actions.act_window",
            res_model: resModel,
            res_id: resId,
            views: [[false, "form"]],
        });
    }

    async invite() {
        const action = await this.orm.call("advanced.project", "action_invite", [[this.projectId]]);
        await this.action.doAction(action, { onClose: () => this.load() });
    }

    // ------------------------------------------------------------------
    // Customize
    // ------------------------------------------------------------------

    toggleEditing() {
        const editing = !this.state.editing;
        if (!editing) {
            this.flushSave();
        }
        this.state.editing = editing;
        this.paletteReady = false;
        this.grid?.setStatic(!editing);
    }

    async addWidget(item, layout = {}) {
        const { x = null, y = null, w = item.w, h = item.h } = layout;
        await this.saveLayout();
        await this.orm.call("advanced.project", "overview_add_widget", [
            [this.projectId],
            item.type,
            item.task_filter || false,
            x,
            y,
            w,
            h,
        ]);
        await this.load();
    }

    configure(widget) {
        this.dialog.add(FormViewDialog, {
            resModel: "advanced.project.overview.widget",
            resId: widget.id,
            title: _t("Configure “%s”", widget.title),
            onRecordSaved: () => this.refreshWidget(widget.id),
        });
    }

    async refreshWidget(widgetId) {
        const [values] = await this.orm.call("advanced.project.overview.widget", "get_widget_values", [[widgetId]]);
        const index = this.state.data.widgets.findIndex((w) => w.id === widgetId);
        if (index >= 0 && values) {
            // keep the place gridstack already has for it
            const { x, y, w, h } = this.state.data.widgets[index];
            this.state.data.widgets[index] = { ...values, x, y, w, h };
        }
    }

    remove(widget) {
        this.dialog.add(ConfirmationDialog, {
            title: _t("Remove Widget"),
            body: _t("Remove “%s” from the Overview?", widget.title),
            confirmLabel: _t("Remove"),
            confirm: async () => {
                await this.orm.unlink("advanced.project.overview.widget", [widget.id]);
                const el = this.gridRef.el?.querySelector(`.grid-stack-item[data-widget-id="${widget.id}"]`);
                if (el && this.grid) {
                    this.grid.removeWidget(el, false);
                }
                this.state.data.widgets = this.state.data.widgets.filter((w) => w.id !== widget.id);
                this.scheduleSave();
            },
            cancel: () => {},
        });
    }

    resetLayout() {
        this.dialog.add(ConfirmationDialog, {
            title: _t("Reset Overview"),
            body: _t("Replace this Overview's widgets with the default layout?"),
            confirmLabel: _t("Reset"),
            confirm: async () => {
                clearTimeout(this.saveTimer);
                this.saveTimer = null;
                await this.orm.call("advanced.project", "overview_reset", [[this.projectId]]);
                this.grid?.removeAll(false);
                await this.load();
            },
            cancel: () => {},
        });
    }

    // ------------------------------------------------------------------
    // Grid (gridstack.js)
    // ------------------------------------------------------------------

    initGrid() {
        if (this.grid || !this.gridRef.el || !window.GridStack) {
            return;
        }
        this.grid = window.GridStack.init(
            {
                column: COLUMNS,
                cellHeight: CELL_HEIGHT,
                margin: 8,
                float: false,
                staticGrid: !this.state.editing,
                animate: true,
                acceptWidgets: ".o_adv_palette_item",
                draggable: { handle: ".o_adv_widget_header", cancel: "button" },
                resizable: { handles: "se,e,s,w,sw" },
                // the resize grips always show while customizing (not only on hover)
                alwaysShowResizeHandle: true,
                columnOpts: { breakpoints: [{ w: 768, c: 1 }] },
            },
            this.gridRef.el
        );
        this.grid.on("change added", () => this.scheduleSave());
        this.grid.on("dropped", (ev, previousNode, newNode) => this.onPaletteDropped(newNode));
    }

    /**
     * Turn widget elements OWL rendered since the last patch into grid items,
     * and drop anything else gridstack left in the grid (e.g. a palette clone).
     */
    syncGridItems() {
        if (!this.grid) {
            return;
        }
        for (const el of this.gridRef.el.querySelectorAll(":scope > .grid-stack-item")) {
            if (!el.dataset.widgetId) {
                this.grid.removeWidget(el, false, false);
                el.remove();
            } else if (!el.gridstackNode) {
                this.grid.makeWidget(el);
            }
        }
    }

    setupPalette() {
        const palette = this.paletteRef.el;
        if (!palette || this.paletteReady || !window.GridStack) {
            return;
        }
        window.GridStack.setupDragIn([...palette.querySelectorAll(".o_adv_palette_item")], {
            appendTo: "body",
            helper: "clone",
        });
        this.paletteReady = true;
    }

    scheduleSave() {
        if (!this.state.editing || !this.grid || this.grid.getColumn() !== COLUMNS) {
            // never save the single-column phone layout over the real one
            return;
        }
        clearTimeout(this.saveTimer);
        this.saveTimer = setTimeout(() => this.saveLayout(), SAVE_DELAY);
    }

    flushSave() {
        if (this.saveTimer) {
            clearTimeout(this.saveTimer);
            this.saveLayout();
        }
    }

    async saveLayout() {
        this.saveTimer = null;
        if (!this.grid || this.grid.getColumn() !== COLUMNS) {
            return;
        }
        const items = this.grid.engine.nodes
            .filter((node) => node.el?.dataset.widgetId)
            .map((node) => ({ id: parseInt(node.el.dataset.widgetId), x: node.x, y: node.y, w: node.w, h: node.h }));
        if (!items.length) {
            return;
        }
        for (const item of items) {
            const widget = this.widgets.find((w) => w.id === item.id);
            if (widget) {
                Object.assign(widget, { x: item.x, y: item.y, w: item.w, h: item.h });
            }
        }
        await this.orm.call("advanced.project", "overview_save_layout", [[this.projectId], items]);
    }

    /** The size gridstack gives a palette item while it is dragged over the grid. */
    paletteSize(item) {
        return JSON.stringify({ w: item.w, h: item.h });
    }

    onPaletteClick(item) {
        return this.addWidget(item);
    }

    async onPaletteDropped(node) {
        const index = parseInt(node.el?.dataset.paletteIndex);
        const item = this.state.data.widget_types[index];
        // Only the place comes from the drop: gridstack may size the clone from
        // the palette tile (about 2 columns), so the widget keeps its own size.
        const layout = { x: node.x, y: node.y };
        // swap gridstack's clone for a widget rendered by OWL
        this.grid.removeWidget(node.el, true, false);
        node.el?.remove();
        if (item) {
            await this.addWidget(item, layout);
        }
    }

    // ------------------------------------------------------------------
    // Helpers for the templates
    // ------------------------------------------------------------------

    asHtml(html) {
        // sanitized by the server (Html field)
        return markup(html);
    }

    daysLeftLabel(days) {
        if (days === null || days === undefined) {
            return "";
        }
        if (days < 0) {
            return _t("%s days overdue", -days);
        }
        if (days === 0) {
            return _t("Due today");
        }
        return _t("%s days left", days);
    }
}

registry.category("actions").add("advanced_project_overview", ProjectOverview);
