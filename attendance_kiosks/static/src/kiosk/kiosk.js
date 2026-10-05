/* Attendance Kiosk - stand-alone PWA, no Odoo web client.
 *
 * Online, the server identifies workers and records sign ins and sign outs.
 * Offline, the kiosk uses its cached roster (eligibility, hashed badge IDs and
 * PINs, sign in state and history) to make the same decisions, queues the
 * events in localStorage and syncs them when the connection returns.
 */
(function () {
    'use strict';

    const TOKEN = document.body.dataset.token;
    const BASE = '/kiosk/' + TOKEN;
    const STORE = 'attendance-kiosk:' + TOKEN + ':';
    const HOME_TIMEOUT = 45 * 1000;
    const RESULT_TIMEOUT = 6 * 1000;
    const SYNC_INTERVAL = 30 * 1000;
    const OFFLINE_PIN_ATTEMPTS = 5;

    const state = {
        config: null,
        roster: [],
        queue: [],
        online: null,
        lastRefresh: 0,
        current: null,      // {employee, ticket, due}
        pin: '',
        pinFailures: {},
        homeTimer: null,
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
        } catch (e) { /* storage full or blocked: keep working in memory */ }
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
        const data = new TextEncoder().encode(text);
        const digest = await crypto.subtle.digest('SHA-256', data);
        return Array.from(new Uint8Array(digest)).map((b) => b.toString(16).padStart(2, '0')).join('');
    }

    const pad = (n) => String(n).padStart(2, '0');
    const fmtTime = (d) => pad(d.getHours()) + ':' + pad(d.getMinutes());
    const fmtDate = (d) => pad(d.getDate()) + '/' + pad(d.getMonth() + 1) + '/' + d.getFullYear();
    const isoDate = (d) => d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());

    function fmtStamp(iso) {
        if (!iso) return '';
        const d = new Date(iso);
        return isoDate(d) === isoDate(new Date()) ? fmtTime(d) : fmtDate(d) + ' ' + fmtTime(d);
    }

    function initials(name) {
        return (name || '?').split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0].toUpperCase()).join('');
    }

    function avatar(employee, size) {
        const img = el('img', { class: 'k-avatar k-avatar-' + size, alt: '', src: employee.avatar, loading: 'lazy' });
        img.addEventListener('error', () => img.replaceWith(el('div', { class: 'k-avatar k-avatar-' + size + ' k-avatar-initials' }, initials(employee.name))));
        return img;
    }

    // ── Network ─────────────────────────────────────────────────────────────
    async function request(path, body, timeout) {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), timeout || 10000);
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
        setOnline(true);
        let data = {};
        try {
            data = await response.json();
        } catch (e) { /* not JSON */ }
        return { ok: response.ok, status: response.status, data: data };
    }

    function setOnline(online) {
        if (state.online === online) return;
        state.online = online;
        renderFooter();
        if (online) syncNow().catch(() => {});
    }

    // ── Data ────────────────────────────────────────────────────────────────
    function rosterById(id) {
        return state.roster.find((e) => e.id === id);
    }

    function storeRoster() {
        save('roster', state.roster);
    }

    function mergeEmployee(fresh) {
        const existing = rosterById(fresh.id);
        if (existing) {
            // Identification responses leave out the hashed badge / PIN.
            Object.assign(existing, fresh, {
                badge: fresh.badge !== undefined ? fresh.badge : existing.badge,
                pin: fresh.pin !== undefined ? fresh.pin : existing.pin,
            });
        } else {
            state.roster.push(fresh);
        }
        // Re-apply anything this kiosk recorded that the server has not seen yet.
        const employee = rosterById(fresh.id);
        state.queue.filter((ev) => ev.employee_id === employee.id).forEach((ev) => applyEventLocally(employee, ev));
        storeRoster();
        return employee;
    }

    async function refresh(force) {
        const minutes = (state.config && state.config.refresh_minutes) || 15;
        if (!force && Date.now() - state.lastRefresh < minutes * 60 * 1000) return;
        try {
            await syncNow();
            const [config, roster] = await Promise.all([request('/config.json'), request('/roster.json', undefined, 30000)]);
            if (config.ok && roster.ok) {
                state.config = config.data;
                save('config', state.config);
                state.roster = roster.data.employees || [];
                state.queue.forEach((ev) => {
                    const employee = rosterById(ev.employee_id);
                    if (employee) applyEventLocally(employee, ev);
                });
                storeRoster();
                state.lastRefresh = Date.now();
                save('refreshed', state.lastRefresh);
                renderConfig();
                renderGrid();
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
            const response = await request('/sync', { events: batch.map(({ blocked, ...ev }) => ev) }, 30000);
            if (!response.ok) return false;
            const done = new Set((response.data.results || []).map((r) => r.id));
            state.queue = state.queue.filter((ev) => !done.has(ev.id));
            save('queue', state.queue);
            renderFooter();
            return true;
        } finally {
            state.syncing = false;
        }
    }

    // ── Rules (mirrors the server, used offline) ────────────────────────────
    function autoSignOutAt(checkIn) {
        const auto = state.config && state.config.auto_sign_out;
        if (!auto || !auto.enabled) return null;
        if (auto.type === 'duration') {
            return auto.hours > 0 ? new Date(checkIn.getTime() + auto.hours * 3600 * 1000) : null;
        }
        const minutes = Math.min(Math.round(auto.time * 60), 24 * 60 - 1);
        const due = new Date(checkIn);
        due.setHours(Math.floor(minutes / 60), minutes % 60, 0, 0);
        if (due <= checkIn) due.setDate(due.getDate() + 1);
        return due;
    }

    function openAttendance(employee) {
        const open = employee.open;
        if (!open) return null;
        if (open.auto_out && new Date(open.auto_out) <= new Date()) return null;
        return open;
    }

    function signInState(employee) {
        const open = openAttendance(employee);
        if (!open) return { state: 'out' };
        if (open.kiosk_id === state.config.id) return { state: 'here', open: open };
        return { state: 'elsewhere', open: open };
    }

    function eligibility(employee) {
        const reasons = (employee.reasons || []).slice();
        if (employee.ok && employee.until && isoDate(new Date()) > employee.until) {
            reasons.push('A capability needed at this kiosk has expired.');
        }
        return { ok: !reasons.length, reasons: reasons, warnings: employee.warnings || [] };
    }

    function dueQuestionnaires(employee) {
        const today = isoDate(new Date());
        const history = employee.history || {};
        const due = [];
        for (const line of state.config.lines || []) {
            if (!(employee.lines || []).includes(line.id)) continue;
            const fires = {
                always: true,
                first_of_day: !history.any || history.any < today,
                first_of_day_location: !history.loc || history.loc < today,
                first_at_location: !history.loc,
            }[line.trigger];
            if (fires && !due.includes(line.questionnaire_id)) due.push(line.questionnaire_id);
        }
        return due;
    }

    function questionnaire(id) {
        return (state.config.questionnaires || []).find((q) => q.id === id);
    }

    function applyEventLocally(employee, event) {
        if (event.action === 'sign_in') {
            if (event.blocked) return;
            const time = new Date(event.time);
            const due = autoSignOutAt(time);
            employee.open = {
                kiosk_id: state.config.id,
                kiosk_name: state.config.name,
                check_in: event.time,
                auto_out: due ? due.toISOString() : null,
                block_in: false,
                block_out: false,
            };
            employee.history = { any: isoDate(time), loc: isoDate(time) };
        } else {
            employee.open = null;
        }
    }

    // ── Screens ─────────────────────────────────────────────────────────────
    function show(screen, timeout) {
        document.querySelectorAll('.k-screen').forEach((s) => s.classList.toggle('k-active', s.id === 'screen-' + screen));
        clearTimeout(state.homeTimer);
        if (screen !== 'home') {
            state.homeTimer = setTimeout(goHome, timeout || HOME_TIMEOUT);
        }
        window.scrollTo(0, 0);
    }

    function goHome() {
        state.current = null;
        state.pin = '';
        $('k-search').value = '';
        renderGrid();
        show('home');
    }

    function resetTimer() {
        if (!$('screen-home').classList.contains('k-active') && !$('screen-result').classList.contains('k-active')) {
            clearTimeout(state.homeTimer);
            state.homeTimer = setTimeout(goHome, HOME_TIMEOUT);
        }
    }

    function personCard(employee) {
        return [
            avatar(employee, 'lg'),
            el('div', { class: 'k-person-name' }, employee.name),
            employee.job ? el('div', { class: 'k-person-job' }, employee.job) : null,
        ];
    }

    function showResult(kind, title, lines) {
        $('k-result').replaceChildren(
            el('div', { class: 'k-result-icon k-result-' + kind }, kind === 'success' ? '✓' : kind === 'info' ? 'i' : '✕'),
            el('div', { class: 'k-result-title' }, title),
            ...(lines || []).filter(Boolean).map((line) => el('div', { class: 'k-result-line' }, line)),
        );
        show('result', kind === 'success' ? RESULT_TIMEOUT : RESULT_TIMEOUT * 2);
    }

    // ── Home ────────────────────────────────────────────────────────────────
    function renderConfig() {
        const config = state.config;
        if (!config) return;
        $('k-kiosk-name').textContent = config.name;
        $('k-kiosk-place').textContent = config.location + ' · ' + config.company;
        $('k-welcome').textContent = config.welcome || '';
        $('k-welcome').hidden = !config.welcome;
        $('k-badge-hint').hidden = !config.identify_badge;
        $('k-name-select').hidden = !config.identify_name;
        $('k-camera-btn').hidden = !(config.identify_badge && 'BarcodeDetector' in window && navigator.mediaDevices);
    }

    function renderGrid() {
        if (!state.config || !state.config.identify_name) return;
        const term = $('k-search').value.trim().toLowerCase();
        let employees = state.roster;
        if (term) employees = employees.filter((e) => e.name.toLowerCase().includes(term));
        const limit = 60;
        const tiles = employees.slice(0, limit).map((employee) => {
            const status = signInState(employee);
            return el('button', {
                type: 'button',
                class: 'k-tile' + (status.state === 'here' ? ' k-tile-in' : ''),
                onclick: () => selectName(employee),
            },
            avatar(employee, 'sm'),
            el('span', { class: 'k-tile-name' }, employee.name),
            status.state === 'here' ? el('span', { class: 'k-tile-status' }, 'Signed in') : null);
        });
        if (!tiles.length) {
            tiles.push(el('div', { class: 'k-empty' }, state.roster.length ? 'No one matches that name.' : 'Loading workers...'));
        } else if (employees.length > limit) {
            tiles.push(el('div', { class: 'k-empty' }, 'Keep typing to find your name.'));
        }
        $('k-grid').replaceChildren(...tiles);
    }

    function renderFooter() {
        const conn = $('k-conn');
        conn.textContent = state.online === false ? 'Offline' : state.online ? 'Online' : 'Connecting...';
        conn.className = 'k-conn' + (state.online === false ? ' k-conn-off' : state.online ? ' k-conn-on' : '');
        const pending = $('k-pending');
        pending.hidden = !state.queue.length;
        pending.textContent = state.queue.length + ' waiting to sync';
        $('k-install-btn').hidden = !state.installPrompt;
    }

    function tickClock() {
        const now = new Date();
        $('k-clock').textContent = fmtTime(now);
        $('k-date').textContent = now.toLocaleDateString('en-AU', { weekday: 'long' }) + ' ' + fmtDate(now);
    }

    // ── Identification ──────────────────────────────────────────────────────
    function offlineAllowed() {
        if (state.config && state.config.offline) return true;
        showResult('error', 'The kiosk is offline', ['Please try again shortly or see your supervisor.']);
        return false;
    }

    async function identifyBadge(code) {
        if (!state.config || !state.config.identify_badge || !code) return;
        try {
            const response = await request('/identify', { method: 'badge', badge: code });
            return handleIdentify(response);
        } catch (e) {
            if (!(e instanceof NetworkError)) throw e;
        }
        if (!offlineAllowed()) return;
        const hash = await sha256(state.config.salt + ':' + code);
        const employee = hash && state.roster.find((e) => e.badge === hash);
        if (!employee) {
            showResult('error', 'Badge not recognised', ['Please try again or see your supervisor.']);
            return;
        }
        showEmployee(employee, null, null);
    }

    function selectName(employee) {
        if (state.config.require_pin) {
            state.current = { employee: employee };
            state.pin = '';
            $('k-pin-person').replaceChildren(...personCard(employee));
            $('k-pin-message').textContent = '';
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
                showResult('error', 'You do not have a PIN yet', ['Please see your supervisor.']);
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
        showEmployee(employee, null, null);
    }

    function handleIdentify(response) {
        if (!response.ok) {
            showResult('error', response.data.message || 'Sign in is not available.', []);
            return;
        }
        const employee = mergeEmployee(response.data.employee);
        showEmployee(employee, response.data.ticket, response.data.due);
    }

    // ── PIN pad ─────────────────────────────────────────────────────────────
    function renderPin() {
        $('k-pin-dots').replaceChildren(...Array.from({ length: Math.max(4, state.pin.length) }, (_, i) =>
            el('span', { class: 'k-pin-dot' + (i < state.pin.length ? ' k-pin-dot-full' : '') })));
    }

    function pinKey(key) {
        resetTimer();
        if (key === 'back') state.pin = state.pin.slice(0, -1);
        else if (key === 'ok') {
            if (state.pin && state.current) identifyName(state.current.employee, state.pin);
            return;
        } else if (state.pin.length < 12) state.pin += key;
        $('k-pin-message').textContent = '';
        renderPin();
    }

    function pinError(message) {
        state.pin = '';
        renderPin();
        $('k-pin-message').textContent = message || 'Wrong PIN.';
        const dots = $('k-pin-dots');
        dots.classList.remove('k-shake');
        void dots.offsetWidth;
        dots.classList.add('k-shake');
        if (!$('screen-pin').classList.contains('k-active')) show('pin');
    }

    function buildKeypad() {
        const keys = ['1', '2', '3', '4', '5', '6', '7', '8', '9', 'back', '0', 'ok'];
        $('k-keypad').replaceChildren(...keys.map((key) => el('button', {
            type: 'button',
            class: 'k-key' + (key === 'ok' ? ' k-key-ok' : ''),
            onclick: () => pinKey(key),
        }, key === 'back' ? '⌫' : key === 'ok' ? 'OK' : key)));
    }

    // ── Employee ────────────────────────────────────────────────────────────
    function showEmployee(employee, ticket, due) {
        state.current = { employee: employee, ticket: ticket, due: due };
        const status = signInState(employee);
        const access = eligibility(employee);
        $('k-emp-person').replaceChildren(...personCard(employee));

        let statusText;
        if (status.state === 'here') statusText = 'Signed in here since ' + fmtStamp(status.open.check_in);
        else if (status.state === 'elsewhere') statusText = 'Signed in at ' + status.open.kiosk_name + ' since ' + fmtStamp(status.open.check_in);
        else statusText = 'Not signed in';
        $('k-emp-status').textContent = statusText;

        const showWarnings = status.state !== 'here' && access.ok;
        $('k-emp-warnings').replaceChildren(...(showWarnings ? access.warnings : []).map((w) => el('li', {}, w)));
        const needsAccess = status.state !== 'here';
        $('k-emp-reasons').replaceChildren(...(needsAccess && !access.ok ? access.reasons : []).map((r) => el('li', {}, r)));

        const buttons = [];
        if (status.state === 'here') {
            buttons.push(actionButton('Sign Out', 'k-btn-danger', () => doAction('sign_out')));
        } else if (status.state === 'out') {
            if (access.ok) buttons.push(actionButton('Sign In', 'k-btn-primary', startSignIn));
        } else {
            if (access.ok) {
                buttons.push(actionButton('Sign In Here', 'k-btn-primary', startSignIn, status.open.block_in
                    ? 'Sign out at ' + status.open.kiosk_name + ' first.' : null));
            }
            buttons.push(actionButton('Sign Out', 'k-btn-danger', () => doAction('sign_out'), status.open.block_out
                ? 'You must sign out at ' + status.open.kiosk_name + '.' : null));
        }
        $('k-emp-actions').replaceChildren(...buttons);
        show('employee');
    }

    function actionButton(label, kind, handler, blockedReason) {
        return el('div', { class: 'k-action' },
            el('button', {
                type: 'button',
                class: 'k-btn k-btn-lg ' + kind,
                disabled: !!blockedReason,
                onclick: handler,
            }, label),
            blockedReason ? el('div', { class: 'k-action-note' }, blockedReason) : null);
    }

    function startSignIn() {
        const current = state.current;
        const due = current.due || dueQuestionnaires(current.employee);
        const questionnaires = due.map(questionnaire).filter(Boolean);
        if (questionnaires.length) showQuestionnaires(questionnaires);
        else doAction('sign_in', []);
    }

    // ── Questionnaires ──────────────────────────────────────────────────────
    function showQuestionnaires(questionnaires) {
        state.current.questionnaires = questionnaires;
        state.current.answers = {};
        const blocks = questionnaires.map((q) => el('fieldset', { class: 'k-questionnaire' },
            el('legend', {}, q.name),
            q.introduction ? el('p', { class: 'k-intro' }, q.introduction) : null,
            ...q.questions.map((question) => renderQuestion(q, question))));
        $('k-questionnaires').replaceChildren(...blocks);
        $('k-questionnaire-message').textContent = '';
        show('questionnaire', HOME_TIMEOUT * 3);
    }

    function setAnswer(q, question, answer) {
        const answers = state.current.answers;
        answers[q.id] = answers[q.id] || {};
        answers[q.id][question.id] = answer;
        resetTimer();
    }

    function renderQuestion(q, question) {
        const name = 'q' + question.id;
        let input;
        const choice = (options) => el('div', { class: 'k-choices' }, ...options.map((option) =>
            el('label', { class: 'k-choice' },
                el('input', {
                    type: 'radio',
                    name: name,
                    value: option.value,
                    onchange: () => setAnswer(q, question, option.answer),
                }),
                el('span', {}, option.label))));
        if (question.type === 'yes_no') {
            input = choice([
                { value: 'yes', label: 'Yes', answer: { value: 'yes' } },
                { value: 'no', label: 'No', answer: { value: 'no' } },
            ]);
        } else if (question.type === 'choice') {
            input = choice(question.options.map((o) => ({ value: o.id, label: o.name, answer: { option_id: o.id } })));
        } else {
            input = el('input', {
                type: question.type === 'number' ? 'number' : 'text',
                inputmode: question.type === 'number' ? 'decimal' : null,
                class: 'k-input',
                name: name,
                oninput: (ev) => setAnswer(q, question, { value: ev.target.value }),
            });
        }
        return el('div', { class: 'k-question', 'data-question': question.id },
            el('div', { class: 'k-question-text' }, question.name, question.required ? el('span', { class: 'k-required' }, ' *') : null),
            question.help ? el('div', { class: 'k-question-help' }, question.help) : null,
            input);
    }

    function answered(answer) {
        return answer && ((answer.value !== undefined && String(answer.value).trim() !== '') || answer.option_id);
    }

    function submitQuestionnaires(ev) {
        ev.preventDefault();
        const current = state.current;
        let missing = false;
        document.querySelectorAll('.k-question').forEach((node) => node.classList.remove('k-question-missing'));
        for (const q of current.questionnaires) {
            for (const question of q.questions) {
                const answer = (current.answers[q.id] || {})[question.id];
                if (question.required && !answered(answer)) {
                    missing = true;
                    const node = document.querySelector('[data-question="' + question.id + '"]');
                    if (node) node.classList.add('k-question-missing');
                }
            }
        }
        if (missing) {
            $('k-questionnaire-message').textContent = 'Please answer every question marked *.';
            return;
        }
        const answers = current.questionnaires.map((q) => ({ questionnaire_id: q.id, answers: current.answers[q.id] || {} }));
        doAction('sign_in', answers);
    }

    function blockedMessages(answers) {
        const messages = [];
        for (const entry of answers) {
            const q = questionnaire(entry.questionnaire_id);
            if (!q) continue;
            const blocks = q.questions.some((question) => {
                const answer = entry.answers[question.id] || {};
                if (question.type === 'yes_no') return answer.value && answer.value === question.blocking_answer;
                if (question.type === 'choice') return question.options.some((o) => o.id === answer.option_id && o.blocks);
                return false;
            });
            if (blocks) messages.push(q.blocked_message || 'Based on your answers you cannot sign in.');
        }
        return messages;
    }

    // ── Sign in / out ───────────────────────────────────────────────────────
    async function doAction(action, answers) {
        const current = state.current;
        if (!current) return;
        const employee = current.employee;
        if (current.ticket) {
            try {
                if (!(await syncNow())) throw new NetworkError('sync failed');
                const response = await request('/action', {
                    ticket: current.ticket,
                    employee_id: employee.id,
                    action: action,
                    answers: answers || [],
                });
                return handleActionResult(response, action);
            } catch (e) {
                if (!(e instanceof NetworkError)) throw e;
            }
        }
        if (!offlineAllowed()) return;
        offlineAction(employee, action, answers || []);
    }

    function handleActionResult(response, action) {
        const data = response.data || {};
        if (data.employee) mergeEmployee(data.employee);
        const employee = state.current.employee;
        if (data.code === 'ticket') {
            showResult('error', 'Please scan your badge or select your name again.', []);
            return;
        }
        switch (data.status) {
        case 'signed_in':
            showResult('success', 'Welcome, ' + employee.name.split(' ')[0], [
                'Signed in at ' + fmtStamp(data.time),
                data.transferred_from ? 'You have been signed out of ' + data.transferred_from + '.' : null,
                ...(eligibility(employee).warnings),
            ]);
            break;
        case 'signed_out':
            showResult('success', 'Goodbye, ' + employee.name.split(' ')[0], [
                'Signed out at ' + fmtStamp(data.time),
            ]);
            break;
        case 'questionnaire_required': {
            const questionnaires = (data.questionnaire_ids || []).map(questionnaire).filter(Boolean);
            if (questionnaires.length) {
                showQuestionnaires(questionnaires);
                $('k-questionnaire-message').textContent = data.message || '';
            } else {
                refresh(true);
                showResult('error', 'Please try again', ['The kiosk has been updated.']);
            }
            break;
        }
        case 'blocked':
            showResult('error', 'You cannot sign in', data.messages || []);
            break;
        case 'refused':
            showResult('error', 'You cannot sign in here', data.reasons || []);
            break;
        default:
            showResult('error', data.message || 'Something went wrong. Please try again.', []);
        }
        renderGrid();
    }

    function offlineAction(employee, action, answers) {
        const now = new Date();
        const event = {
            id: uuid(),
            employee_id: employee.id,
            action: action,
            time: now.toISOString(),
            answers: answers,
        };
        const status = signInState(employee);
        const blocked = action === 'sign_in' ? blockedMessages(answers) : [];
        event.blocked = blocked.length > 0;
        state.queue.push(event);
        save('queue', state.queue);
        applyEventLocally(employee, event);
        storeRoster();
        renderFooter();
        renderGrid();
        if (blocked.length) {
            showResult('error', 'You cannot sign in', blocked);
        } else if (action === 'sign_in') {
            showResult('success', 'Welcome, ' + employee.name.split(' ')[0], [
                'Signed in at ' + fmtTime(now) + ' (offline)',
                status.state === 'elsewhere' ? 'You have been signed out of ' + status.open.kiosk_name + '.' : null,
                ...eligibility(employee).warnings,
            ]);
        } else {
            showResult('success', 'Goodbye, ' + employee.name.split(' ')[0], ['Signed out at ' + fmtTime(now) + ' (offline)']);
        }
    }

    // ── Badge scanners ──────────────────────────────────────────────────────
    // USB / Bluetooth scanners type the badge ID quickly and press Enter.
    function setupKeyboardWedge() {
        let buffer = '';
        let last = 0;
        document.addEventListener('keydown', (ev) => {
            const target = ev.target;
            if (target && (target.tagName === 'INPUT' && target.id !== 'k-search' || target.tagName === 'TEXTAREA')) return;
            const now = Date.now();
            if (now - last > 100) buffer = '';
            last = now;
            if (ev.key === 'Enter') {
                if (buffer.length >= 3 && $('screen-home').classList.contains('k-active')) {
                    ev.preventDefault();
                    const code = buffer;
                    buffer = '';
                    $('k-search').value = '';
                    renderGrid();
                    identifyBadge(code);
                }
                buffer = '';
            } else if (ev.key.length === 1) {
                buffer += ev.key;
            }
        });
    }

    async function openCamera() {
        const overlay = $('k-camera');
        const video = $('k-camera-video');
        let stream;
        try {
            stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } });
        } catch (e) {
            showResult('error', 'The camera is not available', []);
            return;
        }
        const detector = new window.BarcodeDetector();
        overlay.hidden = false;
        video.srcObject = stream;
        await video.play();
        let active = true;
        const close = () => {
            active = false;
            overlay.hidden = true;
            stream.getTracks().forEach((t) => t.stop());
        };
        $('k-camera-close').onclick = close;
        const scan = async () => {
            if (!active) return;
            try {
                const codes = await detector.detect(video);
                if (codes.length) {
                    close();
                    identifyBadge(codes[0].rawValue);
                    return;
                }
            } catch (e) { /* frame not ready */ }
            setTimeout(scan, 250);
        };
        scan();
        setTimeout(() => active && close(), 60 * 1000);
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
        $('k-install-btn').addEventListener('click', async () => {
            if (!state.installPrompt) return;
            state.installPrompt.prompt();
            await state.installPrompt.userChoice;
            state.installPrompt = null;
            renderFooter();
        });
        // Keep the screen on while the kiosk is showing.
        const wake = () => {
            if (navigator.wakeLock && document.visibilityState === 'visible') {
                navigator.wakeLock.request('screen').catch(() => {});
            }
        };
        document.addEventListener('visibilitychange', wake);
        wake();
    }

    // ── Start ───────────────────────────────────────────────────────────────
    async function start() {
        state.config = load('config', null);
        state.roster = load('roster', []);
        state.queue = load('queue', []);
        state.lastRefresh = 0;

        buildKeypad();
        tickClock();
        setInterval(tickClock, 1000);
        renderConfig();
        renderFooter();
        renderGrid();
        setupKeyboardWedge();
        setupPwa();

        document.querySelectorAll('.k-back').forEach((b) => b.addEventListener('click', goHome));
        $('k-search').addEventListener('input', () => renderGrid());
        $('k-questionnaire-form').addEventListener('submit', submitQuestionnaires);
        $('k-camera-btn').addEventListener('click', openCamera);
        document.addEventListener('pointerdown', resetTimer);
        window.addEventListener('online', () => refresh(true));

        await refresh(true);
        if (!state.config) {
            $('k-welcome').hidden = false;
            $('k-welcome').textContent = 'This kiosk needs a connection the first time it starts.';
        }
        setInterval(() => syncNow().catch(() => {}), SYNC_INTERVAL);
        setInterval(() => refresh(false), 60 * 1000);
    }

    start();
})();
