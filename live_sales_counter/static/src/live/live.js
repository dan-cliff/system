/* Live Sales Counter - the live page.
 *
 * Polls /live-sales/<token>/data, rolls the counters up when sales come in,
 * adds them to the feed and flies them in on the map.
 */
(function () {
    'use strict';

    const PLACES_EVERY_MS = 5 * 60 * 1000;
    const SALE_STAGGER_MS = 1800;
    const FEED_SIZE = 12;

    const config = JSON.parse(document.body.dataset.config || '{}');
    const $ = (id) => document.getElementById(id);

    // ── Formatting ─────────────────────────────────────────────────────────
    const currency = config.currency || { symbol: '', position: 'before', decimals: 2 };
    const numberFormat = new Intl.NumberFormat('en-GB', {
        minimumFractionDigits: currency.decimals,
        maximumFractionDigits: currency.decimals,
    });
    const countFormat = new Intl.NumberFormat('en-GB');

    function money(amount) {
        const negative = amount < 0;
        const text = numberFormat.format(Math.abs(amount));
        const withSymbol = currency.position === 'after' ? `${text} ${currency.symbol}` : `${currency.symbol}${text}`;
        return negative ? `-${withSymbol}` : withSymbol;
    }

    function pad(n) {
        return String(n).padStart(2, '0');
    }

    /** Date parts in the counter's timezone. */
    function zoned(date) {
        const parts = {};
        try {
            new Intl.DateTimeFormat('en-GB', {
                timeZone: config.tz || undefined,
                year: 'numeric', month: '2-digit', day: '2-digit',
                hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
            }).formatToParts(date).forEach((p) => {
                parts[p.type] = p.value;
            });
        } catch {
            return { day: pad(date.getDate()), month: pad(date.getMonth() + 1), year: date.getFullYear(),
                     hour: pad(date.getHours()), minute: pad(date.getMinutes()) };
        }
        return parts;
    }

    function formatDateTime(date) {
        const p = zoned(date);
        return `${p.day}/${p.month}/${p.year} ${p.hour}:${p.minute}`;
    }

    function timeAgo(iso) {
        const date = new Date(iso);
        const seconds = Math.max(0, (Date.now() - serverOffset - date.getTime()) / 1000);
        if (seconds < 45) {
            return 'just now';
        }
        if (seconds < 3600) {
            return `${Math.round(seconds / 60)} min ago`;
        }
        const p = zoned(date);
        const today = zoned(new Date());
        if (p.day === today.day && p.month === today.month && p.year === today.year) {
            return `${p.hour}:${p.minute}`;
        }
        return formatDateTime(date);
    }

    function flag(code) {
        if (!code || code.length !== 2) {
            return '\u{1F310}';
        }
        return String.fromCodePoint(...[...code.toUpperCase()].map((c) => 0x1f1e6 + c.charCodeAt(0) - 65));
    }

    function place(sale) {
        if (sale.in_store) {
            return 'In store';
        }
        return [sale.city, sale.country].filter(Boolean).join(', ') || 'Unknown location';
    }

    // ── Rolling digits ─────────────────────────────────────────────────────
    class Odometer {
        constructor(el) {
            this.el = el;
            this.el.classList.add('ls-odometer');
            this.slots = [];
        }

        set(text) {
            const chars = [...text];
            const shape = chars.map((c) => (/\d/.test(c) ? 'd' : c)).join('');
            if (shape !== this.shape) {
                this._build(chars, shape);
            }
            chars.forEach((c, i) => {
                const slot = this.slots[i];
                if (slot.strip) {
                    const digit = Number(c);
                    // Stagger so the counter rolls from the right like a meter.
                    slot.strip.style.transitionDelay = `${(chars.length - i) * 35}ms`;
                    slot.strip.style.transform = `translateY(${-digit * 10}%)`;
                }
            });
        }

        _build(chars, shape) {
            // Keep digits already showing (aligned from the right) so they roll on from there.
            const old = this.slots.map((s) => (s.strip ? s.strip.style.transform : null));
            const offset = old.length - chars.length;
            this.el.textContent = '';
            this.slots = chars.map((c, i) => {
                const span = document.createElement('span');
                if (/\d/.test(c)) {
                    span.className = 'ls-digit';
                    const strip = document.createElement('span');
                    strip.className = 'ls-strip';
                    strip.textContent = '0123456789';
                    const prev = old[i + offset];
                    strip.style.transform = prev || 'translateY(0%)';
                    span.appendChild(strip);
                    this.el.appendChild(span);
                    return { strip };
                }
                span.className = 'ls-sep';
                span.textContent = c;
                this.el.appendChild(span);
                return {};
            });
            this.shape = shape;
            // Let the browser lay out the start position before rolling.
            void this.el.offsetWidth;
        }
    }

    // ── Sound ──────────────────────────────────────────────────────────────
    let audio = null;
    let soundOn = false;

    function chime() {
        if (!soundOn || !audio) {
            return;
        }
        const t = audio.currentTime;
        [[880, 0], [1318.5, 0.12]].forEach(([freq, delay]) => {
            const osc = audio.createOscillator();
            const gain = audio.createGain();
            osc.type = 'sine';
            osc.frequency.value = freq;
            gain.gain.setValueAtTime(0.0001, t + delay);
            gain.gain.exponentialRampToValueAtTime(0.25, t + delay + 0.02);
            gain.gain.exponentialRampToValueAtTime(0.0001, t + delay + 0.9);
            osc.connect(gain).connect(audio.destination);
            osc.start(t + delay);
            osc.stop(t + delay + 1);
        });
    }

    function setupSound() {
        const button = $('ls-sound');
        if (!config.sound) {
            return;
        }
        button.hidden = false;
        const render = () => {
            button.textContent = soundOn ? '\u{1F514}' : '\u{1F507}';
            button.title = soundOn ? 'Sound on' : 'Sound off - click to turn on';
        };
        button.addEventListener('click', () => {
            if (!audio) {
                const Ctx = window.AudioContext || window.webkitAudioContext;
                audio = Ctx ? new Ctx() : null;
            }
            soundOn = !soundOn && !!audio;
            if (audio && audio.state === 'suspended') {
                audio.resume();
            }
            render();
            chime();
        });
        render();
    }

    // ── Page state ─────────────────────────────────────────────────────────
    const totalOdometer = new Odometer($('ls-total'));
    const countOdometer = new Odometer($('ls-count'));
    const seen = new Set();
    let firstLoad = true;
    let lastPlaces = 0;
    let serverOffset = 0;
    let map = null;
    let queue = [];
    let queueTimer = null;
    let shown = { total: 0, count: 0 };
    let latest = null;
    // Display Screen Nodes: the screen's reload counter, to reload when asked.
    let reloadCounter = null;
    const demo = { total: 0, count: 0, sales: [] };

    function applyLayout() {
        const app = $('ls-app');
        if (!config.show_map) {
            $('ls-map-wrap').hidden = true;
            app.classList.add('ls-no-map');
        }
        if (!config.show_feed) {
            $('ls-feed-card').hidden = true;
        }
        if (!config.show_channels) {
            $('ls-channels-card').hidden = true;
        }
        if (config.show_map && window.LiveMap) {
            map = new window.LiveMap($('ls-map'), $('ls-map-labels'), {
                style: config.map_style,
                dark: config.dark,
            });
        }
        if (config.demo) {
            $('ls-demo').hidden = false;
        }
    }

    function renderTotals(total, count) {
        shown = { total, count };
        totalOdometer.set(money(total));
        countOdometer.set(countFormat.format(count));
        $('ls-aov').textContent = count ? money(total / count) : money(0);
    }

    function renderChannels(channels) {
        const box = $('ls-channels');
        const list = channels.slice();
        if (demo.count) {
            list.push({ name: 'Demo', total: demo.total, count: demo.count });
        }
        const max = Math.max(1, ...list.map((c) => Math.abs(c.total)));
        const existing = new Map([...box.children].map((el) => [el.dataset.name, el]));
        box.textContent = '';
        if (!list.length) {
            const empty = document.createElement('div');
            empty.className = 'ls-empty';
            empty.textContent = 'No sales yet';
            box.appendChild(empty);
            return;
        }
        list.sort((a, b) => b.total - a.total).forEach((channel) => {
            let row = existing.get(channel.name);
            if (!row) {
                row = document.createElement('div');
                row.className = 'ls-channel';
                row.dataset.name = channel.name;
                row.innerHTML = '<div class="ls-channel-head"><span class="ls-channel-name"></span>'
                    + '<span class="ls-channel-total"></span></div>'
                    + '<div class="ls-bar"><span></span></div>';
                row.querySelector('.ls-channel-name').textContent = channel.name;
            }
            row.querySelector('.ls-channel-total').textContent = `${money(channel.total)} · ${countFormat.format(channel.count)}`;
            box.appendChild(row);
            const bar = row.querySelector('.ls-bar span');
            requestAnimationFrame(() => {
                bar.style.width = `${Math.max(2, (Math.abs(channel.total) / max) * 100)}%`;
            });
        });
    }

    function feedItem(sale, fresh) {
        const li = document.createElement('li');
        li.className = 'ls-feed-item' + (fresh ? ' ls-fresh' : '');
        li.dataset.key = sale.key;
        li.innerHTML = '<span class="ls-flag"></span><div class="ls-feed-main"><div class="ls-feed-place"></div>'
            + '<div class="ls-feed-meta"><span class="ls-badge"></span><span class="ls-ago"></span></div></div>'
            + '<span class="ls-feed-amount"></span>';
        li.querySelector('.ls-flag').textContent = sale.in_store ? '\u{1F3EA}' : flag(sale.country_code);
        li.querySelector('.ls-feed-place').textContent = place(sale);
        li.querySelector('.ls-badge').textContent = sale.channel;
        const ago = li.querySelector('.ls-ago');
        ago.dataset.date = sale.date;
        ago.textContent = timeAgo(sale.date);
        li.querySelector('.ls-feed-amount').textContent = money(sale.amount);
        return li;
    }

    function renderFeed(sales) {
        const feed = $('ls-feed');
        feed.textContent = '';
        sales.slice(0, FEED_SIZE).forEach((sale) => feed.appendChild(feedItem(sale, false)));
        if (!sales.length) {
            const empty = document.createElement('li');
            empty.className = 'ls-empty';
            empty.textContent = 'Waiting for the first sale...';
            feed.appendChild(empty);
        }
    }

    function pushFeed(sale) {
        const feed = $('ls-feed');
        const empty = feed.querySelector('.ls-empty');
        if (empty) {
            empty.remove();
        }
        feed.insertBefore(feedItem(sale, true), feed.firstChild);
        while (feed.children.length > FEED_SIZE) {
            feed.lastChild.remove();
        }
    }

    function burst(amount) {
        const el = document.createElement('div');
        el.className = 'ls-burst';
        el.textContent = `+${money(amount)}`;
        $('ls-bursts').appendChild(el);
        setTimeout(() => el.remove(), 2600);
        const card = document.querySelector('.ls-total-card');
        card.classList.remove('ls-flash');
        void card.offsetWidth;
        card.classList.add('ls-flash');
    }

    /** Show one new sale: counters, burst, feed, map and chime. */
    function celebrate(sale) {
        renderTotals(shown.total + sale.amount, shown.count + 1);
        burst(sale.amount);
        pushFeed(sale);
        chime();
        if (map) {
            const pos = sale.in_store ? map.store : map.position(sale);
            map.addSale(sale, `${sale.in_store ? 'In store' : (sale.city || sale.country || '')} · ${money(sale.amount)}`);
            if (pos) {
                map.addPlace(pos);
            }
        }
    }

    function runQueue() {
        if (queueTimer || !queue.length) {
            return;
        }
        const sale = queue.shift();
        celebrate(sale);
        queueTimer = setTimeout(() => {
            queueTimer = null;
            if (queue.length) {
                runQueue();
            } else if (latest) {
                // Settle on the server's figures once every new sale has been shown.
                renderTotals(latest.total + demo.total, latest.count + demo.count);
            }
        }, SALE_STAGGER_MS);
    }

    function applyData(data) {
        if (data.switch_page || (reloadCounter !== null && data.reload !== reloadCounter)) {
            // The screen now shows something else, or was asked to reload.
            window.location.reload();
            return;
        }
        if (data.reload !== undefined) {
            reloadCounter = data.reload;
        }
        latest = data;
        serverOffset = data.server_time ? Date.now() - new Date(data.server_time).getTime() : 0;
        $('ls-period').textContent = data.period || '';
        if (map) {
            map.setStore(data.store);
            if (data.places) {
                map.setPlaces(data.places);
            }
        }
        const recent = data.recent || [];
        if (firstLoad) {
            recent.forEach((sale) => seen.add(sale.key));
            renderTotals(data.total, data.count);
            renderFeed(recent);
            renderChannels(data.channels || []);
            firstLoad = false;
            return;
        }
        // A new day / week / ... started: the totals go down, so start afresh.
        if (data.total < shown.total - demo.total && data.count < shown.count - demo.count) {
            queue = [];
            renderTotals(data.total + demo.total, data.count + demo.count);
            renderFeed(recent);
        }
        const fresh = recent.filter((sale) => !seen.has(sale.key)).reverse();
        fresh.forEach((sale) => seen.add(sale.key));
        renderChannels(data.channels || []);
        if (fresh.length) {
            queue.push(...fresh);
            runQueue();
        } else if (!queueTimer) {
            renderTotals(data.total + demo.total, data.count + demo.count);
        }
    }

    function setStatus(text, link) {
        const el = $('ls-status');
        el.hidden = !text;
        el.textContent = text || '';
        if (link) {
            const a = document.createElement('a');
            a.href = link;
            a.textContent = 'Sign in';
            el.append(' ', a);
        }
    }

    async function poll() {
        const now = Date.now();
        const wantPlaces = config.show_map && now - lastPlaces > PLACES_EVERY_MS;
        const url = config.data_url + (wantPlaces ? '?places=1' : '');
        try {
            const response = await fetch(url, { credentials: 'same-origin', cache: 'no-store' });
            if (response.status === 403) {
                setStatus('This page needs you to be signed in.', `/web/login?redirect=${encodeURIComponent(location.pathname)}`);
            } else if (response.status === 404) {
                setStatus('This live sales link is no longer valid.');
            } else if (!response.ok) {
                setStatus('Reconnecting...');
            } else {
                const data = await response.json();
                if (wantPlaces) {
                    lastPlaces = now;
                }
                setStatus('');
                applyData(data);
            }
        } catch {
            setStatus('Reconnecting...');
        }
        setTimeout(poll, (config.refresh_seconds || 10) * 1000);
    }

    // ── Demo sales ─────────────────────────────────────────────────────────
    const DEMO_PLACES = [
        ['London', 'United Kingdom', 'GB', 51.5, -0.1], ['Cardiff', 'United Kingdom', 'GB', 51.5, -3.2],
        ['Manchester', 'United Kingdom', 'GB', 53.5, -2.2], ['Edinburgh', 'United Kingdom', 'GB', 56.0, -3.2],
        ['Dublin', 'Ireland', 'IE', 53.3, -6.3], ['Paris', 'France', 'FR', 48.9, 2.4],
        ['Berlin', 'Germany', 'DE', 52.5, 13.4], ['New York', 'United States', 'US', 40.7, -74.0],
        ['Toronto', 'Canada', 'CA', 43.7, -79.4], ['Sydney', 'Australia', 'AU', -33.9, 151.2],
        ['Auckland', 'New Zealand', 'NZ', -36.8, 174.8], ['Amsterdam', 'Netherlands', 'NL', 52.4, 4.9],
        ['Stockholm', 'Sweden', 'SE', 59.3, 18.1], ['Austin', 'United States', 'US', 30.3, -97.7],
    ];
    const DEMO_CHANNELS = ['Website', 'Point of Sale', 'Etsy', 'Sales'];

    function demoSale() {
        const inStore = Math.random() < 0.2;
        const p = DEMO_PLACES[Math.floor(Math.random() * DEMO_PLACES.length)];
        const amount = Math.round((8 + Math.random() * 90) * 100) / 100;
        const sale = {
            key: `demo-${Date.now()}`,
            channel: inStore ? 'Point of Sale' : DEMO_CHANNELS[Math.floor(Math.random() * DEMO_CHANNELS.length)],
            amount,
            date: new Date(Date.now() - serverOffset).toISOString(),
            in_store: inStore,
            city: p[0],
            country: p[1],
            country_code: p[2],
            lat: p[3],
            lng: p[4],
        };
        demo.total += amount;
        demo.count += 1;
        if (!firstLoad) {
            queue.push(sale);
            runQueue();
            if (latest) {
                renderChannels(latest.channels || []);
            }
        }
        setTimeout(demoSale, 3500 + Math.random() * 5000);
    }

    // ── Chrome: clock, full screen, idle cursor ───────────────────────────
    function tickClock() {
        $('ls-clock').textContent = formatDateTime(new Date());
        document.querySelectorAll('.ls-ago').forEach((el) => {
            el.textContent = timeAgo(el.dataset.date);
        });
    }

    function setupChrome() {
        $('ls-fullscreen').addEventListener('click', () => {
            if (document.fullscreenElement) {
                document.exitFullscreen();
            } else if (document.documentElement.requestFullscreen) {
                document.documentElement.requestFullscreen();
            }
        });
        let idle = null;
        const wake = () => {
            document.body.classList.remove('ls-idle');
            clearTimeout(idle);
            idle = setTimeout(() => document.body.classList.add('ls-idle'), 4000);
        };
        ['mousemove', 'pointerdown', 'keydown'].forEach((ev) => document.addEventListener(ev, wake));
        wake();
        tickClock();
        setInterval(tickClock, 5000);
    }

    applyLayout();
    setupSound();
    setupChrome();
    poll();
    if (config.demo) {
        setTimeout(demoSale, 2500);
    }
})();
