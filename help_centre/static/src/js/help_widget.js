/**
 * Help Centre KC Bot Widget
 * Gainsight-inspired slide-out panel with Home / Chat tabs and in-panel article viewing.
 */
(function () {
    'use strict';

    // ── Constants ────────────────────────────────────────────────────────────────
    const STORAGE_SESSION = 'hc_session_token';
    const STORAGE_OPEN    = 'hc_panel_open';
    const DEBOUNCE_MS     = 280;

    // ── Utility helpers ──────────────────────────────────────────────────────────

    function rpc(url, params) {
        return fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ jsonrpc: '2.0', method: 'call', id: Date.now(), params: params }),
        })
            .then(r => r.json())
            .then(d => {
                if (d.error) throw new Error(d.error.data?.message || d.error.message || 'RPC error');
                return d.result;
            });
    }

    function debounce(fn, ms) {
        let t;
        return function (...args) {
            clearTimeout(t);
            t = setTimeout(() => fn.apply(this, args), ms);
        };
    }

    function escHtml(str) {
        const d = document.createElement('div');
        d.appendChild(document.createTextNode(str || ''));
        return d.innerHTML;
    }

    /**
     * Very lightweight Markdown → HTML converter for chat messages.
     * Handles bold, italic, inline code, numbered lists, bullet lists, line breaks.
     */
    function mdToHtml(text) {
        if (!text) return '';
        let html = escHtml(text);

        // Bold  **text**
        html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        // Italic  *text*
        html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');
        // Inline code  `code`
        html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

        // Headings  ### ## # (must process ### before ## before # to avoid partial matches)
        html = html.replace(/(?:^|\n)###\s+(.+)/g, (_, c) => `\n<span class="hc-md-h3">${c}</span>`);
        html = html.replace(/(?:^|\n)##\s+(.+)/g,  (_, c) => `\n<span class="hc-md-h2">${c}</span>`);
        html = html.replace(/(?:^|\n)#\s+(.+)/g,   (_, c) => `\n<span class="hc-md-h1">${c}</span>`);

        // Numbered lists  (lines starting with "1. " etc)
        html = html.replace(/(?:^|\n)(\d+)\.\s+(.+)/g, (_, n, content) =>
            `\n<span class="hc-list-item"><span class="hc-list-num">${escHtml(n)}.</span> ${content}</span>`
        );
        // Bullet lists  - item
        html = html.replace(/(?:^|\n)[•\-]\s+(.+)/g, (_, content) =>
            `\n<span class="hc-list-item"><span class="hc-bullet">•</span> ${content}</span>`
        );
        // Navigation arrows  →
        html = html.replace(/→/g, '<span class="hc-nav-arrow">→</span>');
        // Line breaks
        html = html.replace(/\n/g, '<br>');

        return html;
    }

    // ── Main widget class ────────────────────────────────────────────────────────

    class HCWidget {
        constructor(rootEl) {
            this.root = rootEl;
            this.centreName = rootEl.dataset.centreName || 'Help Centre';

            // Branding / AI config (set via data-* attributes from QWeb template)
            this.aiName         = (rootEl.dataset.aiName || 'KC Bot').trim();
            this.aiWelcome      = (rootEl.dataset.aiWelcome || '').trim();
            this.primaryColor   = (rootEl.dataset.primaryColor || '').trim();

            // Apply primary colour override on the widget root so CSS vars cascade
            // for all descendant elements regardless of page context.
            if (this.primaryColor) {
                rootEl.style.setProperty('--hc-primary',   this.primaryColor);
                rootEl.style.setProperty('--hc-primary-d', this.primaryColor);
            }

            // State
            this.isOpen              = false;
            this.activeTab           = 'home';   // 'home' | 'chat' | 'article' | 'ticket'
            this.chatMessages        = [];        // {role, content, articles?}[]
            this.sessionToken        = localStorage.getItem(STORAGE_SESSION) || null;
            this.articleStack        = [];        // breadcrumb stack of {id, name}
            this.searchTimer         = null;
            this.helpdeskEnabled     = rootEl.dataset.helpdeskEnabled === '1';
            this.userAuthenticated   = rootEl.dataset.userAuthenticated === '1';
            this.ticketStatus        = 'idle';   // 'idle' | 'submitting' | 'success' | 'error'
            this.ticketId            = null;

            this._build();
            this._bindEvents();

            // Restore open state on /help pages
            if (window.location.pathname.startsWith('/help')) {
                const wasOpen = sessionStorage.getItem(STORAGE_OPEN);
                if (wasOpen === '1') this.open();
            }
        }

        // ── DOM construction ───────────────────────────────────────────────────

        _build() {
            this.root.innerHTML = `
<div id="hc-toggle-btn" title="Help Centre" role="button" tabindex="0" aria-label="Open Help Centre">
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="10"/>
        <path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3"/>
        <circle cx="12" cy="17" r=".5" fill="currentColor"/>
    </svg>
    <span>Help</span>
    <span id="hc-unread-badge" class="hc-unread-badge d-none">1</span>
</div>

<div id="hc-panel" class="hc-panel" role="dialog" aria-label="Help Centre" aria-hidden="true">

    <!-- Panel header -->
    <div class="hc-panel-header">
        <span class="hc-panel-title" id="hc-panel-title">${escHtml(this.centreName)}</span>
        <div class="d-flex align-items-center gap-2">
            <button class="hc-icon-btn" id="hc-open-site" title="Open full Help Centre" aria-label="Open full Help Centre">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                     stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
                    <polyline points="15 3 21 3 21 9"/>
                    <line x1="10" y1="14" x2="21" y2="3"/>
                </svg>
            </button>
            <button class="hc-icon-btn" id="hc-close-btn" title="Close" aria-label="Close Help Centre">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                     stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="18" y1="6" x2="6" y2="18"/>
                    <line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
            </button>
        </div>
    </div>

    <!-- Tab bar -->
    <div class="hc-tabs" id="hc-tabs">
        <button class="hc-tab active" data-tab="home" aria-selected="true">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
                <polyline points="9 22 9 12 15 12 15 22"/>
            </svg>
            Home
        </button>
        <button class="hc-tab" data-tab="chat" aria-selected="false">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
            </svg>
            Ask AI
        </button>
        ${this.helpdeskEnabled && this.userAuthenticated ? `
        <button class="hc-tab" data-tab="ticket" aria-selected="false">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M15 5H7a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V9l-4-4z"/>
                <polyline points="15 5 15 9 19 9"/>
            </svg>
            Lodge Ticket
        </button>` : ''}
    </div>

    <!-- Tab content -->
    <div class="hc-panel-body" id="hc-panel-body">

        <!-- Home tab -->
        <div class="hc-tab-pane active" id="hc-pane-home">
            <div class="hc-search-wrap">
                <div class="hc-search-inner">
                    <svg class="hc-search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none"
                         stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <circle cx="11" cy="11" r="8"/>
                        <line x1="21" y1="21" x2="16.65" y2="16.65"/>
                    </svg>
                    <input type="text" id="hc-search-input" placeholder="Search articles…"
                           autocomplete="off" aria-label="Search articles"/>
                </div>
                <div id="hc-suggestions" class="hc-suggestions" role="listbox" aria-label="Suggestions"></div>
            </div>
            <div id="hc-home-content" class="hc-home-content">
                <div class="hc-loading-spinner">
                    <div class="hc-spinner"></div>
                    <span>Loading…</span>
                </div>
            </div>
        </div>

        <!-- Chat tab -->
        <div class="hc-tab-pane" id="hc-pane-chat">
            <div class="hc-chat-messages" id="hc-chat-messages" role="log" aria-live="polite"></div>
            <div class="hc-chat-input-wrap">
                <div class="hc-chat-input-row">
                    <input type="text" id="hc-chat-input"
                           placeholder="Ask me anything about Odoo…"
                           aria-label="Type your question" maxlength="1000"/>
                    <button id="hc-chat-send" class="hc-send-btn" aria-label="Send message">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                             stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <line x1="22" y1="2" x2="11" y2="13"/>
                            <polygon points="22 2 15 22 11 13 2 9 22 2"/>
                        </svg>
                    </button>
                </div>
                <p class="hc-chat-hint">
                    Powered by AI · Responses may not be 100% accurate
                </p>
            </div>
        </div>

        ${this.helpdeskEnabled && this.userAuthenticated ? `
        <!-- Lodge Ticket tab -->
        <div class="hc-tab-pane" id="hc-pane-ticket">
            <div class="hc-ticket-wrap">
                <!-- Idle / submitting form -->
                <div id="hc-ticket-form-view">
                    <p class="hc-ticket-intro">
                        Can't find what you're looking for? Lodge a support ticket and our team will get back to you.
                    </p>
                    <div class="mb-3">
                        <label class="hc-form-label" for="hc-ticket-subject">Subject <span style="color:#dc3545">*</span></label>
                        <input type="text" id="hc-ticket-subject" class="hc-form-input"
                               placeholder="Brief description of your issue" maxlength="200" autocomplete="off"/>
                        <div class="hc-field-error d-none" id="hc-ticket-subject-err"></div>
                    </div>
                    <div class="mb-3">
                        <label class="hc-form-label" for="hc-ticket-desc">Description</label>
                        <textarea id="hc-ticket-desc" class="hc-form-input" rows="4"
                                  placeholder="Describe the issue in more detail…"></textarea>
                    </div>
                    <div class="hc-ticket-error d-none" id="hc-ticket-error"></div>
                    <button id="hc-ticket-submit" class="hc-ticket-submit-btn">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <line x1="22" y1="2" x2="11" y2="13"/>
                            <polygon points="22 2 15 22 11 13 2 9 22 2"/>
                        </svg>
                        Submit Ticket
                    </button>
                </div>
                <!-- Success state -->
                <div id="hc-ticket-success-view" class="hc-ticket-success d-none">
                    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#198754" stroke-width="1.5">
                        <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                        <polyline points="22 4 12 14.01 9 11.01"/>
                    </svg>
                    <h6>Ticket Submitted!</h6>
                    <p id="hc-ticket-success-msg"></p>
                    <button id="hc-ticket-new" class="hc-ticket-new-btn">Submit Another</button>
                </div>
            </div>
        </div>` : ''}

        <!-- Article view (virtual tab, shown when user clicks an article) -->
        <div class="hc-tab-pane" id="hc-pane-article">
            <div class="hc-article-nav">
                <button id="hc-back-btn" class="hc-back-btn">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                         stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="15 18 9 12 15 6"/>
                    </svg>
                    Back
                </button>
                <a id="hc-full-article-link" href="#" target="_blank" class="hc-full-link">
                    Open full page ↗
                </a>
            </div>
            <div id="hc-article-content" class="hc-article-content"></div>
            <div id="hc-article-rating" class="hc-article-rating d-none">
                <p>Was this helpful?</p>
                <div class="d-flex gap-2">
                    <button class="hc-rate-btn-yes" data-helpful="1">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3H14z"/>
                            <path d="M7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/>
                        </svg>
                        Yes
                    </button>
                    <button class="hc-rate-btn-no" data-helpful="0">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3H10z"/>
                            <path d="M17 2h2.67A2.31 2.31 0 0 1 22 4v7a2.31 2.31 0 0 1-2.33 2H17"/>
                        </svg>
                        No
                    </button>
                </div>
                <span id="hc-rate-thanks" class="hc-rate-thanks d-none">Thanks for your feedback!</span>
            </div>
        </div>

    </div>
</div>
            `;

            this.toggleBtn = this.root.querySelector('#hc-toggle-btn');
            this.panel     = this.root.querySelector('#hc-panel');
            this.tabs      = this.root.querySelectorAll('.hc-tab');
            this.panes     = this.root.querySelectorAll('.hc-tab-pane');
        }

        // ── Events ─────────────────────────────────────────────────────────────

        _bindEvents() {
            // Toggle
            this.root.querySelector('#hc-toggle-btn').addEventListener('click', () => this.toggle());
            this.root.querySelector('#hc-toggle-btn').addEventListener('keydown', e => {
                if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); this.toggle(); }
            });
            this.root.querySelector('#hc-close-btn').addEventListener('click', () => this.close());
            this.root.querySelector('#hc-open-site').addEventListener('click', () => {
                window.open('/help', '_blank');
            });

            // Tabs
            this.tabs.forEach(tab => {
                tab.addEventListener('click', () => this.switchTab(tab.dataset.tab));
            });

            // Home search
            const searchInput = this.root.querySelector('#hc-search-input');
            searchInput.addEventListener('input', debounce(e => this._onSearch(e.target.value), DEBOUNCE_MS));
            searchInput.addEventListener('keydown', e => {
                if (e.key === 'Escape') { searchInput.value = ''; this._clearSuggestions(); }
            });
            document.addEventListener('click', e => {
                if (!e.target.closest('#hc-widget-root')) this._clearSuggestions();
            });

            // Chat
            const chatInput = this.root.querySelector('#hc-chat-input');
            chatInput.addEventListener('keydown', e => {
                if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); this._sendChat(); }
            });
            this.root.querySelector('#hc-chat-send').addEventListener('click', () => this._sendChat());

            // Lodge Ticket form
            if (this.helpdeskEnabled && this.userAuthenticated) {
                this.root.querySelector('#hc-ticket-submit').addEventListener('click', () => this._submitTicket());
                this.root.querySelector('#hc-ticket-subject').addEventListener('keydown', e => {
                    if (e.key === 'Enter') { e.preventDefault(); this._submitTicket(); }
                });
                this.root.querySelector('#hc-ticket-new').addEventListener('click', () => this._resetTicket());
            }

            // Article back button
            this.root.querySelector('#hc-back-btn').addEventListener('click', () => this._articleBack());

            // Article rating
            this.root.querySelector('.hc-rate-btn-yes').addEventListener('click', () => this._rateArticle(true));
            this.root.querySelector('.hc-rate-btn-no').addEventListener('click',  () => this._rateArticle(false));

            // Article rating on the main page (static buttons, not widget)
            document.querySelectorAll('.hc-rate-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    const id = btn.dataset.articleId;
                    const helpful = btn.dataset.helpful === '1';
                    if (!id) return;
                    rpc('/help/api/rate', { article_id: parseInt(id, 10), helpful })
                        .then(res => {
                            document.querySelectorAll('.hc-rate-btn').forEach(b => b.disabled = true);
                            document.getElementById('hc-helpful-count').textContent = res.helpful_count;
                            document.getElementById('hc-not-helpful-count').textContent = res.not_helpful_count;
                        });
                });
            });
        }

        // ── Open / close ───────────────────────────────────────────────────────

        toggle() { this.isOpen ? this.close() : this.open(); }

        open() {
            this.isOpen = true;
            this.panel.classList.add('hc-panel--open');
            this.panel.setAttribute('aria-hidden', 'false');
            this.toggleBtn.classList.add('hc-toggle--active');
            this.root.querySelector('#hc-unread-badge').classList.add('d-none');
            sessionStorage.setItem(STORAGE_OPEN, '1');

            if (this.activeTab === 'home') {
                this._loadHome();
            } else if (this.activeTab === 'chat' && this.chatMessages.length === 0) {
                this._addChatMessage('assistant', this._greeting());
            }

            setTimeout(() => this.root.querySelector('#hc-search-input').focus(), 300);
        }

        close() {
            this.isOpen = false;
            this.panel.classList.remove('hc-panel--open');
            this.panel.setAttribute('aria-hidden', 'true');
            this.toggleBtn.classList.remove('hc-toggle--active');
            sessionStorage.setItem(STORAGE_OPEN, '0');
        }

        // ── Tab switching ──────────────────────────────────────────────────────

        switchTab(tab) {
            this.activeTab = tab;

            this.tabs.forEach(t => {
                const active = t.dataset.tab === tab;
                t.classList.toggle('active', active);
                t.setAttribute('aria-selected', String(active));
            });

            this.panes.forEach(p => p.classList.remove('active'));

            if (tab === 'home') {
                this.root.querySelector('#hc-pane-home').classList.add('active');
                this._showTabs(true);
                this._loadHome();
            } else if (tab === 'chat') {
                this.root.querySelector('#hc-pane-chat').classList.add('active');
                this._showTabs(true);
                if (this.chatMessages.length === 0) {
                    this._addChatMessage('assistant', this._greeting());
                }
                setTimeout(() => this.root.querySelector('#hc-chat-input').focus(), 100);
            } else if (tab === 'ticket') {
                this.root.querySelector('#hc-pane-ticket').classList.add('active');
                this._showTabs(true);
                setTimeout(() => this.root.querySelector('#hc-ticket-subject').focus(), 100);
            }
        }

        _showTabs(visible) {
            this.root.querySelector('#hc-tabs').style.display = visible ? '' : 'none';
        }

        /** Build the opening chat greeting from configured AI name / welcome message. */
        _greeting() {
            if (this.aiWelcome) return this.aiWelcome;
            return (
                `Hi! I'm **${this.aiName}**, your **${this.centreName}** assistant. ` +
                "Ask me anything about Odoo and I'll give you step-by-step guidance."
            );
        }

        // ── Home tab ───────────────────────────────────────────────────────────

        _loadHome() {
            const content = this.root.querySelector('#hc-home-content');
            content.innerHTML = `
                <div class="hc-loading-spinner">
                    <div class="hc-spinner"></div><span>Loading…</span>
                </div>`;

            rpc('/help/api/featured', {})
                .then(data => this._renderHome(data))
                .catch(() => {
                    content.innerHTML = '<p class="text-muted p-3">Unable to load articles.</p>';
                });
        }

        _renderHome(data) {
            const content = this.root.querySelector('#hc-home-content');
            let html = '';

            if (data.featured && data.featured.length) {
                html += `<h6 class="hc-section-label">⭐ Featured</h6>`;
                html += data.featured.map(a => this._articleRow(a)).join('');
            }

            if (data.recent && data.recent.length) {
                html += `<h6 class="hc-section-label">🕒 Recently Updated</h6>`;
                html += data.recent.map(a => this._articleRow(a)).join('');
            }

            if (!html) {
                html = '<p class="hc-empty-state">No articles published yet.</p>';
            }

            content.innerHTML = html;

            // Bind article click events
            content.querySelectorAll('[data-article-id]').forEach(el => {
                el.addEventListener('click', e => {
                    e.preventDefault();
                    const id   = parseInt(el.dataset.articleId, 10);
                    const name = el.dataset.articleName || '';
                    this._openArticle(id, name);
                });
            });
        }

        _articleRow(a) {
            return `
<div class="hc-article-row" data-article-id="${a.id}" data-article-name="${escHtml(a.name)}" role="button" tabindex="0">
    <div class="hc-article-row-title">${escHtml(a.name)}</div>
    <div class="hc-article-row-meta">
        ${a.category ? `<span>${escHtml(a.category)}</span>` : ''}
        <span><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg> ${a.read_time} min</span>
    </div>
</div>`;
        }

        // ── Search ─────────────────────────────────────────────────────────────

        _onSearch(query) {
            const box = this.root.querySelector('#hc-suggestions');
            const homeContent = this.root.querySelector('#hc-home-content');
            query = query.trim();

            if (!query) {
                this._clearSuggestions();
                this._loadHome();
                return;
            }

            rpc('/help/api/suggestions', { q: query })
                .then(results => {
                    if (!results || !results.length) {
                        box.innerHTML = '<div class="hc-suggestion-empty">No matches found</div>';
                        box.classList.add('hc-suggestions--open');
                        homeContent.innerHTML = '';
                        return;
                    }

                    box.innerHTML = results.map(r => `
<div class="hc-suggestion-item" data-article-id="${r.id}" data-article-name="${escHtml(r.name)}" role="option" tabindex="0">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
        <polyline points="14 2 14 8 20 8"/>
    </svg>
    <span class="flex-grow-1">${escHtml(r.name)}</span>
    <span class="hc-suggestion-meta">${r.read_time} min</span>
</div>`).join('');

                    box.classList.add('hc-suggestions--open');
                    homeContent.innerHTML = '';

                    box.querySelectorAll('.hc-suggestion-item').forEach(el => {
                        const openIt = () => {
                            this._clearSuggestions();
                            this.root.querySelector('#hc-search-input').value = '';
                            this._openArticle(
                                parseInt(el.dataset.articleId, 10),
                                el.dataset.articleName
                            );
                        };
                        el.addEventListener('click', openIt);
                        el.addEventListener('keydown', e => {
                            if (e.key === 'Enter') openIt();
                        });
                    });
                })
                .catch(() => this._clearSuggestions());
        }

        _clearSuggestions() {
            const box = this.root.querySelector('#hc-suggestions');
            box.innerHTML = '';
            box.classList.remove('hc-suggestions--open');
        }

        // ── Article viewer ─────────────────────────────────────────────────────

        _openArticle(id, name, fromTab) {
            this.articleStack.push({ id, name, fromTab: fromTab || this.activeTab });
            this._loadArticle(id);
        }

        _loadArticle(id) {
            // Switch to article pane
            this.panes.forEach(p => p.classList.remove('active'));
            this.root.querySelector('#hc-pane-article').classList.add('active');
            this._showTabs(false);

            const contentEl = this.root.querySelector('#hc-article-content');
            contentEl.innerHTML = `
                <div class="hc-loading-spinner" style="padding: 2rem;">
                    <div class="hc-spinner"></div><span>Loading…</span>
                </div>`;
            this.root.querySelector('#hc-article-rating').classList.add('d-none');
            this.root.querySelector('#hc-rate-thanks').classList.add('d-none');
            this._currentArticleId = null;

            rpc(`/help/api/article/${id}`, {})
                .then(data => {
                    if (data.error === 'auth_required') {
                        contentEl.innerHTML = `
                            <div class="hc-auth-wall">
                                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                                    <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                                    <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                                </svg>
                                <p>This article is for internal users only.</p>
                                <a href="${data.login_url || '/web/login'}" class="btn btn-primary btn-sm mt-2">
                                    Log in to read
                                </a>
                            </div>`;
                        return;
                    }
                    if (data.error) {
                        contentEl.innerHTML = '<p class="text-danger p-3">Article not found.</p>';
                        return;
                    }

                    this._currentArticleId = data.id;

                    // Update panel title
                    this.root.querySelector('#hc-panel-title').textContent = data.name;
                    this.root.querySelector('#hc-full-article-link').href = data.url;

                    contentEl.innerHTML = `
                        <div class="hc-article-header">
                            <h5>${escHtml(data.name)}</h5>
                            <div class="hc-article-meta-row">
                                ${data.category ? `<span>${escHtml(data.category)}</span>` : ''}
                                <span>
                                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                                    ${data.read_time} min read
                                </span>
                                <span>
                                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                                    ${data.view_count || 0} views
                                </span>
                            </div>
                            ${data.tags && data.tags.length ? `<div class="hc-tags">${data.tags.map(t => `<span class="hc-tag">${escHtml(t)}</span>`).join('')}</div>` : ''}
                            ${data.summary ? `<p class="hc-article-summary">${escHtml(data.summary)}</p>` : ''}
                        </div>
                        <div class="hc-article-body">${data.content || '<p class="text-muted">No content yet.</p>'}</div>`;

                    this.root.querySelector('#hc-article-rating').classList.remove('d-none');
                })
                .catch(err => {
                    contentEl.innerHTML = `<p class="text-danger p-3">Error loading article: ${escHtml(err.message)}</p>`;
                });
        }

        _articleBack() {
            this.articleStack.pop();
            this.root.querySelector('#hc-panel-title').textContent = this.centreName;

            if (this.articleStack.length > 0) {
                const prev = this.articleStack[this.articleStack.length - 1];
                this._loadArticle(prev.id);
                return;
            }

            // Return to the tab we came from
            const fromTab = this.articleStack.length > 0
                ? this.articleStack[this.articleStack.length - 1].fromTab
                : this.activeTab;

            this._showTabs(true);
            this.panes.forEach(p => p.classList.remove('active'));
            const target = fromTab || 'home';
            this.root.querySelector(`#hc-pane-${target}`).classList.add('active');
            this.tabs.forEach(t => {
                t.classList.toggle('active', t.dataset.tab === target);
                t.setAttribute('aria-selected', String(t.dataset.tab === target));
            });

            if (target === 'home') this._loadHome();
        }

        _rateArticle(helpful) {
            if (!this._currentArticleId) return;
            const rating = this.root.querySelector('#hc-article-rating');
            rating.querySelectorAll('button').forEach(b => (b.disabled = true));
            rpc('/help/api/rate', { article_id: this._currentArticleId, helpful })
                .then(() => {
                    this.root.querySelector('#hc-rate-thanks').classList.remove('d-none');
                });
        }

        // ── Lodge Ticket tab ───────────────────────────────────────────────────

        async _submitTicket() {
            const subjectEl  = this.root.querySelector('#hc-ticket-subject');
            const descEl     = this.root.querySelector('#hc-ticket-desc');
            const subjectErr = this.root.querySelector('#hc-ticket-subject-err');
            const errorEl    = this.root.querySelector('#hc-ticket-error');
            const submitBtn  = this.root.querySelector('#hc-ticket-submit');

            // Validate
            const subject = subjectEl.value.trim();
            subjectErr.classList.add('d-none');
            subjectEl.classList.remove('is-invalid');
            errorEl.classList.add('d-none');

            if (!subject) {
                subjectErr.textContent = 'Please enter a subject for your ticket.';
                subjectErr.classList.remove('d-none');
                subjectEl.classList.add('is-invalid');
                subjectEl.focus();
                return;
            }

            submitBtn.disabled = true;
            submitBtn.innerHTML = '<span class="hc-spinner-sm"></span> Submitting…';

            try {
                const result = await rpc('/help/api/create_ticket', {
                    subject,
                    description: descEl.value.trim(),
                });

                if (result.error) {
                    errorEl.textContent = result.message || 'An error occurred. Please try again.';
                    errorEl.classList.remove('d-none');
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg> Submit Ticket`;
                    return;
                }

                // Success
                this.ticketId = result.ticket_id;
                this.root.querySelector('#hc-ticket-form-view').classList.add('d-none');
                const successView = this.root.querySelector('#hc-ticket-success-view');
                successView.classList.remove('d-none');
                this.root.querySelector('#hc-ticket-success-msg').textContent =
                    `Ticket #${result.ticket_id} has been lodged. Someone will be in touch shortly.`;

            } catch (e) {
                errorEl.textContent = 'Something went wrong. Please try again.';
                errorEl.classList.remove('d-none');
                submitBtn.disabled = false;
                submitBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg> Submit Ticket`;
            }
        }

        _resetTicket() {
            this.root.querySelector('#hc-ticket-subject').value = '';
            this.root.querySelector('#hc-ticket-desc').value = '';
            this.root.querySelector('#hc-ticket-subject-err').classList.add('d-none');
            this.root.querySelector('#hc-ticket-subject').classList.remove('is-invalid');
            this.root.querySelector('#hc-ticket-error').classList.add('d-none');
            const submitBtn = this.root.querySelector('#hc-ticket-submit');
            submitBtn.disabled = false;
            submitBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg> Submit Ticket`;
            this.root.querySelector('#hc-ticket-form-view').classList.remove('d-none');
            this.root.querySelector('#hc-ticket-success-view').classList.add('d-none');
            this.ticketId = null;
            setTimeout(() => this.root.querySelector('#hc-ticket-subject').focus(), 50);
        }

        // ── Chat tab ───────────────────────────────────────────────────────────

        async _sendChat() {
            const input = this.root.querySelector('#hc-chat-input');
            const message = input.value.trim();
            if (!message) return;

            input.value = '';
            this._addChatMessage('user', message);
            this._setLoading(true);

            try {
                const data = await rpc('/help/chat', {
                    message,
                    session_token: this.sessionToken,
                    context_url: window.location.href,
                });

                if (data.session_token) {
                    this.sessionToken = data.session_token;
                    localStorage.setItem(STORAGE_SESSION, this.sessionToken);
                }

                this._addChatMessage('assistant', data.response, data.articles);
            } catch (e) {
                this._addChatMessage('assistant',
                    "I'm sorry, I couldn't process that request. Please try again or check your AI settings."
                );
            }

            this._setLoading(false);
        }

        _addChatMessage(role, content, articles) {
            this.chatMessages.push({ role, content });
            const container = this.root.querySelector('#hc-chat-messages');

            const el = document.createElement('div');
            el.className = `hc-chat-msg hc-chat-msg--${role}`;

            if (role === 'assistant') {
                el.innerHTML = `
                    <div class="hc-chat-avatar">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <circle cx="12" cy="12" r="10"/>
                            <path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3"/>
                            <circle cx="12" cy="17" r=".5" fill="currentColor"/>
                        </svg>
                    </div>
                    <div class="hc-chat-bubble">${mdToHtml(content)}</div>`;
            } else {
                el.innerHTML = `<div class="hc-chat-bubble">${escHtml(content)}</div>`;
            }

            container.appendChild(el);

            // Article chips
            if (articles && articles.length) {
                const chips = document.createElement('div');
                chips.className = 'hc-chat-articles';
                chips.innerHTML = `<p class="hc-chat-articles-label">📚 Related articles</p>` +
                    articles.map(a => `
                        <div class="hc-chat-article-chip" data-article-id="${a.id}" data-article-name="${escHtml(a.name)}" role="button" tabindex="0">
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                                <polyline points="14 2 14 8 20 8"/>
                            </svg>
                            ${escHtml(a.name)}
                            <span class="hc-chip-time">${a.read_time} min</span>
                        </div>`).join('');

                container.appendChild(chips);

                chips.querySelectorAll('[data-article-id]').forEach(el => {
                    const openIt = () => this._openArticle(
                        parseInt(el.dataset.articleId, 10),
                        el.dataset.articleName,
                        'chat'
                    );
                    el.addEventListener('click', openIt);
                    el.addEventListener('keydown', e => { if (e.key === 'Enter') openIt(); });
                });
            }

            container.scrollTop = container.scrollHeight;
        }

        _setLoading(loading) {
            const btn = this.root.querySelector('#hc-chat-send');
            const input = this.root.querySelector('#hc-chat-input');
            btn.disabled = loading;
            input.disabled = loading;

            const container = this.root.querySelector('#hc-chat-messages');
            const existing = container.querySelector('#hc-typing');
            if (loading && !existing) {
                const typing = document.createElement('div');
                typing.id = 'hc-typing';
                typing.className = 'hc-chat-msg hc-chat-msg--assistant';
                typing.innerHTML = `
                    <div class="hc-chat-avatar">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <circle cx="12" cy="12" r="10"/>
                            <path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3"/>
                        </svg>
                    </div>
                    <div class="hc-chat-bubble hc-typing-bubble">
                        <span class="hc-typing-dot"></span>
                        <span class="hc-typing-dot"></span>
                        <span class="hc-typing-dot"></span>
                    </div>`;
                container.appendChild(typing);
                container.scrollTop = container.scrollHeight;
            } else if (!loading && existing) {
                existing.remove();
            }
        }
    }

    // ── Boot ─────────────────────────────────────────────────────────────────────

    function boot() {
        const rootEl = document.getElementById('hc-widget-root');
        if (!rootEl) return;
        // eslint-disable-next-line no-new
        new HCWidget(rootEl);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }

})();
