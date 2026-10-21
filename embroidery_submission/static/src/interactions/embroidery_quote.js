import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";
import { registry } from "@web/core/registry";
import { Interaction } from "@web/public/interaction";

const STEPS = ["upload", "read", "price"];

export class EmbroideryQuote extends Interaction {
    static selector = ".o_embroidery_quote";
    dynamicContent = {
        ".o_embroidery_submit": { "t-on-click": this.onSubmit },
        ".o_embroidery_file": { "t-on-keydown": this.onInputKeydown },
        ".o_embroidery_quantity": { "t-on-change": this.onQuantityChange, "t-on-keydown": this.onInputKeydown },
        ".o_embroidery_add_to_cart": { "t-on-click": this.onAddToCart },
    };

    setup() {
        this.quote = null;
        this.busy = false;
        this.form = this.el.querySelector(".o_embroidery_upload_form");
    }

    destroy() {
        this.stopTimer();
    }

    // ── Events ──────────────────────────────────────────────────────────

    async onSubmit(ev) {
        ev.preventDefault();
        if (this.busy) {
            return;
        }
        const fileInput = this.form.querySelector(".o_embroidery_file");
        if (!fileInput.files.length) {
            this.showError(_t("Choose a .pes embroidery file to upload."));
            return;
        }
        const formData = new FormData();
        formData.append("csrf_token", odoo.csrf_token);
        formData.append("product_id", this.el.dataset.productId);
        formData.append("quantity", String(this.quantity()));
        formData.append("file", fileInput.files[0]);
        this.startProgress();
        try {
            // The server reads the file and prices it in the same request;
            // move the progress on once the upload itself has gone through.
            const readTimer = setTimeout(() => this.setStep("read"), 1000);
            const response = await this.waitFor(
                fetch("/shop/embroidery-quote/upload", { method: "POST", body: formData })
            );
            clearTimeout(readTimer);
            this.setStep("price");
            let data;
            try {
                data = await this.waitFor(response.json());
            } catch {
                throw new Error(_t("The server could not read this file. Please try another file."));
            }
            if (!response.ok || data.error) {
                throw new Error(data.error || _t("Your file could not be priced."));
            }
            this.quote = data;
            this.render();
        } catch (error) {
            this.quote = null;
            this.showError(error.message || String(error));
        } finally {
            this.stopProgress();
        }
    }

    onInputKeydown(ev) {
        // Enter must not submit the shop's add-to-cart form around the widget.
        if (ev.key === "Enter") {
            ev.preventDefault();
        }
    }

    async onQuantityChange() {
        if (!this.quote) {
            return;
        }
        this.busy = true;
        try {
            this.quote = await this.waitFor(
                rpc("/shop/embroidery-quote/update", {
                    submission_id: this.quote.submission_id,
                    access_token: this.quote.access_token,
                    quantity: this.quantity(),
                })
            );
            this.render();
        } catch (error) {
            this.showError(error.data?.message || error.message || String(error));
        } finally {
            this.busy = false;
        }
    }

    async onAddToCart(ev) {
        ev.preventDefault();
        if (!this.quote || this.busy) {
            return;
        }
        this.busy = true;
        const button = ev.currentTarget;
        button.disabled = true;
        try {
            const result = await this.waitFor(
                rpc("/shop/embroidery-quote/add-to-cart", {
                    submission_id: this.quote.submission_id,
                    access_token: this.quote.access_token,
                    quantity: this.quantity(),
                })
            );
            window.location.href = result.redirect || "/shop/cart";
        } catch (error) {
            this.showError(error.data?.message || error.message || String(error));
            button.disabled = false;
        } finally {
            this.busy = false;
        }
    }

    // ── Helpers ─────────────────────────────────────────────────────────

    quantity() {
        const input = this.el.querySelector(".o_embroidery_quantity");
        return Math.max(parseInt(input?.value) || 1, 1);
    }

    startProgress() {
        this.busy = true;
        this.el.querySelector(".o_embroidery_error").classList.add("d-none");
        this.el.querySelector(".o_embroidery_result").classList.add("d-none");
        this.el.querySelector(".o_embroidery_progress").classList.remove("d-none");
        this.form.querySelector(".o_embroidery_submit").disabled = true;
        this.setStep("upload");
        const started = Date.now();
        const elapsed = this.el.querySelector(".o_embroidery_elapsed");
        elapsed.textContent = "";
        this.timer = setInterval(() => {
            const seconds = Math.round((Date.now() - started) / 1000);
            const minutes = Math.floor(seconds / 60);
            elapsed.textContent = `(${minutes}:${String(seconds % 60).padStart(2, "0")})`;
        }, 1000);
    }

    stopProgress() {
        this.busy = false;
        this.stopTimer();
        this.el.querySelector(".o_embroidery_progress").classList.add("d-none");
        this.form.querySelector(".o_embroidery_submit").disabled = false;
    }

    stopTimer() {
        if (this.timer) {
            clearInterval(this.timer);
            this.timer = null;
        }
    }

    setStep(step) {
        const current = STEPS.indexOf(step);
        for (const li of this.el.querySelectorAll(".o_embroidery_steps li")) {
            const index = STEPS.indexOf(li.dataset.step);
            const icon = li.querySelector("i");
            icon.className =
                "me-2 fa " +
                (index < current ? "fa-check text-success" : index === current ? "fa-spinner fa-spin" : "fa-circle-o");
            li.classList.toggle("fw-bold", index === current);
        }
    }

    showError(message) {
        const box = this.el.querySelector(".o_embroidery_error");
        box.textContent = message;
        box.classList.remove("d-none");
    }

    render() {
        const quote = this.quote;
        const result = this.el.querySelector(".o_embroidery_result");
        if (quote.state !== "done") {
            result.classList.add("d-none");
            this.showError(quote.error || _t("Your file could not be read."));
            return;
        }
        this.el.querySelector(".o_embroidery_error").classList.add("d-none");
        const set = (selector, text) => {
            this.el.querySelector(selector).textContent = text;
        };
        set(".o_embroidery_stitches", quote.stitch_count_formatted);
        set(".o_embroidery_colours", String(quote.color_count));
        set(".o_embroidery_changes", String(quote.color_change_count));
        set(".o_embroidery_duration", quote.duration || "-");
        set(".o_embroidery_size", quote.size || "-");
        set(".o_embroidery_price", quote.price_formatted);
        set(".o_embroidery_total", quote.total_formatted);
        set(".o_embroidery_tax", quote.tax_included ? _t("(incl. tax)") : _t("(excl. tax)"));

        const preview = this.el.querySelector(".o_embroidery_preview");
        preview.classList.toggle("d-none", !quote.preview);
        if (quote.preview) {
            preview.src = quote.preview;
        }

        const tbody = this.el.querySelector(".o_embroidery_colors tbody");
        tbody.replaceChildren();
        quote.colors.forEach((color, index) => {
            const row = document.createElement("tr");
            const numberCell = document.createElement("td");
            numberCell.textContent = String(index + 1);
            const nameCell = document.createElement("td");
            const swatch = document.createElement("span");
            swatch.className = "d-inline-block rounded-circle border me-2 align-middle";
            swatch.style.width = swatch.style.height = "1rem";
            swatch.style.background = color.hex || "transparent";
            nameCell.append(swatch, document.createTextNode(color.name || _t("Colour %s", index + 1)));
            const stitchCell = document.createElement("td");
            stitchCell.className = "text-end text-nowrap";
            stitchCell.textContent = color.stitches;
            row.append(numberCell, nameCell, stitchCell);
            tbody.append(row);
        });

        const warnings = this.el.querySelector(".o_embroidery_warnings");
        warnings.replaceChildren(
            ...quote.warnings.map((text) => {
                const li = document.createElement("li");
                li.textContent = text;
                return li;
            })
        );
        this.el.querySelector(".o_embroidery_add_to_cart").disabled = !quote.price;
        result.classList.remove("d-none");
    }
}

registry.category("public.interactions").add("embroidery_submission.embroidery_quote", EmbroideryQuote);
