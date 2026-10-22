/* SCORM Authoring player.
 *
 * Runs a course exported by the SCORM Authoring app (window.SCORM_COURSE,
 * written to course.js). No dependencies, so the package works in any LMS.
 *
 * - Talks to the LMS through the SCORM 1.2 (API) or 2004 (API_1484_11)
 *   runtime; without one it runs in preview mode and saves nothing.
 * - Slide gates: Continue only shows once the slide's required items are
 *   done, its minimum time has passed and its questions reach the pass mark.
 * - Scored questions make up the assessment; the result is reported as the
 *   SCORM score and pass/fail status.
 */
(function () {
    'use strict';

    var C = window.SCORM_COURSE;
    if (!C) { return; }
    var S = C.settings || {};
    var L = C.labels || {};
    // Shapes cut out with clip-path (their borders and shadows can't show)
    var CLIPPED_SHAPES = ['star', 'triangle', 'trapezoid'];
    var QUESTION_TYPES = ['mcq', 'mrq', 'truefalse', 'fillblank', 'matching', 'sequence', 'survey'];
    var params = new URLSearchParams(window.location.search);

    // ─────────────────────────────────────────────────────────────────
    // Utilities
    // ─────────────────────────────────────────────────────────────────
    function h(tag, attrs, children) {
        var el = document.createElement(tag);
        Object.keys(attrs || {}).forEach(function (key) {
            var value = attrs[key];
            if (value === null || value === undefined || value === false) { return; }
            if (key === 'class') { el.className = value; }
            else if (key === 'text') { el.textContent = value; }
            else if (key === 'html') { el.innerHTML = value; }
            else if (key.slice(0, 2) === 'on') { el.addEventListener(key.slice(2), value); }
            else if (key === 'style' && typeof value === 'object') { Object.assign(el.style, value); }
            else { el.setAttribute(key, value === true ? '' : value); }
        });
        (children || []).forEach(function (child) {
            if (child === null || child === undefined || child === false) { return; }
            el.appendChild(typeof child === 'string' ? document.createTextNode(child) : child);
        });
        return el;
    }

    function isQuestion(el) { return QUESTION_TYPES.indexOf(el.type) !== -1; }
    function isGraded(el) { return isQuestion(el) && el.type !== 'survey'; }

    function shuffle(list, seed) {
        var copy = list.slice();
        var s = seed || 1;
        for (var i = copy.length - 1; i > 0; i--) {
            s = (s * 9301 + 49297) % 233280;
            var j = Math.floor((s / 233280) * (i + 1));
            var tmp = copy[i]; copy[i] = copy[j]; copy[j] = tmp;
        }
        return copy;
    }

    function hashSeed(text) {
        var hash = 7;
        for (var i = 0; i < text.length; i++) { hash = (hash * 31 + text.charCodeAt(i)) % 100000; }
        return hash || 1;
    }

    function normalise(text, caseSensitive) {
        var value = String(text || '').trim().replace(/\s+/g, ' ');
        return caseSensitive ? value : value.toLowerCase();
    }

    function label(key, fallback) { return L[key] || fallback || ''; }

    function videoEmbedUrl(url) {
        var m = /(?:youtube\.com\/(?:watch\?v=|embed\/|shorts\/)|youtu\.be\/)([\w-]{6,})/.exec(url || '');
        if (m) { return 'https://www.youtube.com/embed/' + m[1] + '?rel=0'; }
        m = /vimeo\.com\/(?:video\/)?(\d+)/.exec(url || '');
        if (m) { return 'https://player.vimeo.com/video/' + m[1]; }
        return null;
    }

    // ─────────────────────────────────────────────────────────────────
    // SCORM runtime
    // ─────────────────────────────────────────────────────────────────
    var Scorm = {
        api: null,
        v2004: false,
        started: Date.now(),

        find: function () {
            var names = C.scorm_version === '2004' ? ['API_1484_11', 'API'] : ['API', 'API_1484_11'];
            var wins = [];
            var win = window;
            for (var depth = 0; win && depth < 12; depth++) {
                wins.push(win);
                if (win.parent === win) { break; }
                win = win.parent;
            }
            try { if (window.opener) { wins.push(window.opener); } } catch (e) { /* cross-origin */ }
            for (var n = 0; n < names.length; n++) {
                for (var w = 0; w < wins.length; w++) {
                    try {
                        if (wins[w][names[n]]) {
                            this.api = wins[w][names[n]];
                            this.v2004 = names[n] === 'API_1484_11';
                            return true;
                        }
                    } catch (e) { /* cross-origin frame */ }
                }
            }
            return false;
        },
        call: function (name12, name2004) {
            if (!this.api) { return ''; }
            var args = Array.prototype.slice.call(arguments, 2);
            var fn = this.api[this.v2004 ? name2004 : name12];
            try { return fn ? String(fn.apply(this.api, args)) : ''; } catch (e) { return ''; }
        },
        init: function () {
            if (!this.find()) { return false; }
            this.call('LMSInitialize', 'Initialize', '');
            return true;
        },
        key: function (k12, k2004) { return this.v2004 ? k2004 : k12; },
        get: function (k12, k2004) { return this.call('LMSGetValue', 'GetValue', this.key(k12, k2004)); },
        set: function (k12, k2004, value) {
            if (!k12 && this.v2004 === false) { return; }
            if (!k2004 && this.v2004) { return; }
            this.call('LMSSetValue', 'SetValue', this.key(k12, k2004), String(value));
        },
        commit: function () { this.call('LMSCommit', 'Commit', ''); },
        sessionTime: function () {
            var secs = Math.round((Date.now() - this.started) / 1000);
            if (this.v2004) {
                return 'PT' + Math.floor(secs / 3600) + 'H' + Math.floor((secs % 3600) / 60) + 'M' + (secs % 60) + 'S';
            }
            var pad = function (n) { return (n < 10 ? '0' : '') + n; };
            return pad(Math.min(Math.floor(secs / 3600), 9999)) + ':' + pad(Math.floor((secs % 3600) / 60)) + ':' + pad(secs % 60);
        },
        finished: false,
        finish: function () {
            if (!this.api || this.finished) { return; }
            this.finished = true;
            this.set('cmi.core.session_time', 'cmi.session_time', this.sessionTime());
            this.set('cmi.core.exit', 'cmi.exit', state.completed ? '' : 'suspend');
            this.commit();
            this.call('LMSFinish', 'Terminate', '');
        },
    };

    // ─────────────────────────────────────────────────────────────────
    // State (saved to suspend_data)
    // ─────────────────────────────────────────────────────────────────
    var slides = C.slides || [];
    var state = {
        current: 0,
        visited: {},      // slide index -> 1
        cleared: {},      // slide index -> 1 (gate passed)
        done: {},         // element id -> 1 (required interaction done)
        answers: {},      // question id -> {r: response, c: correct, n: tries, f: final}
        gateTries: {},    // slide index -> failed attempts
        attempt: 1,       // assessment attempt
        completed: false,
        status: '',
    };
    var preview = false;
    var reportedStatus = null;
    var skipGates = false;
    var slideTimer = null;
    var slideEnteredAt = 0;
    var ui = {};

    function storageKey() { return 'scorm_preview_' + C.identifier + '_' + C.version; }

    function serialise() {
        var data = {
            c: state.current,
            v: Object.keys(state.visited).map(Number),
            g: Object.keys(state.cleared).map(Number),
            d: Object.keys(state.done),
            a: state.answers,
            t: state.gateTries,
            n: state.attempt,
            x: state.completed ? 1 : 0,
        };
        var text = JSON.stringify(data);
        if (!Scorm.v2004 && text.length > 4000) {
            // SCORM 1.2 caps suspend_data at 4096 characters: keep results, drop responses
            Object.keys(data.a).forEach(function (id) { delete data.a[id].r; });
            text = JSON.stringify(data);
        }
        return text;
    }

    function restore(text) {
        try {
            var data = JSON.parse(text);
            state.current = data.c || 0;
            (data.v || []).forEach(function (i) { state.visited[i] = 1; });
            (data.g || []).forEach(function (i) { state.cleared[i] = 1; });
            (data.d || []).forEach(function (id) { state.done[id] = 1; });
            state.answers = data.a || {};
            state.gateTries = data.t || {};
            state.attempt = data.n || 1;
            state.completed = !!data.x;
            return true;
        } catch (e) {
            return false;
        }
    }

    function save() {
        var text = serialise();
        if (preview) {
            try { window.sessionStorage.setItem(storageKey(), text); } catch (e) { /* private mode */ }
            return;
        }
        Scorm.set('cmi.suspend_data', 'cmi.suspend_data', text);
        Scorm.set('cmi.core.lesson_location', 'cmi.location', String(state.current));
        reportProgress();
        Scorm.commit();
    }

    // ─────────────────────────────────────────────────────────────────
    // Scoring and completion
    // ─────────────────────────────────────────────────────────────────
    function scoredQuestions() {
        var list = [];
        slides.forEach(function (slide, index) {
            slide.elements.forEach(function (el) {
                if (el.scored && isGraded(el)) { list.push({ el: el, slide: index }); }
            });
        });
        return list;
    }

    function assessment() {
        var questions = scoredQuestions();
        if (!questions.length) { return null; }
        var total = 0;
        var earned = 0;
        var answered = 0;
        questions.forEach(function (q) {
            var points = Number(q.el.props.points) || 1;
            var answer = state.answers[q.el.id];
            total += points;
            if (answer && answer.f) {
                answered += 1;
                if (answer.c) { earned += points; }
            }
        });
        var score = total ? Math.round((earned / total) * 100) : 0;
        return {
            total: questions.length,
            answered: answered,
            finished: answered === questions.length,
            score: score,
            passed: score >= (S.passing_score || 0),
        };
    }

    function attemptsLeft() {
        return !S.max_attempts || state.attempt < S.max_attempts;
    }

    function allViewed() {
        return slides.every(function (slide, index) { return state.visited[index]; });
    }

    function evaluateCompletion(finishing) {
        var result = assessment();
        var viewedOk = !S.require_all_slides || allViewed();
        var passOk = !S.require_pass || (result && result.finished && result.passed);
        var status = 'incomplete';
        var complete = state.completed || (viewedOk && passOk && (finishing || S.require_all_slides || S.require_pass));
        if (complete) {
            status = result && S.require_pass ? 'passed' : 'completed';
        } else if (S.require_pass && result && result.finished && !result.passed && !attemptsLeft()) {
            status = 'failed';
        }
        state.status = status;
        if (complete) { state.completed = true; }
        return { complete: complete, status: status, assessment: result };
    }

    function reportProgress() {
        if (preview || !Scorm.api) { return; }
        var result = evaluateCompletion(false);
        var a = result.assessment;
        if (a && a.answered) {
            Scorm.set('cmi.core.score.raw', 'cmi.score.raw', a.score);
            Scorm.set('cmi.core.score.min', 'cmi.score.min', 0);
            Scorm.set('cmi.core.score.max', 'cmi.score.max', 100);
            Scorm.set(null, 'cmi.score.scaled', (a.score / 100).toFixed(2));
        }
        var progress = slides.length ? Object.keys(state.visited).length / slides.length : 0;
        Scorm.set(null, 'cmi.progress_measure', Math.min(progress, 1).toFixed(2));
        // Only send the status when it changes: some LMSs post every change
        // asynchronously, and a stale status could arrive after the final one.
        if (result.status === reportedStatus) { return; }
        reportedStatus = result.status;
        if (Scorm.v2004) {
            Scorm.set(null, 'cmi.completion_status', result.complete || state.completed ? 'completed' : 'incomplete');
            if (result.status === 'passed') { Scorm.set(null, 'cmi.success_status', 'passed'); }
            else if (result.status === 'failed') { Scorm.set(null, 'cmi.success_status', 'failed'); }
            else { Scorm.set(null, 'cmi.success_status', 'unknown'); }
        } else {
            Scorm.set('cmi.core.lesson_status', null, result.status);
        }
    }

    function recordInteraction(el, answer) {
        if (preview || !Scorm.api) { return; }
        var count = parseInt(Scorm.get('cmi.interactions._count', 'cmi.interactions._count'), 10) || 0;
        var prefix = 'cmi.interactions.' + count + '.';
        var types = { mcq: 'choice', mrq: 'choice', truefalse: 'true-false', fillblank: 'fill-in',
                      matching: 'matching', sequence: 'sequencing', survey: 'likert' };
        Scorm.set(prefix + 'id', prefix + 'id', el.id);
        Scorm.set(prefix + 'type', prefix + 'type', types[el.type] || 'other');
        if (el.type !== 'survey') {
            var res = answer.c ? 'correct' : (Scorm.v2004 ? 'incorrect' : 'wrong');
            Scorm.set(prefix + 'result', prefix + 'result', res);
        }
        var text = String(answer.r === undefined ? '' : JSON.stringify(answer.r)).slice(0, 250);
        Scorm.set(prefix + 'student_response', prefix + 'learner_response', text);
    }

    // ─────────────────────────────────────────────────────────────────
    // Gates
    // ─────────────────────────────────────────────────────────────────
    function gateStatus(index) {
        var slide = slides[index];
        var gate = slide.gate || {};
        if (skipGates || state.cleared[index]) { return { open: true }; }
        var pending = [];
        if (gate.require_interactions) {
            slide.elements.forEach(function (el) {
                if (el.required && !state.done[el.id] && !isHiddenNow(el)) { pending.push(el); }
            });
        }
        var waited = (Date.now() - slideEnteredAt) / 1000;
        var wait = Math.max(0, Math.ceil((gate.min_seconds || 0) - waited));
        var questions = slide.elements.filter(isGraded);
        var scoreOk = true;
        var allFinal = questions.every(function (q) { return state.answers[q.id] && state.answers[q.id].f; });
        var slideScore = null;
        if (gate.pass_score && questions.length) {
            if (!allFinal) {
                scoreOk = false;
                questions.forEach(function (q) {
                    if (!(state.answers[q.id] && state.answers[q.id].f) && pending.indexOf(q) === -1) { pending.push(q); }
                });
            } else {
                var correct = questions.filter(function (q) { return state.answers[q.id].c; }).length;
                slideScore = Math.round((correct / questions.length) * 100);
                scoreOk = slideScore >= gate.pass_score;
            }
        }
        var open = !pending.length && !wait && scoreOk;
        return { open: open, pending: pending, wait: wait, failed: allFinal && !scoreOk && gate.pass_score,
                 slideScore: slideScore };
    }

    function isHiddenNow(el) {
        var node = document.querySelector('[data-el="' + el.id + '"]');
        return node ? node.classList.contains('sp-hidden') : !!el.hidden;
    }

    function markDone(el) {
        if (!el || state.done[el.id]) { return; }
        state.done[el.id] = 1;
        var node = document.querySelector('[data-el="' + el.id + '"]');
        if (node) { node.classList.add('sp-done'); }
        refreshNav();
        save();
    }

    // ─────────────────────────────────────────────────────────────────
    // Element rendering
    // ─────────────────────────────────────────────────────────────────
    function applyStyle(node, style) {
        style = style || {};
        if (style.fontSize) { node.style.fontSize = style.fontSize + 'px'; }
        if (style.color) { node.style.color = style.color; }
        if (style.fontFamily) { node.style.fontFamily = style.fontFamily; }
        if (style.bold) { node.style.fontWeight = 'bold'; }
        if (style.italic) { node.style.fontStyle = 'italic'; }
        if (style.align) { node.style.textAlign = style.align; }
        if (style.background) { node.style.background = style.background; }
        if (style.borderWidth) {
            node.style.border = style.borderWidth + 'px ' + (style.borderStyle || 'solid') + ' ' + (style.borderColor || '#000');
        }
        if (style.radius) { node.style.borderRadius = Math.min(style.radius, 9999) + 'px'; }
        if (style.opacity !== undefined && style.opacity !== '') { node.style.opacity = style.opacity; }
        if (style.padding) { node.style.padding = style.padding + 'px'; }
        if (style.shadow) { node.style.boxShadow = '0 6px 18px rgba(0,0,0,0.18)'; }
    }

    function renderElement(el, slideIndex) {
        var node = h('div', { class: 'sp-el sp-el-' + el.type + (el.hidden ? ' sp-hidden' : '') +
                                     (state.done[el.id] ? ' sp-done' : ''),
                              'data-el': el.id });
        node.style.left = el.x + 'px';
        node.style.top = el.y + 'px';
        node.style.width = el.w + 'px';
        node.style.height = el.h + 'px';
        node.style.zIndex = el.z || 1;
        if (el.rotation) { node.style.transform = 'rotate(' + el.rotation + 'deg)'; }
        var render = RENDERERS[el.type];
        if (render) { render(node, el, slideIndex); }
        // These style their own inner box (buttons: so shaped buttons keep their outline)
        if (!isQuestion(el) && ['text', 'shape', 'results', 'button'].indexOf(el.type) === -1) {
            applyStyle(node, el.style);
        }
        return node;
    }

    function doAction(props, el) {
        var action = props.action || 'next';
        markDone(el);
        if (action === 'next') { goNext(); }
        else if (action === 'prev') { goTo(state.current - 1); }
        else if (action === 'goto') {
            var target = Number(props.target_slide);
            if (target >= 0) {
                var open = gateStatus(state.current).open;
                if (target <= state.current || open) {
                    if (open && !skipGates) { state.cleared[state.current] = 1; }
                    goTo(target, true);
                } else { flashLocked(); }
            }
        } else if (action === 'url' && props.url) { window.open(props.url, '_blank', 'noopener'); }
        else if (action === 'reveal' && props.target_element) {
            var target_node = document.querySelector('[data-el="' + props.target_element + '"]');
            if (target_node) {
                target_node.classList.remove('sp-hidden');
                target_node.classList.add('sp-reveal');
            }
        } else if (action === 'popup') { openPopup(props.popup_title, props.popup_text); }
    }

    function openPopup(title, html) {
        var close = function () { overlay.remove(); };
        var overlay = h('div', { class: 'sp-modal', onclick: function (ev) { if (ev.target === overlay) { close(); } } }, [
            h('div', { class: 'sp-modal-box', role: 'dialog', 'aria-modal': 'true' }, [
                title ? h('h2', { text: title }) : null,
                h('div', { class: 'sp-modal-body', html: html || '' }),
                h('button', { class: 'sp-btn sp-btn-primary', text: label('label_close', 'Close'), onclick: close }),
            ]),
        ]);
        ui.app.appendChild(overlay);
        overlay.querySelector('button').focus();
    }

    var RENDERERS = {
        text: function (node, el) {
            var inner = h('div', { class: 'sp-text sp-valign-' + (el.props.valign || 'top'), html: el.props.html || '' });
            applyStyle(inner, el.style);
            if (!el.style || !el.style.padding) { inner.style.padding = '4px 8px'; }
            node.appendChild(inner);
        },
        shape: function (node, el) {
            var shape = el.props.shape || 'rect';
            var inner = h('div', { class: 'sp-shape sp-shape-' + shape });
            if (shape === 'line') {
                inner.style.borderTop = (el.style.borderWidth || 2) + 'px solid ' + (el.style.borderColor || '#333');
                inner.style.top = '50%';
            } else {
                applyStyle(inner, el.style);
                if (CLIPPED_SHAPES.indexOf(shape) !== -1 && el.style.shadow) {
                    // A clipped shape would cut its own shadow off: shadow the wrapper instead
                    inner.style.boxShadow = '';
                    node.classList.add('sp-drop-shadow');
                }
                if (!el.style.background && !el.style.borderWidth) { inner.style.background = 'var(--brand-primary)'; }
            }
            node.appendChild(inner);
        },
        image: function (node, el) {
            if (!el.props.src) { return; }
            var fit = el.props.fit === 'fill' ? 'fill' : (el.props.fit || 'contain');
            node.appendChild(h('img', { src: el.props.src, alt: el.props.alt || '', style: { objectFit: fit } }));
        },
        video: function (node, el) {
            var embed = el.props.src ? null : videoEmbedUrl(el.props.url);
            if (embed) {
                var frame = h('iframe', { src: embed, allow: 'autoplay; fullscreen; picture-in-picture', allowfullscreen: true,
                                          title: el.props.title || 'Video' });
                node.appendChild(frame);
                watchIframe(frame, el);
                return;
            }
            var src = el.props.src || el.props.url;
            if (!src) { return; }
            var video = h('video', { src: src, controls: true, playsinline: true, preload: 'metadata',
                                     poster: el.props.poster_src || null });
            if (el.props.autoplay) { video.autoplay = true; video.muted = true; }
            trackMedia(video, el);
            node.appendChild(video);
        },
        audio: function (node, el) {
            var src = el.props.src || el.props.url;
            if (!src) { return; }
            var audio = h('audio', { src: src, controls: true, preload: 'metadata' });
            if (el.props.autoplay) { audio.autoplay = true; }
            trackMedia(audio, el);
            node.appendChild(audio);
        },
        embed: function (node, el) {
            if (!el.props.url) { return; }
            var frame = h('iframe', { src: el.props.url, title: el.props.title || 'Web content', allowfullscreen: true });
            node.appendChild(frame);
            watchIframe(frame, el);
        },
        button: function (node, el) {
            var p = el.props;
            var shape = p.shape || 'rect';
            var content = p.content || 'text';
            var btn = h('button', { class: 'sp-btn sp-btn-primary sp-btn-fill sp-shape-' + shape, type: 'button',
                                    onclick: function () { doAction(p, el); } });
            var label = h('span', { class: 'sp-btn-label' });
            if (p.label_html) {
                label.innerHTML = p.label_html;
            } else {
                label.textContent = p.label || 'Button';
            }
            var icon = p.icon && content !== 'text' ? h('i', { class: 'fa ' + p.icon, 'aria-hidden': 'true' }) : null;
            var inner = h('span', { class: 'sp-btn-content' + (p.icon_position === 'right' ? ' sp-icon-right' : '') });
            if (icon) { inner.appendChild(icon); }
            if (content !== 'icon') { inner.appendChild(label); }
            btn.appendChild(inner);
            btn.setAttribute('aria-label', p.label || label.textContent.trim() || (p.icon || '').replace('fa-', ''));
            applyStyle(btn, el.style);
            if (CLIPPED_SHAPES.indexOf(shape) !== -1) {
                btn.style.borderRadius = '';
                if (el.style.shadow) { btn.style.boxShadow = ''; node.classList.add('sp-drop-shadow'); }
            }
            node.appendChild(btn);
        },
        hotspot: function (node, el) {
            node.classList.add('sp-hotspot');
            if (el.props.pulse !== false) { node.classList.add('sp-pulse'); }
            node.setAttribute('role', 'button');
            node.setAttribute('tabindex', '0');
            node.setAttribute('aria-label', el.props.popup_title || 'Hotspot');
            var activate = function () {
                node.classList.add('sp-visited');
                doAction(Object.assign({ action: 'popup' }, el.props), el);
            };
            node.addEventListener('click', activate);
            node.addEventListener('keydown', function (ev) { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); activate(); } });
        },
        tabs: function (node, el) {
            var items = el.props.items || [];
            var seen = {};
            var head = h('div', { class: 'sp-tabs-head', role: 'tablist' });
            var body = h('div', { class: 'sp-tabs-body' });
            var show = function (index) {
                seen[index] = true;
                Array.prototype.forEach.call(head.children, function (b, i) {
                    b.classList.toggle('active', i === index);
                    b.setAttribute('aria-selected', i === index ? 'true' : 'false');
                    if (seen[i]) { b.classList.add('seen'); }
                });
                body.innerHTML = items[index] ? items[index].html || '' : '';
                if (Object.keys(seen).length >= items.length) { markDone(el); }
            };
            items.forEach(function (item, index) {
                head.appendChild(h('button', { type: 'button', role: 'tab', text: item.title || ('Tab ' + (index + 1)),
                                               onclick: function () { show(index); } }));
            });
            node.appendChild(head);
            node.appendChild(body);
            if (items.length) { show(0); }
        },
        accordion: function (node, el) {
            var items = el.props.items || [];
            var seen = {};
            items.forEach(function (item, index) {
                var panel = h('div', { class: 'sp-acc-panel', html: item.html || '' });
                var head = h('button', { type: 'button', class: 'sp-acc-head', 'aria-expanded': 'false',
                    onclick: function () {
                        var open = !wrap.classList.contains('open');
                        wrap.classList.toggle('open', open);
                        head.setAttribute('aria-expanded', open ? 'true' : 'false');
                        if (open) {
                            seen[index] = true;
                            wrap.classList.add('seen');
                            if (Object.keys(seen).length >= items.length) { markDone(el); }
                        }
                    } }, [item.title || ('Section ' + (index + 1))]);
                var wrap = h('div', { class: 'sp-acc-item' }, [head, panel]);
                node.appendChild(wrap);
            });
        },
        flipcard: function (node, el) {
            var card = h('div', { class: 'sp-flip', role: 'button', tabindex: '0', 'aria-label': 'Flip card' }, [
                h('div', { class: 'sp-flip-inner' }, [
                    h('div', { class: 'sp-flip-front', html: el.props.front_html || '' }),
                    h('div', { class: 'sp-flip-back', html: el.props.back_html || '' }),
                ]),
            ]);
            var front = card.querySelector('.sp-flip-front');
            var back = card.querySelector('.sp-flip-back');
            applyStyle(front, el.style);
            front.style.background = el.style.background || 'var(--brand-primary)';
            front.style.color = el.style.color || 'var(--brand-button-text)';
            back.style.background = el.props.back_background || 'var(--brand-slide)';
            back.style.borderColor = el.style.background || 'var(--brand-primary)';
            var flip = function () { card.classList.toggle('flipped'); markDone(el); };
            card.addEventListener('click', flip);
            card.addEventListener('keydown', function (ev) { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); flip(); } });
            node.appendChild(card);
        },
        labeled_graphic: function (node, el) {
            var markers = el.props.markers || [];
            var seen = {};
            var wrap = h('div', { class: 'sp-lg' });
            if (el.props.src) { wrap.appendChild(h('img', { src: el.props.src, alt: el.props.alt || '' })); }
            markers.forEach(function (marker, index) {
                var dot = h('button', { type: 'button', class: 'sp-lg-marker', text: String(index + 1),
                                        'aria-label': marker.title || ('Marker ' + (index + 1)),
                                        style: { left: (marker.x || 0) + '%', top: (marker.y || 0) + '%' },
                    onclick: function () {
                        seen[index] = true;
                        dot.classList.add('seen');
                        openPopup(marker.title, marker.text);
                        if (Object.keys(seen).length >= markers.length) { markDone(el); }
                    } });
                wrap.appendChild(dot);
            });
            node.appendChild(wrap);
        },
        results: function (node, el, slideIndex) {
            node.classList.add('sp-results');
            applyStyle(node, el.style);
            var draw = function () {
                node.innerHTML = '';
                var result = evaluateCompletion(false);
                var a = result.assessment;
                if (!a) {
                    node.appendChild(h('div', { class: 'sp-results-msg', html: el.props.pass_html || label('label_complete') }));
                    markDone(el);
                    return;
                }
                if (!a.finished) {
                    node.appendChild(h('div', { class: 'sp-results-msg', text: a.answered + ' / ' + a.total }));
                    return;
                }
                node.appendChild(h('div', { class: 'sp-results-score' }, [
                    h('span', { class: 'sp-results-label', text: label('label_score', 'Your score') }),
                    h('strong', { text: a.score + '%' }),
                ]));
                var passed = a.passed;
                node.appendChild(h('div', { class: 'sp-results-msg ' + (passed ? 'sp-pass' : 'sp-fail'),
                                            html: passed ? (el.props.pass_html || label('label_passed'))
                                                         : (el.props.fail_html || label('label_failed')) }));
                if (!passed && attemptsLeft() && el.props.allow_retry !== false) {
                    node.appendChild(h('button', { type: 'button', class: 'sp-btn sp-btn-primary', text: label('label_retry', 'Try Again'),
                                                   onclick: retryAssessment }));
                }
                markDone(el);
            };
            node._draw = draw;
            draw();
        },
    };
    QUESTION_TYPES.forEach(function (type) { RENDERERS[type] = renderQuestion; });

    function trackMedia(media, el) {
        var furthest = 0;
        media.addEventListener('timeupdate', function () {
            furthest = Math.max(furthest, media.currentTime);
            if (media.duration && furthest / media.duration >= 0.95) { markDone(el); }
        });
        media.addEventListener('ended', function () { markDone(el); });
    }

    function watchIframe(frame, el) {
        // Clicking into a cross-origin frame blurs this window: count it as viewed.
        var onBlur = function () {
            setTimeout(function () {
                if (document.activeElement === frame) { markDone(el); }
            }, 0);
        };
        window.addEventListener('blur', onBlur);
        frame._cleanup = function () { window.removeEventListener('blur', onBlur); };
    }

    // ─────────────────────────────────────────────────────────────────
    // Questions
    // ─────────────────────────────────────────────────────────────────
    function renderQuestion(node, el) {
        var p = el.props || {};
        node.classList.add('sp-question');
        applyStyle(node, el.style);
        var answer = state.answers[el.id];
        var box = h('div', { class: 'sp-q-inner' });
        box.appendChild(h('div', { class: 'sp-q-prompt', html: p.prompt || '' }));
        var form = h('div', { class: 'sp-q-form' });
        var seed = hashSeed(el.id + ':' + state.attempt);
        var getResponse;
        var setLocked;
        var showCorrect;

        if (el.type === 'mcq' || el.type === 'truefalse' || el.type === 'mrq' || el.type === 'survey') {
            var multi = el.type === 'mrq';
            var options = (p.options || []).map(function (o, i) { return { text: o.text, correct: !!o.correct, i: i }; });
            if (p.shuffle && el.type !== 'truefalse' && el.type !== 'survey') { options = shuffle(options, seed); }
            var inputs = [];
            var list = h('div', { class: 'sp-q-options' + (el.type === 'survey' ? ' sp-q-scale' : '') });
            options.forEach(function (o) {
                var input = h('input', { type: multi ? 'checkbox' : 'radio', name: 'q_' + el.id, value: String(o.i) });
                inputs.push(input);
                list.appendChild(h('label', { class: 'sp-q-option', 'data-index': o.i }, [input, h('span', { text: o.text || '' })]));
            });
            form.appendChild(list);
            getResponse = function () {
                var chosen = inputs.filter(function (i) { return i.checked; }).map(function (i) { return Number(i.value); });
                return chosen.length ? (multi ? chosen.sort() : chosen[0]) : null;
            };
            var check = function (resp) {
                if (el.type === 'survey') { return true; }
                var correct = (p.options || []).map(function (o, i) { return o.correct ? i : -1; }).filter(function (i) { return i >= 0; });
                if (multi) { return JSON.stringify((resp || []).slice().sort()) === JSON.stringify(correct); }
                return correct.indexOf(resp) !== -1;
            };
            form._check = check;
            form._restore = function (resp) {
                inputs.forEach(function (i) {
                    i.checked = multi ? (resp || []).indexOf(Number(i.value)) !== -1 : Number(i.value) === resp;
                });
            };
            setLocked = function (locked) { inputs.forEach(function (i) { i.disabled = locked; }); };
            showCorrect = function () {
                Array.prototype.forEach.call(list.children, function (lab) {
                    var o = (p.options || [])[Number(lab.getAttribute('data-index'))];
                    if (o && o.correct) { lab.classList.add('sp-correct-answer'); }
                });
            };
        } else if (el.type === 'fillblank') {
            var input = h('input', { type: 'text', class: 'sp-q-text', 'aria-label': 'Answer', autocomplete: 'off' });
            form.appendChild(input);
            getResponse = function () { return input.value.trim() ? input.value.trim() : null; };
            form._check = function (resp) {
                return (p.answers || []).some(function (a) { return normalise(a, p.case_sensitive) === normalise(resp, p.case_sensitive); });
            };
            form._restore = function (resp) { input.value = resp || ''; };
            setLocked = function (locked) { input.disabled = locked; };
            showCorrect = function () {
                if ((p.answers || []).length) {
                    form.appendChild(h('div', { class: 'sp-correct-answer sp-q-answer', text: p.answers[0] }));
                }
            };
            input.addEventListener('keydown', function (ev) { if (ev.key === 'Enter') { submit(); } });
        } else if (el.type === 'matching') {
            var pairs = p.pairs || [];
            var rights = shuffle(pairs.map(function (pair, i) { return { text: pair.right, i: i }; }), seed);
            var selects = [];
            var table = h('div', { class: 'sp-q-matching' });
            pairs.forEach(function (pair) {
                var select = h('select', { 'aria-label': pair.left || '' }, [h('option', { value: '', text: '—' })]
                    .concat(rights.map(function (r) { return h('option', { value: String(r.i), text: r.text || '' }); })));
                selects.push(select);
                table.appendChild(h('div', { class: 'sp-q-match-row' }, [h('span', { text: pair.left || '' }), select]));
            });
            form.appendChild(table);
            getResponse = function () {
                var resp = selects.map(function (s) { return s.value === '' ? null : Number(s.value); });
                return resp.some(function (r) { return r === null; }) ? null : resp;
            };
            form._check = function (resp) { return resp.every(function (r, i) { return r === i; }); };
            form._restore = function (resp) { selects.forEach(function (s, i) { s.value = resp && resp[i] !== null ? String(resp[i]) : ''; }); };
            setLocked = function (locked) { selects.forEach(function (s) { s.disabled = locked; }); };
            showCorrect = function () {
                selects.forEach(function (s, i) {
                    var row = s.parentNode;
                    if (Number(s.value) !== i) {
                        row.appendChild(h('span', { class: 'sp-correct-answer sp-q-answer', text: pairs[i].right }));
                    }
                });
            };
        } else if (el.type === 'sequence') {
            var items = (p.items || []).map(function (text, i) { return { text: text, i: i }; });
            var order = shuffle(items, seed);
            if (order.every(function (o, i) { return o.i === i; }) && order.length > 1) { order.push(order.shift()); }
            var listEl = h('ol', { class: 'sp-q-sequence' });
            var draw = function () {
                listEl.innerHTML = '';
                order.forEach(function (item, index) {
                    var up = h('button', { type: 'button', class: 'sp-seq-btn', 'aria-label': 'Move up', text: '▲',
                                           onclick: function () { move(index, -1); } });
                    var down = h('button', { type: 'button', class: 'sp-seq-btn', 'aria-label': 'Move down', text: '▼',
                                             onclick: function () { move(index, 1); } });
                    up.disabled = index === 0 || listEl._locked;
                    down.disabled = index === order.length - 1 || listEl._locked;
                    listEl.appendChild(h('li', { draggable: listEl._locked ? 'false' : 'true', 'data-index': index,
                        ondragstart: function (ev) { ev.dataTransfer.setData('text/plain', String(index)); },
                        ondragover: function (ev) { ev.preventDefault(); },
                        ondrop: function (ev) {
                            ev.preventDefault();
                            var from = Number(ev.dataTransfer.getData('text/plain'));
                            var moved = order.splice(from, 1)[0];
                            order.splice(index, 0, moved);
                            draw();
                        } }, [h('span', { class: 'sp-seq-text', text: item.text || '' }), up, down]));
                });
            };
            var move = function (index, delta) {
                var target = index + delta;
                if (target < 0 || target >= order.length) { return; }
                var moved = order.splice(index, 1)[0];
                order.splice(target, 0, moved);
                draw();
            };
            draw();
            form.appendChild(listEl);
            getResponse = function () { return order.map(function (o) { return o.i; }); };
            form._check = function (resp) { return resp.every(function (r, i) { return r === i; }); };
            form._restore = function (resp) {
                if (resp && resp.length === items.length) { order = resp.map(function (i) { return items[i]; }); draw(); }
            };
            setLocked = function (locked) { listEl._locked = locked; draw(); };
            showCorrect = function () {
                form.appendChild(h('ol', { class: 'sp-correct-answer sp-q-answer' },
                    items.map(function (i) { return h('li', { text: i.text }); })));
            };
        }

        var feedback = h('div', { class: 'sp-q-feedback', 'aria-live': 'polite' });
        var submitBtn = h('button', { type: 'button', class: 'sp-btn sp-btn-primary', text: label('label_submit', 'Submit') });
        var retryBtn = h('button', { type: 'button', class: 'sp-btn sp-btn-secondary sp-hidden', text: label('label_retry', 'Try Again') });
        var actions = h('div', { class: 'sp-q-actions' }, [submitBtn, retryBtn]);
        box.appendChild(form);
        box.appendChild(actions);
        box.appendChild(feedback);
        node.appendChild(box);

        var maxTries = Number(p.attempts) || 0;
        function showFeedback(ans) {
            feedback.innerHTML = '';
            if (el.type === 'survey') {
                feedback.appendChild(h('div', { class: 'sp-fb sp-fb-neutral', html: p.feedback_correct || '' }));
                return;
            }
            var good = ans.c;
            var text = good ? (p.feedback_correct || label('label_correct', 'Correct!'))
                            : (p.feedback_incorrect || label('label_incorrect', 'Not quite.'));
            feedback.appendChild(h('div', { class: 'sp-fb ' + (good ? 'sp-fb-good' : 'sp-fb-bad'), html: text }));
        }
        function lock(ans) {
            setLocked(true);
            submitBtn.classList.add('sp-hidden');
            retryBtn.classList.toggle('sp-hidden', ans.f || ans.c);
            if (ans.f && !ans.c && S.show_answers && el.type !== 'survey') { showCorrect(); }
        }
        function submit() {
            var resp = getResponse();
            if (resp === null || resp === undefined) {
                node.classList.add('sp-shake');
                setTimeout(function () { node.classList.remove('sp-shake'); }, 400);
                return;
            }
            var prev = state.answers[el.id] || { n: 0 };
            var correct = !!form._check(resp);
            var tries = (prev.n || 0) + 1;
            // Final once right, or once the question's attempts are used up.
            // With unlimited attempts a wrong answer can be retried until right.
            var final = correct || el.type === 'survey' || (maxTries > 0 && tries >= maxTries);
            var ans = { r: resp, c: correct, n: tries, f: final ? 1 : 0 };
            state.answers[el.id] = ans;
            recordInteraction(el, ans);
            showFeedback(ans);
            lock(ans);
            if (final) { markDone(el); }
            onAnswered();
            save();
        }
        submitBtn.addEventListener('click', submit);
        retryBtn.addEventListener('click', function () {
            setLocked(false);
            feedback.innerHTML = '';
            retryBtn.classList.add('sp-hidden');
            submitBtn.classList.remove('sp-hidden');
        });
        if (answer) {
            form._restore(answer.r);
            showFeedback(answer);
            lock(answer);
            if (!answer.f && !answer.c) {
                setLocked(false);
                retryBtn.classList.add('sp-hidden');
                submitBtn.classList.remove('sp-hidden');
            }
        }
    }

    function onAnswered() {
        var status = gateStatus(state.current);
        var gate = slides[state.current].gate || {};
        if (status.failed) {
            state.gateTries[state.current] = (state.gateTries[state.current] || 0) + 1;
        }
        document.querySelectorAll('.sp-results').forEach(function (node) { if (node._draw) { node._draw(); } });
        refreshNav();
        if (status.failed) { showGateFailure(gate, status); }
    }

    function resetQuestions(index) {
        slides[index].elements.forEach(function (el) {
            if (isQuestion(el)) {
                delete state.answers[el.id];
                delete state.done[el.id];
            }
        });
    }

    function showGateFailure(gate, status) {
        var tries = state.gateTries[state.current] || 0;
        var exhausted = gate.max_attempts && tries >= gate.max_attempts;
        var index = state.current;
        var msg = h('div', { class: 'sp-gate-fail' }, [
            h('strong', { text: label('label_score', 'Your score') + ': ' + status.slideScore + '%' }),
            h('span', { text: ' — ' + label('label_failed', '') }),
        ]);
        var retry = function () {
            resetQuestions(index);
            if (exhausted) { state.gateTries[index] = 0; }
            save();
            if (exhausted && gate.fail_slide >= 0) {
                goTo(gate.fail_slide, true);
            } else {
                renderSlide();
            }
        };
        var button = h('button', { type: 'button', class: 'sp-btn sp-btn-primary',
                                   text: exhausted && gate.fail_slide >= 0 ? label('label_review', 'Review') : label('label_retry', 'Try Again'),
                                   onclick: retry });
        msg.appendChild(button);
        ui.notice.innerHTML = '';
        ui.notice.appendChild(msg);
        ui.notice.classList.remove('sp-hidden');
    }

    function retryAssessment() {
        state.attempt += 1;
        var first = -1;
        slides.forEach(function (slide, index) {
            var hasScored = slide.elements.some(function (el) { return el.scored && isGraded(el); });
            if (hasScored) {
                resetQuestions(index);
                delete state.cleared[index];
                delete state.gateTries[index];
                if (first === -1) { first = index; }
            }
        });
        state.completed = false;
        save();
        goTo(first >= 0 ? first : 0, true);
    }

    // ─────────────────────────────────────────────────────────────────
    // Navigation
    // ─────────────────────────────────────────────────────────────────
    function maxReachable() {
        if (S.navigation === 'free' || skipGates) { return slides.length - 1; }
        var max = 0;
        for (var i = 0; i < slides.length; i++) {
            max = i;
            if (!state.cleared[i]) { break; }
        }
        return max;
    }

    function goTo(index, force) {
        if (index < 0 || index >= slides.length) { return; }
        if (!force && index > maxReachable()) { flashLocked(); return; }
        state.current = index;
        renderSlide();
        save();
    }

    function goNext() {
        var status = gateStatus(state.current);
        if (!status.open) { flashLocked(); return; }
        if (!skipGates) { state.cleared[state.current] = 1; }
        if (state.current >= slides.length - 1) { finishCourse(); return; }
        goTo(state.current + 1, true);
    }

    function flashLocked() {
        ui.hint.classList.add('sp-flash');
        setTimeout(function () { ui.hint.classList.remove('sp-flash'); }, 600);
    }

    function finishCourse() {
        var result = evaluateCompletion(true);
        if (!result.complete && result.status !== 'failed') {
            var a = result.assessment;
            var unvisited = S.require_all_slides && !allViewed();
            var unanswered = S.require_pass && a && !a.finished;
            if (unvisited || unanswered) {
                openMenu();
                flashLocked();
                return;
            }
        }
        save();
        // Leave the session open while the learner can still retry the assessment
        if (!preview && (result.complete || result.status === 'failed')) { Scorm.finish(); }
        showEndScreen(result);
    }

    function showEndScreen(result) {
        clearTimer();
        var a = result.assessment;
        ui.stageWrap.innerHTML = '';
        ui.footer.classList.add('sp-hidden');
        var children = [
            C.branding && C.branding.logo ? h('img', { class: 'sp-start-logo', src: C.branding.logo, alt: '' }) : null,
            h('h1', { text: C.title }),
        ];
        if (a && a.finished) {
            children.push(h('p', { class: 'sp-end-score', text: label('label_score', 'Your score') + ': ' + a.score + '%' }));
            children.push(h('p', { text: a.passed ? label('label_passed') : label('label_failed') }));
        }
        if (result.complete) {
            children.push(h('p', { text: label('label_complete') }));
        } else if (a && a.finished && !a.passed && attemptsLeft()) {
            children.push(h('button', { type: 'button', class: 'sp-btn sp-btn-primary', text: label('label_retry', 'Try Again'),
                                        onclick: function () { ui.footer.classList.remove('sp-hidden'); retryAssessment(); } }));
        }
        if (preview) {
            children.push(h('button', { type: 'button', class: 'sp-btn sp-btn-primary', text: label('label_restart', 'Start Again'),
                                        onclick: resetPreview }));
        }
        ui.stageWrap.appendChild(h('div', { class: 'sp-start' }, [h('div', { class: 'sp-start-card' }, children)]));
    }

    function clearTimer() {
        if (slideTimer) { clearInterval(slideTimer); slideTimer = null; }
    }

    function refreshNav() {
        if (!ui.next) { return; }
        var index = state.current;
        var status = gateStatus(index);
        var last = index === slides.length - 1;
        ui.back.classList.toggle('sp-hidden', !(S.allow_back && index > 0));
        ui.next.textContent = last ? label('label_finish', 'Finish') : (state.cleared[index] ? label('label_next', 'Next') : label('label_continue', 'Continue'));
        // Continue only appears once the slide's requirements are met
        ui.next.classList.toggle('sp-hidden', !status.open);
        ui.hint.classList.toggle('sp-hidden', status.open);
        if (!status.open) {
            ui.hint.textContent = status.wait && !(status.pending || []).length
                ? label('label_wait', 'Continue in {seconds}s').replace('{seconds}', status.wait)
                : label('label_locked');
        }
        if (status.open && !state.cleared[index] && !skipGates) {
            state.cleared[index] = 1;
            save();
        }
        if (ui.counter) {
            ui.counter.textContent = S.show_slide_numbers ? (index + 1) + ' / ' + slides.length : '';
        }
        if (ui.progress) {
            var pct = slides.length ? Math.round((Object.keys(state.visited).length / slides.length) * 100) : 0;
            ui.progress.style.width = pct + '%';
            ui.progressWrap.setAttribute('aria-valuenow', String(pct));
        }
        if (ui.menu && ui.menu.classList.contains('open')) { drawMenu(); }
    }

    function renderSlide() {
        clearTimer();
        document.querySelectorAll('iframe').forEach(function (f) { if (f._cleanup) { f._cleanup(); } });
        var index = state.current;
        var slide = slides[index];
        state.visited[index] = 1;
        slideEnteredAt = Date.now();
        ui.notice.classList.add('sp-hidden');
        ui.footer.classList.remove('sp-hidden');
        ui.stageWrap.innerHTML = '';
        var stage = h('div', { class: 'sp-slide', role: 'region', 'aria-label': slide.title || ('Slide ' + (index + 1)) });
        stage.style.width = C.width + 'px';
        stage.style.height = C.height + 'px';
        if (slide.background_color) { stage.style.background = slide.background_color; }
        if (slide.background_image) {
            stage.style.backgroundImage = 'url("' + slide.background_image + '")';
            stage.style.backgroundSize = 'cover';
            stage.style.backgroundPosition = 'center';
        }
        slide.elements.slice().sort(function (a, b) { return (a.z || 0) - (b.z || 0); }).forEach(function (el) {
            stage.appendChild(renderElement(el, index));
        });
        ui.stage = stage;
        ui.stageWrap.appendChild(stage);
        fitStage();
        var gate = slide.gate || {};
        if (gate.min_seconds && !state.cleared[index] && !skipGates) {
            slideTimer = setInterval(function () {
                refreshNav();
                if (gateStatus(index).wait <= 0) { clearTimer(); refreshNav(); }
            }, 1000);
        }
        refreshNav();
        var status = gateStatus(index);
        if (status.failed) { showGateFailure(gate, status); }
        ui.stageWrap.focus({ preventScroll: true });
        if (preview && ui.previewSlide) { ui.previewSlide.textContent = 'Slide ' + (index + 1); }
    }

    function fitStage() {
        if (!ui.stage) { return; }
        var wrap = ui.stageWrap.getBoundingClientRect();
        var scale = Math.min((wrap.width - 16) / C.width, (wrap.height - 16) / C.height);
        scale = Math.max(scale, 0.1);
        ui.stage.style.transform = 'scale(' + scale + ')';
        ui.stage.style.left = Math.max((wrap.width - C.width * scale) / 2, 0) + 'px';
        ui.stage.style.top = Math.max((wrap.height - C.height * scale) / 2, 0) + 'px';
    }

    // ─────────────────────────────────────────────────────────────────
    // Menu
    // ─────────────────────────────────────────────────────────────────
    function drawMenu() {
        var reach = maxReachable();
        ui.menuList.innerHTML = '';
        slides.forEach(function (slide, index) {
            if (slide.hide_in_menu) { return; }
            var locked = index > reach;
            var item = h('button', { type: 'button', class: 'sp-menu-item' + (index === state.current ? ' current' : '') +
                                                           (state.visited[index] ? ' visited' : '') + (locked ? ' locked' : ''),
                                     disabled: locked,
                                     onclick: function () { closeMenu(); goTo(index); } }, [
                h('span', { class: 'sp-menu-num', text: String(index + 1) }),
                h('span', { class: 'sp-menu-title', text: slide.title || ('Slide ' + (index + 1)) }),
            ]);
            ui.menuList.appendChild(item);
        });
    }
    function openMenu() { drawMenu(); ui.menu.classList.add('open'); ui.menu.setAttribute('aria-hidden', 'false'); }
    function closeMenu() { ui.menu.classList.remove('open'); ui.menu.setAttribute('aria-hidden', 'true'); }

    // ─────────────────────────────────────────────────────────────────
    // Shell
    // ─────────────────────────────────────────────────────────────────
    function buildShell() {
        var app = document.getElementById('sp-app');
        app.innerHTML = '';
        ui.app = app;
        var brand = C.branding || {};
        var header = h('header', { class: 'sp-header' }, [
            S.show_menu ? h('button', { type: 'button', class: 'sp-icon-btn', 'aria-label': label('label_menu', 'Menu'),
                                        title: label('label_menu', 'Menu'),
                                        onclick: function () { if (ui.menu.classList.contains('open')) { closeMenu(); } else { openMenu(); } } },
                            [h('span', { class: 'sp-burger' })]) : null,
            brand.logo ? h('img', { class: 'sp-logo', src: brand.logo, alt: '' }) : null,
            h('div', { class: 'sp-title', text: C.title }),
        ]);
        if (S.show_progress) {
            ui.progress = h('div', { class: 'sp-progress-bar' });
            ui.progressWrap = h('div', { class: 'sp-progress', role: 'progressbar', 'aria-valuemin': '0', 'aria-valuemax': '100' }, [ui.progress]);
            header.appendChild(ui.progressWrap);
        }
        ui.menuList = h('div', { class: 'sp-menu-list' });
        ui.menu = h('nav', { class: 'sp-menu', 'aria-hidden': 'true' }, [
            h('div', { class: 'sp-menu-head' }, [
                h('span', { text: label('label_menu', 'Menu') }),
                h('button', { type: 'button', class: 'sp-icon-btn', 'aria-label': label('label_close', 'Close'), text: '×', onclick: closeMenu }),
            ]),
            ui.menuList,
        ]);
        ui.stageWrap = h('main', { class: 'sp-stage-wrap', tabindex: '-1' });
        ui.notice = h('div', { class: 'sp-notice sp-hidden', 'aria-live': 'polite' });
        ui.back = h('button', { type: 'button', class: 'sp-btn sp-btn-secondary', text: label('label_back', 'Back'),
                                onclick: function () { goTo(state.current - 1, true); } });
        ui.next = h('button', { type: 'button', class: 'sp-btn sp-btn-primary', text: label('label_next', 'Next'), onclick: goNext });
        ui.hint = h('div', { class: 'sp-hint', 'aria-live': 'polite' });
        ui.counter = h('div', { class: 'sp-counter' });
        ui.footer = h('footer', { class: 'sp-footer' }, [
            h('div', { class: 'sp-footer-left' }, [ui.back]),
            ui.counter,
            h('div', { class: 'sp-footer-right' }, [ui.hint, ui.next]),
        ]);
        if (preview) {
            ui.previewSlide = h('span', { class: 'sp-preview-slide' });
            var skip = h('input', { type: 'checkbox', onchange: function () { skipGates = skip.checked; refreshNav(); } });
            app.appendChild(h('div', { class: 'sp-preview-bar' }, [
                h('strong', { text: 'Preview mode' }),
                h('span', { text: ' – nothing is saved to the LMS or to any training record. ' }),
                ui.previewSlide,
                h('label', { class: 'sp-preview-skip' }, [skip, ' Skip slide gates']),
                h('button', { type: 'button', class: 'sp-btn sp-btn-small', text: 'Restart', onclick: resetPreview }),
            ]));
        }
        app.appendChild(header);
        app.appendChild(h('div', { class: 'sp-body' }, [ui.menu, ui.stageWrap, ui.notice]));
        app.appendChild(ui.footer);
        document.addEventListener('keydown', function (ev) {
            if (ev.target && /input|textarea|select/i.test(ev.target.tagName)) { return; }
            if (ev.key === 'Escape') { closeMenu(); }
        });
        window.addEventListener('resize', fitStage);
    }

    function resetPreview() {
        try { window.sessionStorage.removeItem(storageKey()); } catch (e) { /* private mode */ }
        window.location.search = '';
    }

    function showStartScreen(resumable) {
        ui.footer.classList.add('sp-hidden');
        ui.stageWrap.innerHTML = '';
        var start = function (resume) {
            if (!resume) {
                var completed = state.completed;
                state.current = 0;
                state.visited = {};
                state.done = {};
                state.answers = {};
                state.gateTries = {};
                state.cleared = {};
                state.completed = completed;
            }
            renderSlide();
            save();
        };
        var buttons = [];
        if (resumable) {
            buttons.push(h('button', { type: 'button', class: 'sp-btn sp-btn-primary sp-btn-large', text: label('label_resume', 'Resume'),
                                       onclick: function () { start(true); } }));
            buttons.push(h('button', { type: 'button', class: 'sp-btn sp-btn-secondary sp-btn-large', text: label('label_restart', 'Start Again'),
                                       onclick: function () { start(false); } }));
        } else {
            buttons.push(h('button', { type: 'button', class: 'sp-btn sp-btn-primary sp-btn-large', text: label('label_start', 'Start'),
                                       onclick: function () { start(true); } }));
        }
        ui.stageWrap.appendChild(h('div', { class: 'sp-start' }, [h('div', { class: 'sp-start-card' }, [
            C.branding && C.branding.logo ? h('img', { class: 'sp-start-logo', src: C.branding.logo, alt: '' }) : null,
            h('h1', { text: C.title }),
            C.description ? h('p', { class: 'sp-start-desc', text: C.description }) : null,
            h('div', { class: 'sp-start-meta', text: slides.length + ' slides' }),
            h('div', { class: 'sp-start-actions' }, buttons),
        ])]));
    }

    function boot() {
        document.title = C.title || document.title;
        var connected = Scorm.init();
        preview = !connected;
        buildShell();
        if (!slides.length) {
            ui.stageWrap.appendChild(h('div', { class: 'sp-start' }, [h('p', { text: 'This course has no slides yet.' })]));
            ui.footer.classList.add('sp-hidden');
            return;
        }
        var saved = '';
        if (preview) {
            try { saved = window.sessionStorage.getItem(storageKey()) || ''; } catch (e) { saved = ''; }
        } else {
            saved = Scorm.get('cmi.suspend_data', 'cmi.suspend_data');
            var entry = Scorm.get('cmi.core.entry', 'cmi.entry');
            if (entry === 'ab-initio') { saved = ''; }
            Scorm.set('cmi.core.score.min', 'cmi.score.min', 0);
            Scorm.set('cmi.core.score.max', 'cmi.score.max', 100);
            var status = Scorm.get('cmi.core.lesson_status', 'cmi.completion_status');
            if (!status || status === 'not attempted' || status === 'unknown') {
                Scorm.set('cmi.core.lesson_status', 'cmi.completion_status', 'incomplete');
                status = 'incomplete';
            }
            reportedStatus = Scorm.v2004 ? null : status;
            Scorm.commit();
            window.addEventListener('pagehide', function () { Scorm.finish(); });
            window.addEventListener('beforeunload', function () { Scorm.finish(); });
        }
        var restored = saved && restore(saved);
        if (state.current >= slides.length) { state.current = 0; }
        if (!S.allow_resume && !preview) {
            restored = false;
            state.current = 0;
        }
        var startAt = parseInt(params.get('slide') || '', 10);
        if (preview && startAt > 0 && startAt <= slides.length) {
            skipGates = params.get('gates') === '0';
            state.current = startAt - 1;
            if (skipGates) {
                var box = document.querySelector('.sp-preview-skip input');
                if (box) { box.checked = true; }
            }
            renderSlide();
            return;
        }
        if (S.show_start_screen) {
            showStartScreen(restored && state.current > 0);
        } else {
            renderSlide();
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }
})();
