/** Overview: the live status of a Room Board's rooms (or all rooms) inside Odoo. */
import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const STATUS = {
    available: ["Available", "o_vr_ok"],
    soon: ["Booked soon", "o_vr_soon"],
    in_use: ["In use", "o_vr_busy"],
    dnd: ["Do not disturb", "o_vr_dnd"],
};

export class RoomBoard extends Component {
    static template = "video_rooms.RoomBoard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        const params = this.props.action?.params || {};
        this.state = useState({ boards: [], board: null, boardId: params.board_id || false, loading: true });
        onWillStart(() => this.load());
        this.timer = setInterval(() => this.load(), 15000);
        onWillUnmount(() => clearInterval(this.timer));
    }

    async load() {
        const data = await this.orm.call("video.room.board", "get_overview", [], { board_id: this.state.boardId || false });
        this.state.boards = data.boards;
        this.state.board = data.board;
        this.state.loading = false;
    }

    async chooseBoard(ev) {
        this.state.boardId = Number(ev.target.value) || false;
        await this.load();
    }

    status(room) {
        return STATUS[room.availability] || STATUS.available;
    }

    openRoom(room) {
        this.action.doAction({ type: "ir.actions.act_window", res_model: "video.room", res_id: room.id, views: [[false, "form"]] });
    }

    get hours() {
        return [8, 10, 12, 14, 16, 18];
    }

    pct(ts) {
        const d = new Date(ts.replace(" ", "T") + "Z");
        const hours = d.getHours() + d.getMinutes() / 60;
        return Math.max(0, Math.min(100, ((hours - 8) / 10) * 100));
    }

    barStyle(meeting) {
        const left = this.pct(meeting.start_ts);
        return `left:${left}%;width:${Math.max(0.5, this.pct(meeting.end_ts) - left)}%`;
    }

    get nowStyle() {
        const now = new Date();
        return `left:${Math.max(0, Math.min(100, ((now.getHours() + now.getMinutes() / 60 - 8) / 10) * 100))}%`;
    }

    get showTiles() {
        return ["tiles", "tiles_timeline", "list"].includes(this.state.board?.view);
    }

    get showTimeline() {
        return ["timeline", "tiles_timeline"].includes(this.state.board?.view);
    }
}

registry.category("actions").add("video_rooms.room_board", RoomBoard);
