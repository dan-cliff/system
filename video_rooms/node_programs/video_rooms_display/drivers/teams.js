/** Microsoft Teams (web, anonymous guest). The first driver: everything comes from
 *  selectors.json except the launcher URL, which Teams accepts with a web-join hint. */
(function () {
    window.__vrHooks = window.__vrHooks || {};
    window.__vrHooks.teams = {
        /** Teams v2 sometimes keeps the room on "How do you want to join?": nudge it to the web app. */
        beforeStep(params) {
            const { find, click } = window.__vrDriverBase;
            const signIn = find([{ text: "^sign in$" }]);
            const guest = find([{ text: "^(join as a guest|continue without signing in)$" }]);
            if (signIn && guest) {
                click(guest);
                return true;
            }
            return false;
        },
    };
})();
