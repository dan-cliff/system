/** Room Designer client action: loads a room, mounts the visual editor and publishes. */
import { Component, onMounted, onWillStart, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { mountDesigner } from "./designer_core";

export class RoomDesigner extends Component {
    static template = "video_rooms.RoomDesigner";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");
        this.root = useRef("editor");
        const params = this.props.action?.params || {};
        this.roomId = params.room_id || this.props.action?.context?.active_id;
        this.state = useState({ name: "", dirty: false, saving: false, error: "" });
        onWillStart(async () => {
            if (!this.roomId) {
                this.state.error = "Open the Room Designer from a room.";
                return;
            }
            this.data = await this.orm.call("video.room", "designer_load", [[this.roomId]]);
            this.state.name = this.data.name;
        });
        onMounted(() => this.mount());
    }

    mount() {
        if (!this.data) {
            return;
        }
        this.editor = mountDesigner(this.root.el, this.data, {
            notify: (message, type = "info") => this.notification.add(message, { type }),
            changed: () => (this.state.dirty = true),
            identify: () => this.orm.call("video.room", "action_identify_screens", [[this.roomId]]).then(
                () => this.notification.add("Showing numbers on the room's screens.", { type: "success" })),
            saveTemplate: (kind, name, layout) => this.orm.call("video.room", "designer_save_template", [[this.roomId], kind, name, layout]),
            followTemplate: async (kind, templateId) => {
                this.data = await this.orm.call("video.room", "designer_follow_template", [[this.roomId], kind, templateId]);
                this.state.dirty = false;
                this.mount();
                this.notification.add("The room now follows the template.", { type: "success" });
            },
        });
    }

    async publish() {
        this.state.saving = true;
        try {
            this.data = await this.orm.call("video.room", "designer_save", [[this.roomId], this.editor.getData()]);
            this.state.dirty = false;
            this.mount();
            this.notification.add(`Published to ${this.state.name}'s screens and tablets.`, { type: "success" });
        } finally {
            this.state.saving = false;
        }
    }

    openRoom() {
        this.action.doAction({ type: "ir.actions.act_window", res_model: "video.room", res_id: this.roomId, views: [[false, "form"]] });
    }
}

registry.category("actions").add("video_rooms.room_designer", RoomDesigner);
