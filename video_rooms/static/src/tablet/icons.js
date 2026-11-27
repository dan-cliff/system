/** Simple geometric glyphs for the tablet apps (Video Rooms icon style: no text, rounded). */
const P = {
    join: '<rect x="3" y="6" width="13" height="12" rx="3"/><path d="M16 10l5-3v10l-5-3z"/>',
    today: '<rect x="3" y="5" width="18" height="16" rx="2"/><rect x="3" y="5" width="18" height="5" rx="2"/><rect x="7" y="13" width="4" height="4" rx="1" fill="#fff"/>',
    mic: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M6 11a6 6 0 0012 0M12 17v4" fill="none" stroke="currentColor" stroke-width="2"/>',
    mic_off: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M6 11a6 6 0 0012 0M12 17v4" fill="none" stroke="currentColor" stroke-width="2"/><path d="M4 4l16 16" stroke="currentColor" stroke-width="2.4"/>',
    camera: '<rect x="3" y="7" width="13" height="10" rx="2"/><path d="M16 11l5-3v8l-5-3z"/>',
    camera_off: '<rect x="3" y="7" width="13" height="10" rx="2"/><path d="M16 11l5-3v8l-5-3z"/><path d="M3 4l17 17" stroke="currentColor" stroke-width="2.4"/>',
    volume: '<path d="M4 9h4l5-4v14l-5-4H4z"/><path d="M16 9a4 4 0 010 6M18.5 6.5a7.5 7.5 0 010 11" fill="none" stroke="currentColor" stroke-width="2"/>',
    share: '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M12 7l3 3h-2v3h-2v-3H9z" fill="#fff"/><path d="M8 20h8" stroke="currentColor" stroke-width="2"/>',
    layout: '<rect x="3" y="4" width="8" height="7" rx="1.5"/><rect x="13" y="4" width="8" height="7" rx="1.5"/><rect x="3" y="13" width="8" height="7" rx="1.5"/><rect x="13" y="13" width="8" height="7" rx="1.5"/>',
    leave: '<path d="M3 13c5-5 13-5 18 0l-3 3-3-2v-2a9 9 0 00-6 0v2l-3 2z"/>',
    dnd: '<circle cx="12" cy="12" r="9"/><rect x="7" y="10.5" width="10" height="3" rx="1.5" fill="#fff"/>',
    ptz: '<circle cx="12" cy="11" r="6"/><circle cx="12" cy="11" r="2.5" fill="#fff"/><path d="M8 20h8" stroke="currentColor" stroke-width="2"/>',
    tv: '<rect x="3" y="5" width="18" height="12" rx="2"/><path d="M9 20h6" stroke="currentColor" stroke-width="2"/>',
    lighting: '<path d="M12 3a6 6 0 00-3.5 10.9V17h7v-3.1A6 6 0 0012 3z"/><rect x="9" y="18.5" width="6" height="2.5" rx="1"/>',
    climate: '<rect x="10" y="3" width="4" height="12" rx="2"/><circle cx="12" cy="17" r="4"/>',
    blinds: '<rect x="4" y="3" width="16" height="3" rx="1"/><rect x="4" y="8" width="16" height="3" rx="1"/><rect x="4" y="13" width="16" height="3" rx="1"/><path d="M12 16v5" stroke="currentColor" stroke-width="2"/>',
    glass: '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M4 21L20 5" stroke="#fff" stroke-width="2"/>',
    scenes: '<path d="M12 3l2.6 5.6 6 .7-4.5 4.1 1.2 6L12 16.4 6.7 19.4l1.2-6L3.4 9.3l6-.7z"/>',
    gear: '<circle cx="12" cy="12" r="3.2" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1" stroke="currentColor" stroke-width="2"/>',
    check: '<circle cx="12" cy="12" r="10"/><path d="M7 12.5l3 3 7-7" fill="none" stroke="#fff" stroke-width="2.4"/>',
};

export function icon(name, cls = "vr-ico") {
    const span = document.createElement("span");
    span.className = cls;
    span.innerHTML = `<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">${P[name] || P.today}</svg>`;
    return span;
}
