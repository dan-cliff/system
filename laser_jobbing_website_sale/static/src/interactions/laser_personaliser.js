import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";
import { registry } from "@web/core/registry";
import { Interaction } from "@web/public/interaction";
import {
    browserImageUrl,
    drawLaserCanvas,
    whenLaserFontsLoaded,
} from "@laser_jobbing/canvas/laser_canvas";

export class LaserPersonaliser extends Interaction {
    static selector = ".o_laser_personaliser";
    dynamicContent = {
        ".o_laser_text": { "t-on-input": this.onChange, "t-on-keydown": this.onKeydown },
        ".o_laser_file": { "t-on-change": this.onFileChange },
        ".o_laser_quantity": { "t-on-keydown": this.onKeydown },
        ".o_laser_preview_btn": { "t-on-click": this.onPreview },
        ".o_laser_add_to_cart": { "t-on-click": this.onAddToCart },
    };

    setup() {
        try {
            this.data = JSON.parse(this.el.dataset.editor || "null");
        } catch {
            this.data = null;
        }
        this.visual = this.el.dataset.visual === "1";
        this.svg = this.el.querySelector(".o_laser_svg");
        this.job = null;
        this.dirty = true;
        this.busy = false;
        this.imageUrls = {};
        this.fileNames = {};
    }

    start() {
        if (this.visual && this.svg) {
            this.draw();
            whenLaserFontsLoaded(this.data, () => this.draw());
        }
    }

    destroy() {
        for (const url of Object.values(this.imageUrls)) {
            if (url) {
                URL.revokeObjectURL(url);
            }
        }
    }

    // ── Events ──────────────────────────────────────────────────────────

    onKeydown(ev) {
        // Enter must not submit the shop's add-to-cart form around the personaliser.
        if (ev.key === "Enter" && ev.currentTarget.tagName !== "TEXTAREA") {
            ev.preventDefault();
        }
    }

    onChange() {
        this.dirty = true;
        this.hideError();
        if (this.visual && this.svg) {
            this.draw();
        }
    }

    onFileChange(ev) {
        const input = ev.currentTarget;
        const id = input.dataset.elementId;
        const file = input.files[0];
        if (this.imageUrls[id]) {
            URL.revokeObjectURL(this.imageUrls[id]);
        }
        this.imageUrls[id] = file ? browserImageUrl(file) : "";
        this.fileNames[id] = file ? file.name : "";
        this.onChange();
    }

    async onPreview(ev) {
        ev.preventDefault();
        if (this.busy) {
            return;
        }
        this.startBusy();
        try {
            const job = await this.design();
            this.showServerPreview(job);
        } catch (error) {
            this.showError(error.message || String(error));
        } finally {
            this.stopBusy();
        }
    }

    async onAddToCart(ev) {
        ev.preventDefault();
        if (this.busy) {
            return;
        }
        this.startBusy();
        try {
            if (this.dirty || !this.job) {
                const job = await this.design();
                this.showServerPreview(job);
            }
            const result = await this.waitFor(
                rpc("/shop/laser/add-to-cart", {
                    job_id: this.job.job_id,
                    access_token: this.job.access_token,
                    quantity: this.quantity(),
                })
            );
            window.location.href = result.redirect || "/shop/cart";
        } catch (error) {
            this.showError(error.data?.message || error.message || String(error));
            this.stopBusy();
        }
    }

    // ── Helpers ─────────────────────────────────────────────────────────

    values() {
        const values = {};
        for (const input of this.el.querySelectorAll(".o_laser_text")) {
            values[input.dataset.elementId] = { text: input.value };
        }
        for (const input of this.el.querySelectorAll(".o_laser_file")) {
            const id = input.dataset.elementId;
            values[id] = { imageUrl: this.imageUrls[id] || "", fileName: this.fileNames[id] || "" };
        }
        return values;
    }

    draw() {
        drawLaserCanvas(this.svg, this.data, { values: this.values(), mode: "fill" });
    }

    quantity() {
        const input = this.el.querySelector(".o_laser_quantity");
        return Math.max(parseInt(input?.value) || 1, 1);
    }

    variantId() {
        const input = document.querySelector(".js_product input.product_id, input[name='product_id']");
        return input ? input.value : "";
    }

    async design() {
        const missing = [...this.el.querySelectorAll(".o_laser_fields [required]")].filter((input) =>
            input.type === "file" ? !input.files.length && !this.job : !input.value.trim()
        );
        if (missing.length) {
            missing[0].focus();
            throw new Error(_t("Please fill in every field marked with *."));
        }
        const formData = new FormData();
        formData.append("csrf_token", odoo.csrf_token);
        formData.append("product_template_id", this.el.dataset.productTemplateId);
        formData.append("product_id", this.variantId());
        formData.append("quantity", String(this.quantity()));
        if (this.job) {
            formData.append("job_id", this.job.job_id);
            formData.append("access_token", this.job.access_token);
        }
        for (const input of this.el.querySelectorAll(".o_laser_text")) {
            formData.append(input.name, input.value);
        }
        for (const input of this.el.querySelectorAll(".o_laser_file")) {
            if (input.files.length) {
                formData.append(input.name, input.files[0]);
            }
        }
        const response = await this.waitFor(fetch("/shop/laser/design", { method: "POST", body: formData }));
        let data;
        try {
            data = await this.waitFor(response.json());
        } catch {
            throw new Error(_t("Your design could not be made. Please try again."));
        }
        if (!response.ok || data.error) {
            throw new Error(data.error || _t("Your design could not be made."));
        }
        this.job = data;
        this.dirty = false;
        return data;
    }

    showServerPreview(job) {
        const img = this.el.querySelector(".o_laser_preview_img");
        if (!img || !job.preview_url) {
            return;
        }
        const hint = this.el.querySelector(".o_laser_preview_hint");
        img.onerror = () => {
            img.classList.add("d-none");
            if (hint) {
                hint.textContent = _t("Your design is ready (this picture format can't be previewed here).");
                hint.classList.remove("d-none");
            }
        };
        img.onload = () => hint?.classList.add("d-none");
        img.src = job.preview_url;
        img.classList.remove("d-none");
    }

    startBusy() {
        this.busy = true;
        this.hideError();
        this.el.querySelector(".o_laser_progress").classList.remove("d-none");
        for (const button of this.el.querySelectorAll("button")) {
            button.disabled = true;
        }
    }

    stopBusy() {
        this.busy = false;
        this.el.querySelector(".o_laser_progress").classList.add("d-none");
        for (const button of this.el.querySelectorAll("button")) {
            button.disabled = false;
        }
    }

    showError(message) {
        const box = this.el.querySelector(".o_laser_error");
        box.textContent = message;
        box.classList.remove("d-none");
    }

    hideError() {
        this.el.querySelector(".o_laser_error").classList.add("d-none");
    }
}

registry.category("public.interactions").add("laser_jobbing_website_sale.laser_personaliser", LaserPersonaliser);
