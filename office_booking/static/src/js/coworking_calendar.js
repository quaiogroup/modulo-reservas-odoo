/**
 * SpootCoworkingCalendar
 * Lightweight, self-contained month-view calendar for the /my/coworking portal page.
 * Pure vanilla JS — no external library dependencies.
 * Reads booking data embedded in the page as JSON.
 */
(function () {
    'use strict';

    // ── Helpers ──────────────────────────────────────────────────────────────

    function pad2(n) { return n < 10 ? '0' + n : '' + n; }

    function dateStr(y, m, d) {
        return y + '-' + pad2(m + 1) + '-' + pad2(d);
    }

    function hexToRgba(hex, alpha) {
        var r = parseInt(hex.slice(1, 3), 16);
        var g = parseInt(hex.slice(3, 5), 16);
        var b = parseInt(hex.slice(5, 7), 16);
        return 'rgba(' + r + ',' + g + ',' + b + ',' + alpha + ')';
    }

    function esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function truncate(name, max) {
        if (!name) return 'Reserva';
        return name.length > max ? name.substring(0, max - 1) + '\u2026' : name;
    }

    // ── Calendar factory ─────────────────────────────────────────────────────

    function SpootCalendar(container, events) {
        var today = new Date();
        var curYear = today.getFullYear();
        var curMonth = today.getMonth(); // 0-indexed

        var MONTHS = [
            'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
            'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'
        ];
        var DAYS = ['Dom', 'Lun', 'Mar', 'Mi\u00e9', 'Jue', 'Vie', 'S\u00e1b'];

        // Group by date string
        var byDate = {};
        events.forEach(function (ev) {
            if (!ev.date) return;
            if (!byDate[ev.date]) byDate[ev.date] = [];
            byDate[ev.date].push(ev);
        });

        function todayIso() {
            return dateStr(today.getFullYear(), today.getMonth(), today.getDate());
        }

        function render() {
            var y = curYear;
            var m = curMonth;
            var firstDow = new Date(y, m, 1).getDay();
            var daysInMonth = new Date(y, m + 1, 0).getDate();
            var tIso = todayIso();

            var buf = [];

            // ── Calendar header ───────────────────────────────────────────
            buf.push('<div class="spoot-cal-header">');
            buf.push(
                '<button class="spoot-cal-nav spoot-cal-prev" type="button" aria-label="Mes anterior">' +
                '<span aria-hidden="true">&#8249;</span></button>'
            );
            buf.push('<h6 class="spoot-cal-month-title mb-0">' + MONTHS[m] + ' ' + y + '</h6>');
            buf.push(
                '<button class="spoot-cal-nav spoot-cal-next" type="button" aria-label="Mes siguiente">' +
                '<span aria-hidden="true">&#8250;</span></button>'
            );
            buf.push('</div>');

            // ── Day-of-week labels ────────────────────────────────────────
            buf.push('<div class="spoot-cal-grid spoot-cal-dow-row">');
            DAYS.forEach(function (d) {
                buf.push('<div class="spoot-cal-dow">' + d + '</div>');
            });
            buf.push('</div>');

            // ── Day cells ─────────────────────────────────────────────────
            buf.push('<div class="spoot-cal-grid spoot-cal-body">');

            // Leading blanks
            for (var b = 0; b < firstDow; b++) {
                buf.push('<div class="spoot-cal-cell spoot-cal-blank"></div>');
            }

            for (var day = 1; day <= daysInMonth; day++) {
                var ds = dateStr(y, m, day);
                var isToday = (ds === tIso);
                var dayEvs = byDate[ds] || [];
                var hasEvs = dayEvs.length > 0;

                var isBlocked = dayEvs.some(function(ev) { return ev.type === 'blocked'; });
                var bookingEvs = dayEvs.filter(function(ev) { return ev.type !== 'blocked'; });

                var cls = 'spoot-cal-cell';
                if (isToday)   cls += ' sc-today';
                if (isBlocked) cls += ' sc-blocked';
                else if (bookingEvs.length > 0) cls += ' sc-has-events';

                buf.push('<div class="' + cls + '">');

                // Day number
                if (isToday) {
                    buf.push('<span class="spoot-cal-num sc-today-num">' + day + '</span>');
                } else {
                    buf.push('<span class="spoot-cal-num">' + day + '</span>');
                }

                // Blocked: show a single indicator instead of pills
                if (isBlocked) {
                    var blockNote = dayEvs.find(function(ev) { return ev.type === 'blocked'; });
                    buf.push(
                        '<span class="spoot-cal-blocked-label" title="' +
                        esc(blockNote ? blockNote.slot_label : 'Bloqueado') + '">' +
                        'No disponible' +
                        '</span>'
                    );
                } else {
                    // Regular event pills (up to 2 visible, then overflow badge)
                    var max = 2;
                    var shown = Math.min(bookingEvs.length, max);
                    for (var i = 0; i < shown; i++) {
                        var ev = bookingEvs[i];
                        var bg = hexToRgba(ev.color, 0.14);
                        var border = hexToRgba(ev.color, 0.35);
                        var pillLabel = truncate(ev.title, 12);
                        var tooltip = esc(ev.title) + ' \u2014 ' + esc(ev.slot_label);
                        buf.push(
                            '<a href="' + esc(ev.url) + '" ' +
                            'class="spoot-cal-pill" ' +
                            'style="background:' + bg + ';color:' + esc(ev.color) + ';border-color:' + border + ';" ' +
                            'title="' + tooltip + '">' +
                            esc(pillLabel) +
                            '</a>'
                        );
                    }
                    if (bookingEvs.length > max) {
                        buf.push(
                            '<a href="/my/office-bookings" class="spoot-cal-more">+' +
                            (bookingEvs.length - max) + ' m\u00e1s</a>'
                        );
                    }
                }

                buf.push('</div>'); // .spoot-cal-cell
            }

            // Trailing blanks to complete the last row
            var total = firstDow + daysInMonth;
            var trail = (7 - (total % 7)) % 7;
            for (var t = 0; t < trail; t++) {
                buf.push('<div class="spoot-cal-cell spoot-cal-blank"></div>');
            }

            buf.push('</div>'); // .spoot-cal-body

            container.innerHTML = buf.join('');

            // Navigation
            var prevBtn = container.querySelector('.spoot-cal-prev');
            var nextBtn = container.querySelector('.spoot-cal-next');
            if (prevBtn) {
                prevBtn.addEventListener('click', function () {
                    curMonth--;
                    if (curMonth < 0) { curMonth = 11; curYear--; }
                    render();
                });
            }
            if (nextBtn) {
                nextBtn.addEventListener('click', function () {
                    curMonth++;
                    if (curMonth > 11) { curMonth = 0; curYear++; }
                    render();
                });
            }
        }

        render();
    }

    // ── Boot on DOM ready ─────────────────────────────────────────────────────

    function boot() {
        var container = document.getElementById('spoot-coworking-calendar');
        if (!container) return;

        var events = [];
        try {
            var dataEl = document.getElementById('spoot-calendar-data');
            if (dataEl) {
                events = JSON.parse(dataEl.textContent || '[]');
            }
        } catch (e) {
            console.error('[SpootCalendar] error parsing event data:', e);
        }

        SpootCalendar(container, events);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }

})();
