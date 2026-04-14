/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

class SpootAvailabilityDashboard extends Component {
  setup() {
    this.orm = useService("orm");
    this.actionService = useService("action");

    const today = new Date();
    const monday = new Date(today);
    const diff = (today.getDay() === 0 ? -6 : 1) - today.getDay();
    monday.setDate(today.getDate() + diff);
    const sunday = new Date(monday);
    sunday.setDate(monday.getDate() + 6);

    this.state = useState({
      mode: "week",
      dateStart: this._iso(monday),
      dateEnd:   this._iso(sunday),
      matrix:    null,
      stats:     null,
      loading:   true,
      monthLabel: "",
      monthWeeks: [],
    });

    onWillStart(async () => { await this.load(); });
  }

  /* ── helpers de fecha ─────────────────────────────────────────── */
  _iso(d) {
    return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;
  }
  _parse(iso) {
    const [y, m, d] = iso.split("-").map(Number);
    return new Date(y, m-1, d);
  }

  /* ── carga principal ──────────────────────────────────────────── */
  async load() {
    this.state.loading = true;

    const [matrix, stats] = await Promise.all([
      this.orm.call("spoot.office.booking", "get_admin_availability_matrix",
        [this.state.dateStart, this.state.dateEnd, null]),
      this.orm.call("spoot.office.booking", "get_dashboard_stats", []),
    ]);

    /* --- matrix days --- */
    const days = (matrix.days || []).map(ds => {
      const [y,m,d] = ds.split("-").map(Number);
      const obj = new Date(y, m-1, d);
      return {
        date: ds, day: d,
        dow: obj.toLocaleDateString("es-CO", { weekday: "short" }),
      };
    });

    const rows = (matrix.rows || []).map(row => {
      const map = {};
      (row.days || []).forEach(c => { map[c.date] = c; });
      return { ...row, days_by_date: map };
    });

    this.state.matrix = { ...matrix, days, rows };
    this.state.stats  = stats;

    /* --- label del mes --- */
    const base = this._parse(this.state.dateStart);
    this.state.monthLabel = base.toLocaleDateString("es-CO", { month: "long", year: "numeric" });

    /* --- grid mensual --- */
    if (this.state.mode === "month") {
      this.state.monthWeeks = this._buildMonthWeeks(base);
    } else {
      this.state.monthWeeks = [];
    }

    this.state.loading = false;
  }

  _buildMonthWeeks(base) {
    const firstOfMonth = new Date(base.getFullYear(), base.getMonth(), 1);
    const lastOfMonth  = new Date(base.getFullYear(), base.getMonth()+1, 0);
    const dow0 = firstOfMonth.getDay();
    const toMon = (dow0 === 0 ? -6 : 1) - dow0;
    const gridStart = new Date(firstOfMonth);
    gridStart.setDate(firstOfMonth.getDate() + toMon);
    const lastDow = lastOfMonth.getDay();
    const toSun = lastDow === 0 ? 0 : 7 - lastDow;
    const gridEnd = new Date(lastOfMonth);
    gridEnd.setDate(lastOfMonth.getDate() + toSun);

    const weeks = [];
    let cursor = new Date(gridStart);
    while (cursor <= gridEnd) {
      const week = [];
      for (let i = 0; i < 7; i++) {
        const y = cursor.getFullYear(), m = cursor.getMonth()+1, d = cursor.getDate();
        week.push({
          date: `${y}-${String(m).padStart(2,"0")}-${String(d).padStart(2,"0")}`,
          day: d,
          isInMonth: cursor.getMonth() === base.getMonth(),
        });
        cursor.setDate(cursor.getDate()+1);
      }
      weeks.push(week);
    }
    return weeks;
  }

  /* ── modo ─────────────────────────────────────────────────────── */
  async setMode(mode) {
    this.state.mode = mode;
    const base = this._parse(this.state.dateStart);
    if (mode === "day") {
      this.state.dateEnd = this.state.dateStart;
    } else if (mode === "week") {
      const mon = new Date(base);
      mon.setDate(base.getDate() + ((base.getDay()===0?-6:1) - base.getDay()));
      const sun = new Date(mon); sun.setDate(mon.getDate()+6);
      this.state.dateStart = this._iso(mon);
      this.state.dateEnd   = this._iso(sun);
    } else {
      const first = new Date(base.getFullYear(), base.getMonth(), 1);
      const last  = new Date(base.getFullYear(), base.getMonth()+1, 0);
      this.state.dateStart = this._iso(first);
      this.state.dateEnd   = this._iso(last);
    }
    await this.load();
  }

  async goToday() {
    const t = new Date();
    const iso = this._iso(t);
    if (this.state.mode === "day") {
      this.state.dateStart = this.state.dateEnd = iso;
    } else if (this.state.mode === "week") {
      const mon = new Date(t);
      mon.setDate(t.getDate() + ((t.getDay()===0?-6:1) - t.getDay()));
      const sun = new Date(mon); sun.setDate(mon.getDate()+6);
      this.state.dateStart = this._iso(mon);
      this.state.dateEnd   = this._iso(sun);
    } else {
      const first = new Date(t.getFullYear(), t.getMonth(), 1);
      const last  = new Date(t.getFullYear(), t.getMonth()+1, 0);
      this.state.dateStart = this._iso(first);
      this.state.dateEnd   = this._iso(last);
    }
    await this.load();
  }

  async shift(step) {
    const start = this._parse(this.state.dateStart);
    const end   = this._parse(this.state.dateEnd);
    if (this.state.mode === "day") {
      start.setDate(start.getDate()+step);
      end.setDate(end.getDate()+step);
      this.state.dateStart = this._iso(start);
      this.state.dateEnd   = this._iso(end);
    } else if (this.state.mode === "week") {
      start.setDate(start.getDate()+7*step);
      end.setDate(end.getDate()+7*step);
      this.state.dateStart = this._iso(start);
      this.state.dateEnd   = this._iso(end);
    } else {
      const first = new Date(start.getFullYear(), start.getMonth()+step, 1);
      const last  = new Date(start.getFullYear(), start.getMonth()+step+1, 0);
      this.state.dateStart = this._iso(first);
      this.state.dateEnd   = this._iso(last);
    }
    await this.load();
  }

  /* ── acciones ─────────────────────────────────────────────────── */
  async onSegmentClick(officeId, dateStr, slotType, seg) {
    if (seg.booking_id) {
      await this.actionService.doAction({
        type: "ir.actions.act_window",
        name: "Reserva",
        res_model: "spoot.office.booking",
        res_id: seg.booking_id,
        views: [[false, "form"]],
        target: "current",
      });
    } else {
      await this.actionService.doAction({
        type: "ir.actions.act_window",
        name: "Crear reserva",
        res_model: "spoot.booking.quick.create.wizard",
        views: [[false, "form"]],
        target: "new",
        context: {
          default_office_id: officeId,
          default_date: dateStr,
          default_slot_type: slotType,
        },
      });
    }
  }

  async openBooking(id) {
    await this.actionService.doAction({
      type: "ir.actions.act_window",
      name: "Reserva",
      res_model: "spoot.office.booking",
      res_id: id,
      views: [[false, "form"]],
      target: "current",
    });
  }

  async createBooking() {
    await this.actionService.doAction({
      type: "ir.actions.act_window",
      name: "Crear reserva",
      res_model: "spoot.booking.quick.create.wizard",
      views: [[false, "form"]],
      target: "new",
    });
  }

  async openAllPending() {
    await this.actionService.doAction({
      type: "ir.actions.act_window",
      name: "Reservas pendientes",
      res_model: "spoot.office.booking",
      views: [[false, "list"], [false, "form"]],
      domain: [["state", "=", "pending_payment"]],
      target: "current",
    });
  }

  /* ── helpers visuales ────────────────────────────────────────── */
  segClass(status) {
    if (status === "busy")    return "sd-seg--busy";
    if (status === "pending") return "sd-seg--pending";
    return "sd-seg--free";
  }

  isToday(dateStr) {
    return dateStr === this._iso(new Date());
  }

  fmtDate(ds) {
    const [y,m,d] = ds.split("-").map(Number);
    return new Date(y,m-1,d).toLocaleDateString("es-CO",
      { weekday:"short", day:"numeric", month:"short" });
  }

  stateLabel(s) {
    return s === "confirmed" ? "Confirmada" : "Pend. pago";
  }

  stateClass(s) {
    return s === "confirmed" ? "sd-badge--ok" : "sd-badge--warn";
  }

  payClass(p) {
    return p === "plan" ? "sd-badge--plan" : "sd-badge--bold";
  }

  payLabel(p) {
    return p === "plan" ? "Plan" : "Bold";
  }

  fmtMoney(n, sym) {
    return (sym || "$") + " " + Math.round(n || 0).toLocaleString("es-CO");
  }
}

SpootAvailabilityDashboard.template =
  "spoot_office_booking.SpootAvailabilityDashboard";

registry
  .category("actions")
  .add("spoot_office_booking.availability_dashboard", SpootAvailabilityDashboard);
