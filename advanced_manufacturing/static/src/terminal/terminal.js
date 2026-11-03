/* Work Centre app - stand-alone PWA, no Odoo web client.
 *
 * Workers sign in with their ID badge (camera or reader) or their name and PIN,
 * as chosen in Manufacturing's Settings (the same ways as On Site's kiosks).
 * They start, pause and finish the work centre's work orders, record what they
 * produced (and its lot / serial number) and, with Checklists, fill in QA
 * checklists.
 *
 * Online, everything goes straight to Odoo. Offline, the app uses its copy of
 * the workers (hashed badge IDs and PINs) and work orders, keeps what workers
 * record in a queue (localStorage) and shows it as done; the queue is synced, in
 * order, when the connection returns. Offline use is limited to the hours set
 * in Settings, so the copy of the work orders never gets too old.
 */
(function () {
    'use strict';

    const TOKEN = document.body.dataset.token;
    const BASE = '/manufacturing/workcentre/' + TOKEN;
    const STORE = 'mrp-workcentre:' + TOKEN + ':';
    const SYNC_INTERVAL = 30 * 1000;
    const TOAST_TIME = 3500;
    const OFFLINE_PIN_ATTEMPTS = 5;

    const state = {
        config: null,
        employees: [],
        workorders: [],
        queue: [],
        online: null,
        lastContact: 0,     // last time Odoo answered (ms)
        lastRefresh: 0,
        dataTime: 0,        // when the work orders came from Odoo (ms)
        current: null,      // {employee, ticket}
        pinEmployee: null,
        pin: '',
        pinFailures: {},
        workorderId: null,
        qa: null,           // {workorder, template, answers}
        idleTimer: null,
        syncing: false,
        installPrompt: null,
    };

    class NetworkError extends Error {}

    // ── Helpers ─────────────────────────────────────────────────────────────
    const $ = (id) => document.getElementById(id);

    function el(tag, attrs, ...children) {
        const node = document.createElement(tag);
        for (const [key, value] of Object.entries(attrs || {})) {
            if (value === null || value === undefined || value === false) continue;
            if (key === 'class') node.className = value;
            else if (key === 'html') node.innerHTML = value;
            else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
            else node.setAttribute(key, value === true ? '' : value);
        }
        for (const child of children.flat()) {
            if (child === null || child === undefined || child === false) continue;
            node.append(child instanceof Node ? child : document.createTextNode(String(child)));
        }
        return node;
    }

    function load(key, fallback) {
        try {
            const raw = localStorage.getItem(STORE + key);
            return raw ? JSON.parse(raw) : fallback;
        } catch (e) {
            return fallback;
        }
    }

    function save(key, value) {
        try {
            localStorage.setItem(STORE + key, JSON.stringify(value));
            return true;
        } catch (e) {
            return false;  // storage full or blocked: keep working in memory
        }
    }

    function uuid() {
        if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
            const r = Math.random() * 16 | 0;
            return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
        });
    }

    async function sha256(text) {
        if (!(window.crypto && crypto.subtle)) return null;
        const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
        return Array.from(new Uint8Array(digest)).map((b) => b.toString(16).padStart(2, '0')).join('');
    }

    const pad = (n) => String(n).padStart(2, '0');
    const fmtTime = (d) => pad(d.getHours()) + ':' + pad(d.getMinutes());
    const fmtDate = (d) => pad(d.getDate()) + '/' + pad(d.getMonth() + 1) + '/' + d.getFullYear();
    const fmtStamp = (iso) => (iso ? fmtDate(new Date(iso)) + ' ' + fmtTime(new Date(iso)) : '');
    const fmtQty = (n) => (Math.round((Number(n) || 0) * 1000) / 1000).toLocaleString('en-AU');

    function fmtMinutes(minutes) {
        const total = Math.max(0, Math.round(minutes));
        return Math.floor(total / 60) + ':' + pad(total % 60);
    }

    function initials(name) {
        return (name || '?').split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0].toUpperCase()).join('');
    }

    function avatar(employee, size) {
        const img = el('img', { class: 'w-avatar w-avatar-' + size, alt: '', src: employee.avatar, loading: 'lazy' });
        img.addEventListener('error', () => img.replaceWith(
            el('div', { class: 'w-avatar w-avatar-' + size + ' w-avatar-initials' }, initials(employee.name))));
        return img;
    }

    // dd/mm/yyyy (HH:MM) <-> ISO, for the QA form's date answers.
    function parseDate(text, withTime) {
        const m = String(text || '').trim().match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})(?:\s+(\d{1,2}):(\d{2}))?$/);
        if (!m) return null;
        const d = new Date(+m[3], +m[2] - 1, +m[1], withTime ? +(m[4] || 0) : 0, withTime ? +(m[5] || 0) : 0);
        if (d.getDate() !== +m[1] || d.getMonth() !== +m[2] - 1) return null;
        return d;
    }

    // ── Toasts ──────────────────────────────────────────────────────────────
    function toast(kind, title, text) {
        const node = el('div', { class: 'w-toast w-toast-' + kind },
            el('div', { class: 'w-toast-title' }, title),
            text ? el('div', { class: 'w-toast-text' }, text) : null);
        $('w-toasts').append(node);
        setTimeout(() => node.classList.add('w-toast-out'), kind === 'error' ? TOAST_TIME * 2 : TOAST_TIME);
        setTimeout(() => node.remove(), (kind === "error" ? TOAST_TIME * 2 : TOAST_TIME) + 400);
    }

    // ── Network ─────────────────────────────────────────────────────────────
    async function request(path, body, timeout) {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), timeout || 15000);
        const options = body === undefined
            ? { cache: 'no-store', signal: controller.signal }
            : {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
                signal: controller.signal,
            };
        let response;
        try {
            response = await fetch(BASE + path, options);
        } catch (e) {
            setOnline(false);
            throw new NetworkError(e.message);
        } finally {
            clearTimeout(timer);
        }
        if (response.status >= 500) {
            setOnline(false);
            throw new NetworkError('Server error ' + response.status);
        }
        let data = {};
        try {
            data = await response.json();
        } catch (e) {
            // A captive portal or proxy page: not Odoo.
            setOnline(false);
            throw new NetworkError('Not Odoo');
        }
        state.lastContact = Date.now();
        save('contact', state.lastContact);
        setOnline(true);
        return { ok: response.ok, status: response.status, data: data };
    }

    function setOnline(online) {
        if (state.online === online) return;
        state.online = online;
        renderFooter();
        if (online) syncNow().catch(() => {});
    }

    /** Whether work may be recorded without Odoo right now. */
    function offlineAllowed(quiet) {
        const config = state.config;
        if (!config || !config.offline) {
            if (!quiet) toast('error', 'No connection', 'This work centre needs a connection to record work.');
            return false;
        }
        const hours = config.offline_hours || 24;
        if (state.lastContact && Date.now() - state.lastContact > hours * 3600 * 1000) {
            if (!quiet) {
                toast('error', 'Offline for too long',
                    'This work centre has been offline for more than ' + hours + ' hours. Connect it to the network to carry on.');
            }
            return false;
        }
        return true;
    }

    // ── Data ────────────────────────────────────────────────────────────────
    function employeeById(id) {
        return state.employees.find((e) => e.id === id);
    }

    function workorderById(id) {
        return state.workorders.find((w) => w.id === id);
    }

    function setData(data) {
        state.employees = data.employees || [];
        state.workorders = data.workorders || [];
        state.dataTime = Date.now();
        save('dataTime', state.dataTime);
        // Re-apply what this device recorded that Odoo has not seen yet.
        state.queue.forEach(applyLocally);
        save('employees', state.employees);
        save('workorders', state.workorders);
        if (state.current) {
            const fresh = employeeById(state.current.employee.id);
            if (fresh) state.current.employee = fresh;
        }
        render();
    }

    async function refresh(force) {
        const minutes = (state.config && state.config.refresh_minutes) || 5;
        if (!force && Date.now() - state.lastRefresh < minutes * 60 * 1000) return;
        try {
            await syncNow();
            const [config, data] = await Promise.all([request('/config.json'), request('/data.json', undefined, 30000)]);
            if (config.ok && data.ok) {
                state.config = config.data;
                save('config', state.config);
                state.lastRefresh = Date.now();
                renderConfig();
                setData(data.data);
            }
        } catch (e) {
            if (!(e instanceof NetworkError)) console.error(e);
        }
    }

    async function syncNow() {
        if (state.syncing || !state.queue.length) return true;
        state.syncing = true;
        try {
            const batch = state.queue.slice();
            const response = await request('/sync', { events: batch }, 60000);
            if (!response.ok) return false;
            const results = response.data.results || [];
            const done = new Set(results.map((r) => r.id));
            const failed = results.filter((r) => r.status === 'error');
            state.queue = state.queue.filter((ev) => !done.has(ev.id));
            save('queue', state.queue);
            if (failed.length) {
                toast('error', failed.length + ' offline record(s) could not be synced',
                    'Your supervisor can see them in the Work Centre App Log.');
            }
            if (response.data.data) setData(response.data.data);
            renderFooter();
            return true;
        } catch (e) {
            if (!(e instanceof NetworkError)) console.error(e);
            return false;
        } finally {
            state.syncing = false;
        }
    }

    /** Show an event as done on this device (mirrors what Odoo does with it). */
    function applyLocally(event) {
        const wo = workorderById(event.workorder_id);
        if (!wo) return;
        if (event.action === 'start') {
            if (!wo.running.some((r) => r.employee_id === event.employee_id)) {
                wo.running.push({ employee_id: event.employee_id, start: event.time });
            }
            wo.state = 'progress';
        } else if (event.action === 'pause') {
            wo.running = wo.running.filter((r) => r.employee_id !== event.employee_id);
        }
        if (event.action === 'produce' || event.action === 'finish') {
            if (event.qty) wo.qty_producing = Number(event.qty);
            if ('lot' in event && wo.tracking !== 'none') {
                const name = event.lot || (wo.lots.length ? wo.lots[0].name : 'New (on sync)');
                wo.lots = [{ id: null, name: name }];
            }
            state.workorders.filter((o) => o.production_id === wo.production_id && o !== wo)
                .forEach((o) => { o.qty_producing = wo.qty_producing; o.lots = wo.lots; });
        }
        if (event.action === 'finish') {
            state.workorders = state.workorders.filter((o) => o.id !== wo.id);
        } else if (event.action === 'qa') {
            wo.qa = wo.qa || [];
            wo.qa.push({ id: null, name: 'Waiting to sync', template: event.template_name || '', state: event.state });
        }
    }

    // ── Recording work ──────────────────────────────────────────────────────
    async function record(action, workorder, extra) {
        const current = state.current;
        if (!current) return false;
        const event = Object.assign({
            id: uuid(),
            action: action,
            workorder_id: workorder.id,
            employee_id: current.employee.id,
            time: new Date().toISOString(),
        }, extra || {});
        if (current.ticket) {
            try {
                if (!(await syncNow())) throw new NetworkError('sync failed');
                const response = await request('/action', {
                    ticket: current.ticket, employee_id: current.employee.id, event: event,
                }, 60000);
                const data = response.data || {};
                if (data.code === 'ticket') {
                    signOut();
                    toast('error', 'Please sign in again', '');
                    return false;
                }
                if (data.data) setData(data.data);
                if (!response.ok || data.status === 'error') {
                    toast('error', 'Not recorded', data.message || 'Something went wrong. Please try again.');
                    return false;
                }
                toast('success', 'Done', data.message || '');
                return true;
            } catch (e) {
                if (!(e instanceof NetworkError)) throw e;
            }
        }
        if (!offlineAllowed()) return false;
        state.queue.push(event);
        if (!save('queue', state.queue)) {
            toast('error', 'Device storage is full', 'Connect to the network so the work recorded here can sync.');
        }
        applyLocally(event);
        save('workorders', state.workorders);
        render();
        toast('success', 'Recorded offline', 'It will sync when the connection returns.');
        if (state.online !== false) syncNow().catch(() => {});
        return true;
    }

    // ── Screens ─────────────────────────────────────────────────────────────
    function show(screen) {
        document.querySelectorAll('.w-screen').forEach((s) => s.classList.toggle('w-active', s.id === 'screen-' + screen));
        document.body.dataset.screen = screen;
        if (screen === 'home') stopIdleTimer();
        else touch();
        if (screen === 'home' && state.config && state.config.identify_badge && !state.config.identify_reader) startCamera();
        else stopCamera();
        window.scrollTo(0, 0);
    }

    function current(screen) {
        return document.body.dataset.screen === screen;
    }

    function stopIdleTimer() {
        clearTimeout(state.idleTimer);
    }

    function touch() {
        clearTimeout(state.idleTimer);
        const minutes = state.config && state.config.idle_minutes;
        if (!state.current || !minutes) return;
        state.idleTimer = setTimeout(() => {
            if (current('qa')) return touch();  // never lose a checklist being filled in
            signOut();
        }, minutes * 60 * 1000);
    }

    function signOut() {
        state.current = null;
        state.workorderId = null;
        state.qa = null;
        state.pin = '';
        $('w-search').value = '';
        renderGrid();
        show('home');
    }

    function render() {
        renderFooter();
        if (current('home')) renderGrid();
        else if (current('orders')) renderOrders();
        else if (current('order')) {
            if (workorderById(state.workorderId)) renderOrder();
            else showOrders();
        }
    }

    function renderConfig() {
        const config = state.config;
        if (!config) return;
        $('w-name').textContent = config.name;
        $('w-place').textContent = (config.code ? config.code + ' · ' : '') + config.company;
        $('w-message').textContent = config.message || '';
        $('w-message').hidden = !config.message;
        // The external reader replaces the camera when both are on.
        const mode = config.identify_reader ? 'reader' : config.identify_badge ? 'camera' : null;
        $('w-scan').hidden = !mode;
        $('w-scan-camera').hidden = mode !== 'camera';
        $('w-scan-reader').hidden = mode !== 'reader';
        $('w-name-select').hidden = !config.identify_name;
        $('w-home').classList.toggle('w-home-split', Boolean(mode && config.identify_name));
        if (current('home')) {
            if (mode === 'camera') startCamera();
            else stopCamera();
        }
    }

    function renderFooter() {
        const conn = $('w-conn');
        conn.textContent = state.online === false ? 'Offline' : state.online ? 'Online' : 'Connecting...';
        conn.className = 'w-conn' + (state.online === false ? ' w-conn-off' : state.online ? ' w-conn-on' : '');
        const pending = $('w-pending');
        pending.hidden = !state.queue.length;
        pending.textContent = state.queue.length + ' waiting to sync';
        $('w-install-btn').hidden = !state.installPrompt;
        const user = $('w-user');
        if (state.current) {
            user.hidden = false;
            $('w-user-name').textContent = state.current.employee.name;
        } else {
            user.hidden = true;
        }
    }

    function tickClock() {
        const now = new Date();
        $('w-clock').textContent = fmtTime(now);
        $('w-date').textContent = now.toLocaleDateString('en-AU', { weekday: 'long' }) + ' ' + fmtDate(now);
        if (current('order')) updateTimers();
    }

    // ── Sign in ─────────────────────────────────────────────────────────────
    function renderGrid() {
        if (!state.config || !state.config.identify_name) return;
        const term = $('w-search').value.trim().toLowerCase();
        let employees = state.employees;
        if (term) employees = employees.filter((e) => e.name.toLowerCase().includes(term));
        const limit = 60;
        const working = new Set(state.workorders.flatMap((w) => w.running.map((r) => r.employee_id)));
        const tiles = employees.slice(0, limit).map((employee) => el('button', {
            type: 'button',
            class: 'w-tile' + (working.has(employee.id) ? ' w-tile-in' : ''),
            onclick: () => selectName(employee),
        },
        avatar(employee, 'sm'),
        el('span', { class: 'w-tile-name' }, employee.name),
        working.has(employee.id) ? el('span', { class: 'w-tile-status' }, 'Working') : null));
        if (!tiles.length) {
            tiles.push(el('div', { class: 'w-empty' }, state.employees.length ? 'No one matches that name.' : 'Loading workers...'));
        } else if (employees.length > limit) {
            tiles.push(el('div', { class: 'w-empty' }, 'Keep typing to find your name.'));
        }
        $('w-grid').replaceChildren(...tiles);
    }

    function normalizeBadge(code) {
        // eslint-disable-next-line no-control-regex
        return String(code || '').replace(/[\s\x00-\x1f\x7f]+/g, '').toUpperCase().replace(/^0+(?=.)/, '');
    }

    function signedIn(employee, ticket) {
        if (employee.refusals && employee.refusals.length) {
            toast('error', 'You cannot work here now', employee.refusals.join(' '));
            return;
        }
        state.current = { employee: employee, ticket: ticket };
        state.pin = '';
        renderFooter();
        toast('success', 'Hello, ' + employee.name.split(' ')[0], '');
        showOrders();
    }

    async function identifyBadge(code, method) {
        const config = state.config;
        if (!config || !code) return;
        if (method === 'badge' ? !config.identify_badge : !config.identify_reader) return;
        try {
            const response = await request('/identify', { method: method, badge: code });
            return handleIdentify(response);
        } catch (e) {
            if (!(e instanceof NetworkError)) throw e;
        }
        if (!offlineAllowed()) return;
        const hash = await sha256(config.salt + ':' + normalizeBadge(code));
        const employee = hash && state.employees.find((e) => e.badge === hash);
        if (!employee) {
            toast('error', 'Badge not recognised', 'Read: ' + JSON.stringify(code));
            return;
        }
        signedIn(employee, null);
    }

    function selectName(employee) {
        if (state.config.require_pin) {
            state.pinEmployee = employee;
            state.pin = '';
            $('w-pin-person').replaceChildren(avatar(employee, 'lg'), el('div', { class: 'w-person-name' }, employee.name));
            $('w-pin-message').textContent = '';
            renderPin();
            show('pin');
        } else {
            identifyName(employee, '');
        }
    }

    async function identifyName(employee, pin) {
        try {
            const response = await request('/identify', { method: 'name', employee_id: employee.id, pin: pin });
            if (response.data.code === 'bad_pin' || response.status === 429) {
                pinError(response.data.message);
                return;
            }
            return handleIdentify(response);
        } catch (e) {
            if (!(e instanceof NetworkError)) throw e;
        }
        if (!offlineAllowed()) return;
        if (state.config.require_pin) {
            if (!employee.has_pin) {
                toast('error', 'You do not have a PIN yet', 'Please see your supervisor.');
                show('home');
                return;
            }
            const failures = (state.pinFailures[employee.id] || []).filter((t) => Date.now() - t < 5 * 60 * 1000);
            if (failures.length >= OFFLINE_PIN_ATTEMPTS) {
                pinError('Too many wrong PINs. Please wait a few minutes and try again.');
                return;
            }
            const hash = await sha256(state.config.salt + ':' + pin);
            if (!hash || hash !== employee.pin) {
                failures.push(Date.now());
                state.pinFailures[employee.id] = failures;
                pinError('Wrong PIN. Please try again.');
                return;
            }
        }
        signedIn(employee, null);
    }

    function handleIdentify(response) {
        const data = response.data || {};
        if (!response.ok) {
            if (current('pin')) show('home');
            toast('error', data.message || 'Sign in is not available.',
                data.scanned !== undefined ? 'Read: ' + JSON.stringify(data.scanned) : '');
            return;
        }
        const fresh = data.employee;
        const known = employeeById(fresh.id);
        const employee = known ? Object.assign(known, fresh, { badge: known.badge, pin: known.pin }) : fresh;
        signedIn(employee, data.ticket);
    }

    function renderPin() {
        $('w-pin-dots').replaceChildren(...Array.from({ length: Math.max(4, state.pin.length) }, (_, i) =>
            el('span', { class: 'w-pin-dot' + (i < state.pin.length ? ' w-pin-dot-full' : '') })));
    }

    function pinKey(key) {
        touch();
        if (key === 'back') state.pin = state.pin.slice(0, -1);
        else if (key === 'ok') {
            if (state.pin && state.pinEmployee) identifyName(state.pinEmployee, state.pin);
            return;
        } else if (state.pin.length < 12) state.pin += key;
        $('w-pin-message').textContent = '';
        renderPin();
    }

    function pinError(message) {
        state.pin = '';
        renderPin();
        $('w-pin-message').textContent = message || 'Wrong PIN.';
        const dots = $('w-pin-dots');
        dots.classList.remove('w-shake');
        void dots.offsetWidth;
        dots.classList.add('w-shake');
        if (!current('pin')) show('pin');
    }

    function buildKeypad() {
        const keys = ['1', '2', '3', '4', '5', '6', '7', '8', '9', 'back', '0', 'ok'];
        $('w-keypad').replaceChildren(...keys.map((key) => el('button', {
            type: 'button',
            class: 'w-key' + (key === 'ok' ? ' w-key-ok' : ''),
            onclick: () => pinKey(key),
        }, key === 'back' ? '⌫' : key === 'ok' ? 'OK' : key)));
    }

    // ── Work orders ─────────────────────────────────────────────────────────
    const STATE_LABELS = { blocked: 'Waiting', ready: 'To Do', progress: 'In Progress' };

    function myRun(wo) {
        return state.current && wo.running.find((r) => r.employee_id === state.current.employee.id);
    }

    function showOrders() {
        state.workorderId = null;
        renderOrders();
        show('orders');
    }

    function renderOrders() {
        const orders = state.workorders.slice().sort((a, b) =>
            (myRun(b) ? 1 : 0) - (myRun(a) ? 1 : 0) || (b.priority ? 1 : 0) - (a.priority ? 1 : 0));
        const cards = orders.map((wo) => {
            const names = wo.running.map((r) => (employeeById(r.employee_id) || { name: '?' }).name);
            return el('button', {
                type: 'button',
                class: 'w-card w-card-' + wo.state + (myRun(wo) ? ' w-card-mine' : ''),
                onclick: () => openOrder(wo.id),
            },
            el('div', { class: 'w-card-top' },
                el('span', { class: 'w-card-mo' }, (wo.priority ? '★ ' : '') + wo.production),
                el('span', { class: 'w-badge w-badge-' + wo.state }, STATE_LABELS[wo.state] || wo.state)),
            el('div', { class: 'w-card-product' }, wo.product),
            el('div', { class: 'w-card-op' }, wo.name),
            el('div', { class: 'w-card-meta' },
                el('span', {}, fmtQty(wo.qty_remaining) + ' ' + wo.uom),
                wo.date_start ? el('span', {}, fmtStamp(wo.date_start)) : null),
            names.length ? el('div', { class: 'w-card-workers' }, '● ' + names.join(', ')) : null);
        });
        if (!cards.length) cards.push(el('div', { class: 'w-empty w-empty-lg' }, 'No work orders waiting at this work centre.'));
        $('w-orders').replaceChildren(...cards);
    }

    function openOrder(id) {
        state.workorderId = id;
        renderOrder();
        show('order');
    }

    function elapsedMinutes(wo) {
        let minutes = wo.duration || 0;
        // Odoo's duration already includes running timers up to the last refresh;
        // add the time since for the timers still running.
        const since = new Date(state.dataTime || Date.now());
        for (const run of wo.running) {
            const start = new Date(run.start);
            minutes += (Date.now() - Math.max(start.getTime(), since.getTime())) / 60000;
        }
        return minutes;
    }

    function updateTimers() {
        const wo = workorderById(state.workorderId);
        const node = $('w-elapsed');
        if (wo && node) node.textContent = fmtMinutes(elapsedMinutes(wo));
    }

    function section(title, ...children) {
        return el('section', { class: 'w-section' }, el('h3', {}, title), ...children);
    }

    function renderOrder() {
        const wo = workorderById(state.workorderId);
        if (!wo) return;
        const mine = myRun(wo);
        const names = wo.running.map((r) => (employeeById(r.employee_id) || { name: '?' }).name);
        const blocks = [];

        blocks.push(el('div', { class: 'w-order-head' },
            el('div', {},
                el('div', { class: 'w-order-mo' }, wo.production + ' · ' + wo.name),
                el('div', { class: 'w-order-product' }, wo.product),
                el('div', { class: 'w-order-meta' },
                    fmtQty(wo.qty_production) + ' ' + wo.uom + ' to make',
                    wo.date_deadline ? ' · due ' + fmtDate(new Date(wo.date_deadline)) : '')),
            el('span', { class: 'w-badge w-badge-' + wo.state }, STATE_LABELS[wo.state] || wo.state)));

        // Time
        blocks.push(section('Time',
            el('div', { class: 'w-time' },
                el('div', { class: 'w-elapsed', id: 'w-elapsed' }, fmtMinutes(elapsedMinutes(wo))),
                el('div', { class: 'w-expected' }, 'Expected ' + fmtMinutes(wo.duration_expected || 0))),
            names.length ? el('div', { class: 'w-working' }, 'Working now: ' + names.join(', ')) : null,
            el('div', { class: 'w-actions' },
                mine
                    ? el('button', { type: 'button', class: 'w-btn w-btn-warning w-btn-lg', onclick: () => record('pause', wo) }, 'Pause')
                    : el('button', {
                        type: 'button',
                        class: 'w-btn w-btn-primary w-btn-lg',
                        onclick: () => record('start', wo),
                    }, wo.state === 'progress' ? 'Join' : 'Start'))));

        if (wo.instructions) {
            blocks.push(section('Instructions', el('div', { class: 'w-instructions', html: wo.instructions })));
        }

        if (wo.components.length) {
            blocks.push(section('Components', el('table', { class: 'w-table' },
                el('tbody', {}, ...wo.components.map((c) => el('tr', {},
                    el('td', {}, c.product),
                    el('td', { class: 'w-num' }, fmtQty(c.qty) + ' ' + c.uom),
                    el('td', { class: c.available ? 'w-ok' : 'w-warn' }, c.available ? 'Available' : 'Not reserved')))))));
        }

        // Production
        const qtyInput = el('input', {
            type: 'number', inputmode: 'decimal', min: '0', step: 'any', class: 'w-input', id: 'w-qty',
            value: String(wo.qty_producing || wo.qty_remaining || ''),
        });
        const produce = [el('label', { class: 'w-field' }, el('span', {}, 'Quantity produced (' + wo.uom + ')'), qtyInput)];
        let lotInput = null;
        if (wo.tracking !== 'none') {
            lotInput = el('input', {
                type: 'text', class: 'w-input', id: 'w-lot', autocomplete: 'off',
                value: wo.lots.length ? wo.lots[0].name : '',
                placeholder: 'Leave empty to number it automatically',
            });
            produce.push(el('label', { class: 'w-field' },
                el('span', {}, wo.tracking === 'serial' ? 'Serial number' : 'Lot number'), lotInput));
        }
        const productionEvent = () => {
            const extra = { qty: qtyInput.value };
            if (lotInput) extra.lot = lotInput.value.trim();
            return extra;
        };
        produce.push(el('div', { class: 'w-actions' },
            el('button', { type: 'button', class: 'w-btn w-btn-light', onclick: () => record('produce', wo, productionEvent()) },
                'Save Quantity' + (lotInput ? ' and ' + (wo.tracking === 'serial' ? 'Serial' : 'Lot') : ''))));
        blocks.push(section('Production', ...produce));

        // QA (with Checklists)
        const qa = state.config.features && state.config.features.qa;
        if (qa && qa.templates && qa.templates.length) {
            const done = (wo.qa || []).map((c) => el('li', {},
                el('span', {}, c.name + (c.template ? ' · ' + c.template : '')),
                el('span', { class: 'w-badge ' + (c.state === 'done' ? 'w-badge-done' : 'w-badge-ready') },
                    c.state === 'done' ? 'Completed' : 'In Progress')));
            blocks.push(section('QA',
                done.length ? el('ul', { class: 'w-qa-list' }, ...done) : el('p', { class: 'w-muted' }, 'No QA checks yet for this order.'),
                el('div', { class: 'w-qa-templates' }, ...qa.templates.map((template) => el('button', {
                    type: 'button', class: 'w-btn w-btn-secondary', onclick: () => openQa(wo, template),
                }, '+ ' + template.name)))));
        }

        // Finish
        const finishLabel = wo.is_last && state.config.close_production ? 'Finish and Produce' : 'Finish Work Order';
        blocks.push(el('div', { class: 'w-actions w-actions-end' },
            el('button', {
                type: 'button', class: 'w-btn w-btn-success w-btn-lg',
                onclick: async () => {
                    if (!window.confirm(finishLabel + ' ' + wo.production + ' · ' + wo.name + '?')) return;
                    if (await record('finish', wo, productionEvent())) showOrders();
                },
            }, finishLabel)));

        $('w-order').replaceChildren(...blocks);
    }

    // ── QA checklists (with Checklists) ─────────────────────────────────────
    const SINGLE_OPTION_TYPES = ['buttons', 'select', 'radio', 'slider'];
    const MULTI_OPTION_TYPES = ['multi_select', 'multi_checkbox'];
    const TEXT_TYPES = ['text', 'text_area', 'phone', 'email', 'website'];
    const LAYOUT_TYPES = ['section_title', 'section_break', 'instructions'];

    /** What a question is filled in with from the work order, or undefined. */
    function prefillValue(question, wo) {
        const employee = state.current.employee;
        const now = new Date();
        const lot = wo.lots.length ? wo.lots[0] : null;
        switch (question.prefill) {
            case 'product': return { ref: { id: wo.product_id, name: wo.product } };
            case 'product_tmpl': return { ref: { id: wo.product_tmpl_id, name: wo.product } };
            case 'production': return { ref: { id: wo.production_id, name: wo.production } };
            case 'workorder': return { ref: { id: wo.id, name: wo.production + ' · ' + wo.name } };
            case 'workcenter': return { ref: { id: state.config.id, name: state.config.name } };
            case 'employee': return { ref: { id: employee.id, name: employee.name } };
            case 'lot': return lot ? { ref: { id: lot.id, name: lot.name } } : undefined;
            case 'text_product': return { value: wo.product };
            case 'text_production': return { value: wo.production };
            case 'text_workorder': return { value: wo.name };
            case 'text_workcenter': return { value: state.config.name };
            case 'text_employee': return { value: employee.name };
            case 'text_lot': return lot ? { value: lot.name } : undefined;
            case 'quantity': return { value: String(wo.qty_producing || wo.qty_production || '') };
            case 'date': return { value: fmtDate(now) };
            case 'datetime': return { value: fmtDate(now) + ' ' + fmtTime(now) };
        }
        return undefined;
    }

    function openQa(wo, template) {
        const answers = {};
        for (const question of template.questions) {
            const value = prefillValue(question, wo);
            if (value !== undefined) answers[question.id] = Object.assign({ prefilled: true }, value);
        }
        state.qa = { workorder: wo, template: template, answers: answers };
        renderQa();
        show('qa');
    }

    function answerOf(question) {
        const answer = state.qa.answers[question.id] || {};
        const kind = question.type;
        if (SINGLE_OPTION_TYPES.includes(kind)) return answer.option_id || false;
        if (MULTI_OPTION_TYPES.includes(kind)) return answer.option_ids || [];
        if (TEXT_TYPES.includes(kind)) return answer.value || '';
        switch (kind) {
            case 'number': return parseFloat(answer.value) || 0;
            case 'integer': return parseInt(answer.value, 10) || 0;
            case 'date': { const d = parseDate(answer.value, false); return d ? d.getTime() : false; }
            case 'datetime': { const d = parseDate(answer.value, true); if (!d) return false; d.setHours(0, 0, 0, 0); return d.getTime(); }
            case 'boolean': return Boolean(answer.value);
            case 'geolocation': return Boolean(answer.lat || answer.lng);
            case 'image': case 'file': return Boolean(answer.data);
            case 'many2one': return answer.ref ? answer.ref.id : false;
            case 'many2many': return answer.ref ? [answer.ref.id] : [];
        }
        return false;
    }

    function isAnswered(answer) {
        if (Array.isArray(answer)) return answer.length > 0;
        return answer !== false && answer !== null && answer !== undefined && answer !== '' && answer !== 0;
    }

    function compare(operator, a, b) {
        return { eq: a === b, ne: a !== b, gt: a > b, lt: a < b }[operator] || false;
    }

    // Mirrors evaluateRule in the Checklists app (checklist_checks/conditions.js).
    function evaluateRule(rule, answer) {
        const kind = rule.question_type;
        const operator = rule.operator;
        const value = rule.value || '';
        const options = rule.option_ids || [];
        const answered = isAnswered(answer);
        if (operator === 'set') return answered;
        if (operator === 'not_set') return !answered;
        if (SINGLE_OPTION_TYPES.includes(kind) || MULTI_OPTION_TYPES.includes(kind)) {
            const chosen = Array.isArray(answer) ? answer : answer ? [answer] : [];
            const overlap = chosen.some((id) => options.includes(id));
            if (operator === 'in' || operator === 'eq') return overlap;
            if (operator === 'not_in' || operator === 'ne') return !overlap;
            if (operator === 'contains') return options.every((id) => chosen.includes(id));
            return false;
        }
        if (kind === 'boolean') {
            const wanted = ['1', 'true', 'yes', 'y'].includes(value.trim().toLowerCase());
            return operator === 'eq' ? answer === wanted : operator === 'ne' ? answer !== wanted : false;
        }
        if (kind === 'number' || kind === 'integer') {
            const number = parseFloat(value.replace(/,/g, '').trim());
            return isNaN(number) ? false : compare(operator, answer || 0, number);
        }
        if (kind === 'date' || kind === 'datetime') {
            const wanted = parseDate(value, false);
            if (!wanted || !answer) return operator === 'ne' && !answer;
            return compare(operator, answer, wanted.getTime());
        }
        if (TEXT_TYPES.includes(kind)) {
            const text = (answer || '').trim().toLowerCase();
            const wanted = value.trim().toLowerCase();
            return operator === 'contains' ? text.includes(wanted) : compare(operator, text, wanted);
        }
        return false;
    }

    function visibleQuestions() {
        const questions = state.qa.template.questions;
        const byId = new Map(questions.map((q) => [q.id, q]));
        const cache = new Map();
        const isVisible = (question, seen) => {
            if (!question.conditional) return true;
            if (cache.has(question.id)) return cache.get(question.id);
            const results = (question.condition_rules || []).map((rule) => {
                const source = byId.get(rule.question_id);
                return Boolean(source) && !seen.has(source.id)
                    && isVisible(source, new Set([...seen, source.id])) && evaluateRule(rule, answerOf(source));
            });
            for (const key of ['user', 'record']) {
                if (question.condition_context && key in question.condition_context) {
                    results.push(Boolean(question.condition_context[key]));
                }
            }
            const visible = !results.length
                || (question.condition_logic === 'any' ? results.some(Boolean) : results.every(Boolean));
            cache.set(question.id, visible);
            return visible;
        };
        return new Set(questions.filter((q) => isVisible(q, new Set([q.id]))).map((q) => q.id));
    }

    function setAnswer(question, patch, rerender) {
        const answers = state.qa.answers;
        answers[question.id] = Object.assign({}, answers[question.id] || {}, patch, { prefilled: false });
        touch();
        if (rerender) renderQa();
        else applyVisibility();
    }

    function applyVisibility() {
        const visible = visibleQuestions();
        document.querySelectorAll('.w-q').forEach((node) => {
            node.hidden = !visible.has(Number(node.dataset.question));
        });
    }

    function readImage(file, maxSize) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onerror = reject;
            reader.onload = () => {
                const img = new Image();
                img.onerror = reject;
                img.onload = () => {
                    // Scaled down so it fits in the offline queue.
                    const scale = Math.min(1, maxSize / Math.max(img.width, img.height));
                    const canvas = document.createElement('canvas');
                    canvas.width = Math.round(img.width * scale);
                    canvas.height = Math.round(img.height * scale);
                    canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
                    resolve(canvas.toDataURL('image/jpeg', 0.82).split(',')[1]);
                };
                img.src = reader.result;
            };
            reader.readAsDataURL(file);
        });
    }

    function readFile(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onerror = reject;
            reader.onload = () => resolve(String(reader.result).split(',')[1]);
            reader.readAsDataURL(file);
        });
    }

    function questionInput(question) {
        const answer = state.qa.answers[question.id] || {};
        const kind = question.type;
        const name = 'q' + question.id;
        if (answer.ref) {
            return el('div', { class: 'w-prefilled' }, answer.ref.name);
        }
        if (SINGLE_OPTION_TYPES.includes(kind)) {
            return el('div', { class: 'w-choices' }, ...question.options.map((option) => el('button', {
                type: 'button',
                class: 'w-choice' + (answer.option_id === option.id ? ' w-choice-on' : ''),
                style: option.color && answer.option_id === option.id ? 'background:' + option.color + ';border-color:' + option.color : null,
                onclick: () => setAnswer(question, { option_id: answer.option_id === option.id ? false : option.id }, true),
            }, option.name)));
        }
        if (MULTI_OPTION_TYPES.includes(kind)) {
            const chosen = answer.option_ids || [];
            return el('div', { class: 'w-choices' }, ...question.options.map((option) => el('button', {
                type: 'button',
                class: 'w-choice' + (chosen.includes(option.id) ? ' w-choice-on' : ''),
                onclick: () => setAnswer(question, {
                    option_ids: chosen.includes(option.id) ? chosen.filter((id) => id !== option.id) : [...chosen, option.id],
                }, true),
            }, option.name)));
        }
        if (kind === 'boolean') {
            return el('div', { class: 'w-choices' },
                ...[[true, 'Yes'], [false, 'No']].map(([value, label]) => el('button', {
                    type: 'button',
                    class: 'w-choice' + (answer.value === value ? ' w-choice-on' : ''),
                    onclick: () => setAnswer(question, { value: value }, true),
                }, label)));
        }
        if (kind === 'text_area') {
            return el('textarea', {
                class: 'w-input', rows: '3', name: name,
                oninput: (ev) => setAnswer(question, { value: ev.target.value }),
            }, answer.value || '');
        }
        if (kind === 'image' || kind === 'file') {
            const status = el('span', { class: 'w-muted' }, answer.data ? (answer.name || 'Photo added') : '');
            return el('div', { class: 'w-file' },
                el('input', {
                    type: 'file', accept: kind === 'image' ? 'image/*' : null, capture: kind === 'image' ? 'environment' : null,
                    onchange: async (ev) => {
                        const file = ev.target.files[0];
                        if (!file) return;
                        try {
                            const data = kind === 'image' ? await readImage(file, 1600) : await readFile(file);
                            setAnswer(question, { data: data, name: file.name });
                            status.textContent = file.name;
                        } catch (e) {
                            toast('error', 'Could not read the file', '');
                        }
                    },
                }),
                status);
        }
        if (kind === 'geolocation') {
            const status = el('span', { class: 'w-muted' },
                answer.lat ? Number(answer.lat).toFixed(5) + ', ' + Number(answer.lng).toFixed(5) : '');
            return el('div', { class: 'w-file' },
                el('button', {
                    type: 'button', class: 'w-btn w-btn-light',
                    onclick: () => {
                        if (!navigator.geolocation) return toast('error', 'Location is not available on this device', '');
                        navigator.geolocation.getCurrentPosition((pos) => {
                            setAnswer(question, { lat: pos.coords.latitude, lng: pos.coords.longitude });
                            status.textContent = pos.coords.latitude.toFixed(5) + ', ' + pos.coords.longitude.toFixed(5);
                        }, () => toast('error', 'Could not get the location', ''));
                    },
                }, 'Use My Location'),
                status);
        }
        if (kind === 'many2one' || kind === 'many2many') {
            return el('div', { class: 'w-muted' }, 'Fill this in in Odoo.');
        }
        const types = { number: 'number', integer: 'number', email: 'email', phone: 'tel', website: 'url' };
        return el('input', {
            type: types[kind] || 'text',
            inputmode: kind === 'number' ? 'decimal' : kind === 'integer' ? 'numeric' : null,
            step: kind === 'integer' ? '1' : kind === 'number' ? 'any' : null,
            placeholder: kind === 'date' ? 'dd/mm/yyyy' : kind === 'datetime' ? 'dd/mm/yyyy hh:mm' : null,
            class: 'w-input', name: name, value: answer.value || '',
            oninput: (ev) => setAnswer(question, { value: ev.target.value }),
        });
    }

    function renderQa() {
        const qa = state.qa;
        const wo = qa.workorder;
        const visible = visibleQuestions();
        const nodes = qa.template.questions.map((question) => {
            const kind = question.type;
            if (kind === 'section_title') {
                return el('h3', { class: 'w-q w-q-section', 'data-question': question.id, hidden: !visible.has(question.id) }, question.name);
            }
            if (kind === 'section_break') {
                return el('div', { class: 'w-q w-q-break', 'data-question': question.id, hidden: !visible.has(question.id) },
                    question.title_position !== 'none' ? el('span', {}, question.name) : null);
            }
            if (kind === 'instructions') {
                return el('div', { class: 'w-q w-q-instructions', 'data-question': question.id, hidden: !visible.has(question.id) },
                    el('div', { class: 'w-q-title' }, question.name),
                    el('div', { html: question.instructions || '' }));
            }
            return el('div', { class: 'w-q', 'data-question': question.id, hidden: !visible.has(question.id) },
                el('div', { class: 'w-q-title' }, question.name),
                question.description ? el('div', { class: 'w-q-help' }, question.description) : null,
                questionInput(question));
        });
        $('w-qa-title').textContent = qa.template.name;
        $('w-qa-sub').textContent = wo.production + ' · ' + wo.product + (wo.lots.length ? ' · ' + wo.lots[0].name : '');
        $('w-qa-questions').replaceChildren(...nodes);
        $('w-qa-message').textContent = '';
    }

    async function submitQa(status) {
        const qa = state.qa;
        const visible = visibleQuestions();
        const answers = {};
        for (const question of qa.template.questions) {
            if (LAYOUT_TYPES.includes(question.type) || !visible.has(question.id)) continue;
            const answer = qa.answers[question.id];
            if (!answer || answer.ref) continue;  // records are filled in by Odoo
            if ((question.type === 'date' || question.type === 'datetime') && answer.value) {
                const d = parseDate(answer.value, question.type === 'datetime');
                if (!d) {
                    $('w-qa-message').textContent = '"' + question.name + '" needs a date like 31/12/2026'
                        + (question.type === 'datetime' ? ' 14:30' : '') + '.';
                    return;
                }
                answers[question.id] = {
                    value: question.type === 'date'
                        ? d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate())
                        : d.toISOString(),
                };
                continue;
            }
            const { prefilled, ...rest } = answer;
            answers[question.id] = rest;
        }
        const ok = await record('qa', qa.workorder, {
            template_id: qa.template.id, template_name: qa.template.name, state: status, answers: answers,
        });
        if (ok) {
            state.qa = null;
            openOrder(qa.workorder.id);
        }
    }

    // ── External RFID / barcode reader ─────────────────────────────────────
    // Readers type the badge ID quickly, usually followed by Enter (or Tab). A burst
    // of fast keystrokes that stops without one also counts.
    function setupKeyboardWedge() {
        const KEY_GAP = 80;
        const IDLE_SUBMIT = 250;
        let buffer = '';
        let last = 0;
        let idleTimer = null;
        const submit = () => {
            clearTimeout(idleTimer);
            const code = buffer;
            buffer = '';
            if (code.length < 3 || !state.config || !state.config.identify_reader || !current('home')) return;
            const search = $('w-search');
            if (document.activeElement === search && search.value.endsWith(code)) {
                search.value = search.value.slice(0, -code.length);
                renderGrid();
            }
            identifyBadge(code, 'reader');
        };
        document.addEventListener('keydown', (ev) => {
            if (!state.config || !state.config.identify_reader || !current('home')) return;
            const target = ev.target;
            if (target && ((target.tagName === 'INPUT' && target.id !== 'w-search') || target.tagName === 'TEXTAREA')) return;
            const now = Date.now();
            if (now - last > KEY_GAP) buffer = '';
            last = now;
            clearTimeout(idleTimer);
            if (ev.key === 'Enter' || ev.key === 'Tab') {
                if (buffer.length >= 3) {
                    ev.preventDefault();
                    submit();
                }
                buffer = '';
            } else if (ev.key.length === 1) {
                buffer += ev.key;
                if (buffer.length >= 4) idleTimer = setTimeout(submit, IDLE_SUBMIT);
            }
        }, true);
    }

    // ── Camera (Badge Scan) ─────────────────────────────────────────────────
    // As On Site's kiosks: the built-in barcode detector where the browser has one,
    // otherwise ZXing (shipped with Odoo, cached by the service worker for offline use).
    const ZXING_URL = '/web/static/lib/zxing-library/zxing-library.js';
    const SCAN_INTERVAL = 200;
    const GONE_AFTER = 2500;
    const BADGE_FORMATS = ['qr_code', 'code_128', 'code_39', 'data_matrix'];
    const camera = { stream: null, detector: null, starting: null, timer: null, used: '', usedSeenAt: 0, candidate: '' };

    function loadScript(src) {
        return new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = src;
            script.onload = resolve;
            script.onerror = () => reject(new Error('Could not load ' + src));
            document.head.appendChild(script);
        });
    }

    async function nativeDetector() {
        if (!('BarcodeDetector' in window)) return null;
        try {
            const supported = await window.BarcodeDetector.getSupportedFormats();
            if (!supported.includes('qr_code')) return null;
            return new window.BarcodeDetector({ formats: BADGE_FORMATS.filter((f) => supported.includes(f)) });
        } catch (e) {
            return null;
        }
    }

    async function zxingDetector() {
        if (!window.ZXing) await loadScript(ZXING_URL);
        const ZXing = window.ZXing;
        const F = ZXing.BarcodeFormat;
        const reader = new ZXing.MultiFormatReader();
        reader.setHints(new Map([
            [ZXing.DecodeHintType.POSSIBLE_FORMATS, [F.QR_CODE, F.CODE_128, F.CODE_39, F.DATA_MATRIX]],
            [ZXing.DecodeHintType.TRY_HARDER, true],
        ]));
        const canvas = document.createElement('canvas');
        return {
            async detect(video) {
                if (!video.videoWidth) return [];
                const scale = Math.min(1, 800 / Math.max(video.videoWidth, video.videoHeight));
                canvas.width = Math.round(video.videoWidth * scale);
                canvas.height = Math.round(video.videoHeight * scale);
                canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
                const bitmap = new ZXing.BinaryBitmap(new ZXing.HybridBinarizer(
                    new ZXing.HTMLCanvasElementLuminanceSource(canvas)));
                try {
                    const result = reader.decodeWithState(bitmap);
                    return [{ rawValue: result.getText(), format: result.getBarcodeFormat() === F.QR_CODE ? 'qr_code' : 'other' }];
                } catch (e) {
                    return [];
                } finally {
                    reader.reset();
                }
            },
        };
    }

    function cameraMessage(text) {
        $('w-camera-message').hidden = !text;
        $('w-camera-message-text').textContent = text || '';
    }

    function startCamera() {
        if (camera.stream || camera.starting) return camera.starting;
        camera.starting = (async () => {
            if (!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia)) {
                cameraMessage('This device has no camera the app can use.');
                return;
            }
            try {
                camera.detector = camera.detector || await nativeDetector() || await zxingDetector();
            } catch (e) {
                cameraMessage('The badge scanner could not start. Check the connection and try again.');
                return;
            }
            try {
                camera.stream = await navigator.mediaDevices.getUserMedia({
                    audio: false,
                    video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 }, height: { ideal: 720 } },
                });
            } catch (e) {
                cameraMessage(e && e.name === 'NotAllowedError'
                    ? 'Allow this app to use the camera to scan badges.' : 'The camera is not available.');
                return;
            }
            if (!current('home')) {
                stopCamera();
                return;
            }
            const video = $('w-camera-video');
            video.srcObject = camera.stream;
            const settings = camera.stream.getVideoTracks()[0].getSettings();
            video.style.setProperty('--w-mirror', settings.facingMode === 'environment' ? 1 : -1);
            try {
                await video.play();
            } catch (e) { /* muted autoplay */ }
            cameraMessage('');
            scheduleScan();
        })().finally(() => {
            camera.starting = null;
        });
        return camera.starting;
    }

    function stopCamera() {
        clearTimeout(camera.timer);
        if (camera.stream) {
            camera.stream.getTracks().forEach((track) => track.stop());
            camera.stream = null;
        }
        $('w-camera-video').srcObject = null;
    }

    function scheduleScan() {
        clearTimeout(camera.timer);
        camera.timer = setTimeout(scanFrame, SCAN_INTERVAL);
    }

    async function scanFrame() {
        if (!camera.stream) return;
        if (document.visibilityState !== 'visible') return scheduleScan();
        let codes = [];
        try {
            codes = await camera.detector.detect($('w-camera-video'));
        } catch (e) { /* frame not ready */ }
        const best = codes.find((c) => c.format === 'qr_code') || codes[0];
        const read = best ? String(best.rawValue || '').trim() : '';
        const code = read && read === camera.candidate ? read : '';
        camera.candidate = read;
        const now = Date.now();
        if (camera.used) {
            if (read === camera.used) camera.usedSeenAt = now;
            else if (now - camera.usedSeenAt > GONE_AFTER) camera.used = '';
        }
        if (code && code !== camera.used && current('home')) {
            camera.used = code;
            camera.usedSeenAt = now;
            const viewport = document.querySelector('.w-viewport');
            viewport.classList.add('w-viewport-found');
            setTimeout(() => viewport.classList.remove('w-viewport-found'), 600);
            await identifyBadge(code, 'badge');
        }
        scheduleScan();
    }

    // ── PWA ─────────────────────────────────────────────────────────────────
    function setupPwa() {
        if ('serviceWorker' in navigator) {
            navigator.serviceWorker.register(BASE + '/sw.js', { scope: BASE }).catch((e) => console.warn('Service worker:', e));
        }
        window.addEventListener('beforeinstallprompt', (ev) => {
            ev.preventDefault();
            state.installPrompt = ev;
            renderFooter();
        });
        $('w-install-btn').addEventListener('click', async () => {
            if (!state.installPrompt) return;
            state.installPrompt.prompt();
            await state.installPrompt.userChoice;
            state.installPrompt = null;
            renderFooter();
        });
        const wake = () => {
            if (navigator.wakeLock && document.visibilityState === 'visible') {
                navigator.wakeLock.request('screen').catch(() => {});
            }
        };
        document.addEventListener('visibilitychange', wake);
        wake();
        // Ask the browser to keep this app's data (the offline queue) when space runs low.
        if (navigator.storage && navigator.storage.persist) navigator.storage.persist().catch(() => {});
    }

    // ── Start ───────────────────────────────────────────────────────────────
    async function start() {
        state.config = load('config', null);
        state.employees = load('employees', []);
        state.workorders = load('workorders', []);
        state.queue = load('queue', []);
        state.lastContact = load('contact', 0);
        state.dataTime = load('dataTime', 0);

        buildKeypad();
        tickClock();
        setInterval(tickClock, 1000);
        renderConfig();
        renderFooter();
        renderGrid();
        setupKeyboardWedge();
        setupPwa();

        $('w-pin-cancel').addEventListener('click', () => show('home'));
        $('w-signout').addEventListener('click', signOut);
        $('w-back-orders').addEventListener('click', showOrders);
        $('w-qa-cancel').addEventListener('click', () => {
            if (window.confirm('Discard this checklist?')) openOrder(state.qa.workorder.id);
        });
        $('w-qa-save').addEventListener('click', () => submitQa('draft'));
        $('w-qa-complete').addEventListener('click', () => submitQa('done'));
        $('w-refresh').addEventListener('click', () => refresh(true));
        $('w-search').addEventListener('input', () => renderGrid());
        $('w-camera-retry').addEventListener('click', () => {
            cameraMessage('');
            stopCamera();
            startCamera();
        });
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'hidden') stopCamera();
            else if (current('home') && state.config && state.config.identify_badge && !state.config.identify_reader) startCamera();
        });
        document.addEventListener('pointerdown', touch);
        document.addEventListener('keydown', touch);
        window.addEventListener('online', () => refresh(true));

        show('home');
        await refresh(true);
        if (!state.config) {
            $('w-message').hidden = false;
            $('w-message').textContent = 'This work centre needs a connection the first time it starts.';
        }
        setInterval(() => syncNow().catch(() => {}), SYNC_INTERVAL);
        setInterval(() => refresh(false), 60 * 1000);
    }

    start();
})();
