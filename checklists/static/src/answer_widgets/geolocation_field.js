import { Component, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

/**
 * GeoLocation answer: a latitude field (this widget) and its longitude
 * field, filled from the device's location or typed in. The question's
 * options (on the line) choose what shows: the coordinates, a map and/or
 * the closest street address (looked up on the server, kept in
 * value_address).
 */
export class ChecklistGeolocationField extends Component {
    static template = "checklists.GeolocationField";
    static props = { ...standardFieldProps, longitudeField: { type: String, optional: true } };
    static defaultProps = { longitudeField: "value_longitude" };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({ locating: false, lookingUp: false });
    }

    get data() {
        return this.props.record.data;
    }

    get showCoordinates() {
        // Nothing chosen: the coordinates, so the answer is visible somehow.
        return this.data.geo_show_coordinates || !(this.data.geo_show_map || this.data.geo_show_address);
    }

    get latitude() {
        return this.data[this.props.name] || 0;
    }

    get longitude() {
        return this.data[this.props.longitudeField] || 0;
    }

    get isSet() {
        return Boolean(this.latitude || this.longitude);
    }

    get display() {
        return `${this.latitude.toFixed(6)}, ${this.longitude.toFixed(6)}`;
    }

    get mapUrl() {
        return `https://www.openstreetmap.org/?mlat=${this.latitude}&mlon=${this.longitude}#map=17/${this.latitude}/${this.longitude}`;
    }

    get mapEmbedUrl() {
        const d = 0.004;
        const bbox = [this.longitude - d, this.latitude - d, this.longitude + d, this.latitude + d].join(",");
        return `https://www.openstreetmap.org/export/embed.html?bbox=${bbox}&layer=mapnik&marker=${this.latitude},${this.longitude}`;
    }

    async update(latitude, longitude) {
        const values = { [this.props.name]: latitude, [this.props.longitudeField]: longitude };
        if (this.data.geo_show_address) {
            values.value_address = false;
        }
        await this.props.record.update(values);
        if (this.data.geo_show_address && (latitude || longitude)) {
            this.state.lookingUp = true;
            try {
                const address = await this.orm.call("checklist.line", "checklist_reverse_geocode", [
                    latitude,
                    longitude,
                ]);
                // Only if the location hasn't moved on meanwhile.
                if (this.latitude === latitude && this.longitude === longitude) {
                    await this.props.record.update({ value_address: address || false });
                    if (!address) {
                        this.notification.add(_t("No street address was found for this location."), {
                            type: "warning",
                        });
                    }
                }
            } finally {
                this.state.lookingUp = false;
            }
        }
    }

    onInput(ev, which) {
        const value = parseFloat(ev.target.value);
        if (which === "latitude") {
            this.update(isNaN(value) ? 0 : value, this.longitude);
        } else {
            this.update(this.latitude, isNaN(value) ? 0 : value);
        }
    }

    locate() {
        if (!navigator.geolocation) {
            this.notification.add(_t("This device can't share its location."), { type: "warning" });
            return;
        }
        this.state.locating = true;
        navigator.geolocation.getCurrentPosition(
            (position) => {
                this.state.locating = false;
                this.update(position.coords.latitude, position.coords.longitude);
            },
            (error) => {
                this.state.locating = false;
                this.notification.add(_t("Couldn't get the location: %s", error.message), {
                    type: "warning",
                });
            },
            { enableHighAccuracy: true, timeout: 20000 }
        );
    }

    clear() {
        this.update(0, 0);
    }
}

registry.category("fields").add("checklist_geolocation", {
    component: ChecklistGeolocationField,
    displayName: _t("GeoLocation"),
    supportedTypes: ["float"],
    isEmpty: () => false,
    extractProps: ({ options }) => ({ longitudeField: options.longitude_field }),
});
