/** Google Meet (guest: "Ask to join", someone in the call admits the room). Layout is in
 *  More options › Change layout (Auto / Tiled / Spotlight / Sidebar). */
(function () {
    window.__vrHooks = window.__vrHooks || {};
    window.__vrHooks.google_meet = {
        setLayout(name) {
            const { find, click } = window.__vrDriverBase;
            click(find(this.s.layout_button));
            setTimeout(() => {
                click(find([{ text: "^change layout$" }]));
                const option = { gallery: "^tiled", speaker: "^spotlight", content: "^sidebar" }[name] || "^auto";
                setTimeout(() => {
                    click(find([{ text: option, tag: "label,[role=radio],span" }]));
                    setTimeout(() => click(find([{ label: "^close$" }])), 400);
                }, 600);
            }, 600);
            return this.state();
        },
    };
})();
