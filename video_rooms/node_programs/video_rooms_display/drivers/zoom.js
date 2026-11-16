/** Zoom (web client, guest). After joining, Zoom asks to "Join Audio by Computer". */
(function () {
    window.__vrHooks = window.__vrHooks || {};
    window.__vrHooks.zoom = {
        state(result) {
            const { find, click } = window.__vrDriverBase;
            if (result.state === "in_call") {
                click(find(this.s.join_audio));
            }
            if (/captcha|robot|human/i.test(result.error || "")) {
                result.error = "Zoom is asking to prove a person is joining: tap through it on the screen, or ask the host.";
            }
            return result;
        },
    };
})();
