/** @odoo-module **/

import { Component, useState, onWillUpdateProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

// ── Main body — front view (all 23 main regions) ─────────────────────────────
const BODY_PARTS_FRONT = [
    { code: "head",           label: "Head" },
    { code: "neck",           label: "Neck" },
    { code: "left_shoulder",  label: "Left Shoulder" },
    { code: "left_arm",       label: "Left Arm" },
    { code: "left_elbow",     label: "Left Elbow" },
    { code: "left_hand",      label: "Left Hand" },
    { code: "right_shoulder", label: "Right Shoulder" },
    { code: "right_arm",      label: "Right Arm" },
    { code: "right_elbow",    label: "Right Elbow" },
    { code: "right_hand",     label: "Right Hand" },
    { code: "chest",          label: "Chest" },
    { code: "abdomen",        label: "Abdomen" },
    { code: "pelvis",         label: "Pelvis" },
    { code: "left_hip",       label: "Left Hip" },
    { code: "right_hip",      label: "Right Hip" },
    { code: "left_thigh",     label: "Left Thigh" },
    { code: "right_thigh",    label: "Right Thigh" },
    { code: "left_knee",      label: "Left Knee" },
    { code: "right_knee",     label: "Right Knee" },
    { code: "left_shin",      label: "Left Shin" },
    { code: "right_shin",     label: "Right Shin" },
    { code: "left_foot",      label: "Left Foot" },
    { code: "right_foot",     label: "Right Foot" },
];

// ── Main body — back-only regions ─────────────────────────────────────────────
const BODY_PARTS_BACK_ONLY = [
    { code: "upper_back",    label: "Upper Back" },
    { code: "lower_back",    label: "Lower Back" },
    { code: "left_buttock",  label: "Left Buttock" },
    { code: "right_buttock", label: "Right Buttock" },
];

// ── Left hand detail ──────────────────────────────────────────────────────────
const BODY_PARTS_HAND_L = [
    { code: "lhand_palm",   label: "Left Palm" },
    { code: "lhand_thumb",  label: "Left Thumb" },
    { code: "lhand_index",  label: "Left Index Finger" },
    { code: "lhand_middle", label: "Left Middle Finger" },
    { code: "lhand_ring",   label: "Left Ring Finger" },
    { code: "lhand_pinky",  label: "Left Pinky Finger" },
];

// ── Right hand detail ─────────────────────────────────────────────────────────
const BODY_PARTS_HAND_R = [
    { code: "rhand_palm",   label: "Right Palm" },
    { code: "rhand_thumb",  label: "Right Thumb" },
    { code: "rhand_index",  label: "Right Index Finger" },
    { code: "rhand_middle", label: "Right Middle Finger" },
    { code: "rhand_ring",   label: "Right Ring Finger" },
    { code: "rhand_pinky",  label: "Right Pinky Finger" },
];

// ── Left foot detail ──────────────────────────────────────────────────────────
const BODY_PARTS_FOOT_L = [
    { code: "lfoot_upper",   label: "Left Upper Foot" },
    { code: "lfoot_sole",    label: "Left Sole" },
    { code: "lfoot_ball",    label: "Left Ball of Foot" },
    { code: "lfoot_big_toe", label: "Left Big Toe" },
    { code: "lfoot_toe2",    label: "Left Toe 2" },
    { code: "lfoot_toe3",    label: "Left Toe 3" },
    { code: "lfoot_toe4",    label: "Left Toe 4" },
    { code: "lfoot_toe5",    label: "Left Toe 5" },
];

// ── Right foot detail ─────────────────────────────────────────────────────────
const BODY_PARTS_FOOT_R = [
    { code: "rfoot_upper",   label: "Right Upper Foot" },
    { code: "rfoot_sole",    label: "Right Sole" },
    { code: "rfoot_ball",    label: "Right Ball of Foot" },
    { code: "rfoot_big_toe", label: "Right Big Toe" },
    { code: "rfoot_toe2",    label: "Right Toe 2" },
    { code: "rfoot_toe3",    label: "Right Toe 3" },
    { code: "rfoot_toe4",    label: "Right Toe 4" },
    { code: "rfoot_toe5",    label: "Right Toe 5" },
];

// ── Head detail ───────────────────────────────────────────────────────────────
const BODY_PARTS_HEAD_DETAIL = [
    { code: "hd_forehead",      label: "Forehead" },
    { code: "hd_crown",         label: "Crown" },
    { code: "hd_back_of_head",  label: "Back of Head" },
    { code: "hd_left_face",     label: "Left Face" },
    { code: "hd_right_face",    label: "Right Face" },
    { code: "hd_left_eye",      label: "Left Eye" },
    { code: "hd_right_eye",     label: "Right Eye" },
    { code: "hd_nose",          label: "Nose" },
    { code: "hd_mouth",         label: "Mouth" },
    { code: "hd_teeth",         label: "Teeth" },
    { code: "hd_mental_health", label: "Mental Health" },
];

const ALL_PART_LISTS = [
    BODY_PARTS_FRONT,
    BODY_PARTS_BACK_ONLY,
    BODY_PARTS_HAND_L,
    BODY_PARTS_HAND_R,
    BODY_PARTS_FOOT_L,
    BODY_PARTS_FOOT_R,
    BODY_PARTS_HEAD_DETAIL,
];

export class BodyPartWidget extends Component {
    static template = "incident_management.BodyPartWidget";
    static props = { ...standardFieldProps };

    setup() {
        this.bodyPartsFront    = BODY_PARTS_FRONT;
        this.bodyPartsBackOnly = BODY_PARTS_BACK_ONLY;
        this.handPartsL        = BODY_PARTS_HAND_L;
        this.handPartsR        = BODY_PARTS_HAND_R;
        this.footPartsL        = BODY_PARTS_FOOT_L;
        this.footPartsR        = BODY_PARTS_FOOT_R;
        this.headParts         = BODY_PARTS_HEAD_DETAIL;

        this.state = useState({
            selected: new Set(this._parseCodes(this._fieldValue(this.props))),
            view: "front",
        });

        onWillUpdateProps((nextProps) => {
            const incoming = this._parseCodes(this._fieldValue(nextProps));
            const current  = [...this.state.selected].sort().join(",");
            const next     = [...incoming].sort().join(",");
            if (current !== next) {
                this.state.selected = new Set(incoming);
            }
        });
    }

    _fieldValue(props) {
        return props.record.data[props.name];
    }

    _parseCodes(raw) {
        if (!raw) return [];
        try {
            const parsed = JSON.parse(raw);
            return Array.isArray(parsed) ? parsed : [];
        } catch {
            return [];
        }
    }

    isSelected(code) {
        return this.state.selected.has(code);
    }

    get selectedParts() {
        const allParts = ALL_PART_LISTS.flat();
        return allParts.filter((p) => this.state.selected.has(p.code));
    }

    get isFrontView()    { return this.state.view === "front"; }
    get showHeadDetail() { return this.state.selected.has("head"); }
    get showLeftHand()   { return this.state.selected.has("left_hand"); }
    get showRightHand()  { return this.state.selected.has("right_hand"); }
    get showLeftFoot()   { return this.state.selected.has("left_foot"); }
    get showRightFoot()  { return this.state.selected.has("right_foot"); }

    toggle(code) {
        if (this.props.readonly) return;
        const s = new Set(this.state.selected);
        s.has(code) ? s.delete(code) : s.add(code);
        this.state.selected = s;
        this.props.record.update({ [this.props.name]: JSON.stringify([...s]) });
    }

    switchView(view) { this.state.view = view; }
    removeTag(code)  { this.toggle(code); }
}

registry.category("fields").add("body_part_selector", {
    component: BodyPartWidget,
    supportedTypes: ["char"],
});
