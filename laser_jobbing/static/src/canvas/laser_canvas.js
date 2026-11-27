/**
 * Draws a laser template and its variable elements in an <svg>, in mm.
 *
 * Shared by the backend visual editor (template design and job preview) and
 * the eCommerce personaliser, so it is plain JavaScript without OWL.
 *
 *   drawLaserCanvas(svg, data, {
 *       values: { [elementId]: { text, imageUrl, fileName } },
 *       mode: "fill" | "design",
 *       selectedId, onSelect(id), onMove(id, { x, y, w, h }),
 *   })
 *
 * data is laser.template.laser_editor_data(): { width, height, operation,
 * base_url, elements: [...], fixed_elements: [...] }.
 */

const SVG_NS = "http://www.w3.org/2000/svg";
const LINE_HEIGHT = 1.2;
const loadedFonts = new Map();
const loadedFamilies = new Map();

function svgEl(tag, attrs = {}, parent = null) {
    const el = document.createElementNS(SVG_NS, tag);
    for (const [key, value] of Object.entries(attrs)) {
        if (value !== undefined && value !== null && value !== false) {
            el.setAttribute(key, String(value));
        }
    }
    if (parent) {
        parent.appendChild(el);
    }
    return el;
}

/** Load an element's font file once; resolves with the family to use. */
export function loadLaserFont(element) {
    if (!element.font_url || !element.font_id || !window.FontFace) {
        return Promise.resolve(element.font_family || "sans-serif");
    }
    const family = `laser-font-${element.font_id}`;
    if (!loadedFonts.has(element.font_url)) {
        const face = new FontFace(family, `url(${element.font_url})`);
        loadedFonts.set(
            element.font_url,
            face
                .load()
                .then((loaded) => {
                    document.fonts.add(loaded);
                    const css = `"${family}", ${element.font_family || "sans-serif"}`;
                    loadedFamilies.set(element.font_url, css);
                    return css;
                })
                .catch(() => element.font_family || "sans-serif")
        );
    }
    return loadedFonts.get(element.font_url);
}

function fontFamilyNow(element) {
    // The family once its file has loaded, else the fallback (redrawn on load).
    return loadedFamilies.get(element.font_url) || element.font_family || "sans-serif";
}

function textLines(element, text) {
    const value = text || "";
    const lines = element.multiline ? value.split(/\r?\n/) : [value.replace(/\r?\n/g, " ")];
    return lines.length ? lines : [""];
}

function drawText(layer, element, text, operation) {
    const lines = textLines(element, text);
    if (!lines.some((line) => line.trim())) {
        return null;
    }
    const vector = operation === "cut" || operation === "score";
    const color = element.color || "#000000";
    const anchor = { left: "start", right: "end" }[element.align] || "middle";
    const x = { start: element.x, end: element.x + element.w }[anchor] ?? element.x + element.w / 2;
    let size = Math.max(element.font_size || 5, 0.1);
    const node = svgEl(
        "text",
        {
            "font-family": fontFamilyNow(element),
            "text-anchor": anchor,
            fill: vector ? "none" : color,
            stroke: vector ? color : null,
            "stroke-width": vector ? 0.15 : null,
        },
        layer
    );
    const place = () => {
        node.setAttribute("font-size", size);
        const lineHeight = LINE_HEIGHT * size;
        const top = element.y + (element.h - lines.length * lineHeight) / 2;
        node.replaceChildren();
        lines.forEach((line, index) => {
            const span = svgEl("tspan", { x, y: top + index * lineHeight + lineHeight / 2 + size * 0.35 }, node);
            span.textContent = line;
        });
    };
    place();
    if (element.auto_fit !== false) {
        let widest = 0;
        try {
            for (const span of node.childNodes) {
                widest = Math.max(widest, span.getComputedTextLength());
            }
        } catch {
            widest = 0; // not rendered (hidden): keep the size
        }
        const factor = Math.min(
            1,
            widest ? element.w / widest : 1,
            element.h / (lines.length * LINE_HEIGHT * size)
        );
        if (factor < 1) {
            size *= factor;
            place();
        }
    }
    return node;
}

function drawImage(layer, defs, element, url, index) {
    if (!url) {
        return null;
    }
    const cover = element.fit === "cover";
    let parent = layer;
    if (cover) {
        const clipId = `laser-clip-${index}-${Math.random().toString(36).slice(2, 8)}`;
        const clip = svgEl("clipPath", { id: clipId }, defs);
        svgEl("rect", { x: element.x, y: element.y, width: element.w, height: element.h }, clip);
        parent = svgEl("g", { "clip-path": `url(#${clipId})` }, layer);
    }
    return svgEl(
        "image",
        {
            href: url,
            x: element.x,
            y: element.y,
            width: element.w,
            height: element.h,
            preserveAspectRatio: cover ? "xMidYMid slice" : "xMidYMid meet",
        },
        parent
    );
}

function svgPoint(svg, event) {
    const point = svg.createSVGPoint();
    point.x = event.clientX;
    point.y = event.clientY;
    const matrix = svg.getScreenCTM();
    return matrix ? point.matrixTransform(matrix.inverse()) : { x: 0, y: 0 };
}

const round = (value) => Math.round(value * 10) / 10;

function makeDraggable(svg, group, element, data, options) {
    const startDrag = (event, resize) => {
        event.preventDefault();
        event.stopPropagation();
        options.onSelect?.(element.id);
        const start = svgPoint(svg, event);
        const box = { x: element.x, y: element.y, w: element.w, h: element.h };
        const rect = group.querySelector(".o_laser_box");
        const handle = group.querySelector(".o_laser_handle");
        let current = { ...box };
        const move = (ev) => {
            const point = svgPoint(svg, ev);
            const dx = point.x - start.x;
            const dy = point.y - start.y;
            if (resize) {
                current.w = Math.max(1, Math.min(data.width - box.x, box.w + dx));
                current.h = Math.max(1, Math.min(data.height - box.y, box.h + dy));
            } else {
                current.x = Math.max(0, Math.min(data.width - box.w, box.x + dx));
                current.y = Math.max(0, Math.min(data.height - box.h, box.y + dy));
            }
            rect.setAttribute("x", current.x);
            rect.setAttribute("y", current.y);
            rect.setAttribute("width", current.w);
            rect.setAttribute("height", current.h);
            handle.setAttribute("x", current.x + current.w - handleSize(data) / 2);
            handle.setAttribute("y", current.y + current.h - handleSize(data) / 2);
        };
        const up = () => {
            window.removeEventListener("pointermove", move);
            window.removeEventListener("pointerup", up);
            current = { x: round(current.x), y: round(current.y), w: round(current.w), h: round(current.h) };
            if (current.x !== box.x || current.y !== box.y || current.w !== box.w || current.h !== box.h) {
                options.onMove?.(element.id, current);
            }
        };
        window.addEventListener("pointermove", move);
        window.addEventListener("pointerup", up);
    };
    group.querySelector(".o_laser_box").addEventListener("pointerdown", (ev) => startDrag(ev, false));
    group.querySelector(".o_laser_handle").addEventListener("pointerdown", (ev) => startDrag(ev, true));
}

function handleSize(data) {
    return Math.max(Math.min(data.width, data.height) / 40, 1);
}

/** Redraw the whole canvas. */
export function drawLaserCanvas(svg, data, options = {}) {
    const values = options.values || {};
    const mode = options.mode || "fill";
    svg.replaceChildren();
    if (!data) {
        return;
    }
    svg.setAttribute("viewBox", `0 0 ${data.width} ${data.height}`);
    svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
    const defs = svgEl("defs", {}, svg);
    svgEl("rect", { x: 0, y: 0, width: data.width, height: data.height, class: "o_laser_artboard" }, svg);
    if (data.base_url) {
        svgEl(
            "image",
            {
                href: data.base_url,
                x: 0,
                y: 0,
                width: data.width,
                height: data.height,
                preserveAspectRatio: "xMidYMid meet",
            },
            svg
        );
    }
    const content = svgEl("g", {}, svg);
    const overlay = svgEl("g", {}, svg);
    const all = [
        ...(data.fixed_elements || []).map((el) => ({ el, fixed: true })),
        ...(data.elements || []).map((el) => ({ el, fixed: false })),
    ];
    const strokeWidth = Math.max(Math.min(data.width, data.height) / 300, 0.15);
    all.forEach(({ el, fixed }, index) => {
        const value = (!fixed && values[el.id]) || {};
        let drawn = null;
        if (el.type === "text") {
            const text = value.text !== undefined ? value.text : el.default_text;
            drawn = drawText(content, el, text, data.operation);
        } else {
            drawn = drawImage(content, defs, el, value.imageUrl || el.default_image_url, index);
        }
        if (fixed) {
            return;
        }
        const placeholder = !drawn && mode === "fill" && options.placeholders !== false;
        if (mode !== "design" && !placeholder && el.id !== options.selectedId) {
            return;
        }
        const group = svgEl("g", { class: "o_laser_element", "data-id": el.id }, overlay);
        svgEl(
            "rect",
            {
                class: "o_laser_box" + (el.id === options.selectedId ? " o_laser_selected" : ""),
                x: el.x,
                y: el.y,
                width: el.w,
                height: el.h,
                "stroke-width": strokeWidth,
                "stroke-dasharray": `${strokeWidth * 4} ${strokeWidth * 3}`,
            },
            group
        );
        if (mode === "design") {
            // A small tag in the box's top left corner, clear of the content.
            const size = Math.max(Math.min(data.width, data.height) / 28, 0.8);
            const label = svgEl(
                "text",
                { class: "o_laser_label o_laser_tag", x: el.x + size * 0.3, y: el.y + size * 1.05, "font-size": size },
                group
            );
            label.textContent = el.name;
        } else if (placeholder) {
            const label = svgEl(
                "text",
                {
                    class: "o_laser_label",
                    x: el.x + el.w / 2,
                    y: el.y + el.h / 2,
                    "font-size": Math.max(Math.min(el.h * 0.35, el.w / Math.max(el.name.length, 1)), 0.5),
                    "text-anchor": "middle",
                    "dominant-baseline": "middle",
                },
                group
            );
            label.textContent = value.fileName || el.name;
        }
        if (mode === "design") {
            const size = handleSize(data);
            svgEl(
                "rect",
                {
                    class: "o_laser_handle",
                    x: el.x + el.w - size / 2,
                    y: el.y + el.h - size / 2,
                    width: size,
                    height: size,
                },
                group
            );
            makeDraggable(svg, group, el, data, options);
        } else if (options.onSelect) {
            group.addEventListener("click", () => options.onSelect(el.id));
        }
    });
}

/** Load every font the template uses, then call redraw (fonts change text widths). */
export function whenLaserFontsLoaded(data, redraw) {
    const elements = [...(data?.elements || []), ...(data?.fixed_elements || [])].filter(
        (el) => el.type === "text" && el.font_url
    );
    if (!elements.length) {
        return;
    }
    if (elements.every((el) => loadedFamilies.has(el.font_url))) {
        return;
    }
    Promise.all(elements.map((el) => loadLaserFont(el))).then(redraw);
}

/** A data: URL for a file picked in the browser, when browsers can show it. */
export function browserImageUrl(file) {
    if (!file) {
        return "";
    }
    const ext = (file.name.split(".").pop() || "").toLowerCase();
    if (!["png", "jpg", "jpeg", "gif", "webp", "bmp", "svg"].includes(ext)) {
        return "";
    }
    return URL.createObjectURL(file);
}
