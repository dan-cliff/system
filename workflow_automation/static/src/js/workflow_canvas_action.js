/** @odoo-module **/

import { Component, useState, useRef, onMounted, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const NODE_WIDTH = 200;
const NODE_HEIGHT = 80;

const STEP_TYPE_CONFIG = {
    create_record:      { icon: "fa-plus-circle",    color: "#3498DB", label: "Create Record" },
    update_record:      { icon: "fa-pencil",         color: "#2980B9", label: "Update Record" },
    delete_record:      { icon: "fa-trash",          color: "#C0392B", label: "Delete Record" },
    add_activity:       { icon: "fa-calendar-plus-o",color: "#E67E22", label: "Add Activity" },
    post_message:       { icon: "fa-comment",        color: "#27AE60", label: "Post Message" },
    send_notification:  { icon: "fa-bell",           color: "#16A085", label: "Send Notification" },
    send_email:         { icon: "fa-envelope",       color: "#2471A3", label: "Send Email" },
    generate_report:    { icon: "fa-file-text-o",   color: "#117A65", label: "Generate Report" },
    python_code:        { icon: "fa-code",           color: "#8E44AD", label: "Python Code" },
    api_call:           { icon: "fa-exchange",       color: "#0D6EFD", label: "API Call" },
    random_generator:   { icon: "fa-random",         color: "#9B59B6", label: "Random Generator" },
    conditional_branch: { icon: "fa-code-fork",      color: "#D35400", label: "Condition Branch" },
    stop_workflow:      { icon: "fa-stop-circle",    color: "#E74C3C", label: "Stop Workflow" },
    trigger_workflow:   { icon: "fa-bolt",           color: "#1ABC9C", label: "Trigger Workflow" },
};

const STEP_TYPES = Object.entries(STEP_TYPE_CONFIG).map(([value, cfg]) => ({ value, ...cfg }));

export class WorkflowCanvasAction extends Component {
    static template = "workflow_automation.WorkflowCanvasAction";
    static props = ["action", "actionService?", "*"];

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.notification = useService("notification");
        this.canvasOuter = useRef("canvasOuter");
        this.stepTypes = STEP_TYPES;

        // params is the canonical place for client-action data; context is the fallback.
        // Always coerce to Number — JSON can sometimes deliver strings.
        const rawId =
            this.props.action.params?.workflow_id ??
            this.props.action.context?.workflow_id;
        this.workflowId = rawId ? Number(rawId) : null;

        this.state = useState({
            workflowName: "",
            steps: [],
            connections: [],
            selectedStepId: null,
            selectedConnectionId: null,
            editingConnection: null,
            loading: true,
            saving: false,
            showAddMenu: false,
            zoom: 1.0,
            panX: 80,
            panY: 80,
            // Internal interaction flags (not for rendering)
            _dragging: null,
            _panning: null,
            _connecting: null,
        });

        this._onMousemove = this._globalMousemove.bind(this);
        this._onMouseup = this._globalMouseup.bind(this);

        onMounted(async () => {
            await this.loadWorkflow();
        });

        onWillUnmount(() => {
            document.removeEventListener("mousemove", this._onMousemove);
            document.removeEventListener("mouseup", this._onMouseup);
        });
    }

    // ------------------------------------------------------------------ //
    // Data loading                                                         //
    // ------------------------------------------------------------------ //

    async loadWorkflow() {
        this.state.loading = true;
        if (!this.workflowId) {
            this.state.loading = false;
            this.notification.add(
                "No workflow ID found. Please reopen the canvas from a Workflow Automation record.",
                { type: "danger", sticky: true }
            );
            return;
        }
        try {
            const [wf] = await this.orm.read(
                "wf.automation",
                [this.workflowId],
                ["name", "canvas_zoom", "canvas_pan_x", "canvas_pan_y"]
            );
            this.state.workflowName = wf.name;
            if (wf.canvas_zoom) {
                this.state.zoom = wf.canvas_zoom;
                this.state.panX = wf.canvas_pan_x || 80;
                this.state.panY = wf.canvas_pan_y || 80;
            }

            const steps = await this.orm.searchRead(
                "wf.step",
                [["workflow_id", "=", this.workflowId]],
                ["id", "name", "step_type", "canvas_x", "canvas_y", "condition_type",
                 "active", "sequence", "api_method", "api_url_slug"],
                { context: { active_test: false } }
            );

            const rawConns = await this.orm.searchRead(
                "wf.step.connection",
                [["workflow_id", "=", this.workflowId]],
                ["id", "from_step_id", "to_step_id", "label", "condition_type",
                 "condition_domain", "condition_expression", "sequence"]
            );

            // Normalise many2one tuples [id, name] → id
            const connections = rawConns.map((c) => ({
                ...c,
                from_step_id: Array.isArray(c.from_step_id) ? c.from_step_id[0] : c.from_step_id,
                to_step_id: Array.isArray(c.to_step_id) ? c.to_step_id[0] : c.to_step_id,
            }));

            // Auto-layout when every step sits at the default (100, 100)
            if (steps.length > 1 && steps.every((s) => s.canvas_x === 100 && s.canvas_y === 100)) {
                this._autoLayout(steps, connections);
                this._savePositions(steps);
            }

            this.state.steps = steps;
            this.state.connections = connections;
        } finally {
            this.state.loading = false;
        }
    }

    _autoLayout(steps, connections) {
        const COLS = Math.min(4, steps.length);
        const gapX = NODE_WIDTH + 80;
        const gapY = NODE_HEIGHT + 60;
        steps.sort((a, b) => a.sequence - b.sequence || a.id - b.id);
        steps.forEach((s, i) => {
            s.canvas_x = 80 + (i % COLS) * gapX;
            s.canvas_y = 80 + Math.floor(i / COLS) * gapY;
        });
    }

    async _savePositions(steps) {
        for (const s of steps) {
            await this.orm.write("wf.step", [s.id], { canvas_x: s.canvas_x, canvas_y: s.canvas_y });
        }
    }

    async _savePanZoom() {
        await this.orm.write("wf.automation", [this.workflowId], {
            canvas_zoom: this.state.zoom,
            canvas_pan_x: this.state.panX,
            canvas_pan_y: this.state.panY,
        });
    }

    // ------------------------------------------------------------------ //
    // Computed helpers                                                     //
    // ------------------------------------------------------------------ //

    get viewportStyle() {
        return `transform: translate(${this.state.panX}px,${this.state.panY}px) scale(${this.state.zoom}); transform-origin: 0 0;`;
    }

    getStepConfig(type) {
        return STEP_TYPE_CONFIG[type] || { icon: "fa-cog", color: "#95A5A6", label: type };
    }

    nodeStyle(step) {
        return `left:${step.canvas_x}px;top:${step.canvas_y}px;width:${NODE_WIDTH}px;`;
    }

    nodeHeaderStyle(step) {
        return `background:${this.getStepConfig(step.step_type).color};`;
    }

    isEntryStep(step) {
        return !this.state.connections.some((c) => c.to_step_id === step.id);
    }

    getSelectedStep() {
        return this.state.steps.find((s) => s.id === this.state.selectedStepId) || null;
    }

    getSelectedConnection() {
        return (
            this.state.editingConnection ||
            this.state.connections.find((c) => c.id === this.state.selectedConnectionId) ||
            null
        );
    }

    connectionPath(conn) {
        const from = this.state.steps.find((s) => s.id === conn.from_step_id);
        const to = this.state.steps.find((s) => s.id === conn.to_step_id);
        if (!from || !to) return null;
        const x1 = from.canvas_x + NODE_WIDTH;
        const y1 = from.canvas_y + NODE_HEIGHT / 2;
        const x2 = to.canvas_x;
        const y2 = to.canvas_y + NODE_HEIGHT / 2;
        const dx = Math.max(80, Math.abs(x2 - x1) / 2);
        return {
            d: `M ${x1} ${y1} C ${x1 + dx} ${y1} ${x2 - dx} ${y2} ${x2} ${y2}`,
            labelX: (x1 + x2) / 2,
            labelY: Math.min(y1, y2) - 10,
        };
    }

    ghostPath() {
        const c = this.state._connecting;
        if (!c) return "";
        const from = this.state.steps.find((s) => s.id === c.fromStepId);
        if (!from) return "";
        const x1 = from.canvas_x + NODE_WIDTH;
        const y1 = from.canvas_y + NODE_HEIGHT / 2;
        const dx = Math.max(80, Math.abs(c.cursorX - x1) / 2);
        return `M ${x1} ${y1} C ${x1 + dx} ${y1} ${c.cursorX - dx} ${c.cursorY} ${c.cursorX} ${c.cursorY}`;
    }

    _screenToWorld(clientX, clientY) {
        const el = this.canvasOuter.el;
        if (!el) return { x: 0, y: 0 };
        const r = el.getBoundingClientRect();
        return {
            x: (clientX - r.left - this.state.panX) / this.state.zoom,
            y: (clientY - r.top - this.state.panY) / this.state.zoom,
        };
    }

    // ------------------------------------------------------------------ //
    // Canvas mouse events                                                  //
    // ------------------------------------------------------------------ //

    onCanvasMousedown(ev) {
        if (ev.button !== 0) return;
        const target = ev.target;
        const onEmpty =
            target === this.canvasOuter.el ||
            target.classList.contains("wf-viewport") ||
            target.classList.contains("wf-svg");
        if (!onEmpty) return;
        this.state.selectedStepId = null;
        this.state.selectedConnectionId = null;
        this.state.editingConnection = null;
        this.state.showAddMenu = false;
        this.state._panning = {
            sx: ev.clientX,
            sy: ev.clientY,
            px: this.state.panX,
            py: this.state.panY,
        };
        document.addEventListener("mousemove", this._onMousemove);
        document.addEventListener("mouseup", this._onMouseup);
    }

    onNodeMousedown(ev, step) {
        if (ev.button !== 0) return;
        ev.stopPropagation();
        this.state.selectedStepId = step.id;
        this.state.selectedConnectionId = null;
        this.state.editingConnection = null;
        this.state.showAddMenu = false;
        this.state._dragging = {
            stepId: step.id,
            sx: ev.clientX,
            sy: ev.clientY,
            ox: step.canvas_x,
            oy: step.canvas_y,
        };
        document.addEventListener("mousemove", this._onMousemove);
        document.addEventListener("mouseup", this._onMouseup);
    }

    onOutputPortMousedown(ev, stepId) {
        if (ev.button !== 0) return;
        ev.stopPropagation();
        const pos = this._screenToWorld(ev.clientX, ev.clientY);
        this.state._connecting = { fromStepId: stepId, cursorX: pos.x, cursorY: pos.y };
        document.addEventListener("mousemove", this._onMousemove);
        document.addEventListener("mouseup", this._onMouseup);
    }

    async onInputPortMouseup(ev, toStepId) {
        ev.stopPropagation();
        if (!this.state._connecting) return;
        const fromStepId = this.state._connecting.fromStepId;
        this.state._connecting = null;
        document.removeEventListener("mousemove", this._onMousemove);
        document.removeEventListener("mouseup", this._onMouseup);

        if (fromStepId === toStepId) return;
        const dup = this.state.connections.some(
            (c) => c.from_step_id === fromStepId && c.to_step_id === toStepId
        );
        if (dup) return;

        // orm.create() in Odoo 19 requires an array of record dicts and returns an array of IDs
        const [newId] = await this.orm.create("wf.step.connection", [{
            from_step_id: fromStepId,
            to_step_id: toStepId,
            condition_type: "none",
        }]);
        this.state.connections.push({
            id: newId,
            from_step_id: fromStepId,
            to_step_id: toStepId,
            label: "",
            condition_type: "none",
            condition_domain: "[]",
            condition_expression: "",
            sequence: 10,
        });
    }

    _globalMousemove(ev) {
        if (this.state._dragging) {
            const d = this.state._dragging;
            const dx = (ev.clientX - d.sx) / this.state.zoom;
            const dy = (ev.clientY - d.sy) / this.state.zoom;
            const step = this.state.steps.find((s) => s.id === d.stepId);
            if (step) {
                step.canvas_x = Math.max(0, d.ox + dx);
                step.canvas_y = Math.max(0, d.oy + dy);
            }
        } else if (this.state._panning) {
            const p = this.state._panning;
            this.state.panX = p.px + (ev.clientX - p.sx);
            this.state.panY = p.py + (ev.clientY - p.sy);
        } else if (this.state._connecting) {
            const pos = this._screenToWorld(ev.clientX, ev.clientY);
            this.state._connecting.cursorX = pos.x;
            this.state._connecting.cursorY = pos.y;
        }
    }

    async _globalMouseup(ev) {
        if (this.state._dragging) {
            const stepId = this.state._dragging.stepId;
            const step = this.state.steps.find((s) => s.id === stepId);
            this.state._dragging = null;
            if (step) {
                await this.orm.write("wf.step", [step.id], {
                    canvas_x: step.canvas_x,
                    canvas_y: step.canvas_y,
                });
            }
        }
        if (this.state._panning) {
            this.state._panning = null;
            this._savePanZoom();
        }
        if (this.state._connecting) {
            this.state._connecting = null;
        }
        document.removeEventListener("mousemove", this._onMousemove);
        document.removeEventListener("mouseup", this._onMouseup);
    }

    onWheel(ev) {
        ev.preventDefault();
        const el = this.canvasOuter.el;
        if (!el) return;
        const r = el.getBoundingClientRect();
        const mx = ev.clientX - r.left;
        const my = ev.clientY - r.top;
        const factor = ev.deltaY < 0 ? 1.12 : 1 / 1.12;
        const newZoom = Math.max(0.15, Math.min(3.0, this.state.zoom * factor));
        this.state.panX = mx - (mx - this.state.panX) * (newZoom / this.state.zoom);
        this.state.panY = my - (my - this.state.panY) * (newZoom / this.state.zoom);
        this.state.zoom = newZoom;
    }

    // ------------------------------------------------------------------ //
    // Toolbar actions                                                      //
    // ------------------------------------------------------------------ //

    zoomIn() {
        const el = this.canvasOuter.el;
        const cx = el ? el.clientWidth / 2 : 400;
        const cy = el ? el.clientHeight / 2 : 300;
        const newZoom = Math.min(3.0, this.state.zoom * 1.2);
        this.state.panX = cx - (cx - this.state.panX) * (newZoom / this.state.zoom);
        this.state.panY = cy - (cy - this.state.panY) * (newZoom / this.state.zoom);
        this.state.zoom = newZoom;
        this._savePanZoom();
    }

    zoomOut() {
        const el = this.canvasOuter.el;
        const cx = el ? el.clientWidth / 2 : 400;
        const cy = el ? el.clientHeight / 2 : 300;
        const newZoom = Math.max(0.15, this.state.zoom / 1.2);
        this.state.panX = cx - (cx - this.state.panX) * (newZoom / this.state.zoom);
        this.state.panY = cy - (cy - this.state.panY) * (newZoom / this.state.zoom);
        this.state.zoom = newZoom;
        this._savePanZoom();
    }

    fitView() {
        const el = this.canvasOuter.el;
        if (!el || !this.state.steps.length) return;
        const w = el.clientWidth;
        const h = el.clientHeight;
        const minX = Math.min(...this.state.steps.map((s) => s.canvas_x));
        const minY = Math.min(...this.state.steps.map((s) => s.canvas_y));
        const maxX = Math.max(...this.state.steps.map((s) => s.canvas_x + NODE_WIDTH));
        const maxY = Math.max(...this.state.steps.map((s) => s.canvas_y + NODE_HEIGHT));
        const pad = 80;
        const scaleX = (w - pad * 2) / (maxX - minX || 1);
        const scaleY = (h - pad * 2) / (maxY - minY || 1);
        const newZoom = Math.min(scaleX, scaleY, 1.5);
        this.state.zoom = newZoom;
        this.state.panX = pad - minX * newZoom;
        this.state.panY = pad - minY * newZoom;
        this._savePanZoom();
    }

    async addStep(stepType) {
        this.state.showAddMenu = false;
        const el = this.canvasOuter.el;
        const w = el ? el.clientWidth : 800;
        const h = el ? el.clientHeight : 600;
        let x = Math.max(0, (w / 2 - this.state.panX) / this.state.zoom - NODE_WIDTH / 2);
        let y = Math.max(0, (h / 2 - this.state.panY) / this.state.zoom - NODE_HEIGHT / 2);
        // Avoid exact overlap with existing nodes
        while (this.state.steps.some((s) => Math.abs(s.canvas_x - x) < 20 && Math.abs(s.canvas_y - y) < 20)) {
            x += 25;
            y += 25;
        }
        const seq = this.state.steps.length
            ? Math.max(...this.state.steps.map((s) => s.sequence || 10)) + 10
            : 10;

        const cfg = STEP_TYPE_CONFIG[stepType] || { label: "New Step" };
        // orm.create() in Odoo 19 requires an array of record dicts and returns an array of IDs
        const [newId] = await this.orm.create("wf.step", [{
            workflow_id: this.workflowId,
            name: cfg.label,
            step_type: stepType,
            canvas_x: x,
            canvas_y: y,
            sequence: seq,
        }]);

        this.state.steps.push({
            id: newId,
            name: cfg.label,
            step_type: stepType,
            canvas_x: x,
            canvas_y: y,
            condition_type: "none",
            active: true,
            sequence: seq,
        });

        this.editStep(newId);
    }

    editStep(stepId) {
        this.actionService.doAction(
            {
                type: "ir.actions.act_window",
                res_model: "wf.step",
                res_id: stepId,
                views: [[false, "form"]],
                target: "new",
            },
            { onClose: () => this.loadWorkflow() }
        );
    }

    async deleteStep(stepId) {
        const connIds = this.state.connections
            .filter((c) => c.from_step_id === stepId || c.to_step_id === stepId)
            .map((c) => c.id);
        if (connIds.length) await this.orm.unlink("wf.step.connection", connIds);
        await this.orm.unlink("wf.step", [stepId]);
        this.state.steps = this.state.steps.filter((s) => s.id !== stepId);
        this.state.connections = this.state.connections.filter(
            (c) => c.from_step_id !== stepId && c.to_step_id !== stepId
        );
        if (this.state.selectedStepId === stepId) this.state.selectedStepId = null;
    }

    async duplicateStep(stepId) {
        const step = this.state.steps.find((s) => s.id === stepId);
        if (!step) return;

        // action_duplicate() copies all config fields, excludes connections,
        // offsets the canvas position, and returns a plain integer ID.
        const newId = await this.orm.call(
            "wf.step",
            "action_duplicate",
            [stepId],
            {}
        );

        // Pull back the fields the canvas needs to render the new node.
        const [newStep] = await this.orm.read(
            "wf.step",
            [newId],
            ["id", "name", "step_type", "canvas_x", "canvas_y",
             "condition_type", "active", "sequence", "api_method", "api_url_slug"],
            { context: { active_test: false } }
        );

        this.state.steps.push(newStep);
        // Select the duplicate so the user can immediately rename / connect it.
        this.state.selectedStepId = newId;
        this.state.selectedConnectionId = null;
        this.state.editingConnection = null;
        this.state.showAddMenu = false;

        this.notification.add(
            `"${step.name}" duplicated — all configuration copied, no connections.`,
            { type: "info" }
        );
    }

    selectConnection(connId) {
        const conn = this.state.connections.find((c) => c.id === connId);
        this.state.selectedConnectionId = connId;
        this.state.selectedStepId = null;
        this.state.editingConnection = conn ? { ...conn } : null;
    }

    updateEditingConn(field, value) {
        if (this.state.editingConnection) {
            this.state.editingConnection[field] = value;
        }
    }

    async saveConnectionChanges() {
        const ec = this.state.editingConnection;
        if (!ec) return;
        await this.orm.write("wf.step.connection", [ec.id], {
            condition_type: ec.condition_type,
            condition_domain: ec.condition_domain || "[]",
            condition_expression: ec.condition_expression || "",
            label: ec.label || "",
        });
        const idx = this.state.connections.findIndex((c) => c.id === ec.id);
        if (idx >= 0) Object.assign(this.state.connections[idx], ec);
        this.notification.add("Connection saved", { type: "success" });
        this.state.editingConnection = null;
        this.state.selectedConnectionId = null;
    }

    async deleteConnection(connId) {
        await this.orm.unlink("wf.step.connection", [connId]);
        this.state.connections = this.state.connections.filter((c) => c.id !== connId);
        this.state.selectedConnectionId = null;
        this.state.editingConnection = null;
    }

    // Open the connection's Odoo form dialog so the graphical domain builder
    // is available.  On close, refresh connection data without a full reload.
    editConnection(connId) {
        this.actionService.doAction(
            {
                type: "ir.actions.act_window",
                res_model: "wf.step.connection",
                res_id: connId,
                views: [[false, "form"]],
                target: "new",
            },
            {
                onClose: async () => {
                    await this._refreshConnections();
                    // Refresh the sidebar panel if this connection is still selected
                    if (this.state.selectedConnectionId === connId) {
                        const refreshed = this.state.connections.find((c) => c.id === connId);
                        this.state.editingConnection = refreshed ? { ...refreshed } : null;
                    }
                },
            }
        );
    }

    // Lightweight refresh — reloads only connection records, no spinner.
    async _refreshConnections() {
        const rawConns = await this.orm.searchRead(
            "wf.step.connection",
            [["workflow_id", "=", this.workflowId]],
            ["id", "from_step_id", "to_step_id", "label", "condition_type",
             "condition_domain", "condition_expression", "sequence"]
        );
        this.state.connections = rawConns.map((c) => ({
            ...c,
            from_step_id: Array.isArray(c.from_step_id) ? c.from_step_id[0] : c.from_step_id,
            to_step_id:   Array.isArray(c.to_step_id)   ? c.to_step_id[0]   : c.to_step_id,
        }));
    }

    async saveLayout() {
        this.state.saving = true;
        try {
            for (const s of this.state.steps) {
                await this.orm.write("wf.step", [s.id], { canvas_x: s.canvas_x, canvas_y: s.canvas_y });
            }
            await this._savePanZoom();
            this.notification.add("Layout saved", { type: "success" });
        } finally {
            this.state.saving = false;
        }
    }

    goBack() {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "wf.automation",
            res_id: this.workflowId,
            views: [[false, "form"]],
        });
    }

    autoLayoutAll() {
        this._autoLayout(this.state.steps, this.state.connections);
        this._savePositions(this.state.steps);
        this.fitView();
    }
}

registry.category("actions").add("workflow_automation.canvas", WorkflowCanvasAction);
