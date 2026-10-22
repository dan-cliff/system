/* Live Sales Counter - animated world map (spinning globe or flat map).
 *
 * Land is drawn as a grid of dots (world_data.js). Every buyer town in the
 * period glows; each new sale flies in as an arc from the shop to the buyer,
 * with a ripple and a label. Plain canvas, no libraries.
 */
(function () {
    'use strict';

    const DEG = Math.PI / 180;
    const SPIN_DEG_PER_SEC = 5;
    const FOCUS_MS = 1600;
    const FOCUS_HOLD_MS = 7000;
    const ARC_MS = 1400;
    const RIPPLE_MS = 2600;
    const LABEL_MS = 6500;
    const FLAT_TOP = 84;
    const FLAT_BOTTOM = -57;

    const THEMES = {
        dark: {
            land: [120, 150, 200],
            place: [54, 241, 164],
            arc: [54, 241, 164],
            arcHead: [255, 255, 255],
            store: [255, 196, 64],
            glow: 'rgba(54, 120, 255, 0.20)',
            sphere: 'rgba(14, 24, 48, 0.85)',
        },
        light: {
            land: [70, 90, 130],
            place: [0, 158, 104],
            arc: [0, 158, 104],
            arcHead: [0, 90, 60],
            store: [214, 128, 0],
            glow: 'rgba(60, 110, 220, 0.12)',
            sphere: 'rgba(225, 233, 248, 0.9)',
        },
    };

    function rgba(c, a) {
        return `rgba(${c[0]}, ${c[1]}, ${c[2]}, ${a})`;
    }

    function easeInOut(t) {
        return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
    }

    function wrapDeg(d) {
        return ((d + 540) % 360) - 180;
    }

    function toVec(lat, lng) {
        const cl = Math.cos(lat * DEG);
        return [cl * Math.cos(lng * DEG), cl * Math.sin(lng * DEG), Math.sin(lat * DEG)];
    }

    function toLatLng(v) {
        const r = Math.hypot(v[0], v[1], v[2]);
        return [Math.asin(v[2] / r) / DEG, Math.atan2(v[1], v[0]) / DEG];
    }

    /** Points along the great circle from a to b ([lat, lng]); t in 0..1. */
    function slerp(a, b, t) {
        const va = toVec(a[0], a[1]);
        const vb = toVec(b[0], b[1]);
        const dot = Math.min(1, Math.max(-1, va[0] * vb[0] + va[1] * vb[1] + va[2] * vb[2]));
        const omega = Math.acos(dot);
        if (omega < 1e-6) {
            return a;
        }
        const s = Math.sin(omega);
        const ka = Math.sin((1 - t) * omega) / s;
        const kb = Math.sin(t * omega) / s;
        return toLatLng([ka * va[0] + kb * vb[0], ka * va[1] + kb * vb[1], ka * va[2] + kb * vb[2]]);
    }

    function angleBetween(a, b) {
        const va = toVec(a[0], a[1]);
        const vb = toVec(b[0], b[1]);
        return Math.acos(Math.min(1, Math.max(-1, va[0] * vb[0] + va[1] * vb[1] + va[2] * vb[2])));
    }

    class LiveMap {
        constructor(canvas, labels, options) {
            this.canvas = canvas;
            this.ctx = canvas.getContext('2d');
            this.labels = labels;
            this.style = options.style === 'flat' ? 'flat' : 'globe';
            this.theme = THEMES[options.dark ? 'dark' : 'light'];
            this.world = window.LSC_WORLD || { dots: [], centroids: {} };
            this.store = null;
            this.places = [];
            this.sales = [];
            this.lon0 = 0;
            this.lat0 = 20;
            this.focus = null;
            this.dragging = null;
            this.lastFrame = 0;
            this.reducedMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

            const dots = this.world.dots;
            const n = dots.length / 2;
            this.dotCount = n;
            this.dotLat = new Float32Array(n);
            this.dotLng = new Float32Array(n);
            this.dotCosLat = new Float32Array(n);
            this.dotSinLat = new Float32Array(n);
            for (let i = 0; i < n; i++) {
                const lat = dots[2 * i] / 10;
                const lng = dots[2 * i + 1] / 10;
                this.dotLat[i] = lat;
                this.dotLng[i] = lng;
                this.dotCosLat[i] = Math.cos(lat * DEG);
                this.dotSinLat[i] = Math.sin(lat * DEG);
            }

            this._resize = this._resize.bind(this);
            this._frame = this._frame.bind(this);
            if (window.ResizeObserver) {
                new ResizeObserver(this._resize).observe(canvas.parentElement);
            } else {
                window.addEventListener('resize', this._resize);
            }
            this._bindDrag();
            this._resize();
            requestAnimationFrame(this._frame);
        }

        // ── Data ───────────────────────────────────────────────────────────
        /** [lat, lng] of a location, or of its country when the town is not geocoded yet. */
        position(loc) {
            if (!loc) {
                return null;
            }
            if (loc.lat !== null && loc.lat !== undefined && loc.lng !== null && loc.lng !== undefined) {
                return [loc.lat, loc.lng];
            }
            const c = loc.country_code && this.world.centroids[loc.country_code];
            return c ? [c[0], c[1]] : null;
        }

        setStore(loc) {
            const first = !this.store;
            this.store = this.position(loc);
            if (first && this.store) {
                this.lon0 = this.store[1];
                this.lat0 = Math.max(-35, Math.min(35, this.store[0] * 0.6));
            }
        }

        setPlaces(places) {
            this.places = places
                .map((p) => ({ pos: this.position(p), count: p.count || 1 }))
                .filter((p) => p.pos);
        }

        addPlace(pos) {
            const near = this.places.find(
                (p) => Math.abs(p.pos[0] - pos[0]) < 0.05 && Math.abs(p.pos[1] - pos[1]) < 0.05,
            );
            if (near) {
                near.count += 1;
            } else {
                this.places.push({ pos, count: 1 });
            }
        }

        /** Animate a new sale: an arc from the shop and a ripple at the buyer. */
        addSale(sale, labelText) {
            const pos = sale.in_store ? this.store : this.position(sale);
            if (!pos) {
                return;
            }
            const now = performance.now();
            const fromStore = this.store && !sale.in_store && angleBetween(this.store, pos) > 0.004;
            this.sales.push({
                from: fromStore ? this.store : null,
                to: pos,
                start: now,
                landed: !fromStore,
                label: this._makeLabel(labelText),
            });
            if (this.style === 'globe' && !this.dragging) {
                const target = fromStore ? slerp(this.store, pos, 0.6) : pos;
                this.focus = {
                    fromLon: this.lon0,
                    fromLat: this.lat0,
                    toLon: target[1],
                    toLat: Math.max(-40, Math.min(40, target[0] * 0.7)),
                    start: now,
                };
            }
            if (this.sales.length > 40) {
                this.sales.splice(0, this.sales.length - 40).forEach((s) => s.label && s.label.remove());
            }
        }

        _makeLabel(text) {
            if (!text || !this.labels) {
                return null;
            }
            const el = document.createElement('div');
            el.className = 'ls-map-label';
            el.textContent = text;
            el.style.opacity = '0';
            this.labels.appendChild(el);
            return el;
        }

        // ── Layout / input ─────────────────────────────────────────────────
        _resize() {
            const rect = this.canvas.parentElement.getBoundingClientRect();
            const dpr = Math.min(window.devicePixelRatio || 1, 2);
            this.width = Math.max(rect.width, 50);
            this.height = Math.max(rect.height, 50);
            this.canvas.width = Math.round(this.width * dpr);
            this.canvas.height = Math.round(this.height * dpr);
            this.canvas.style.width = `${this.width}px`;
            this.canvas.style.height = `${this.height}px`;
            this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
            if (this.style === 'globe') {
                this.radius = Math.min(this.width, this.height) * 0.44;
                this.cx = this.width / 2;
                this.cy = this.height / 2;
                this.dotSize = Math.max(1.2, this.radius / 190);
            } else {
                const aspect = 360 / (FLAT_TOP - FLAT_BOTTOM);
                let w = this.width * 0.96;
                let h = w / aspect;
                if (h > this.height * 0.96) {
                    h = this.height * 0.96;
                    w = h * aspect;
                }
                this.flat = { x: (this.width - w) / 2, y: (this.height - h) / 2, w, h };
                this.dotSize = Math.max(1.1, w / 520);
            }
        }

        _bindDrag() {
            if (this.style !== 'globe') {
                return;
            }
            const canvas = this.canvas;
            canvas.addEventListener('pointerdown', (ev) => {
                this.dragging = { x: ev.clientX, y: ev.clientY, lon: this.lon0, lat: this.lat0 };
                this.focus = null;
                canvas.setPointerCapture(ev.pointerId);
            });
            canvas.addEventListener('pointermove', (ev) => {
                if (!this.dragging) {
                    return;
                }
                const k = 90 / this.radius;
                this.lon0 = this.dragging.lon - (ev.clientX - this.dragging.x) * k;
                this.lat0 = Math.max(-70, Math.min(70, this.dragging.lat + (ev.clientY - this.dragging.y) * k));
            });
            const end = () => {
                this.dragging = null;
            };
            canvas.addEventListener('pointerup', end);
            canvas.addEventListener('pointercancel', end);
        }

        // ── Projection ─────────────────────────────────────────────────────
        /** Screen position of [lat, lng] lifted ``alt`` (fraction of the radius); null when hidden. */
        project(lat, lng, alt) {
            if (this.style === 'flat') {
                const f = this.flat;
                return {
                    x: f.x + ((wrapDeg(lng) + 180) / 360) * f.w,
                    y: f.y + ((FLAT_TOP - lat) / (FLAT_TOP - FLAT_BOTTOM)) * f.h - (alt || 0) * f.h,
                    z: 1,
                };
            }
            const r = this.radius * (1 + (alt || 0));
            const cl = Math.cos(lat * DEG);
            const dl = (lng - this.lon0) * DEG;
            const x = cl * Math.sin(dl);
            const y = Math.sin(lat * DEG);
            const z = cl * Math.cos(dl);
            const sp = Math.sin(this.lat0 * DEG);
            const cp = Math.cos(this.lat0 * DEG);
            const y2 = y * cp - z * sp;
            const z2 = y * sp + z * cp;
            const px = this.cx + r * x;
            const py = this.cy - r * y2;
            // Lifted points stay visible while they are outside the globe's disc.
            const visible = z2 > 0 || (alt && Math.hypot(px - this.cx, py - this.cy) > this.radius);
            return visible ? { x: px, y: py, z: z2 } : null;
        }

        // ── Drawing ────────────────────────────────────────────────────────
        _frame(now) {
            const dt = this.lastFrame ? Math.min(now - this.lastFrame, 100) : 16;
            this.lastFrame = now;
            this._updateCamera(now, dt);
            this._draw(now);
            requestAnimationFrame(this._frame);
        }

        _updateCamera(now, dt) {
            if (this.style !== 'globe' || this.dragging) {
                return;
            }
            if (this.focus) {
                const t = Math.min(1, (now - this.focus.start) / FOCUS_MS);
                const e = easeInOut(t);
                const dLon = wrapDeg(this.focus.toLon - this.focus.fromLon);
                this.lon0 = this.focus.fromLon + dLon * e;
                this.lat0 = this.focus.fromLat + (this.focus.toLat - this.focus.fromLat) * e;
                if (now - this.focus.start > FOCUS_MS + FOCUS_HOLD_MS) {
                    this.focus = null;
                }
            } else if (!this.reducedMotion) {
                this.lon0 += (SPIN_DEG_PER_SEC * dt) / 1000;
            }
            this.lon0 = wrapDeg(this.lon0);
        }

        _draw(now) {
            const ctx = this.ctx;
            const th = this.theme;
            ctx.clearRect(0, 0, this.width, this.height);

            if (this.style === 'globe') {
                const glow = ctx.createRadialGradient(
                    this.cx, this.cy, this.radius * 0.9, this.cx, this.cy, this.radius * 1.25);
                glow.addColorStop(0, th.glow);
                glow.addColorStop(1, 'rgba(0, 0, 0, 0)');
                ctx.fillStyle = glow;
                ctx.beginPath();
                ctx.arc(this.cx, this.cy, this.radius * 1.25, 0, 2 * Math.PI);
                ctx.fill();
                ctx.fillStyle = th.sphere;
                ctx.beginPath();
                ctx.arc(this.cx, this.cy, this.radius, 0, 2 * Math.PI);
                ctx.fill();
            }

            this._drawLand();
            this._drawPlaces(now);
            this._drawStore(now);
            this._drawSales(now);
        }

        _drawLand() {
            const ctx = this.ctx;
            const land = this.theme.land;
            const size = this.dotSize;
            const half = size / 2;
            if (this.style === 'flat') {
                const f = this.flat;
                ctx.fillStyle = rgba(land, 0.45);
                for (let i = 0; i < this.dotCount; i++) {
                    const x = f.x + ((this.dotLng[i] + 180) / 360) * f.w;
                    const y = f.y + ((FLAT_TOP - this.dotLat[i]) / (FLAT_TOP - FLAT_BOTTOM)) * f.h;
                    ctx.fillRect(x - half, y - half, size, size);
                }
                return;
            }
            const sp = Math.sin(this.lat0 * DEG);
            const cp = Math.cos(this.lat0 * DEG);
            const r = this.radius;
            // Bucket by depth so the limb fades without a fillStyle per dot.
            const buckets = [[], [], [], []];
            for (let i = 0; i < this.dotCount; i++) {
                const dl = (this.dotLng[i] - this.lon0) * DEG;
                const cl = this.dotCosLat[i];
                const z = cl * Math.cos(dl);
                const y = this.dotSinLat[i];
                const z2 = y * sp + z * cp;
                if (z2 <= 0.02) {
                    continue;
                }
                const x = this.cx + r * cl * Math.sin(dl);
                const y2 = this.cy - r * (y * cp - z * sp);
                buckets[Math.min(3, Math.floor(z2 * 4))].push(x, y2);
            }
            const alphas = [0.18, 0.32, 0.48, 0.62];
            for (let b = 0; b < 4; b++) {
                ctx.fillStyle = rgba(land, alphas[b]);
                const pts = buckets[b];
                for (let j = 0; j < pts.length; j += 2) {
                    ctx.fillRect(pts[j] - half, pts[j + 1] - half, size, size);
                }
            }
        }

        _glowDot(x, y, radius, color, alpha) {
            const ctx = this.ctx;
            const g = ctx.createRadialGradient(x, y, 0, x, y, radius * 3);
            g.addColorStop(0, rgba(color, 0.55 * alpha));
            g.addColorStop(1, rgba(color, 0));
            ctx.fillStyle = g;
            ctx.beginPath();
            ctx.arc(x, y, radius * 3, 0, 2 * Math.PI);
            ctx.fill();
            ctx.fillStyle = rgba(color, alpha);
            ctx.beginPath();
            ctx.arc(x, y, radius, 0, 2 * Math.PI);
            ctx.fill();
        }

        _drawPlaces(now) {
            const pulse = 0.8 + 0.2 * Math.sin(now / 700);
            for (const place of this.places) {
                const p = this.project(place.pos[0], place.pos[1]);
                if (!p) {
                    continue;
                }
                const radius = (this.dotSize * 1.2 + Math.log2(place.count + 1) * 1.3) * pulse;
                this._glowDot(p.x, p.y, radius, this.theme.place, 0.55 + 0.45 * Math.min(1, p.z * 1.5));
            }
        }

        _drawStore(now) {
            if (!this.store) {
                return;
            }
            const p = this.project(this.store[0], this.store[1]);
            if (!p) {
                return;
            }
            const ctx = this.ctx;
            const t = (now % 2400) / 2400;
            ctx.strokeStyle = rgba(this.theme.store, 0.6 * (1 - t));
            ctx.lineWidth = 1.5;
            ctx.beginPath();
            ctx.arc(p.x, p.y, 4 + t * 16, 0, 2 * Math.PI);
            ctx.stroke();
            this._glowDot(p.x, p.y, this.dotSize * 2, this.theme.store, 1);
        }

        _arcPoint(sale, t) {
            if (this.style === 'flat') {
                const a = this.project(sale.from[0], sale.from[1]);
                const b = this.project(sale.to[0], sale.to[1]);
                const lift = Math.min(0.35 * Math.hypot(b.x - a.x, b.y - a.y), this.flat.h * 0.3);
                const mx = (a.x + b.x) / 2;
                const my = (a.y + b.y) / 2 - lift;
                const u = 1 - t;
                return { x: u * u * a.x + 2 * u * t * mx + t * t * b.x, y: u * u * a.y + 2 * u * t * my + t * t * b.y };
            }
            const ll = slerp(sale.from, sale.to, t);
            const height = Math.min(0.45, 0.08 + angleBetween(sale.from, sale.to) * 0.25);
            return this.project(ll[0], ll[1], height * Math.sin(Math.PI * t));
        }

        _drawSales(now) {
            const ctx = this.ctx;
            const th = this.theme;
            for (const sale of this.sales) {
                const age = now - sale.start;
                const arcT = sale.from ? Math.min(1, age / ARC_MS) : 1;
                if (sale.from) {
                    const fade = age > ARC_MS ? Math.max(0, 1 - (age - ARC_MS) / 2500) : 1;
                    if (fade > 0) {
                        const steps = 48;
                        ctx.lineWidth = 2;
                        ctx.lineCap = 'round';
                        let prev = null;
                        for (let i = 0; i <= steps; i++) {
                            const t = (arcT * i) / steps;
                            const p = this._arcPoint(sale, t);
                            if (p && prev) {
                                ctx.strokeStyle = rgba(th.arc, fade * (0.25 + 0.75 * (i / steps)));
                                ctx.beginPath();
                                ctx.moveTo(prev.x, prev.y);
                                ctx.lineTo(p.x, p.y);
                                ctx.stroke();
                            }
                            prev = p;
                        }
                        if (arcT < 1 && prev) {
                            this._glowDot(prev.x, prev.y, 3, th.arcHead, 1);
                        }
                    }
                }
                const landedAt = sale.from ? ARC_MS : 0;
                if (age >= landedAt && !sale.landed) {
                    sale.landed = true;
                }
                const rippleAge = age - landedAt;
                const p = this.project(sale.to[0], sale.to[1]);
                if (rippleAge >= 0 && rippleAge < RIPPLE_MS && p) {
                    for (let k = 0; k < 3; k++) {
                        const rt = (rippleAge / RIPPLE_MS) - k * 0.18;
                        if (rt <= 0 || rt >= 1) {
                            continue;
                        }
                        ctx.strokeStyle = rgba(th.place, 0.9 * (1 - rt));
                        ctx.lineWidth = 2;
                        ctx.beginPath();
                        ctx.arc(p.x, p.y, 4 + rt * 42, 0, 2 * Math.PI);
                        ctx.stroke();
                    }
                    this._glowDot(p.x, p.y, 4, th.place, 1);
                }
                if (sale.label) {
                    const shown = rippleAge >= 0 && rippleAge < LABEL_MS && p;
                    if (shown) {
                        const op = Math.min(1, rippleAge / 300, (LABEL_MS - rippleAge) / 600);
                        sale.label.style.opacity = String(Math.max(0, op));
                        sale.label.style.transform = `translate(${p.x}px, ${p.y}px) translate(-50%, -150%)`;
                    } else {
                        sale.label.style.opacity = '0';
                    }
                }
            }
            const keepFrom = now - (ARC_MS + LABEL_MS + 1000);
            while (this.sales.length && this.sales[0].start < keepFrom) {
                const old = this.sales.shift();
                if (old.label) {
                    old.label.remove();
                }
            }
        }
    }

    window.LiveMap = LiveMap;
})();
