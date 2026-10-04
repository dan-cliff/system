/** @odoo-module **/
/**
 * Help Centre — Backend Systray KC Bot
 * Full OWL component: Home tab (search + articles), Ask AI chat, Article viewer.
 * Mirrors the Gainsight KC Bot experience for authenticated backend users.
 */
import { Component, useState, useRef, onMounted, onWillUnmount, onPatched, markup } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";

const STORAGE_SESSION = "hc_session_token";

// ── Helpers ───────────────────────────────────────────────────────────────────

function escHtml(str) {
    const d = document.createElement("div");
    d.appendChild(document.createTextNode(str || ""));
    return d.innerHTML;
}

function mdToHtml(text) {
    if (!text) return "";
    let html = escHtml(text);
    html = html.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/\*(.*?)\*/g, "<em>$1</em>");
    html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
    html = html.replace(/(?:^|\n)(\d+)\.\s+(.+)/g, (_, n, content) =>
        `\n<span class="hc-list-item"><span class="hc-list-num">${n}.</span> ${content}</span>`
    );
    html = html.replace(/(?:^|\n)[•\-]\s+(.+)/g, (_, content) =>
        `\n<span class="hc-list-item"><span class="hc-bullet">•</span> ${content}</span>`
    );
    html = html.replace(/→/g, '<span class="hc-nav-arrow">→</span>');
    html = html.replace(/\n/g, "<br>");
    return html;
}

function debounce(fn, ms) {
    let t;
    return function (...args) {
        clearTimeout(t);
        t = setTimeout(() => fn.apply(this, args), ms);
    };
}

// ── Component ─────────────────────────────────────────────────────────────────

export class HelpCentreSystrayItem extends Component {
    static template = "help_centre.SystrayItem";
    static props = ["*"];

    setup() {
        this.chatRef = useRef("chatMessages");

        this.state = useState({
            isOpen: false,
            activeTab: "home",       // "home" | "chat" | "article" | "ticket"
            homeLoading: false,
            homeFeatured: [],
            homeRecent: [],
            homeLoaded: false,
            searchQuery: "",
            suggestions: [],
            showSuggestions: false,
            chatMessages: [],
            chatInput: "",
            chatLoading: false,
            sessionToken: localStorage.getItem(STORAGE_SESSION) || "",
            article: null,
            articleStack: [],        // [{id, name, fromTab}]
            articleLoading: false,
            articleId: null,
            rateSubmitted: false,
            // Helpdesk / Lodge Ticket
            helpdeskEnabled: false,
            ticketSubject: "",
            ticketDesc: "",
            ticketSubmitting: false,
            ticketSubmitted: false,
            ticketId: null,
            ticketError: "",
            ticketSubjectError: "",
            // Branding
            aiName: "KC Bot",
            aiWelcome: "",
            primaryColor: "",
        });

        this._debouncedSearch = debounce(this._performSearch.bind(this), 280);
        this._handleOutsideClick = this._handleOutsideClick.bind(this);

        // Load config once on mount (helpdesk + branding)
        onMounted(async () => {
            try {
                const cfg = await rpc("/help/api/widget_config", {});
                this.state.helpdeskEnabled = cfg.helpdesk_enabled || false;
                this.state.aiName         = (cfg.ai_name         || "KC Bot").trim();
                this.state.aiWelcome      = (cfg.ai_welcome_message || "").trim();
                this.state.primaryColor   = (cfg.primary_color   || "").trim();
            } catch (e) {
                // silently ignore — widget still works with defaults
            }
        });

        // Scroll chat to bottom whenever it patches
        onPatched(() => {
            const el = this.chatRef.el;
            if (el) el.scrollTop = el.scrollHeight;
        });

        onWillUnmount(() => {
            document.removeEventListener("click", this._handleOutsideClick);
        });
    }

    // ── Panel open / close ────────────────────────────────────────────────────

    toggle() {
        this.state.isOpen = !this.state.isOpen;
        if (this.state.isOpen) {
            if (this.state.activeTab === "home" && !this.state.homeLoaded) {
                this._loadHome();
            } else if (this.state.activeTab === "chat" && this.state.chatMessages.length === 0) {
                this._initChat();
            }
            // Add listener after current click finishes bubbling
            setTimeout(() => document.addEventListener("click", this._handleOutsideClick), 0);
        } else {
            document.removeEventListener("click", this._handleOutsideClick);
        }
    }

    close() {
        this.state.isOpen = false;
        document.removeEventListener("click", this._handleOutsideClick);
    }

    _handleOutsideClick(event) {
        const panel = document.querySelector(".hc-backend-panel");
        const wrap = document.querySelector(".o_help_centre_systray_wrap");
        if (
            panel && !panel.contains(event.target) &&
            wrap && !wrap.contains(event.target)
        ) {
            this.close();
        }
    }

    // ── Home tab ──────────────────────────────────────────────────────────────

    async _loadHome() {
        this.state.homeLoading = true;
        try {
            const data = await rpc("/help/api/featured", {});
            this.state.homeFeatured = data.featured || [];
            this.state.homeRecent = data.recent || [];
            this.state.homeLoaded = true;
        } catch (e) {
            console.error("Help Centre: failed to load articles", e);
        }
        this.state.homeLoading = false;
    }

    // ── Tab switching ─────────────────────────────────────────────────────────

    switchTab(tab) {
        this.state.activeTab = tab;
        this.state.articleStack = [];
        this.state.article = null;
        this.state.articleId = null;
        this.state.searchQuery = "";
        this.state.showSuggestions = false;
        if (tab === "home" && !this.state.homeLoaded) {
            this._loadHome();
        } else if (tab === "chat" && this.state.chatMessages.length === 0) {
            this._initChat();
        }
    }

    _initChat() {
        let greeting = this.state.aiWelcome;
        if (!greeting) {
            greeting = (
                `Hi! I'm **${this.state.aiName}**, your Help Centre assistant. ` +
                "Ask me anything about Odoo and I'll give you step-by-step guidance."
            );
        }
        this.state.chatMessages = [{
            role: "assistant",
            content: greeting,
            articles: [],
        }];
    }

    // ── Search ────────────────────────────────────────────────────────────────

    onSearchInput(event) {
        const q = event.target.value.trim();
        if (!q) {
            this.state.suggestions = [];
            this.state.showSuggestions = false;
            return;
        }
        this._debouncedSearch(q);
    }

    onSearchKeydown(event) {
        if (event.key === "Escape") {
            this.clearSearch();
        }
    }

    async _performSearch(query) {
        if (!query || query.length < 2) return;
        try {
            const results = await rpc("/help/api/suggestions", { q: query });
            this.state.suggestions = results || [];
            this.state.showSuggestions = true;
        } catch (e) {
            this.state.suggestions = [];
        }
    }

    clearSearch() {
        this.state.searchQuery = "";
        this.state.suggestions = [];
        this.state.showSuggestions = false;
    }

    // ── Article viewer ────────────────────────────────────────────────────────

    async openArticle(id, name) {
        const fromTab = this.state.activeTab !== "article"
            ? this.state.activeTab
            : (this.state.articleStack[0]?.fromTab || "home");

        this.state.articleStack = [...this.state.articleStack, { id, name, fromTab }];
        this.state.activeTab = "article";
        this.state.articleLoading = true;
        this.state.article = null;
        this.state.articleId = id;
        this.state.rateSubmitted = false;
        this.state.searchQuery = "";
        this.state.showSuggestions = false;

        try {
            const data = await rpc("/help/api/article/" + id, {});
            this.state.article = data;
        } catch (e) {
            this.state.article = { error: "load_failed" };
        }
        this.state.articleLoading = false;
    }

    async goBack() {
        const stack = [...this.state.articleStack];
        const current = stack.pop();
        this.state.articleStack = stack;

        if (stack.length > 0) {
            const prev = stack[stack.length - 1];
            this.state.articleLoading = true;
            this.state.article = null;
            this.state.articleId = prev.id;
            this.state.rateSubmitted = false;
            try {
                const data = await rpc("/help/api/article/" + prev.id, {});
                this.state.article = data;
            } catch (e) {
                this.state.article = { error: "load_failed" };
            }
            this.state.articleLoading = false;
        } else {
            const fromTab = current?.fromTab || "home";
            this.state.activeTab = fromTab;
            this.state.article = null;
            this.state.articleId = null;
        }
    }

    openFullSite() {
        window.open("/help", "_blank");
    }

    openArticleFullPage() {
        if (this.state.article && this.state.article.url) {
            window.open(this.state.article.url, "_blank");
        }
    }

    async rateArticle(helpful) {
        if (!this.state.articleId || this.state.rateSubmitted) return;
        try {
            await rpc("/help/api/rate", { article_id: this.state.articleId, helpful });
            this.state.rateSubmitted = true;
        } catch (e) {
            // ignore
        }
    }

    // ── Chat ─────────────────────────────────────────────────────────────────

    onChatInput(event) {
        this.state.chatInput = event.target.value;
    }

    onChatKeydown(event) {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            this.sendChat();
        }
    }

    async sendChat() {
        const message = this.state.chatInput.trim();
        if (!message || this.state.chatLoading) return;

        this.state.chatInput = "";
        this.state.chatMessages = [
            ...this.state.chatMessages,
            { role: "user", content: message, articles: [] },
        ];
        this.state.chatLoading = true;

        try {
            const data = await rpc("/help/chat", {
                message,
                session_token: this.state.sessionToken || false,
                context_url: window.location.href,
            });
            if (data.session_token) {
                this.state.sessionToken = data.session_token;
                localStorage.setItem(STORAGE_SESSION, data.session_token);
            }
            this.state.chatMessages = [
                ...this.state.chatMessages,
                { role: "assistant", content: data.response, articles: data.articles || [] },
            ];
        } catch (e) {
            this.state.chatMessages = [
                ...this.state.chatMessages,
                { role: "assistant", content: "Sorry, I couldn't process that request. Please try again.", articles: [] },
            ];
        }
        this.state.chatLoading = false;
    }

    // ── Lodge Ticket ─────────────────────────────────────────────────────────

    onTicketSubjectInput(event) {
        this.state.ticketSubject = event.target.value;
        if (this.state.ticketSubjectError) this.state.ticketSubjectError = "";
    }

    onTicketDescInput(event) {
        this.state.ticketDesc = event.target.value;
    }

    async submitTicket() {
        this.state.ticketSubjectError = "";
        this.state.ticketError = "";

        if (!this.state.ticketSubject.trim()) {
            this.state.ticketSubjectError = "Please enter a subject for your ticket.";
            return;
        }

        this.state.ticketSubmitting = true;
        try {
            const result = await rpc("/help/api/create_ticket", {
                subject: this.state.ticketSubject.trim(),
                description: this.state.ticketDesc.trim(),
            });
            if (result.error) {
                this.state.ticketError = result.message || "An error occurred. Please try again.";
            } else {
                this.state.ticketId = result.ticket_id;
                this.state.ticketSubmitted = true;
            }
        } catch (e) {
            this.state.ticketError = "Something went wrong. Please try again.";
        }
        this.state.ticketSubmitting = false;
    }

    resetTicket() {
        this.state.ticketSubject = "";
        this.state.ticketDesc = "";
        this.state.ticketSubmitting = false;
        this.state.ticketSubmitted = false;
        this.state.ticketId = null;
        this.state.ticketError = "";
        this.state.ticketSubjectError = "";
    }

    // ── Template helpers ──────────────────────────────────────────────────────

    /** Returns an inline style string that overrides the primary colour CSS vars
     *  on the panel element, so the custom colour cascades to all descendants. */
    get panelColorStyle() {
        const c = this.state.primaryColor;
        if (!c) return "";
        return `--hc-primary: ${c}; --hc-primary-d: ${c};`;
    }

    getChatBubbleHtml(content) {
        return markup(mdToHtml(content));
    }

    getArticleContent() {
        if (!this.state.article || !this.state.article.content) return markup("");
        return markup(this.state.article.content);
    }

    getPanelTitle() {
        if (
            this.state.activeTab === "article" &&
            this.state.article &&
            !this.state.article.error &&
            this.state.article.name
        ) {
            return this.state.article.name;
        }
        return "Help Centre";
    }
}

registry.category("systray").add("help_centre.help_button", {
    Component: HelpCentreSystrayItem,
}, { sequence: 50 });
