import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";
import { registry } from "@web/core/registry";
import { Interaction } from "@web/public/interaction";

const STEPS = ["upload", "read", "price"];

export class Print3dQuote extends Interaction {
    static selector = ".o_print3d_quote";
    dynamicContent = {
        ".o_print3d_submit": { "t-on-click": this.onSubmit },
        ".o_print3d_file, .o_print3d_material": { "t-on-keydown": this.onInputKeydown },
        ".o_print3d_quantity": { "t-on-change": this.onQuantityChange, "t-on-keydown": this.onInputKeydown },
        ".o_print3d_lines": { "t-on-change": this.onLineMaterialChange },
        ".o_print3d_add_to_cart": { "t-on-click": this.onAddToCart },
    };

    setup() {
        this.quote = null;
        this.busy = false;
        this.form = this.el.querySelector(".o_print3d_upload_form");
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
        const fileInput = this.form.querySelector(".o_print3d_file");
        if (!fileInput.files.length) {
            this.showError(_t("Choose a 3D print file to upload."));
            return;
        }
        const formData = new FormData();
        formData.append("csrf_token", odoo.csrf_token);
        formData.append("product_id", this.el.dataset.productId);
        formData.append("material_id", this.form.querySelector(".o_print3d_material").value);
        formData.append("quantity", String(this.quantity()));
        formData.append("file", fileInput.files[0]);
        this.startProgress();
        try {
            // The server reads the file and prices it in the same request;
            // move the progress on once the upload itself has gone through.
            const readTimer = setTimeout(() => this.setStep("read"), 1500);
            const response = await this.waitFor(
                fetch("/shop/3d-print-quote/upload", { method: "POST", body: formData })
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
        if (this.quote) {
            await this.refresh({});
        }
    }

    async onLineMaterialChange(ev) {
        const select = ev.target.closest("select[data-line-id]");
        if (!select || !this.quote) {
            return;
        }
        await this.refresh({ [select.dataset.lineId]: parseInt(select.value) });
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
                rpc("/shop/3d-print-quote/add-to-cart", {
                    estimate_id: this.quote.estimate_id,
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
        const input = this.el.querySelector(".o_print3d_quantity");
        return Math.max(parseInt(input?.value) || 1, 1);
    }

    async refresh(materials) {
        this.busy = true;
        try {
            this.quote = await this.waitFor(
                rpc("/shop/3d-print-quote/update", {
                    estimate_id: this.quote.estimate_id,
                    access_token: this.quote.access_token,
                    materials,
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

    startProgress() {
        this.busy = true;
        this.el.querySelector(".o_print3d_error").classList.add("d-none");
        this.el.querySelector(".o_print3d_result").classList.add("d-none");
        this.el.querySelector(".o_print3d_progress").classList.remove("d-none");
        this.form.querySelector(".o_print3d_submit").disabled = true;
        this.setStep("upload");
        const started = Date.now();
        const elapsed = this.el.querySelector(".o_print3d_elapsed");
        this.timer = setInterval(() => {
            const seconds = Math.round((Date.now() - started) / 1000);
            const minutes = Math.floor(seconds / 60);
            elapsed.textContent = `(${minutes}:${String(seconds % 60).padStart(2, "0")})`;
        }, 1000);
    }

    stopProgress() {
        this.busy = false;
        this.stopTimer();
        this.el.querySelector(".o_print3d_progress").classList.add("d-none");
        this.form.querySelector(".o_print3d_submit").disabled = false;
    }

    stopTimer() {
        if (this.timer) {
            clearInterval(this.timer);
            this.timer = null;
        }
    }

    setStep(step) {
        const current = STEPS.indexOf(step);
        for (const li of this.el.querySelectorAll(".o_print3d_steps li")) {
            const index = STEPS.indexOf(li.dataset.step);
            const icon = li.querySelector("i");
            icon.className =
                "me-2 fa " +
                (index < current ? "fa-check text-success" : index === current ? "fa-spinner fa-spin" : "fa-circle-o");
            li.classList.toggle("fw-bold", index === current);
        }
    }

    showError(message) {
        const box = this.el.querySelector(".o_print3d_error");
        box.textContent = message;
        box.classList.remove("d-none");
    }

    render() {
        const quote = this.quote;
        const result = this.el.querySelector(".o_print3d_result");
        if (quote.state !== "done") {
            result.classList.add("d-none");
            this.showError(quote.error || _t("Your file could not be read."));
            return;
        }
        this.el.querySelector(".o_print3d_error").classList.add("d-none");
        const set = (selector, text) => {
            this.el.querySelector(selector).textContent = text;
        };
        set(".o_print3d_filament_count", String(quote.filament_count));
        set(".o_print3d_total_filament", `${quote.total_filament_g} g (${quote.total_filament_m} m)`);
        set(".o_print3d_print_time", quote.print_time || "-");
        set(".o_print3d_size", quote.size);
        this.el.querySelector(".o_print3d_size_wrap").classList.toggle("d-none", !quote.size);
        set(".o_print3d_price", quote.price_formatted);
        set(".o_print3d_total", quote.total_formatted);
        set(".o_print3d_tax", quote.tax_included ? _t("(incl. tax)") : _t("(excl. tax)"));
        set(
            ".o_print3d_note",
            quote.sliced
                ? _t("Figures read from your sliced file%s.", quote.slicer ? ` (${quote.slicer})` : "")
                : _t("Estimated from your model's size - upload a sliced file for an exact price.")
        );

        const tbody = this.el.querySelector(".o_print3d_lines tbody");
        tbody.replaceChildren();
        for (const line of quote.lines) {
            const row = document.createElement("tr");

            const fileCell = document.createElement("td");
            const swatch = document.createElement("span");
            swatch.className = "d-inline-block rounded-circle border me-2 align-middle";
            swatch.style.width = swatch.style.height = "1rem";
            swatch.style.background = line.colour || "transparent";
            fileCell.append(swatch, document.createTextNode(line.file_material || _t("Filament %s", line.slot)));

            const materialCell = document.createElement("td");
            const select = document.createElement("select");
            select.className = "form-select form-select-sm";
            select.dataset.lineId = line.id;
            select.setAttribute("aria-label", _t("Material"));
            for (const material of quote.materials) {
                const option = document.createElement("option");
                option.value = material.id;
                option.textContent = material.name;
                option.selected = material.id === line.material_id;
                select.append(option);
            }
            if (!quote.materials.some((m) => m.id === line.material_id)) {
                const option = document.createElement("option");
                option.value = "";
                option.textContent = _t("Choose a material");
                option.selected = true;
                option.disabled = true;
                select.prepend(option);
            }
            materialCell.append(select);

            const weightCell = document.createElement("td");
            weightCell.className = "text-end text-nowrap";
            weightCell.textContent = `${line.weight_g} g`;

            row.append(fileCell, materialCell, weightCell);
            tbody.append(row);
        }

        const warnings = this.el.querySelector(".o_print3d_warnings");
        warnings.replaceChildren(
            ...quote.warnings.map((text) => {
                const li = document.createElement("li");
                li.textContent = text;
                return li;
            })
        );
        this.el.querySelector(".o_print3d_add_to_cart").disabled = !quote.price;
        result.classList.remove("d-none");
    }
}

registry.category("public.interactions").add("print_3d_calculator.print3d_quote", Print3dQuote);
