/**
 * Video Rooms - platform driver base.
 *
 * room_agent.py injects this file, the platform's file and its selectors (from
 * selectors.json) into the meeting page through Chrome DevTools, in an isolated
 * world: the driver sees the page's DOM, not its scripts. The agent then calls
 * window.__vr.<method>(...) and gets plain JSON back.
 *
 * Joining is a series of steps the agent repeats (`step`) until the room is in the
 * call or the lobby, so a page load in between (launcher -> meeting app) is harmless.
 * Controls are found from candidate selectors (CSS, or button text): when a vendor
 * changes its page, selectors.json is fixed and released as a new program version.
 *
 * Clicks that must count as the user's own (screen sharing) and keyboard shortcuts
 * go through the agent (window.vrNative -> Input.dispatch* in DevTools).
 */
(function () {
    "use strict";
    if (window.__vrDriverBase) {
        return;
    }

    const visible = (el) => {
        if (!el || !el.isConnected) {
            return false;
        }
        const r = el.getBoundingClientRect();
        const s = getComputedStyle(el);
        return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none";
    };

    /** All elements, including inside open shadow roots (Webex, Meet use them). */
    function* everything(root = document) {
        const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
        let node = walker.currentNode;
        while (node) {
            yield node;
            if (node.shadowRoot) {
                yield* everything(node.shadowRoot);
            }
            node = walker.nextNode();
        }
    }

    function query(css) {
        let found = [...document.querySelectorAll(css)];
        if (!found.length) {
            for (const el of everything()) {
                if (el.shadowRoot) {
                    found = found.concat([...el.shadowRoot.querySelectorAll(css)]);
                }
            }
        }
        return found;
    }

    /**
     * The first visible element matching one of the candidates:
     * "css selector" | {css} | {text: "regex", tag: "button,a"} | {label: "regex"} (aria-label/title).
     */
    function find(candidates) {
        for (const c of [].concat(candidates || [])) {
            const spec = typeof c === "string" ? { css: c } : c;
            let list = [];
            if (spec.css) {
                list = query(spec.css);
            } else if (spec.text || spec.label) {
                const re = new RegExp(spec.text || spec.label, "i");
                const tags = (spec.tag || "button,a,[role=button],[role=menuitem],[role=option],span,div").split(",");
                for (const el of everything()) {
                    if (!tags.some((t) => el.matches?.(t.trim()))) {
                        continue;
                    }
                    const value = spec.text ? (el.innerText || el.textContent || "").trim() : (el.getAttribute("aria-label") || el.getAttribute("title") || "");
                    if (value && re.test(value) && (!spec.text || value.length < 80)) {
                        list.push(el);
                    }
                }
            }
            const el = list.find(visible);
            if (el) {
                return el;
            }
        }
        return null;
    }

    function pageText() {
        return (document.body?.innerText || "").slice(0, 20000);
    }

    function textMatches(pattern) {
        return pattern ? new RegExp(pattern, "i").test(pageText()) : false;
    }

    /** Ask the agent for a trusted click at the element's centre (counts as a user gesture). */
    function nativeClick(el) {
        const r = el.getBoundingClientRect();
        window.vrNative?.(JSON.stringify({ op: "click", x: r.left + r.width / 2, y: r.top + r.height / 2 }));
    }

    function nativeKeys(combo) {
        window.vrNative?.(JSON.stringify({ op: "keys", combo }));
    }

    function click(el, trusted = false) {
        if (!el) {
            return false;
        }
        el.scrollIntoView?.({ block: "center" });
        if (trusted && window.vrNative) {
            nativeClick(el);
        } else {
            el.click();
        }
        return true;
    }

    /** Type into a React/Angular input so the page notices. */
    function setValue(input, value) {
        const proto = input instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
        Object.getOwnPropertyDescriptor(proto, "value").set.call(input, value);
        input.dispatchEvent(new Event("input", { bubbles: true }));
        input.dispatchEvent(new Event("change", { bubbles: true }));
    }

    /** Is a toggle (mic / camera) on? From aria-pressed/checked, or its label ("Unmute" = off). */
    function toggleIsOn(el, offPattern) {
        if (!el) {
            return null;
        }
        for (const attr of ["aria-pressed", "aria-checked", "data-is-muted"]) {
            const value = el.getAttribute(attr);
            if (value === "true" || value === "false") {
                return attr === "data-is-muted" ? value !== "true" : value === "true";
            }
        }
        if (el.type === "checkbox") {
            return el.checked;
        }
        const label = `${el.getAttribute("aria-label") || ""} ${el.getAttribute("title") || ""} ${el.innerText || ""}`;
        return offPattern ? !new RegExp(offPattern, "i").test(label) : null;
    }

    class Driver {
        constructor(platform, selectors, hooks = {}) {
            this.platform = platform;
            this.s = selectors || {};
            this.hooks = hooks;
            this.joinParams = null;
            this.lastAction = "";
        }

        has(key) {
            return Boolean(find(this.s[key]));
        }

        /** What the page shows now. */
        state() {
            const s = this.s;
            let state = "idle";
            let error = "";
            if (textMatches(s.error_text)) {
                state = "error";
                error = (pageText().match(new RegExp(s.error_text, "i")) || [""])[0];
            } else if (textMatches(s.ended_text)) {
                state = "ended";
            } else if (this.has("in_call")) {
                state = "in_call";
            } else if (textMatches(s.lobby_text) || this.has("lobby")) {
                state = "lobby";
            } else if (this.has("join_button") || this.has("name_input") || this.has("open_in_browser")) {
                state = "prejoin";
            }
            const mic = toggleIsOn(find(state === "in_call" ? s.mic_button : s.prejoin_mic || s.mic_button), s.mic_off_label);
            const camera = toggleIsOn(find(state === "in_call" ? s.camera_button : s.prejoin_camera || s.camera_button), s.camera_off_label);
            const result = { state, error, mic, camera, sharing: this.has("stop_share"), action: this.lastAction };
            return this.hooks.state ? this.hooks.state.call(this, result) : result;
        }

        /** One step towards joining: returns the state after acting. */
        step(params) {
            this.joinParams = params || this.joinParams || {};
            const p = this.joinParams;
            const s = this.s;
            if (this.hooks.beforeStep && this.hooks.beforeStep.call(this, p)) {
                return this.state();
            }
            const current = this.state();
            if (["in_call", "lobby", "error", "ended"].includes(current.state)) {
                return current;
            }
            const openHere = find(s.open_in_browser);
            if (openHere) {
                this.lastAction = "open in browser";
                click(openHere);
                return this.state();
            }
            const name = find(s.name_input);
            if (name && name.value !== p.display_name && p.display_name) {
                this.lastAction = "name";
                setValue(name, p.display_name);
            }
            const email = find(s.email_input);
            if (email && p.email && email.value !== p.email) {
                setValue(email, p.email);
            }
            const passcode = find(s.passcode_input);
            if (passcode && p.passcode && passcode.value !== p.passcode) {
                setValue(passcode, p.passcode);
            }
            const mic = find(s.prejoin_mic);
            if (mic && p.mic != null && toggleIsOn(mic, s.mic_off_label) === !p.mic) {
                click(mic);
            }
            const camera = find(s.prejoin_camera);
            if (camera && p.camera != null && toggleIsOn(camera, s.camera_off_label) === !p.camera) {
                click(camera);
            }
            const join = find(s.join_button);
            if (join && !join.disabled && join.getAttribute("aria-disabled") !== "true") {
                this.lastAction = "join";
                click(join, true);
            }
            return this.state();
        }

        setMic(on) {
            return this._toggle("mic_button", "mic_off_label", on, this.s.mic_shortcut);
        }

        setCamera(on) {
            return this._toggle("camera_button", "camera_off_label", on, this.s.camera_shortcut);
        }

        _toggle(key, offKey, on, shortcut) {
            const el = find(this.s[key]);
            const current = toggleIsOn(el, this.s[offKey]);
            if (current === on) {
                return this.state();
            }
            if (el) {
                click(el);
            } else if (shortcut) {
                nativeKeys(shortcut);
            }
            return this.state();
        }

        /** Share the window titled ``title`` (Chrome picks it by itself: --auto-select-desktop-capture-source). */
        startShare(title) {
            if (this.hooks.startShare) {
                return this.hooks.startShare.call(this, title);
            }
            const button = find(this.s.share_button);
            if (!button && this.s.share_shortcut) {
                nativeKeys(this.s.share_shortcut);
                return this.state();
            }
            click(button, true);
            // Some platforms open a menu first (Screen / Window / Tab): pick a window.
            setTimeout(() => click(find(this.s.share_window_option), true), 700);
            return this.state();
        }

        stopShare() {
            click(find(this.s.stop_share));
            return this.state();
        }

        setLayout(name) {
            if (this.hooks.setLayout) {
                return this.hooks.setLayout.call(this, name);
            }
            const button = find(this.s.layout_button);
            if (button) {
                click(button);
                setTimeout(() => click(find((this.s.layout_options || {})[name])), 500);
            }
            return this.state();
        }

        leave() {
            const button = find(this.s.leave_button);
            if (button) {
                click(button);
                setTimeout(() => click(find(this.s.leave_confirm)), 600);
            } else if (this.s.leave_shortcut) {
                nativeKeys(this.s.leave_shortcut);
            }
            return this.state();
        }

        /** Keep a companion (content-only) instance silent. */
        silence() {
            for (const media of document.querySelectorAll("audio,video")) {
                media.muted = true;
            }
            return true;
        }

        /** Which of the platform's selectors match the current page (for the self-test). */
        selfTest() {
            const report = {};
            for (const [key, value] of Object.entries(this.s)) {
                if (Array.isArray(value) || typeof value === "object") {
                    report[key] = this.has(key);
                }
            }
            return { state: this.state().state, found: report };
        }
    }

    window.__vrDriverBase = { Driver, find, click, setValue, toggleIsOn, textMatches, nativeKeys, nativeClick };
    window.__vrMake = (platform, selectors, hooks) => {
        window.__vr = new Driver(platform, selectors, hooks);
        return true;
    };
})();
