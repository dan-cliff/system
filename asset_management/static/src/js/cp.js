/**
 * Asset Control Plane — Client-side JS
 * Handles: offline detection, IndexedDB queue, Background Sync, PWA install prompt.
 */
(function () {
  'use strict';

  // ── Token injected by template ─────────────────────────────────────────
  const CP_TOKEN = document.documentElement.dataset.cpToken || '';
  const LOCATION_TRACKING = document.documentElement.dataset.locationTracking === '1';
  const DB_NAME = 'asset-cp-' + CP_TOKEN.substring(0, 8);
  const DB_VERSION = 2;
  const SYNC_TAG = 'asset-cp-sync-' + CP_TOKEN.substring(0, 8);
  const LOC_SYNC_TAG = 'asset-cp-loc-' + CP_TOKEN.substring(0, 8);
  const PERIODIC_LOC_TAG = 'asset-cp-periodic-' + CP_TOKEN.substring(0, 8);

  // ── IndexedDB (v2: pending + last_location stores) ────────────────────
  let db = null;

  function openDB() {
    return new Promise((resolve, reject) => {
      if (db) return resolve(db);
      const req = indexedDB.open(DB_NAME, DB_VERSION);
      req.onupgradeneeded = (e) => {
        const database = e.target.result;
        if (!database.objectStoreNames.contains('pending')) {
          database.createObjectStore('pending', { keyPath: 'id', autoIncrement: true });
        }
        if (!database.objectStoreNames.contains('last_location')) {
          database.createObjectStore('last_location', { keyPath: 'id' });
        }
      };
      req.onsuccess = (e) => { db = e.target.result; resolve(db); };
      req.onerror = (e) => reject(e.target.error);
    });
  }

  // ── Last-known location (shared with service worker via IndexedDB) ─────
  async function saveLastLocation(lat, lon, accuracy) {
    try {
      const database = await openDB();
      return new Promise((resolve) => {
        const tx = database.transaction('last_location', 'readwrite');
        tx.objectStore('last_location').put({
          id: 'current',
          latitude: lat,
          longitude: lon,
          accuracy: accuracy,
          recorded_at: new Date().toISOString(),
        });
        tx.oncomplete = resolve;
      });
    } catch (_) {}
  }

  async function queueEntry(type, data) {
    const database = await openDB();
    return new Promise((resolve, reject) => {
      const tx = database.transaction('pending', 'readwrite');
      tx.objectStore('pending').add({ type, data, queued_at: new Date().toISOString() });
      tx.oncomplete = resolve;
      tx.onerror = (e) => reject(e.target.error);
    });
  }

  async function getPendingCount() {
    const database = await openDB();
    return new Promise((resolve) => {
      const tx = database.transaction('pending', 'readonly');
      const req = tx.objectStore('pending').count();
      req.onsuccess = (e) => resolve(e.target.result);
      req.onerror = () => resolve(0);
    });
  }

  async function getAllPending() {
    const database = await openDB();
    return new Promise((resolve) => {
      const tx = database.transaction('pending', 'readonly');
      const req = tx.objectStore('pending').getAll();
      req.onsuccess = (e) => resolve(e.target.result);
      req.onerror = () => resolve([]);
    });
  }

  async function deletePending(id) {
    const database = await openDB();
    return new Promise((resolve) => {
      const tx = database.transaction('pending', 'readwrite');
      tx.objectStore('pending').delete(id);
      tx.oncomplete = resolve;
    });
  }

  // ── Online / Offline detection ─────────────────────────────────────────
  function updateOnlineStatus() {
    if (navigator.onLine) {
      document.body.classList.remove('offline');
      flushPendingNow();
    } else {
      document.body.classList.add('offline');
    }
    updateQueueBadge();
  }

  async function updateQueueBadge() {
    const count = await getPendingCount();
    const badge = document.querySelector('.cp-queue-badge');
    if (!badge) return;
    if (count > 0) {
      document.body.classList.add('has-pending');
      badge.textContent = `⏳ ${count} entry${count > 1 ? 's' : ''} pending sync…`;
    } else {
      document.body.classList.remove('has-pending');
    }
  }

  // ── Manual flush (when back online) ───────────────────────────────────
  async function flushPendingNow() {
    const items = await getAllPending();
    if (!items.length) return;

    let synced = 0;
    for (const item of items) {
      try {
        const res = await fetch(`/asset/cp/${CP_TOKEN}/sync`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CP-Token': CP_TOKEN },
          body: JSON.stringify({ type: item.type, data: item.data }),
        });
        if (res.ok) {
          await deletePending(item.id);
          synced++;
        }
      } catch (_) {
        // Still offline or server error — leave in queue
      }
    }
    if (synced > 0) updateQueueBadge();
  }

  // ── Form submission with offline fallback ─────────────────────────────
  function setupOfflineForm(form, type, extractData) {
    if (!form) return;

    form.addEventListener('submit', async (e) => {
      e.preventDefault();

      const data = extractData(form);
      const submitBtn = form.querySelector('.cp-submit-btn');
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = 'Saving…';
      }

      if (!navigator.onLine) {
        // Queue for later
        await queueEntry(type, data);
        updateQueueBadge();

        // Register background sync if supported
        if ('serviceWorker' in navigator && 'SyncManager' in window) {
          const reg = await navigator.serviceWorker.ready;
          try { await reg.sync.register(SYNC_TAG); } catch (_) {}
        }

        showOfflineSuccess(form, type);
        form.reset();
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.textContent = getSubmitLabel(type);
        }
        return;
      }

      // Online — submit normally via fetch
      const formData = new FormData(form);
      try {
        const res = await fetch(form.action, {
          method: 'POST',
          body: formData,
          redirect: 'follow',
        });
        if (res.ok || res.redirected) {
          window.location.href = res.url || form.action + '?success=1';
        } else {
          throw new Error('Server error');
        }
      } catch (_) {
        // Fell offline mid-submit — queue it
        await queueEntry(type, data);
        updateQueueBadge();
        showOfflineSuccess(form, type);
        form.reset();
      }

      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.textContent = getSubmitLabel(type);
      }
    });
  }

  function getSubmitLabel(type) {
    const labels = { usage: 'Save Reading', defect: 'Report Defect', maintenance: 'Log Maintenance' };
    return labels[type] || 'Save';
  }

  function showOfflineSuccess(form, type) {
    const labels = {
      usage: '✅ Reading saved offline — will sync when back online.',
      defect: '✅ Defect queued offline — will sync when back online.',
      maintenance: '✅ Maintenance log queued offline — will sync when back online.',
    };
    let alert = form.querySelector('.cp-alert.offline-saved');
    if (!alert) {
      alert = document.createElement('div');
      alert.className = 'cp-alert success offline-saved';
      form.prepend(alert);
    }
    alert.textContent = labels[type] || '✅ Saved offline.';
    alert.style.display = 'block';
    setTimeout(() => { alert.style.display = 'none'; }, 6000);
  }

  // ── Identity management (localStorage, keyed per token) ──────────────
  const IDENTITY_KEY = 'cp_identity_' + CP_TOKEN;

  function getIdentity() {
    try { return JSON.parse(localStorage.getItem(IDENTITY_KEY) || 'null'); } catch (_) { return null; }
  }

  function setIdentity(data) {
    try { localStorage.setItem(IDENTITY_KEY, JSON.stringify(data)); } catch (_) {}
  }

  function clearIdentity() {
    try { localStorage.removeItem(IDENTITY_KEY); } catch (_) {}
  }

  function updateIdentityUI() {
    const identity = getIdentity();

    // ── Header badge (all pages) ───────────────────────────────────────
    const badge = document.getElementById('cp-identity-badge');
    const badgeName = document.getElementById('cp-badge-name');
    if (badge && badgeName) {
      if (identity) {
        badgeName.textContent = identity.employee_name;
        badge.classList.add('visible');
      } else {
        badge.classList.remove('visible');
      }
    }

    // ── Landing sign-in card ───────────────────────────────────────────
    const signinForm   = document.getElementById('cp-signin-form');
    const signinActive = document.getElementById('cp-signin-active');
    const signinName   = document.getElementById('cp-signin-name');
    const photoEl      = document.getElementById('cp-signin-photo');
    const photoPlaceholder = document.getElementById('cp-signin-avatar-placeholder');
    if (signinForm && signinActive) {
      if (identity) {
        signinActive.style.display = 'block';
        signinForm.style.display = 'none';
        if (signinName) signinName.textContent = identity.employee_name;
        // Show photo if available
        if (photoEl && identity.avatar) {
          photoEl.src = identity.avatar;
          photoEl.style.display = 'block';
          if (photoPlaceholder) photoPlaceholder.style.display = 'none';
        } else if (photoEl) {
          photoEl.style.display = 'none';
          if (photoPlaceholder) photoPlaceholder.style.display = '';
        }
      } else {
        signinActive.style.display = 'none';
        signinForm.style.display = 'block';
      }
    }

    // ── Action button locking (landing page) ───────────────────────────
    const lockHint = document.getElementById('cp-action-lock-hint');
    if (identity) {
      document.body.classList.remove('cp-identity-required');
      if (lockHint) lockHint.style.display = 'none';
    } else if (document.querySelector('.cp-action-btn')) {
      document.body.classList.add('cp-identity-required');
      if (lockHint) lockHint.style.display = 'block';
    }

    // ── Pre-populate Recorded By on usage form ─────────────────────────
    const usageUserSel = document.querySelector('#cp-usage-form [name="user_id"]');
    if (usageUserSel && identity && identity.user_id) {
      usageUserSel.value = identity.user_id;
    }

    // ── Pre-populate defect reporter ───────────────────────────────────
    const defectUserSel = document.querySelector('#cp-defect-form [name="user_id"]');
    const reporterHidden = document.getElementById('f-reporter-name-hidden');
    if (defectUserSel) {
      if (identity && identity.user_id) {
        defectUserSel.value = identity.user_id;
        if (reporterHidden) reporterHidden.value = '';
      } else if (identity) {
        defectUserSel.value = '';
        if (reporterHidden) reporterHidden.value = identity.employee_name;
      }
    }

    // ── Pre-populate maintenance technician ────────────────────────────
    const maintUserSel = document.querySelector('#cp-maintenance-form [name="user_id"]');
    const techHidden   = document.getElementById('f-tech-name-hidden');
    if (maintUserSel) {
      if (identity && identity.user_id) {
        maintUserSel.value = identity.user_id;
        if (techHidden) techHidden.value = '';
      } else if (identity) {
        maintUserSel.value = '';
        if (techHidden) techHidden.value = identity.employee_name;
      }
    }
  }

  // ── Barcode verification ───────────────────────────────────────────────
  async function verifyBarcode(barcode) {
    const res = await fetch(`/asset/cp/${CP_TOKEN}/auth/barcode`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ barcode }),
    });
    return res.json();
  }

  function setupSignIn() {
    const barcodeInput   = document.getElementById('cp-barcode-input');
    const barcodeSubmit  = document.getElementById('cp-barcode-submit');
    const cameraScanBtn  = document.getElementById('cp-camera-scan-btn');
    const barcodeError   = document.getElementById('cp-barcode-error');
    const pinInput       = document.getElementById('cp-pin-input');
    const pinSubmit      = document.getElementById('cp-pin-submit');
    const pinError       = document.getElementById('cp-pin-error');
    const manualFallback = document.getElementById('cp-manual-fallback');
    const manualName     = document.getElementById('cp-manual-name');
    const manualSubmit   = document.getElementById('cp-manual-submit');

    // ── Tab switching ──────────────────────────────────────────────────
    document.querySelectorAll('.cp-signin-tab').forEach((tab) => {
      tab.addEventListener('click', () => {
        document.querySelectorAll('.cp-signin-tab').forEach((t) => t.classList.remove('active'));
        tab.classList.add('active');
        const target = tab.dataset.tab;
        document.querySelectorAll('.cp-signin-panel').forEach((panel) => {
          panel.style.display = panel.id === 'cp-tab-' + target ? '' : 'none';
        });
      });
    });

    // ── Verify a barcode value against the server ──────────────────────
    async function doVerify() {
      const barcode = barcodeInput ? barcodeInput.value.trim() : '';
      if (!barcode) return;
      if (!navigator.onLine) {
        if (barcodeError) barcodeError.textContent = 'Cannot verify while offline — use the name field below.';
        if (manualFallback) manualFallback.style.display = 'block';
        return;
      }
      if (barcodeError) barcodeError.textContent = '';
      if (barcodeSubmit) { barcodeSubmit.disabled = true; barcodeSubmit.textContent = '...'; }
      try {
        const data = await verifyBarcode(barcode);
        if (data.status === 'ok') {
          setIdentity(data);
          if (barcodeInput) barcodeInput.value = '';
          updateIdentityUI();
        } else {
          if (barcodeError) barcodeError.textContent = data.message || 'Barcode not recognised.';
          if (manualFallback) manualFallback.style.display = 'block';
        }
      } catch (_) {
        if (barcodeError) barcodeError.textContent = 'Verification failed — check connection.';
        if (manualFallback) manualFallback.style.display = 'block';
      }
      if (barcodeSubmit) { barcodeSubmit.disabled = false; barcodeSubmit.textContent = 'Verify'; }
    }

    // ── Camera scanner ─────────────────────────────────────────────────
    function openCameraScanner() {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        if (barcodeError) barcodeError.textContent = 'Camera not supported on this browser.';
        return;
      }

      // Build overlay DOM
      const overlay = document.createElement('div');
      overlay.className = 'cp-scanner-overlay';
      overlay.innerHTML =
        '<div class="cp-scanner-modal">' +
          '<div class="cp-scanner-header">' +
            '<span class="cp-scanner-title">Scan ID Card Barcode</span>' +
            '<button type="button" class="cp-scanner-close" aria-label="Close">&#x2715;</button>' +
          '</div>' +
          '<div class="cp-scanner-viewport">' +
            '<video autoplay playsinline muted></video>' +
            '<div class="cp-scanner-frame"><div class="cp-scanner-line"></div></div>' +
            '<div class="cp-scanner-hint">Point the camera at the barcode on the ID card</div>' +
          '</div>' +
          '<div class="cp-scanner-status">Starting camera&#x2026;</div>' +
        '</div>';
      document.body.appendChild(overlay);

      const video    = overlay.querySelector('video');
      const statusEl = overlay.querySelector('.cp-scanner-status');
      let stream     = null;
      let scanning   = false;
      let animFrame  = null;

      function closeScanner() {
        scanning = false;
        if (animFrame) cancelAnimationFrame(animFrame);
        if (stream) stream.getTracks().forEach((t) => t.stop());
        overlay.remove();
      }

      overlay.querySelector('.cp-scanner-close').addEventListener('click', closeScanner);
      overlay.addEventListener('click', (e) => { if (e.target === overlay) closeScanner(); });

      (async () => {
        try {
          stream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: 'environment', width: { ideal: 1920 }, height: { ideal: 1080 } },
          });
          video.srcObject = stream;
          await video.play();
          if (statusEl) statusEl.textContent = '';

          if (!('BarcodeDetector' in window)) {
            if (statusEl) statusEl.textContent =
              'Live scanning is not supported on this browser. Enter the barcode manually.';
            return;
          }

          // Pick every format the detector supports; fall back to a broad set
          let formats = ['code_128', 'code_39', 'code_93', 'ean_13', 'ean_8',
                         'upc_a', 'upc_e', 'itf', 'codabar', 'pdf417',
                         'data_matrix', 'qr_code', 'aztec'];
          try {
            const supported = await BarcodeDetector.getSupportedFormats();
            formats = formats.filter((f) => supported.includes(f));
          } catch (_) {}

          const detector = new BarcodeDetector({ formats });
          scanning = true;

          async function detectFrame() {
            if (!scanning || video.readyState < 2) {
              animFrame = requestAnimationFrame(detectFrame);
              return;
            }
            try {
              const barcodes = await detector.detect(video);
              if (barcodes.length > 0) {
                const value = barcodes[0].rawValue;
                closeScanner();
                if (barcodeInput) barcodeInput.value = value;
                await doVerify();
              } else {
                animFrame = requestAnimationFrame(detectFrame);
              }
            } catch (_) {
              animFrame = requestAnimationFrame(detectFrame);
            }
          }

          animFrame = requestAnimationFrame(detectFrame);

        } catch (err) {
          if (statusEl) {
            statusEl.textContent = err.name === 'NotAllowedError'
              ? 'Camera permission denied. Allow camera access in your browser settings.'
              : 'Could not start camera: ' + err.message;
          }
        }
      })();
    }

    if (cameraScanBtn) cameraScanBtn.addEventListener('click', openCameraScanner);

    // ── PIN verification ───────────────────────────────────────────────
    async function doVerifyPin() {
      const pin = pinInput ? pinInput.value.trim() : '';
      if (!pin) return;
      if (!navigator.onLine) {
        if (pinError) pinError.textContent = 'Cannot verify while offline — use the name field below.';
        if (manualFallback) manualFallback.style.display = 'block';
        return;
      }
      if (pinError) pinError.textContent = '';
      if (pinSubmit) { pinSubmit.disabled = true; pinSubmit.textContent = '...'; }
      try {
        const res = await fetch(`/asset/cp/${CP_TOKEN}/auth/pin`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ pin }),
        });
        const data = await res.json();
        if (data.status === 'ok') {
          setIdentity(data);
          if (pinInput) pinInput.value = '';
          updateIdentityUI();
        } else {
          if (pinError) pinError.textContent = data.message || 'PIN not recognised.';
          if (manualFallback) manualFallback.style.display = 'block';
        }
      } catch (_) {
        if (pinError) pinError.textContent = 'Verification failed — check connection.';
        if (manualFallback) manualFallback.style.display = 'block';
      }
      if (pinSubmit) { pinSubmit.disabled = false; pinSubmit.textContent = 'Verify'; }
    }
    if (pinSubmit) pinSubmit.addEventListener('click', doVerifyPin);
    if (pinInput) {
      pinInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { e.preventDefault(); doVerifyPin(); }
      });
    }

    // ── Manual barcode input (HID scanner sends Enter) ─────────────────
    if (barcodeSubmit) barcodeSubmit.addEventListener('click', doVerify);
    if (barcodeInput) {
      barcodeInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { e.preventDefault(); doVerify(); }
      });
    }

    // ── Manual name fallback ───────────────────────────────────────────
    if (manualSubmit) {
      manualSubmit.addEventListener('click', () => {
        const name = manualName ? manualName.value.trim() : '';
        if (!name) return;
        setIdentity({ employee_id: null, employee_name: name, user_id: null });
        if (manualName) manualName.value = '';
        updateIdentityUI();
      });
      if (manualName) {
        manualName.addEventListener('keydown', (e) => {
          if (e.key === 'Enter') { e.preventDefault(); manualSubmit.click(); }
        });
      }
    }

    if (!navigator.onLine && manualFallback) manualFallback.style.display = 'block';

    // ── Block action buttons when not signed in ────────────────────────
    document.addEventListener('click', (e) => {
      const btn = e.target.closest('.cp-action-btn');
      if (btn && !getIdentity()) {
        e.preventDefault();
        const card = document.getElementById('cp-signin-card');
        if (card) {
          card.scrollIntoView({ behavior: 'smooth', block: 'center' });
          card.classList.add('cp-signin-highlight');
          setTimeout(() => card.classList.remove('cp-signin-highlight'), 1000);
        }
      }
    });

    // ── Sign-out ───────────────────────────────────────────────────────
    document.addEventListener('click', (e) => {
      if (e.target.id === 'cp-signout-btn' || e.target.id === 'cp-badge-signout') {
        clearIdentity();
        updateIdentityUI();
      }
    });
  }

  // ── Usage form ─────────────────────────────────────────────────────────
  const usageForm = document.getElementById('cp-usage-form');
  setupOfflineForm(usageForm, 'usage', (f) => ({
    date: f.querySelector('[name="date"]')?.value || '',
    reading: f.querySelector('[name="reading"]')?.value || '',
    user_id: f.querySelector('[name="user_id"]')?.value || '',
    notes: f.querySelector('[name="notes"]')?.value || '',
  }));

  // ── Defect form ────────────────────────────────────────────────────────
  const defectForm = document.getElementById('cp-defect-form');
  if (defectForm) {
    // Severity selector
    const sevInput = defectForm.querySelector('[name="severity"]');
    defectForm.querySelectorAll('.cp-sev-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        defectForm.querySelectorAll('.cp-sev-btn').forEach((b) => b.classList.remove('selected'));
        btn.classList.add('selected');
        if (sevInput) sevInput.value = btn.dataset.sev;
      });
    });
    // Mark initial selection: match hidden input value, or fall back to first button
    const sevBtns = defectForm.querySelectorAll('.cp-sev-btn');
    const preSelected = sevInput && [...sevBtns].find((b) => b.dataset.sev === sevInput.value);
    if (preSelected) {
      preSelected.classList.add('selected');
    } else if (sevBtns.length) {
      sevBtns[0].classList.add('selected');
      if (sevInput) sevInput.value = sevBtns[0].dataset.sev;
    }
  }
  setupOfflineForm(defectForm, 'defect', (f) => ({
    date: f.querySelector('[name="date"]')?.value || '',
    user_id: f.querySelector('[name="user_id"]')?.value || '',
    reporter_name: f.querySelector('[name="reporter_name"]')?.value || '',
    description: f.querySelector('[name="description"]')?.value || '',
    severity: f.querySelector('[name="severity"]')?.value || '',
  }));

  // ── Maintenance form ───────────────────────────────────────────────────
  const maintForm = document.getElementById('cp-maintenance-form');
  setupOfflineForm(maintForm, 'maintenance', (f) => ({
    date: f.querySelector('[name="date"]')?.value || '',
    user_id: f.querySelector('[name="user_id"]')?.value || '',
    technician_name: f.querySelector('[name="technician_name"]')?.value || '',
    maintenance_type: f.querySelector('[name="maintenance_type"]')?.value || '',
    description: f.querySelector('[name="description"]')?.value || '',
    parts_used: f.querySelector('[name="parts_used"]')?.value || '',
    next_due_date: f.querySelector('[name="next_due_date"]')?.value || '',
  }));

  // ── Service Worker Registration ────────────────────────────────────────
  if ('serviceWorker' in navigator && CP_TOKEN) {
    window.addEventListener('load', () => {
      navigator.serviceWorker
        .register(`/asset/cp/${CP_TOKEN}/sw.js`, { scope: `/asset/cp/${CP_TOKEN}/` })
        .then((reg) => {
          console.log('[CP] Service worker registered, scope:', reg.scope);
          // Listen for updates
          reg.addEventListener('updatefound', () => {
            const sw = reg.installing;
            if (sw) sw.addEventListener('statechange', () => {
              if (sw.state === 'installed' && navigator.serviceWorker.controller) {
                console.log('[CP] New service worker available');
              }
            });
          });
        })
        .catch((e) => console.warn('[CP] SW registration failed:', e));
    });
  }

  // ── PWA Install Prompt ─────────────────────────────────────────────────
  let deferredInstallPrompt = null;
  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredInstallPrompt = e;
    const prompt = document.querySelector('.cp-install-prompt');
    if (prompt) prompt.classList.add('visible');
  });

  document.addEventListener('click', (e) => {
    if (e.target.classList.contains('cp-install-btn') && deferredInstallPrompt) {
      deferredInstallPrompt.prompt();
      deferredInstallPrompt.userChoice.then(() => {
        deferredInstallPrompt = null;
        const prompt = document.querySelector('.cp-install-prompt');
        if (prompt) prompt.classList.remove('visible');
      });
    }
  });

  // ── Auto-refresh (5 min, online only, not while editing) ──────────────
  let formFocused = false;
  document.addEventListener('focusin', (e) => {
    if (e.target.matches('input, select, textarea')) formFocused = true;
  });
  document.addEventListener('focusout', (e) => {
    if (e.target.matches('input, select, textarea')) formFocused = false;
  });

  setInterval(() => {
    if (navigator.onLine && !formFocused) {
      window.location.reload();
    }
  }, 5 * 60 * 1000);

  // ── Date inputs: auto-format DD/MM/YYYY ───────────────────────────────
  function parseDMY(str) {
    // Convert DD/MM/YYYY → YYYY-MM-DD for server submission
    if (!str) return '';
    const m = str.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
    if (m) return `${m[3]}-${m[2]}-${m[1]}`;
    return str; // already YYYY-MM-DD or empty
  }

  function setupDateInputs() {
    document.querySelectorAll('.cp-date-input').forEach((input) => {
      // Auto-insert slashes as user types
      input.addEventListener('input', function () {
        let digits = this.value.replace(/\D/g, '').substring(0, 8);
        let formatted = digits;
        if (digits.length > 4) {
          formatted = digits.slice(0, 2) + '/' + digits.slice(2, 4) + '/' + digits.slice(4);
        } else if (digits.length > 2) {
          formatted = digits.slice(0, 2) + '/' + digits.slice(2);
        }
        this.value = formatted;
      });

      // Allow typing slashes directly without duplicating
      input.addEventListener('keydown', function (e) {
        if (e.key === '/' || e.key === '-') {
          e.preventDefault();
          // Trigger auto-slash by firing input with the current digits
          const digits = this.value.replace(/\D/g, '');
          if (digits.length === 2 || digits.length === 4) {
            this.value = this.value; // already has slash from input handler
          }
        }
      });
    });

    // Before any cp-form submits, convert dates from DD/MM/YYYY → YYYY-MM-DD
    document.querySelectorAll('.cp-form').forEach((form) => {
      form.addEventListener('submit', () => {
        form.querySelectorAll('.cp-date-input').forEach((input) => {
          input.value = parseDMY(input.value);
        });
      }, true); // capture phase — runs before setupOfflineForm's handler
    });
  }

  // ── GPS Location Tracking ─────────────────────────────────────────────
  (function setupLocationTracking() {
    if (!LOCATION_TRACKING) return;
    if (!('geolocation' in navigator)) return;

    const statusEl = document.getElementById('cp-location-status');

    function setStatus(msg) {
      if (statusEl) statusEl.textContent = msg;
    }

    // ── Wake Lock — keep device awake while PWA is open ──────────────────
    let wakeLock = null;

    async function requestWakeLock() {
      if (!('wakeLock' in navigator)) return;
      try {
        wakeLock = await navigator.wakeLock.request('screen');
        wakeLock.addEventListener('release', () => { wakeLock = null; });
      } catch (_) {}
    }

    requestWakeLock();

    // Re-acquire wake lock when page becomes visible again
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible') {
        requestWakeLock();
      }
    });

    // ── Debounce: only send if moved > 30 m or > 5 min since last send ───
    const MIN_DISTANCE_M = 30;
    const MIN_INTERVAL_MS = 5 * 60 * 1000;
    let lastSentLat = null;
    let lastSentLon = null;
    let lastSentAt = 0;

    function haversineDistance(lat1, lon1, lat2, lon2) {
      const R = 6371000;
      const toRad = (x) => (x * Math.PI) / 180;
      const dLat = toRad(lat2 - lat1);
      const dLon = toRad(lon2 - lon1);
      const a =
        Math.sin(dLat / 2) * Math.sin(dLat / 2) +
        Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) *
        Math.sin(dLon / 2) * Math.sin(dLon / 2);
      return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    }

    async function sendLocation(lat, lon, accuracy) {
      try {
        const res = await fetch(`/asset/cp/${CP_TOKEN}/location`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ latitude: lat, longitude: lon, accuracy: accuracy }),
        });
        if (res.ok) {
          lastSentLat = lat;
          lastSentLon = lon;
          lastSentAt = Date.now();
          const ts = new Date().toLocaleTimeString();
          setStatus(`\u2705 Updated at ${ts} \u2014 \u00B1${Math.round(accuracy)}m`);
        } else {
          setStatus('Failed to send location \u2014 retrying next update.');
        }
      } catch (_) {
        setStatus('Offline \u2014 location will send when reconnected.');
      }
    }

    function onPosition(pos) {
      const lat = pos.coords.latitude;
      const lon = pos.coords.longitude;
      const accuracy = pos.coords.accuracy;

      // Always save to IndexedDB so the service worker can send it from the background
      saveLastLocation(lat, lon, accuracy);

      const now = Date.now();
      const timeSinceLast = now - lastSentAt;
      const moved = (lastSentLat === null)
        ? Infinity
        : haversineDistance(lastSentLat, lastSentLon, lat, lon);

      if (moved >= MIN_DISTANCE_M || timeSinceLast >= MIN_INTERVAL_MS) {
        setStatus('Sending location\u2026');
        sendLocation(lat, lon, accuracy);
      } else {
        const ts = new Date().toLocaleTimeString();
        setStatus(`\u{1F4CD} Tracking active \u2014 \u00B1${Math.round(accuracy)}m (${ts})`);
      }
    }

    function onError(err) {
      const msgs = {
        1: 'Location permission denied. Enable GPS in browser settings.',
        2: 'GPS position unavailable.',
        3: 'GPS request timed out.',
      };
      setStatus(msgs[err.code] || 'GPS error.');
    }

    setStatus('Requesting GPS\u2026');
    navigator.geolocation.watchPosition(onPosition, onError, {
      enableHighAccuracy: true,
      maximumAge: 30000,
      timeout: 30000,
    });

    // ── Background Sync on visibility change (app backgrounded) ─────────
    document.addEventListener('visibilitychange', async () => {
      if (document.visibilityState === 'hidden' && 'serviceWorker' in navigator) {
        try {
          const reg = await navigator.serviceWorker.ready;
          if ('sync' in reg) await reg.sync.register(LOC_SYNC_TAG);
        } catch (_) {}
      }
    });

    // ── Periodic Background Sync (installed PWA on Android/Chrome) ───────
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.ready.then(async (reg) => {
        if (!('periodicSync' in reg)) return;
        try {
          const status = await navigator.permissions.query({ name: 'periodic-background-sync' });
          if (status.state === 'granted') {
            await reg.periodicSync.register(PERIODIC_LOC_TAG, {
              minInterval: 15 * 60 * 1000, // 15 minutes (browser may enforce longer)
            });
          }
        } catch (_) {}
      });
    }
  })();

  // ── Init ───────────────────────────────────────────────────────────────
  window.addEventListener('online', updateOnlineStatus);
  window.addEventListener('offline', updateOnlineStatus);
  updateOnlineStatus();

  setupDateInputs();
  setupSignIn();
  updateIdentityUI();

})();
