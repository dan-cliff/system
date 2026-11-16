/** Cisco Webex (web app, guest: name and email, then Next, then Join meeting). */
(function () {
    window.__vrHooks = window.__vrHooks || {};
    window.__vrHooks.webex = {
        beforeStep(params) {
            const { find, click, setValue } = window.__vrDriverBase;
            const name = find(this.s.name_input);
            const email = find(this.s.email_input);
            const next = find(this.s.next_button);
            if (name && email && next) {
                if (params.display_name && name.value !== params.display_name) {
                    setValue(name, params.display_name);
                }
                if (params.email && email.value !== params.email) {
                    setValue(email, params.email);
                }
                if (!next.disabled) {
                    click(next);
                }
                return true;
            }
            return false;
        },
    };
})();
