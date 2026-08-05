/** @odoo-module **/
/**
 * LMS Portal JavaScript — enhanced UX for the My Training portal.
 */

// ── Iframe detection (runs immediately, before paint) ─────────────────────────
// When the LMS portal page (/my/training or a sub-path) is loaded inside the
// Odoo backend iframe, add a class to <html> so CSS can hide the portal
// header/footer without a visible flash.
//
// IMPORTANT — URL scope: this check is deliberately restricted to /my/training
// paths so that other pages that happen to be rendered inside an iframe (e.g.
// the Odoo website editor preview, kiosk views, or any other backend-embedded
// page) do NOT have their navigation suppressed.
//
// URL remapping note: the url_slug_manager module can remap backend action
// paths such as /odoo/action-5867 → /odoo/<custom-slug>, but it only ever
// changes ir.actions.actions.path (the Odoo backend router).  The portal HTTP
// route /my/training is defined in server-side Python controllers and is NOT
// subject to slug remapping — so checking window.location.pathname here is
// safe regardless of any slug configuration.
// If the portal base path is ever moved in the Python controllers, update the
// LMS_PORTAL_PREFIX constant below to match.
(function () {
    var LMS_PORTAL_PREFIX = '/my/training';
    var path = window.location.pathname;
    var isLmsPortalPage = path === LMS_PORTAL_PREFIX ||
                          path.startsWith(LMS_PORTAL_PREFIX + '/');
    if (!isLmsPortalPage) { return; }
    try {
        if (window.self !== window.top) {
            document.documentElement.classList.add('lms-iframe-mode');
        }
    } catch (e) {
        // Cross-origin access blocked — we are definitely inside an iframe.
        // Still safe to add the class because we already confirmed the path.
        document.documentElement.classList.add('lms-iframe-mode');
    }
})();

document.addEventListener('DOMContentLoaded', function () {
    'use strict';

    // ── Auto-dismiss success/info alerts after 6 seconds ──────────────
    document.querySelectorAll('.alert.alert-success, .alert.alert-info').forEach(function (el) {
        // Don't auto-dismiss completion banners or important info
        if (el.closest('.lms-upload-section') || el.closest('.card-body')) return;
        setTimeout(function () {
            el.style.transition = 'opacity 0.6s';
            el.style.opacity = '0';
            setTimeout(function () { el.style.display = 'none'; }, 600);
        }, 6000);
    });

    // ── Google Slides fullscreen button ────────────────────────────────
    var slidesFullscreenBtn = document.getElementById('lms-slides-fullscreen-btn');
    if (slidesFullscreenBtn) {
        slidesFullscreenBtn.addEventListener('click', function () {
            var container = document.getElementById('lms-slides-container');
            var frame = document.getElementById('lms-slides-frame');
            var el = container || frame;
            if (!el) return;
            if (el.requestFullscreen) {
                el.requestFullscreen();
            } else if (el.webkitRequestFullscreen) {
                el.webkitRequestFullscreen();
            } else if (el.mozRequestFullScreen) {
                el.mozRequestFullScreen();
            }
        });
    }

    // ── SCORM fullscreen (also handled inline, belt-and-suspenders) ────
    var scormFullscreenBtn = document.getElementById('lms-scorm-fullscreen-btn');
    if (scormFullscreenBtn) {
        scormFullscreenBtn.addEventListener('click', function () {
            var frame = document.getElementById('lms-scorm-frame');
            if (!frame) return;
            if (frame.requestFullscreen) {
                frame.requestFullscreen();
            } else if (frame.webkitRequestFullscreen) {
                frame.webkitRequestFullscreen();
            }
        });
    }

    // ── Drag-and-drop upload zone ──────────────────────────────────────
    var dropzone = document.getElementById('lms-dropzone');
    var fileInput = document.getElementById('upload_file');
    var uploadBtn = document.getElementById('lms-upload-btn');
    var fileNameEl = document.getElementById('lms-file-name');
    var fileSelectedEl = document.getElementById('lms-file-selected');

    if (dropzone && fileInput) {
        // Click on zone opens file picker
        dropzone.addEventListener('click', function (e) {
            if (e.target !== fileInput && !e.target.closest('label')) {
                fileInput.click();
            }
        });

        // Drag events
        ['dragenter', 'dragover'].forEach(function (evt) {
            dropzone.addEventListener(evt, function (e) {
                e.preventDefault();
                dropzone.classList.add('dragover');
            });
        });
        ['dragleave', 'drop'].forEach(function (evt) {
            dropzone.addEventListener(evt, function (e) {
                e.preventDefault();
                dropzone.classList.remove('dragover');
            });
        });
        dropzone.addEventListener('drop', function (e) {
            var files = e.dataTransfer.files;
            if (files.length > 0) {
                // Assign dropped file to input via DataTransfer
                var dt = new DataTransfer();
                dt.items.add(files[0]);
                fileInput.files = dt.files;
                updateFileDisplay(files[0].name);
            }
        });

        // File input change
        fileInput.addEventListener('change', function () {
            if (fileInput.files.length > 0) {
                updateFileDisplay(fileInput.files[0].name);
            }
        });

        function updateFileDisplay(name) {
            if (fileNameEl) fileNameEl.textContent = name;
            if (fileSelectedEl) fileSelectedEl.classList.remove('d-none');
            if (uploadBtn) uploadBtn.removeAttribute('disabled');
        }
    }

    // ── Quick upload cards: auto-submit on file select ─────────────────
    document.querySelectorAll('.lms-auto-submit-file').forEach(function (input) {
        input.addEventListener('change', function () {
            if (input.files.length > 0) {
                var form = input.closest('form');
                if (form) form.submit();
            }
        });
    });

    // ── History table: highlight expiring rows ─────────────────────────
    // (server already controls row classes, this just adds a tooltip)
    document.querySelectorAll('.lms-history-table .table-warning').forEach(function (row) {
        row.setAttribute('title', 'This qualification expires within 90 days — renewal recommended.');
    });
    document.querySelectorAll('.lms-history-table .table-danger').forEach(function (row) {
        row.setAttribute('title', 'This qualification has expired and requires renewal.');
    });

    // ── Google Slides page-by-page tracker ────────────────────────────
    (function () {
        var tracker = document.getElementById('lms-slide-tracker');
        if (!tracker) return;

        var recordId  = parseInt(tracker.dataset.recordId,  10);
        var slideCount = parseInt(tracker.dataset.slideCount, 10);
        var maxPage    = parseInt(tracker.dataset.maxPage,    10) || 0;
        var baseUrl    = tracker.dataset.baseUrl || '';

        // Start where the employee left off (minimum slide 1)
        var currentPage = Math.max(1, maxPage);

        var frame       = document.getElementById('lms-slides-frame');
        var prevBtn     = document.getElementById('lms-slide-prev');
        var nextBtn     = document.getElementById('lms-slide-next');
        var counter     = document.getElementById('lms-slide-counter');
        var label       = document.getElementById('lms-slide-label');
        var bar         = document.getElementById('lms-slide-bar');
        var pctEl       = document.getElementById('lms-slide-pct');
        var completeBtn = document.getElementById('lms-complete-btn');
        var incompleteMsg = document.getElementById('lms-slides-incomplete-msg');
        var unlockHint  = document.getElementById('lms-unlock-hint');

        /** Build the iframe src for slide N (1-indexed). */
        function slideUrl(n) {
            // Strip any existing fragment from the embed URL, then append slide hash.
            // Google Slides embed honours #slide=id.p{N} (1-indexed page number).
            var clean = baseUrl.split('#')[0];
            return clean + '#slide=id.p' + n;
        }

        /** Push slide N into the iframe without a full reload by updating src. */
        function goToSlide(n) {
            if (!frame) return;
            var url = slideUrl(n);
            if (frame.src !== url) {
                frame.src = url;
            }
        }

        /** Redraw counter, progress bar, and button states. */
        function updateUI() {
            var pct = Math.round((currentPage / slideCount) * 100);

            if (counter) counter.textContent = 'Slide ' + currentPage + ' / ' + slideCount;
            if (label)   label.textContent   = 'Slide ' + currentPage + ' of ' + slideCount;
            if (bar)     bar.style.width     = pct + '%';
            if (pctEl)   pctEl.textContent   = pct + '%';

            if (prevBtn) prevBtn.disabled = (currentPage <= 1);
            if (nextBtn) nextBtn.disabled = (currentPage >= slideCount);

            // Unlock the complete button once every slide has been reached
            var allViewed = maxPage >= slideCount;
            if (completeBtn) {
                completeBtn.disabled = !allViewed;
                if (allViewed) {
                    completeBtn.classList.remove('btn-secondary', 'disabled');
                    completeBtn.classList.add('btn-success');
                    if (incompleteMsg) incompleteMsg.style.display = 'none';
                    if (unlockHint)    unlockHint.style.display    = 'none';
                }
            }
        }

        /** POST current page to the server; server updates slides_max_page. */
        function saveProgress(page) {
            fetch('/my/training/' + recordId + '/slides/progress', {
                method:  'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body:    'page=' + page,
            })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data && typeof data.max_page === 'number') {
                    maxPage = data.max_page;
                }
                updateUI();
            })
            .catch(function () {
                // Network error — update UI optimistically
                updateUI();
            });
        }

        // Wire up Prev button
        if (prevBtn) {
            prevBtn.addEventListener('click', function () {
                if (currentPage > 1) {
                    currentPage--;
                    goToSlide(currentPage);
                    updateUI();
                }
            });
        }

        // Wire up Next button
        if (nextBtn) {
            nextBtn.addEventListener('click', function () {
                if (currentPage < slideCount) {
                    currentPage++;
                    goToSlide(currentPage);
                    // Save if this is a new furthest slide
                    if (currentPage > maxPage) {
                        maxPage = currentPage;
                        saveProgress(currentPage);
                    } else {
                        updateUI();
                    }
                }
            });
        }

        // Initialise — show where the employee left off
        goToSlide(currentPage);
        updateUI();
    })();

});
