import {
    Component,
    onMounted,
    onPatched,
    onWillStart,
    onWillUnmount,
    useRef,
    useState,
} from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { loadBundle, loadCSS, loadJS } from "@web/core/assets";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { FormViewDialog } from "@web/views/view_dialogs/form_view_dialog";
import { Layout } from "@web/search/layout";
import { DashboardWidgetCard } from "./widget_card";

const GRIDSTACK_JS = "/custom_dashboard/static/lib/gridstack/gridstack-all.js";
const GRIDSTACK_CSS = "/custom_dashboard/static/lib/gridstack/gridstack.min.css";
const COLUMNS = 12;
const SAVE_DELAY = 500;

/**
 * Client action showing one dashboard on a gridstack.js grid.
 *
 * View mode is a static grid. Managers can switch to edit mode to drag
 * widgets in from the palette, move, resize, configure, duplicate and
 * remove them. Layout changes are saved automatically.
 */
export class CustomDashboardAction extends Component {
    static template = "custom_dashboard.DashboardAction";
    static components = { Layout, DashboardWidgetCard };
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
        this.refreshTimer = null;
        this.paletteReady = false;

        const action = this.props.action || {};
        this.dashboardId = action.params?.dashboard_id || action.context?.active_id || false;

        this.state = useState({
            dashboard: null,
            widgets: [],
            data: {},
            editing: false,
        });

        onWillStart(async () => {
            await Promise.all([
                loadJS(GRIDSTACK_JS),
                loadCSS(GRIDSTACK_CSS),
                loadBundle("web.chartjs_lib"),
                this.loadDashboard(),
            ]);
        });

        onMounted(() => {
            this.initGrid();
            this.loadData();
            this.startAutoRefresh();
        });

        onPatched(() => {
            this.syncGridItems();
            this.setupPalette();
        });

        onWillUnmount(() => {
            this.flushSave();
            clearInterval(this.refreshTimer);
            if (this.grid) {
                this.grid.destroy(false);
                this.grid = null;
            }
        });
    }

    // ------------------------------------------------------------------
    // Getters
    // ------------------------------------------------------------------
    get paletteGroups() {
        const groups = [];
        const byName = {};
        for (const item of this.state.dashboard?.palette || []) {
            if (!byName[item.category]) {
                byName[item.category] = { name: item.category, items: [] };
                groups.push(byName[item.category]);
            }
            byName[item.category].items.push(item);
        }
        return groups;
    }

    widgetData(widget) {
        return this.state.data[widget.id];
    }

    // ------------------------------------------------------------------
    // Data
    // ------------------------------------------------------------------
    async loadDashboard() {
        if (!this.dashboardId) {
            return;
        }
        const dashboard = await this.orm.call("custom.dashboard", "get_dashboard", [[this.dashboardId]]);
        this.state.dashboard = dashboard;
        this.state.widgets = dashboard.widgets;
    }

    async loadData(widgetIds = null) {
        const ids = widgetIds || this.state.widgets.filter((w) => w.data_mode !== "content").map((w) => w.id);
        if (!ids.length) {
            return;
        }
        for (const id of ids) {
            delete this.state.data[id];
        }
        const result = await this.orm.call("custom.dashboard.widget", "get_widget_data", [ids]);
        for (const [id, data] of Object.entries(result)) {
            this.state.data[id] = data;
        }
    }

    startAutoRefresh() {
        const minutes = this.state.dashboard?.refresh_interval;
        if (minutes > 0) {
            this.refreshTimer = setInterval(() => {
                if (!this.state.editing) {
                    this.loadData();
                }
            }, minutes * 60 * 1000);
        }
    }

    // ------------------------------------------------------------------
    // Grid
    // ------------------------------------------------------------------
    initGrid() {
        if (!this.gridRef.el || !window.GridStack) {
            return;
        }
        this.grid = window.GridStack.init(
            {
                column: COLUMNS,
                cellHeight: 80,
                margin: 6,
                float: false,
                staticGrid: true,
                animate: true,
                acceptWidgets: ".o_cd_palette_item",
                draggable: { handle: ".o_cd_card_header", cancel: "button" },
                resizable: { handles: "se,e,s" },
                columnOpts: { breakpoints: [{ w: 768, c: 1 }] },
            },
            this.gridRef.el
        );
        this.grid.on("change added", () => this.scheduleSave());
        this.grid.on("dropped", (ev, previousNode, newNode) => this.onPaletteDropped(newNode));
    }

    /** Turn widget elements OWL rendered since the last patch into grid items. */
    syncGridItems() {
        if (!this.grid) {
            return;
        }
        for (const el of this.gridRef.el.querySelectorAll(":scope > .grid-stack-item")) {
            if (!el.gridstackNode) {
                this.grid.makeWidget(el);
            }
        }
    }

    setupPalette() {
        const palette = this.paletteRef.el;
        if (!palette || this.paletteReady) {
            return;
        }
        window.GridStack.setupDragIn([...palette.querySelectorAll(".o_cd_palette_item")], {
            appendTo: "body",
            helper: "clone",
        });
        this.paletteReady = true;
    }

    scheduleSave() {
        if (!this.state.editing || !this.grid || this.grid.getColumn() !== COLUMNS) {
            // Never save the single-column phone layout over the real one.
            return;
        }
        clearTimeout(this.saveTimer);
        this.saveTimer = setTimeout(() => this.saveLayout(), SAVE_DELAY);
    }

    flushSave() {
        if (this.saveTimer) {
            clearTimeout(this.saveTimer);
            this.saveTimer = null;
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
            .map((node) => ({
                id: parseInt(node.el.dataset.widgetId),
                x: node.x,
                y: node.y,
                w: node.w,
                h: node.h,
            }));
        if (items.length) {
            await this.orm.call("custom.dashboard", "save_layout", [[this.dashboardId], items]);
        }
    }

    // ------------------------------------------------------------------
    // Handlers
    // ------------------------------------------------------------------
    onToggleEdit() {
        const editing = !this.state.editing;
        if (!editing) {
            this.flushSave();
        }
        this.state.editing = editing;
        this.paletteReady = false;
        this.grid?.setStatic(!editing);
    }

    onRefresh() {
        this.loadData();
    }

    onOpenSettings() {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "custom.dashboard",
            res_id: this.dashboardId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    onOpenDashboards() {
        this.action.doAction("custom_dashboard.action_custom_dashboard");
    }

    async onPaletteClick(item) {
        // Clicking adds the widget at the bottom; gridstack finds the spot.
        const y = this.grid ? this.grid.getRow() : 0;
        await this.addWidget(item.code, { x: 0, y, w: item.w, h: item.h });
    }

    async onPaletteDropped(node) {
        const type = node.el?.dataset.type;
        const layout = { x: node.x, y: node.y, w: node.w, h: node.h };
        // Swap gridstack's clone for a widget rendered by OWL.
        this.grid.removeWidget(node.el, true, false);
        if (type) {
            await this.addWidget(type, layout);
        }
    }

    async addWidget(type, { x, y, w, h }) {
        const widget = await this.orm.call("custom.dashboard", "add_widget", [[this.dashboardId], type], {
            x,
            y,
            w,
            h,
        });
        this.state.widgets.push(widget);
        await this.loadData([widget.id]);
        this.onEditWidget(widget);
    }

    onEditWidget(widget) {
        this.dialog.add(FormViewDialog, {
            resModel: "custom.dashboard.widget",
            resId: widget.id,
            title: _t("Configure Widget"),
            size: "lg",
            onRecordSaved: async () => {
                await this.reloadWidget(widget.id);
            },
        });
    }

    async reloadWidget(widgetId) {
        const [config] = await this.orm.call("custom.dashboard.widget", "get_config", [[widgetId]]);
        const index = this.state.widgets.findIndex((w) => w.id === widgetId);
        if (index >= 0 && config) {
            // Keep the position gridstack already has for this element.
            const current = this.state.widgets[index];
            this.state.widgets[index] = { ...config, x: current.x, y: current.y, w: current.w, h: current.h };
        }
        await this.loadData([widgetId]);
    }

    async onDuplicateWidget(widget) {
        await this.saveLayout();
        const copy = await this.orm.call("custom.dashboard.widget", "duplicate_widget", [[widget.id]]);
        this.state.widgets.push(copy);
        await this.loadData([copy.id]);
    }

    onRemoveWidget(widget) {
        this.dialog.add(ConfirmationDialog, {
            title: _t("Remove widget"),
            body: _t('Remove "%s" from this dashboard?', widget.name),
            confirmLabel: _t("Remove"),
            confirm: async () => {
                await this.orm.call("custom.dashboard.widget", "remove_widget", [[widget.id]]);
                const el = this.gridRef.el.querySelector(`.grid-stack-item[data-widget-id="${widget.id}"]`);
                if (el && this.grid) {
                    this.grid.removeWidget(el, false);
                }
                this.state.widgets = this.state.widgets.filter((w) => w.id !== widget.id);
                delete this.state.data[widget.id];
                this.scheduleSave();
            },
            cancel: () => {},
        });
    }
}

registry.category("actions").add("custom_dashboard.dashboard", CustomDashboardAction);
